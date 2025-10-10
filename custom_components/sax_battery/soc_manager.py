"""SOC constraint management for SAX Battery integration.

Security:
    OWASP A05: Implements resource protection to prevent battery damage

Performance:
    Efficient SOC checking with caching to minimize coordinator queries
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from homeassistant.helpers import entity_platform, entity_registry as er

from .const import SAX_COMBINED_SOC, SAX_MAX_DISCHARGE

if TYPE_CHECKING:
    from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class SOCConstraintResult:
    """Result of SOC constraint check."""

    allowed: bool
    original_value: float
    constrained_value: float
    reason: str | None = None
    enforced_hardware_limit: bool = False  # New: tracks if we wrote to hardware


class SOCManager:
    """Manager for SOC-based battery protection constraints."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        min_soc: float,
        enabled: bool = True,
    ) -> None:
        """Initialize SOC manager.

        Args:
            coordinator: Battery coordinator for SOC data access
            min_soc: Minimum allowed SOC percentage (0-100)
            enabled: Whether constraints are enabled

        Security:
            OWASP A05: Validates min_soc bounds to prevent misconfiguration
        """
        self.coordinator = coordinator
        self._min_soc = max(0.0, min(100.0, min_soc))  # Clamp to valid range
        self._enabled = enabled
        self._soc_cache: float | None = None
        self._last_enforced_soc: float | None = None  # Track last enforcement

    @property
    def min_soc(self) -> float:
        """Get minimum SOC threshold."""
        return self._min_soc

    @min_soc.setter
    def min_soc(self, value: float) -> None:
        """Set minimum SOC threshold with validation."""
        old_value = self._min_soc
        self._min_soc = max(0.0, min(100.0, value))
        _LOGGER.debug("Min SOC updated to %s%%", self._min_soc)

        # If min_soc increased, check if we need to enforce new limit
        if self._min_soc > old_value:
            # Trigger asynchronous constraint check
            # This will be handled by the coordinator's next update cycle
            _LOGGER.debug(
                "Min SOC increased, enforcement check will occur on next update"
            )

    @property
    def enabled(self) -> bool:
        """Get constraint enabled state."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set constraint enabled state."""
        self._enabled = bool(value)
        _LOGGER.debug("SOC constraints %s", "enabled" if self._enabled else "disabled")

    async def get_current_soc(self) -> float:
        """Get current combined SOC from coordinator.

        Returns:
            Current SOC percentage (0-100)

        Performance:
            Uses coordinator data cache to avoid redundant queries
        """
        if not self.coordinator.data:
            return 0.0

        soc_value = self.coordinator.data.get(SAX_COMBINED_SOC, 0)
        try:
            return float(soc_value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid SOC value: %s", soc_value)
            return 0.0

    async def check_and_enforce_discharge_limit(self) -> bool:
        """Check SOC and enforce discharge limit by writing to max_discharge register.

        This method writes directly to the Modbus hardware register when SOC
        is below minimum. State synchronization is handled separately by:
        - Initial startup check (_check_soc_constraints_on_startup)
        - Normal coordinator refresh cycle

        Returns:
            bool: True if hardware limit was enforced (written to register)

        Security:
            OWASP A05: Hardware-level battery protection

        Performance:
            Minimal overhead - only writes to hardware without state updates
        """
        if not self._enabled:
            return False

        # Validate config entry exists for entity lookup
        if not self.coordinator.config_entry:
            _LOGGER.error("Cannot enforce discharge limit: config entry not available")
            return False

        current_soc = await self.get_current_soc()

        if current_soc < self._min_soc:
            # Only enforce if SOC level changed (prevents redundant writes)
            if self._last_enforced_soc != current_soc:
                _LOGGER.warning(
                    "SOC %s%% below minimum %s%% - enforcing discharge limit",
                    current_soc,
                    self._min_soc,
                )

                # Get max_discharge entity from registry
                ent_reg = er.async_get(self.coordinator.hass)

                # Find the entity
                entity_entry = None
                for entry in ent_reg.entities.values():
                    if (
                        entry.platform == "sax_battery"
                        and entry.unique_id
                        and SAX_MAX_DISCHARGE in entry.unique_id
                        and entry.config_entry_id
                        == self.coordinator.config_entry.entry_id
                    ):
                        entity_entry = entry
                        break

                if not entity_entry:
                    _LOGGER.error("Could not find max_discharge entity for enforcement")
                    return False

                # Get the entity platform
                platform = entity_platform.async_get_current_platform()
                if not platform:
                    _LOGGER.error("Could not access entity platform")
                    return False

                # Find the entity object
                entity_obj = None
                for entity in platform.entities.values():
                    if entity.entity_id == entity_entry.entity_id:
                        entity_obj = entity
                        break

                if not entity_obj:
                    _LOGGER.error(
                        "Could not find entity object for %s", entity_entry.entity_id
                    )
                    return False

                # Validate entity supports async_set_native_value
                if not hasattr(entity_obj, "async_set_native_value"):
                    _LOGGER.error(
                        "Entity %s does not support async_set_native_value",
                        entity_entry.entity_id,
                    )
                    return False

                try:
                    # Write 0W to Modbus hardware register
                    # Entity state synchronization handled by:
                    # - Startup check (after HA restart)
                    # - Coordinator refresh cycle (during runtime)
                    await entity_obj.async_set_native_value(0.0)  # type: ignore[attr-defined]

                    self._last_enforced_soc = current_soc
                    _LOGGER.info(
                        "Discharge protection enforced: %s set to 0W (SOC: %s%%)",
                        entity_entry.entity_id,
                        current_soc,
                    )
                    return True  # noqa: TRY300

                except Exception as err:  # noqa: BLE001
                    _LOGGER.error(
                        "Failed to enforce discharge limit: %s",
                        err,
                    )
                    return False

        elif self._last_enforced_soc is not None and current_soc >= self._min_soc:
            _LOGGER.info(
                "SOC recovered to %s%% (above minimum %s%%)",
                current_soc,
                self._min_soc,
            )
            self._last_enforced_soc = None

        return False

    async def check_discharge_allowed(self, power_value: float) -> SOCConstraintResult:
        """Check if discharge is allowed at current SOC.

        Args:
            power_value: Proposed power value (positive = discharge)

        Returns:
            SOCConstraintResult with allowed status and reason

        Security:
            OWASP A05: Prevents battery over-discharge damage
        """
        if not self._enabled:
            return SOCConstraintResult(
                allowed=True,
                original_value=power_value,
                constrained_value=power_value,
            )

        current_soc = await self.get_current_soc()

        # Check discharge constraint (positive power = discharge)
        if power_value > 0 and current_soc < self._min_soc:
            _LOGGER.info(
                "Discharge blocked: SOC %s%% < min %s%%",
                current_soc,
                self._min_soc,
            )

            # Attempt hardware enforcement (best effort - may not be available in all contexts)
            enforced = False
            try:
                enforced = await self.check_and_enforce_discharge_limit()
            except (TypeError, AttributeError, RuntimeError) as err:
                # Hardware enforcement not available (e.g., during tests or before entities are created)
                _LOGGER.debug(
                    "Hardware enforcement not available: %s (this is normal during tests)",
                    err,
                )

            return SOCConstraintResult(
                allowed=False,
                original_value=power_value,
                constrained_value=0.0,
                reason=f"SOC {current_soc:.1f}% below minimum {self._min_soc:.1f}%",
                enforced_hardware_limit=enforced,
            )

        return SOCConstraintResult(
            allowed=True,
            original_value=power_value,
            constrained_value=power_value,
        )

    async def check_charge_allowed(self, power_value: float) -> SOCConstraintResult:
        """Check if charge is allowed at current SOC.

        Args:
            power_value: Proposed power value (negative = charge)

        Returns:
            SOCConstraintResult with allowed status and reason

        Security:
            OWASP A05: Prevents battery overcharge damage
        """
        if not self._enabled:
            return SOCConstraintResult(
                allowed=True,
                original_value=power_value,
                constrained_value=power_value,
            )

        current_soc = await self.get_current_soc()

        # Check charge constraint (negative power = charge)
        if power_value < 0 and current_soc >= 100.0:
            _LOGGER.info("Charge blocked: SOC at maximum 100%%")
            return SOCConstraintResult(
                allowed=False,
                original_value=power_value,
                constrained_value=0.0,
                reason="SOC at maximum 100%",
            )

        return SOCConstraintResult(
            allowed=True,
            original_value=power_value,
            constrained_value=power_value,
        )

    async def apply_constraints(self, power_value: float) -> SOCConstraintResult:
        """Apply all SOC constraints to a power value.

        Args:
            power_value: Proposed power value
                Positive = discharge
                Negative = charge

        Returns:
            SOCConstraintResult with constrained value

        Security:
            OWASP A05: Comprehensive battery protection

        Performance:
            Single SOC query for all constraint checks
        """
        if not self._enabled:
            return SOCConstraintResult(
                allowed=True,
                original_value=power_value,
                constrained_value=power_value,
            )

        current_soc = await self.get_current_soc()
        constrained_value = power_value
        reason = None
        enforced = False

        # Check discharge constraint
        if power_value > 0 and current_soc < self._min_soc:
            constrained_value = 0.0
            reason = (
                f"Discharge blocked: SOC {current_soc:.1f}% < min {self._min_soc:.1f}%"
            )
            _LOGGER.info(reason)

            # Enforce hardware limit
            enforced = await self.check_and_enforce_discharge_limit()

        # Check charge constraint
        elif power_value < 0 and current_soc >= 100.0:
            constrained_value = 0.0
            reason = "Charge blocked: SOC at maximum 100%"
            _LOGGER.info(reason)

        if constrained_value != power_value:
            _LOGGER.info(
                "SOC constraint applied: %sW → %sW%s",
                power_value,
                constrained_value,
                " (hardware enforced)" if enforced else "",
            )

        return SOCConstraintResult(
            allowed=(constrained_value == power_value),
            original_value=power_value,
            constrained_value=constrained_value,
            reason=reason,
            enforced_hardware_limit=enforced,
        )
