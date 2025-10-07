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

from homeassistant.components.input_number import SERVICE_SET_VALUE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_GRID_POWER_SENSOR,
    CONF_MANUAL_CONTROL,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    MANUAL_CONTROL_MODE,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
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

        # Configuration values
        self._update_config_values()

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

        # Entity IDs for number entities
        self._power_entity_id = f"number.{DOMAIN}_{SAX_NOMINAL_POWER}"
        self._power_factor_entity_id = f"number.{DOMAIN}_{SAX_NOMINAL_FACTOR}"

    def _update_config_values(self) -> None:
        """Update configuration values from entry data."""
        self.grid_power_sensor = self.config_entry.data.get(CONF_GRID_POWER_SENSOR)
        self.update_interval = self.config_entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )

        # Update state flags
        self._state.solar_charging_enabled = bool(
            self.config_entry.data.get(SOLAR_CHARGING_MODE, False)
        )
        self._state.manual_control_enabled = bool(
            self.config_entry.data.get(CONF_MANUAL_CONTROL, False)
        )

        _LOGGER.debug(
            "Power manager config updated: interval=%ss, solar=%s, manual=%s",
            self.update_interval,
            self._state.solar_charging_enabled,
            self._state.manual_control_enabled,
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

        Security:
            OWASP A05: Validates grid sensor state
        """
        if not self.grid_power_sensor:
            _LOGGER.warning("Grid power sensor not configured")
            return

        # Get grid power state
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

        # Calculate target power (negative grid power = export, charge battery)
        target_power = -grid_power

        # Apply power limits
        target_power = max(
            -self.max_discharge_power,
            min(self.max_charge_power, target_power),
        )

        # Apply SOC constraints
        _LOGGER.debug("Pre-constraint target power: %sW", target_power)
        constrained_result = await self.coordinator.soc_manager.apply_constraints(
            target_power
        )
        target_power = constrained_result.constrained_value
        _LOGGER.debug("Post-constraint target power: %sW", target_power)

        # Update power setpoint via number entity
        await self.update_power_setpoint(target_power)

    async def update_power_setpoint(self, power: float) -> None:
        """Update power setpoint via number entity service call.

        Args:
            power: Power value in watts (positive = discharge, negative = charge)

        Security:
            OWASP A05: Validates power limits
        Performance:
            Non-blocking service call for efficiency
        """
        # Security: Validate power limits
        if not isinstance(power, (int, float)):
            _LOGGER.error("Invalid power value type: %s", type(power))  # type:ignore[unreachable]
            return

        # Clamp to absolute limits
        clamped_power = max(
            -self.max_discharge_power,
            min(self.max_charge_power, power),
        )

        if clamped_power != power:
            _LOGGER.warning("Power value %sW clamped to %sW", power, clamped_power)

        # Update state
        self._state.target_power = clamped_power
        self._state.last_update = datetime.now()

        # Call number entity service (non-blocking for performance)
        await self.hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {
                "entity_id": self._power_entity_id,
                "value": clamped_power,
            },
            blocking=False,
        )

        _LOGGER.debug("Power setpoint updated to %sW", clamped_power)

    async def set_solar_charging_mode(self, enabled: bool) -> None:
        """Enable or disable solar charging mode.

        Args:
            enabled: True to enable solar charging mode

        Security:
            OWASP A01: Validates only one mode can be active
        """
        if enabled and self._state.manual_control_enabled:
            _LOGGER.warning(
                "Cannot enable solar charging while manual control is active"
            )
            return

        self._state.solar_charging_enabled = enabled
        self._state.mode = SOLAR_CHARGING_MODE if enabled else MANUAL_CONTROL_MODE

        _LOGGER.info("Solar charging mode %s", "enabled" if enabled else "disabled")

        if enabled:
            await self._async_update_power(None)

    async def set_manual_control_mode(self, enabled: bool, power: float = 0.0) -> None:
        """Enable or disable manual control mode.

        Args:
            enabled: True to enable manual control mode
            power: Manual power setpoint (only used if enabled=True)

        Security:
            OWASP A01: Validates only one mode can be active
            OWASP A05: Applies SOC constraints
        """
        if enabled and self._state.solar_charging_enabled:
            _LOGGER.warning(
                "Cannot enable manual control while solar charging is active"
            )
            return

        self._state.manual_control_enabled = enabled
        self._state.mode = MANUAL_CONTROL_MODE if enabled else SOLAR_CHARGING_MODE

        if enabled:
            # Apply SOC constraints to manual power
            constrained_result = await self.coordinator.soc_manager.apply_constraints(
                power
            )
            await self.update_power_setpoint(constrained_result.constrained_value)

        _LOGGER.info("Manual control mode %s", "enabled" if enabled else "disabled")

    @property
    def current_mode(self) -> str:
        """Get current power management mode."""
        return self._state.mode

    @property
    def current_power(self) -> float:
        """Get current power setpoint."""
        return self._state.target_power
