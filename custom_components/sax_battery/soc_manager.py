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

from homeassistant.helpers import entity_registry as er

from .const import AGGREGATED_ITEMS, SAX_COMBINED_SOC, SAX_MAX_DISCHARGE

if TYPE_CHECKING:
    from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class SOCConstraintResult:
    """Result of SOC constraint check."""

    allowed: bool
    constrained_value: float
    reason: str | None = None


class SOCManager:
    """Manager for SOC-based battery protection constraints."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        min_soc: float,
        enabled: bool = True,
    ) -> None:
        """Initialize SOC manager."""
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.config_entry = coordinator.config_entry
        self._min_soc = max(0.0, min(100.0, min_soc))
        self._enabled = enabled
        self._last_enforced_soc: float | None = None

    def _get_combined_soc(self) -> float | None:
        """Get combined SOC from Home Assistant state machine.

        Returns:
            float | None: Combined SOC percentage or None if unavailable

        Security:
            OWASP A05: Validates entity availability before access

        Performance:
            Direct state machine access with entity registry lookup
        """
        try:
            # Validate coordinator has required dependencies
            if not hasattr(self.coordinator, "sax_data"):
                _LOGGER.error("Coordinator missing sax_data attribute")
                return None

            if not self.coordinator.config_entry:
                _LOGGER.error("Coordinator missing config_entry")
                return None

            # Get SAXItem for SAX_COMBINED_SOC from list AGGREGATED_ITEMS
            combined_soc_item = None
            for item in AGGREGATED_ITEMS:
                if item.name == SAX_COMBINED_SOC:
                    combined_soc_item = item
                    break

            if combined_soc_item is None:
                _LOGGER.debug(
                    "Could not find SAXItem for SAX_COMBINED_SOC in list AGGREGATED_ITEMS"
                )
                return None

            # SAX_COMBINED_SOC is a cluster-wide entity (battery_id=None)
            # sensor: sensor.sax_cluster_combined_soc (unique_id=combined_soc, device_id=746f49dbe66819b0b95e98d8e67067cd)
            entity_id = self.coordinator.sax_data.get_unique_id_for_item(
                combined_soc_item,
                battery_id=None,  # Cluster-wide entity
            )

            # Type guard: Validate entity_id exists before entity lookup
            if not entity_id:
                _LOGGER.warning("Could not generate entity_id for SAX_COMBINED_SOC")
                return None

            # Get state from Home Assistant
            state = self.hass.states.get(f"sensor.{entity_id}")
            if not state or state.state in ("unknown", "unavailable"):
                _LOGGER.debug(
                    "SAX_COMBINED_SOC state unavailable (entity_id=%s, state=%s)",
                    f"sensor.{entity_id}",
                    state.state if state else "None",
                )
                return None

            # Convert state to float
            try:
                return float(state.state)
            except (ValueError, TypeError) as err:
                _LOGGER.warning(
                    "Invalid combined SOC value: %s (%s)",
                    state.state,
                    err,
                )
                return None

        except Exception as err:
            _LOGGER.error(  # noqa: G201
                "Unexpected error getting combined SOC: %s",
                err,
                exc_info=True,
            )
            return None

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
        """Get current combined SOC (async wrapper for _get_combined_soc).

        Returns:
            float: Current SOC percentage (0-100), defaults to 0.0 if unavailable

        Performance:
            Uses coordinator data cache to avoid redundant queries
        """
        combined_soc = self._get_combined_soc()
        return combined_soc if combined_soc is not None else 0.0

    async def check_and_enforce_discharge_limit(self) -> bool:
        """Check SOC and enforce discharge limit if needed.

        Returns:
            True if enforcement was successful or not needed, False on error

        Security:
            OWASP A05: Protects battery hardware from damage due to over-discharge
        """
        try:
            if self.enabled is None or self.enabled is False:
                _LOGGER.debug("Cannot enforce discharge limit - combined SOC disabled")
                return False

            if not self.coordinator.config_entry:
                _LOGGER.error(
                    "Cannot enforce discharge limit - config entry not available"
                )
                return False

            # Get current combined SOC
            combined_soc = self._get_combined_soc()

            if combined_soc is None:
                _LOGGER.warning(
                    "Cannot enforce discharge limit - combined SOC unavailable"
                )
                return False

            # Check if below minimum
            if combined_soc < self.min_soc:
                _LOGGER.warning(
                    "Combined SOC %.1f%% below minimum %.1f%% - enforcing discharge limit",
                    combined_soc,
                    self._min_soc,
                )

                # Get SAXBatteryData instance from coordinator
                if not hasattr(self.coordinator, "sax_data"):
                    _LOGGER.error("Coordinator missing sax_data attribute")
                    return False

                sax_data = self.coordinator.sax_data

                # Get ModbusItem for SAX_MAX_DISCHARGE from coordinator data
                max_discharge_item = None
                for item_key, item_value in self.coordinator.data.items():
                    if item_key == SAX_MAX_DISCHARGE and hasattr(item_value, "item"):
                        max_discharge_item = item_value.item
                        break

                if max_discharge_item is None:
                    _LOGGER.error(
                        "Could not find ModbusItem for SAX_MAX_DISCHARGE in coordinator data"
                    )
                    return False

                # Generate unique_id using SAXBatteryData.get_unique_id_for_item
                # Use master battery_id since SAX_MAX_DISCHARGE is WO register
                unique_id = sax_data.get_unique_id_for_item(
                    max_discharge_item,
                    battery_id=self.coordinator.battery_id,
                )

                # Type guard: Validate unique_id exists before entity lookup
                if not unique_id:
                    _LOGGER.error(
                        "Could not generate unique_id for SAX_MAX_DISCHARGE(%s) (battery_id=%s)",
                        max_discharge_item,
                        self.coordinator.battery_id,
                    )
                    return False

                # Get entity_id from registry
                ent_reg = er.async_get(self.hass)
                entity_id = ent_reg.async_get_entity_id(
                    "number", "sax_battery", unique_id
                )

                if not entity_id:
                    _LOGGER.error(
                        "SAX_MAX_DISCHARGE entity not found in registry (unique_id=%s, battery_id=%s)",
                        unique_id,
                        self.coordinator.battery_id,
                    )
                    return False

                _LOGGER.debug(
                    "Enforcing discharge limit via entity: %s (unique_id=%s, battery_id=%s)",
                    entity_id,
                    unique_id,
                    self.coordinator.battery_id,
                )

                # Set value through Home Assistant service
                try:
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": entity_id,
                            "value": 0.0,
                        },
                        blocking=True,
                    )

                    self._last_enforced_soc = combined_soc
                    _LOGGER.info(
                        "Successfully enforced discharge limit (set %s to 0W)",
                        entity_id,
                    )
                    return True  # noqa: TRY300

                except Exception as err:  # noqa: BLE001
                    _LOGGER.error(
                        "Failed to set discharge limit on %s: %s",
                        entity_id,
                        err,
                    )
                    return False

            # SOC is acceptable
            return True  # noqa: TRY300

        except Exception:
            _LOGGER.exception("Unexpected error enforcing discharge limit")
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
                enforced = await self.check_and_enforce_discharge_limit()  # noqa: F841
            except (TypeError, AttributeError, RuntimeError) as err:
                # Hardware enforcement not available (e.g., during tests or before entities are created)
                _LOGGER.debug(
                    "Hardware enforcement not available: %s (this is normal during tests)",
                    err,
                )

            return SOCConstraintResult(
                allowed=False,
                constrained_value=0.0,
                reason=f"SOC {current_soc:.1f}% below minimum {self._min_soc:.1f}%",
            )

        return SOCConstraintResult(
            allowed=True,
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
            constrained_value=constrained_value,
            reason=reason,
        )
