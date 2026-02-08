"""SOC constraint management for SAX Battery integration - REFACTORED VERSION.

This is the proposed refactored implementation based on GitHub Issue #40.
DO NOT USE DIRECTLY - This is a reference implementation for review.

Security:
    OWASP A05: Implements resource protection to prevent battery damage
    OWASP A01: Enforces master-only access control with isolated validation

Performance:
    Efficient SOC checking with guard clauses for early returns
    Minimizes coordinator queries through cached validation results
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    MODBUS_BATTERY_POWER_LIMIT_ITEMS,
    SAX_COMBINED_SOC,
    SAX_MAX_DISCHARGE,
)
from .items import ModbusItem

if TYPE_CHECKING:
    from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


class SOCManager:
    """Manager for SOC-based battery protection constraints.

    Refactored to reduce complexity and improve testability.
    See GitHub Issue #40 for rationale.
    """

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        min_soc: int,
        max_soc_charging: int = 90,  # Placeholder for future max SOC charging limit
        enabled: bool = True,
    ) -> None:
        """Initialize SOC manager.

        Args:
            coordinator: SAX Battery coordinator instance
            min_soc: Minimum SOC threshold (0-100)
            max_soc_charging: Maximum SOC threshold for charging (0-100)
            enabled: Whether constraint enforcement is enabled

        Security:
            OWASP A05: Validates min_soc range to prevent invalid configurations
        """
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.config_entry = coordinator.config_entry
        # used for min_soc enforcement - max_soc not implemented yet
        self._min_soc: int = max(0, min(100, min_soc))
        self._max_soc_charging: int = (
            max_soc_charging  # Placeholder for future max SOC charging limit
        )
        self._enabled = enabled

    @property
    def max_soc_charging(self) -> int:
        """Get maximum SOC threshold for charging."""
        return self._max_soc_charging

    @property
    def min_soc(self) -> int:
        """Get minimum SOC threshold."""
        return self._min_soc

    @min_soc.setter
    def min_soc(self, value: int) -> None:
        """Set minimum SOC threshold with validation.

        Args:
            value: New minimum SOC (0-100)

        Security:
            OWASP A05: Validates and clamps input to safe range
        """
        old_value = self._min_soc
        self._min_soc = max(0, min(100, value))
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
        """Set constraint enabled state.

        Args:
            value: New enabled state
        """
        self._enabled = bool(value)
        _LOGGER.debug("SOC constraints %s", "enabled" if self._enabled else "disabled")

    def _validate_enforcement_prerequisites(self) -> tuple[bool, str, float | None]:
        """Validate prerequisites for SOC enforcement.

        Uses guard clauses to check all requirements before enforcement.
        Early returns improve readability and reduce nesting.

        Returns:
            Tuple of (can_enforce, reason, combined_soc):
                - can_enforce: True if enforcement should proceed
                - reason: Human-readable explanation of validation result
                - combined_soc: Current SOC value if available, None otherwise

        Security:
            OWASP A05: Validates system state before hardware operations
            OWASP A01: Enforces master-only access control

        Performance:
            Early returns avoid unnecessary validation steps
        """
        # Guard clause: Check if enforcement is enabled
        if not self.enabled:
            return False, "SOC protection disabled", None

        # Guard clause: Validate coordinator has data
        if not self.coordinator.data:
            return False, "Coordinator data not available", None

        # Guard clause: Only master can enforce (security critical)
        if not self.coordinator.is_master:
            return (
                False,
                f"Coordinator {self.coordinator.battery_id} is not master",
                None,
            )

        # Guard clause: Validate combined SOC is available
        combined_soc = self.coordinator.data.get(SAX_COMBINED_SOC)
        if combined_soc is None:
            return False, "Combined SOC not yet available", None

        # Guard clause: Check if SOC is above minimum (no action needed)
        if combined_soc >= self.min_soc:
            return (
                False,
                f"SOC {combined_soc:.1f}% >= min {self.min_soc:.1f}%",
                combined_soc,
            )

        # All validations passed - enforcement needed
        return True, "Enforcement required", combined_soc

    def _get_max_discharge_item(self) -> ModbusItem | None:
        """Get SAX_MAX_DISCHARGE ModbusItem from power limit items.

        Returns:
            ModbusItem for SAX_MAX_DISCHARGE or None if not found

        Performance:
            Uses generator expression with next() for efficient lookup
        """
        item = next(
            (
                item
                for item in MODBUS_BATTERY_POWER_LIMIT_ITEMS
                if item.name == SAX_MAX_DISCHARGE
            ),
            None,
        )

        if not item:
            _LOGGER.error(
                "Could not find SAX_MAX_DISCHARGE in MODBUS_BATTERY_POWER_LIMIT_ITEMS"
            )

        return item

    def _resolve_max_discharge_entity(self, item: ModbusItem) -> str | None:
        """Resolve entity_id for max discharge control.

        Args:
            item: ModbusItem for SAX_MAX_DISCHARGE

        Returns:
            Entity ID string or None if resolution failed

        Security:
            OWASP A05: Type guard validates unique_id before registry lookup
            OWASP A01: Uses master's battery_id for proper entity addressing
        """
        # Generate unique_id for SAX_MAX_DISCHARGE entity
        unique_id = self.coordinator.sax_data.get_unique_id_for_item(
            item,
            battery_id=self.coordinator.battery_id,  # Master's battery_id
        )

        # Type guard: Validate unique_id before entity lookup
        if not unique_id:
            _LOGGER.error(
                "Could not generate unique_id for SAX_MAX_DISCHARGE on master %s (entry_id=%s)",
                self.coordinator.battery_id,
                self.coordinator.config_entry.entry_id
                if self.coordinator.config_entry
                else None,
            )
            return None

        # Lookup entity in registry
        ent_reg = er.async_get(self.hass)
        entity_id = ent_reg.async_get_entity_id("number", DOMAIN, unique_id)

        if not entity_id:
            # Log available entities for debugging
            available_entities = (
                [
                    e.unique_id
                    for e in ent_reg.entities.get_entries_for_config_entry_id(
                        self.coordinator.config_entry.entry_id
                    )
                    if e.domain == "number"
                ]
                if self.coordinator.config_entry
                else []
            )

            _LOGGER.error(
                "Could not find entity_id for SAX_MAX_DISCHARGE unique_id=%s (available entities: %s)",
                unique_id,
                available_entities,
            )
            return None

        return entity_id

    async def _write_discharge_limit(
        self,
        entity_id: str,
        limit_watts: float,
        current_soc: float,
    ) -> bool:
        """Write discharge limit to hardware via Home Assistant service.

        Args:
            entity_id: Target entity ID for number.set_value service
            limit_watts: Discharge limit in watts (0 = blocked)
            current_soc: Current SOC percentage for logging

        Returns:
            True if write succeeded, False otherwise

        Security:
            OWASP A05: Uses blocking=True for reliable constraint enforcement

        Performance:
            Skips redundant writes if limit already set to target value
        """
        # Check current state to avoid redundant writes
        current_state = self.hass.states.get(entity_id)
        if current_state and current_state.state not in ("unknown", "unavailable"):
            try:
                current_value = float(current_state.state)
                if current_value == limit_watts:
                    _LOGGER.debug(
                        "Discharge limit already set to %sW on master %s, skipping redundant write",
                        limit_watts,
                        self.coordinator.battery_id,
                    )
                    return False  # No write needed, enforcement already active
            except ValueError, TypeError:
                _LOGGER.warning(
                    "Could not parse current SAX_MAX_DISCHARGE value: %s",
                    current_state.state,
                )

        # Log enforcement action at warning level (user-relevant)
        _LOGGER.warning(
            "Combined SOC %.1f%% below minimum %.1f%% - enforcing discharge limit via master %s",
            current_soc,
            self.min_soc,
            self.coordinator.battery_id,
        )

        # Use number.set_value service to write hardware
        try:
            _LOGGER.info(
                "Calling number.set_value service: entity_id=%s, value=%s",
                entity_id,
                limit_watts,
            )

            await self.hass.services.async_call(
                "number",  # Correct domain for NumberEntity
                "set_value",
                {
                    "entity_id": entity_id,
                    "value": limit_watts,
                },
                blocking=True,  # Wait for completion (safety critical)
            )

            _LOGGER.info(
                "Discharge blocked on master %s: SOC %.1f%% < min %.1f%% (entity: %s)",
                self.coordinator.battery_id,
                current_soc,
                self.min_soc,
                entity_id,
            )

            return True # noqa: TRY300

        except HomeAssistantError as exc:
            # Specific exception: Service call failed
            _LOGGER.error(
                "Failed to enforce discharge limit on master %s via entity %s: %s",
                self.coordinator.battery_id,
                entity_id,
                exc,
            )
            return False
        except (OSError, TimeoutError) as exc:
            # Specific exception: Network or hardware error
            _LOGGER.error(
                "Network error enforcing discharge limit on master %s: %s",
                self.coordinator.battery_id,
                exc,
            )
            return False

    async def _enforce_discharge_constraint(self, combined_soc: float) -> bool:
        """Execute discharge constraint enforcement.

        Orchestrates the enforcement process:
        1. Get ModbusItem for SAX_MAX_DISCHARGE
        2. Resolve entity_id from entity registry
        3. Write 0W limit via Home Assistant service

        Args:
            combined_soc: Current combined SOC percentage

        Returns:
            True if enforcement was applied, False otherwise

        Performance:
            Short-circuits on any step failure to avoid unnecessary work
        """
        # Step 1: Get ModbusItem
        max_discharge_item = self._get_max_discharge_item()
        if not max_discharge_item:
            return False

        # Step 2: Resolve entity_id
        entity_id = self._resolve_max_discharge_entity(max_discharge_item)
        if not entity_id:
            return False

        # Step 3: Write discharge limit (0W = block discharge)
        return await self._write_discharge_limit(
            entity_id=entity_id,
            limit_watts=0,
            current_soc=combined_soc,
        )

    async def check_and_enforce_discharge_limit(self) -> bool:
        """Check and enforce discharge limit based on combined SOC.

        Main entry point for SOC-based constraint enforcement.
        Uses guard clauses for validation, then delegates to enforcement logic.

        Returns:
            bool: True if enforcement was applied, False otherwise

        Security:
            OWASP A05: Validates coordinator state before hardware writes
            OWASP A01: Uses is_master property to ensure proper access control

        Performance:
            Early returns via validation avoid unnecessary enforcement attempts
        """
        # Validate all prerequisites before attempting enforcement
        can_enforce, reason, combined_soc = self._validate_enforcement_prerequisites()

        if not can_enforce:
            _LOGGER.debug("SOC enforcement skipped: %s", reason)
            return False

        # All validations passed - proceed with enforcement
        # combined_soc is guaranteed to be float (not None) when can_enforce=True
        assert combined_soc is not None, (
            "combined_soc must be set when can_enforce=True"
        )
        return await self._enforce_discharge_constraint(combined_soc)

    def get_diagnostics(self) -> dict[str, object]:
        """Return diagnostic information for troubleshooting.

        Returns:
            Dictionary with SOC manager state and configuration

        Security:
            OWASP A05: Exposes only non-sensitive configuration data
        """
        combined_soc = None
        if self.coordinator.data:
            combined_soc = self.coordinator.data.get(SAX_COMBINED_SOC)

        return {
            "enabled": self._enabled,
            "min_soc": self._min_soc,
            "coordinator_is_master": self.coordinator.is_master,
            "coordinator_battery_id": self.coordinator.battery_id,
            "combined_soc": combined_soc,
        }
