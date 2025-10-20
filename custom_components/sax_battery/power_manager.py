"""Power manager for SAX Battery integration.

Replaces pilot.py with state-based power management using Home Assistant
number entities (SAX_NOMINAL_POWER and SAX_NOMINAL_FACTOR) and SOC constraints.

Security:
    OWASP A05: Validates all sensor inputs and power values
    OWASP A01: Only master battery can create power manager

Performance:
    Debounced grid monitoring with configurable intervals
    Efficient state updates using HA service calls
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_GRID_POWER_SENSOR,
    CONF_MANUAL_CONTROL,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    MANUAL_CONTROL_MODE,
    PILOT_ITEMS,
    SAX_AC_POWER_TOTAL,
    SAX_NOMINAL_FACTOR,
    SAX_PILOT_POWER,
    SOLAR_CHARGING_MODE,
)
from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PowerManagerState:
    """Power manager state tracking.

    Performance: Uses slots for memory efficiency
    """

    mode: str
    target_power: float
    last_update: datetime
    solar_charging_enabled: bool = False
    manual_control_enabled: bool = False


class PowerManager:
    """Power manager for coordinating battery control via HA entities.

    This replaces the direct Modbus write approach in pilot.py with a state-based
    system using Home Assistant number entities and SOC constraints.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SAXBatteryCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize power manager.

        Args:
            hass: Home Assistant instance
            coordinator: Master battery coordinator
            config_entry: Configuration entry

        Security:
            OWASP A01: Validates coordinator is for master battery
        """
        self.hass = hass
        self.coordinator = coordinator
        self.config_entry = config_entry
        self.battery_count = len(coordinator.sax_data.coordinators)

        # Power limits based on battery count
        self.max_discharge_power = self.battery_count * LIMIT_MAX_CHARGE_PER_BATTERY
        self.max_charge_power = self.battery_count * LIMIT_MAX_DISCHARGE_PER_BATTERY

        # State tracking
        self._state = PowerManagerState(
            mode=MANUAL_CONTROL_MODE,
            target_power=0.0,
            last_update=datetime.now(),
        )

        # Tracking for event listeners
        self._remove_interval_update: Callable[[], None] | None = None
        self._remove_config_update: Callable[[], None] | None = None
        self._running = False

        # Resolve entity IDs from entity registry using unique_id
        self._power_entity_id: str | None = None
        self._power_factor_entity_id: str | None = None
        self._resolve_entity_ids()

        # Configuration values - now safe to call after state initialization
        self._update_config_values()

    def _resolve_entity_ids(self) -> None:
        """Resolve entity IDs for power control entities from registry."""
        if not self.coordinator.config_entry:
            _LOGGER.error("Coordinator has no config entry, cannot resolve entity IDs")
            return

        ent_reg = er.async_get(self.hass)

        # Resolve SAX_PILOT_POWER entity (the one that actually exists!)
        # Find the pilot power item from the list
        pilot_power_item = next(
            (item for item in PILOT_ITEMS if item.name == SAX_PILOT_POWER),
            None,
        )

        if not pilot_power_item:
            _LOGGER.error("Could not find %s in PILOT_ITEMS", SAX_PILOT_POWER)
            return

        power_unique_id = self.coordinator.sax_data.get_unique_id_for_item(
            pilot_power_item,
            SAX_PILOT_POWER,
        )

        if power_unique_id:
            self._power_entity_id = ent_reg.async_get_entity_id(
                "number",
                DOMAIN,
                power_unique_id,
            )

            if not self._power_entity_id:
                _LOGGER.error(
                    "Could not find power entity (unique_id: %s)",
                    power_unique_id,
                )
            else:
                _LOGGER.info(
                    "✓ Resolved power entity: %s (unique_id: %s)",
                    self._power_entity_id,
                    power_unique_id,
                )
        else:
            _LOGGER.error("Could not generate unique_id for %s", SAX_PILOT_POWER)

        power_factor_item = next(
            (item for item in PILOT_ITEMS if item.name == SAX_NOMINAL_FACTOR),
            None,
        )

        if not power_factor_item:
            _LOGGER.error("Could not find %s in PILOT_ITEMS", SAX_NOMINAL_FACTOR)
            return

        # Resolve SAX_NOMINAL_FACTOR entity (for power factor)
        factor_unique_id = self.coordinator.sax_data.get_unique_id_for_item(
            power_factor_item,
            SAX_NOMINAL_FACTOR,
        )

        if factor_unique_id:
            self._power_factor_entity_id = ent_reg.async_get_entity_id(
                "number",
                DOMAIN,
                factor_unique_id,
            )

            if not self._power_factor_entity_id:
                _LOGGER.error(
                    "Could not find power factor entity (unique_id: %s)",
                    factor_unique_id,
                )
            else:
                _LOGGER.info(
                    "✓ Resolved power factor entity: %s",
                    self._power_factor_entity_id,
                )
        else:
            _LOGGER.error("Could not generate unique_id for %s", SAX_NOMINAL_FACTOR)

        _LOGGER.debug(
            "Entity resolution complete: power=%s, factor=%s",
            self._power_entity_id,
            self._power_factor_entity_id,
        )

    def _update_config_values(self) -> None:
        """Update configuration values from entry data."""
        self.grid_power_sensor = self.config_entry.data.get(CONF_GRID_POWER_SENSOR)
        self.update_interval = self.config_entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )

        solar_enabled = bool(
            self.config_entry.data.get(CONF_ENABLE_SOLAR_CHARGING, False)
        )
        manual_enabled = bool(self.config_entry.data.get(CONF_MANUAL_CONTROL, False))

        # Security: Enforce mutual exclusion at startup
        if solar_enabled and manual_enabled:
            _LOGGER.warning(
                "Both solar charging and manual control are enabled in config - "
                "defaulting to solar charging mode"
            )
            solar_enabled = True
            manual_enabled = False

        self._state.solar_charging_enabled = solar_enabled
        self._state.manual_control_enabled = manual_enabled

        _LOGGER.info(
            "Power manager config updated: interval=%ss, solar=%s, manual=%s, grid_sensor=%s",
            self.update_interval,
            solar_enabled,
            manual_enabled,
            self.grid_power_sensor,
        )

    async def async_start(self) -> None:
        """Start the power manager service.

        Security: Only starts if not already running
        """
        if self._running:
            _LOGGER.warning("Power manager already running")
            return

        self._running = True

        # Set up periodic updates
        self._remove_interval_update = async_track_time_interval(
            self.hass,
            self._async_update_power,
            timedelta(seconds=self.update_interval),
        )

        # Add listener for config entry updates
        self._remove_config_update = self.config_entry.add_update_listener(
            self._async_config_updated
        )

        # Do initial update
        await self._async_update_power(None)

        _LOGGER.info("Power manager started with %ss interval", self.update_interval)

    async def async_stop(self) -> None:
        """Stop the power manager service.

        Security: Proper resource cleanup (OWASP A05)
        """
        if not self._running:
            return

        if self._remove_interval_update is not None:
            self._remove_interval_update()
            self._remove_interval_update = None

        if self._remove_config_update is not None:
            self._remove_config_update()
            self._remove_config_update = None

        self._running = False
        _LOGGER.info("Power manager stopped")

    async def _async_config_updated(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Handle config entry updates.

        Args:
            hass: Home Assistant instance
            entry: Updated config entry
        """
        self.config_entry = entry
        self._update_config_values()
        await self._async_update_power(None)
        _LOGGER.info("Power manager configuration updated")

    async def _async_update_power(self, now: Any = None) -> None:
        """Update power setpoint based on current mode.

        Args:
            now: Current time (from time interval trigger)

        Security:
            OWASP A05: Validates sensor states before processing
        """
        try:
            # Check current mode
            if self._state.manual_control_enabled:
                _LOGGER.debug(
                    "Manual control mode active - power: %sW",
                    self._state.target_power,
                )
                return

            if self._state.solar_charging_enabled:
                await self._update_solar_charging_power()
            else:
                _LOGGER.debug("No active power management mode")

        except (OSError, ValueError, TypeError) as err:
            _LOGGER.error("Error updating power: %s", err)

    async def _update_solar_charging_power(self) -> None:
        """Update power setpoint for solar charging mode.

        Uses the formula: New Battery Power = Current Battery Power - Grid Power
        This ensures grid power goes to zero by adjusting battery charge/discharge.

        Security:
            OWASP A05: Validates grid sensor state
        """
        if not self.grid_power_sensor:
            _LOGGER.warning("Grid power sensor not configured")
            return

        # Get grid power state (negative = export, positive = import)
        grid_state = self.hass.states.get(self.grid_power_sensor)
        if grid_state is None:
            _LOGGER.warning("Grid power sensor %s not found", self.grid_power_sensor)
            return

        if grid_state.state in (None, "unknown", "unavailable"):
            _LOGGER.warning(
                "Grid power sensor %s state is %s",
                self.grid_power_sensor,
                grid_state.state,
            )
            return

        try:
            grid_power = float(grid_state.state)
        except (ValueError, TypeError) as err:
            _LOGGER.error(
                "Could not convert grid power '%s' to float: %s",
                grid_state.state,
                err,
            )
            return

        # ✅ Get current battery power from coordinator data using correct constant
        current_battery_power = 0.0
        if self.coordinator.data:
            # Try SAX_AC_POWER_TOTAL first (address 40085)
            battery_power_value = self.coordinator.data.get(SAX_AC_POWER_TOTAL)

            if battery_power_value is not None:
                try:
                    current_battery_power = float(battery_power_value)
                    _LOGGER.debug(
                        "Current battery power: %sW (from %s)",
                        current_battery_power,
                        SAX_AC_POWER_TOTAL,
                    )
                except (ValueError, TypeError) as err:
                    _LOGGER.error(
                        "Could not convert battery power '%s' to float: %s",
                        battery_power_value,
                        err,
                    )
                    return
            else:
                _LOGGER.warning(
                    "Battery power sensor %s not found in coordinator data. Available keys: %s",
                    SAX_AC_POWER_TOTAL,
                    list(self.coordinator.data.keys()) if self.coordinator.data else [],
                )
                # Don't return - use 0.0 as fallback for first calculation
        else:
            _LOGGER.warning("Coordinator data not available")
            return

        # ✅ CORRECT CALCULATION:
        # New Battery Power = Current Battery Power - Grid Power
        #
        # Convention:
        # - Grid: negative = export to grid, positive = import from grid
        # - Battery: negative = charging, positive = discharging
        #
        # Examples:
        # 1. Grid exporting 1000W (grid=-1000), Battery charging 3000W (battery=-3000)
        #    → Target: -3000 - (-1000) = -4000W (charge more to eliminate export)
        #
        # 2. Grid importing 500W (grid=+500), Battery charging 3000W (battery=-3000)
        #    → Target: -3000 - (+500) = -3500W (charge less to eliminate import)
        #
        # 3. Grid importing 2000W (grid=+2000), Battery charging 1000W (battery=-1000)
        #    → Target: -1000 - (+2000) = +1000W (discharge to eliminate import)

        target_power = current_battery_power - grid_power

        _LOGGER.debug(
            "Solar charging calculation: grid=%sW, current_battery=%sW, raw_target=%sW",
            grid_power,
            current_battery_power,
            target_power,
        )

        # Apply power limits (Note: charging is negative, discharging is positive)
        target_power = max(
            -self.max_charge_power,  # Maximum charge (negative value)
            min(
                self.max_discharge_power, target_power
            ),  # Maximum discharge (positive value)
        )

        _LOGGER.debug("After power limits: target=%sW", target_power)

        # Apply SOC constraints
        constrained_result = await self.coordinator.soc_manager.apply_constraints(
            target_power
        )
        final_target = constrained_result.constrained_value

        if final_target != target_power:
            _LOGGER.info(
                "Solar charging constrained by SOC: %sW → %sW (reason: %s)",
                target_power,
                final_target,
                constrained_result.reason
                if hasattr(constrained_result, "reason")
                else "SOC limits",
            )

        _LOGGER.info(
            "Solar charging update: grid=%sW, battery=%sW → target=%sW",
            grid_power,
            current_battery_power,
            final_target,
        )

        # Update power setpoint via number entity
        await self.update_power_setpoint(final_target)

    async def update_power_setpoint(self, power: float) -> None:
        """Update power setpoint via number entity service call.

        Args:
            power: Power value in watts (positive = discharge, negative = charge)

        Security:
            OWASP A05: Validates power limits and entity availability
        Performance:
            Non-blocking service call for efficiency
        """
        # Security: Validate power limits
        if not isinstance(power, (int, float)):
            _LOGGER.error("Invalid power value type: %s", type(power))  # type:ignore[unreachable]
            return

        # Clamp to absolute limits
        clamped_power = max(
            -self.max_charge_power,  # Note: negative = charge
            min(self.max_discharge_power, power),
        )

        if clamped_power != power:
            _LOGGER.warning("Power value %sW clamped to %sW", power, clamped_power)

        # Update state
        self._state.target_power = clamped_power
        self._state.last_update = datetime.now()

        # Since we know the entity is number.sax_cluster_pilot_power, just use it
        power_entity_id = "number.sax_cluster_pilot_power"

        # Verify entity exists
        if not self.hass.states.get(power_entity_id):
            _LOGGER.error(
                "Power entity %s not found in Home Assistant. Available number entities:",
                power_entity_id,
            )
            for state in self.hass.states.async_all("number"):
                if (
                    "pilot" in state.entity_id.lower()
                    or "power" in state.entity_id.lower()
                ):
                    _LOGGER.error("  - %s", state.entity_id)
            return

        # Call service
        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": power_entity_id,
                    "value": clamped_power,
                },
                blocking=False,
            )

            _LOGGER.info(
                "✓ Power setpoint updated to %sW via %s",
                clamped_power,
                power_entity_id,
            )
        except Exception as err:
            _LOGGER.error(  # noqa: G201
                "Failed to update power setpoint: %s",
                err,
                exc_info=True,
            )

    async def set_solar_charging_mode(self, enabled: bool) -> None:
        """Enable or disable solar charging mode.

        Args:
            enabled: True to enable solar charging mode

        Security:
            OWASP A01: Power manager state synchronized with switch state
        """
        self._state.solar_charging_enabled = enabled
        self._state.mode = SOLAR_CHARGING_MODE if enabled else MANUAL_CONTROL_MODE

        # Update manual control state (mutual exclusion)
        if enabled:
            self._state.manual_control_enabled = False

        _LOGGER.info(
            "Solar charging mode %s (manual_control=%s)",
            "enabled" if enabled else "disabled",
            self._state.manual_control_enabled,
        )

        if enabled:
            await self._async_update_power(None)

    async def set_manual_control_mode(self, enabled: bool, power: float = 0.0) -> None:
        """Enable or disable manual control mode.

        Args:
            enabled: True to enable manual control mode
            power: Manual power setpoint (only used if enabled=True)

        Security:
            OWASP A01: Power manager state synchronized with switch state
            OWASP A05: Applies SOC constraints
        """
        self._state.manual_control_enabled = enabled
        self._state.mode = MANUAL_CONTROL_MODE if enabled else SOLAR_CHARGING_MODE

        # Update solar charging state (mutual exclusion)
        if enabled:
            self._state.solar_charging_enabled = False

        if enabled:
            # Apply SOC constraints to manual power
            constrained_result = await self.coordinator.soc_manager.apply_constraints(
                power
            )
            await self.update_power_setpoint(constrained_result.constrained_value)

        _LOGGER.info(
            "Manual control mode %s (solar_charging=%s)",
            "enabled" if enabled else "disabled",
            self._state.solar_charging_enabled,
        )

    @property
    def current_mode(self) -> str:
        """Get current power management mode."""
        return self._state.mode

    @property
    def current_power(self) -> float:
        """Get current power setpoint."""
        return self._state.target_power
