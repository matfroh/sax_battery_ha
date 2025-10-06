"""SAX Battery pilot functionality."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from pymodbus import ModbusException

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    CONF_PRIORITY_DEVICES,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_pilot(hass: HomeAssistant, entry_id: str) -> bool:
    """Set up the SAX Battery pilot service."""
    sax_data = hass.data[DOMAIN][entry_id]

    # Check if pilot mode is enabled
    if not sax_data.entry.data.get(CONF_PILOT_FROM_HA, False):
        _LOGGER.debug("Battery pilot mode is disabled, skipping setup")
        return False

    # Create battery pilot instance
    pilot = SAXBatteryPilot(hass, sax_data)

    # Store pilot instance
    sax_data.pilot = pilot

    # Create entities
    component = EntityComponent(_LOGGER, f"{DOMAIN}_pilot", hass)
    entities = [SAXBatteryPilotPowerEntity(pilot), SAXBatterySolarChargingSwitch(pilot)]

    await component.async_add_entities(entities)

    # Start automatic pilot service
    await pilot.async_start()
    return True


class SAXBatteryPilot:
    """SAX Battery pilot controller for master battery coordination."""

    def __init__(
        self,
        hass: HomeAssistant,
        sax_data: SAXBatteryData,
        coordinator: SAXBatteryCoordinator,
    ) -> None:
        """Initialize the pilot controller."""
        self.hass = hass
        self.sax_data = sax_data
        self.coordinator = coordinator
        self.entry = sax_data.entry
        self.battery_count = len(sax_data.coordinators)

        # Configuration values
        self._update_config_values()
        self.power_sensor_entity_id = self.entry.data.get(CONF_POWER_SENSOR)
        self.pf_sensor_entity_id = self.entry.data.get(CONF_PF_SENSOR)
        self.priority_devices = self.entry.data.get(CONF_PRIORITY_DEVICES, [])
        # self.min_soc = self.entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self.update_interval = self.entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )

        # Calculated values
        self.calculated_power = 0.0
        self.max_discharge_power = self.battery_count * 3600
        self.max_charge_power = self.battery_count * 4500

        # Modbus
        self.master_battery = sax_data.master_battery

        # Track state
        self._remove_interval_update: Callable[[], None] | None = None
        self._remove_config_update: Callable[[], None] | None = None
        self._running = False

    def _update_config_values(self) -> None:
        """Update configuration values from entry data."""
        self.power_sensor_entity_id = self.entry.data.get(CONF_POWER_SENSOR)
        self.pf_sensor_entity_id = self.entry.data.get(CONF_PF_SENSOR)
        self.priority_devices = self.entry.data.get(CONF_PRIORITY_DEVICES, [])
        # self.min_soc = self.entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self.update_interval = self.entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )
        self.solar_charging_enabled = self.entry.data.get(
            CONF_ENABLE_SOLAR_CHARGING, True
        )
        _LOGGER.debug(
            "Updated config value update_interval: %ss",
            self.update_interval,
        )

    async def async_start(self) -> None:
        """Start the pilot service."""
        if self._running:
            return

        self._running = True

        # Get current interval from coordinator or entry options, with min 5s, max 300s
        current_interval = max(
            5,
            min(
                300,
                (
                    self.sax_data.auto_pilot_interval
                    if hasattr(self.sax_data, "auto_pilot_interval")
                    else self.entry.options.get(
                        CONF_AUTO_PILOT_INTERVAL,
                        self.entry.data.get(
                            CONF_AUTO_PILOT_INTERVAL, 5
                        ),  # Default to 5s if not set
                    )
                ),
            ),
        )

        # Update the stored interval
        self.update_interval = current_interval

        # Start the update scheduler
        self._remove_interval_update = async_track_time_interval(
            self.hass, self._async_update_pilot, timedelta(seconds=current_interval)
        )

        # Add listener for config entry updates
        self._remove_config_update = self.entry.add_update_listener(
            self._async_config_updated
        )

        # Do initial calculation
        await self._async_update_pilot(None)

        _LOGGER.info("SAX Battery pilot started with %ss interval", current_interval)

    async def _async_config_updated(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Handle config entry updates."""
        self.entry = entry
        self._update_config_values()
        # Apply new configuration immediately
        await self._async_update_pilot(None)
        _LOGGER.info("SAX Battery pilot configuration updated")

    async def async_stop(self) -> None:
        """Stop the pilot service."""
        if not self._running:
            return

        if self._remove_interval_update is not None:
            self._remove_interval_update()
            self._remove_interval_update = None

        if self._remove_config_update is not None:
            self._remove_config_update()
            self._remove_config_update = None

        self._running = False
        _LOGGER.info("SAX Battery pilot stopped")

    async def _async_update_pilot(self, now: Any = None) -> None:
        """Update the pilot calculations and send to battery."""
        # Enhanced logging to track what's calling this method
        caller_frame = inspect.currentframe()
        caller_info = "unknown"
        if caller_frame and caller_frame.f_back:
            caller_info = f"{caller_frame.f_back.f_code.co_filename}:{caller_frame.f_back.f_lineno}"
            caller_info = (
                caller_info.split("/")[-1] if "/" in caller_info else caller_info
            )

        _LOGGER.info(
            "Pilot update called from: %s, now parameter: %s", caller_info, now
        )

        try:
            # Check if in manual mode - if so, skip automatic calculations entirely
            if self.entry.data.get(CONF_MANUAL_CONTROL, False):
                # Skip automatic calculations in manual mode
                _LOGGER.debug(
                    "Manual control mode active - Current power setting: %sW",
                    self.calculated_power,
                )

                # Check SOC constraints for the current manual power setting
                _LOGGER.debug(
                    "Checking SOC constraints for manual power: %sW",
                    self.calculated_power,
                )
                constrained_power = await self._apply_soc_constraints(
                    self.calculated_power
                )
                if constrained_power != self.calculated_power:
                    _LOGGER.info(
                        "Manual power needs adjustment from %sW to %sW due to SOC constraints",
                        self.calculated_power,
                        constrained_power,
                    )
                    # Update the power setting if constraints changed it
                    await self.send_power_command(constrained_power, 1.0)
                    self.calculated_power = constrained_power
                    _LOGGER.info(
                        "Manual power adjusted to %sW due to SOC constraints",
                        constrained_power,
                    )
                else:
                    _LOGGER.debug(
                        "No SOC constraint adjustments needed for manual power %sW",
                        self.calculated_power,
                    )
                return

            # Get current power sensor state
            if self.power_sensor_entity_id is None:
                _LOGGER.warning("Power sensor entity ID is not configured")
                return

            power_state = self.hass.states.get(self.power_sensor_entity_id)
            if power_state is None:
                _LOGGER.warning(
                    "Power sensor %s not found", self.power_sensor_entity_id
                )
                return

            if power_state.state in (None, "unknown", "unavailable"):
                _LOGGER.warning(
                    "Power sensor %s state is %s",
                    self.power_sensor_entity_id,
                    power_state.state,
                )
                return

            try:
                total_power = float(power_state.state)
            except (ValueError, TypeError) as err:
                _LOGGER.error(
                    "Could not convert power sensor state '%s' to float: %s",
                    power_state.state,
                    err,
                )
                return

            # Get current PF value
            if self.pf_sensor_entity_id is None:
                _LOGGER.warning("PF sensor entity ID is not configured")
                return

            pf_state = self.hass.states.get(self.pf_sensor_entity_id)
            if pf_state is None:
                _LOGGER.warning("PF sensor %s not found", self.pf_sensor_entity_id)
                return

            if pf_state.state in (None, "unknown", "unavailable"):
                _LOGGER.warning(
                    "PF sensor %s state is %s", self.pf_sensor_entity_id, pf_state.state
                )
                return

            try:
                power_factor = float(pf_state.state)
            except (ValueError, TypeError) as err:
                _LOGGER.error(
                    "Could not convert PF sensor state '%s' to float: %s",
                    pf_state.state,
                    err,
                )
                return

            # Get priority device power consumption
            priority_power = 0.0
            for device_id in self.priority_devices:
                device_state = self.hass.states.get(device_id)
                if device_state is not None:
                    try:
                        priority_power += float(device_state.state)
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Could not convert state of %s to number", device_id
                        )

            # Get current battery power
            battery_power_state = self.hass.states.get(
                "sensor.sax_battery_combined_power"
            )
            battery_power = 0.0
            if battery_power_state is not None:
                try:
                    if battery_power_state.state not in (
                        None,
                        "unknown",
                        "unavailable",
                    ):
                        battery_power = float(battery_power_state.state)
                    else:
                        _LOGGER.debug(
                            "Battery power state is %s", battery_power_state.state
                        )
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Could not convert battery power '%s' to number: %s",
                        battery_power_state.state,
                        err,
                    )

            # Get current SOC for logging
            master_soc = await self._get_combined_soc()
            _LOGGER.debug("Current master SOC: %s%%", master_soc)

            # Calculate target power
            _LOGGER.debug(
                "Starting calculation with total_power=%s, priority_power=%s, battery_power=%s",
                total_power,
                priority_power,
                battery_power,
            )

            if priority_power > 50:
                _LOGGER.debug(
                    "Condition met: priority_power > 50 (%s > 50)", priority_power
                )
                net_power = 0.0
                _LOGGER.debug("Set net_power = 0")
            else:
                _LOGGER.debug(
                    "Condition met: priority_power <= 50 (%s <= 50)", priority_power
                )
                net_power = total_power - battery_power
                _LOGGER.debug(
                    "Calculated net_power = %s - %s = %s",
                    total_power,
                    battery_power,
                    net_power,
                )

            _LOGGER.debug("Final net_power value: %s", net_power)

            target_power = -net_power
            _LOGGER.debug("Final target_power value: %s", target_power)

            # Apply limits
            target_power = max(
                -self.max_discharge_power, min(self.max_charge_power, target_power)
            )

            # Apply SOC constraints
            _LOGGER.debug("Pre-constraint target power: %sW", target_power)
            target_power = await self._apply_soc_constraints(target_power)
            _LOGGER.debug("Post-constraint target power: %sW", target_power)

            # Update calculated power
            self.calculated_power = target_power

            # Send to battery if solar charging is enabled
            if self.get_solar_charging_enabled():
                await self.send_power_command(target_power, power_factor)

            _LOGGER.debug(
                "Updated battery pilot: target power = %sW, PF = %s",
                target_power,
                power_factor,
            )

        except (OSError, ValueError, TypeError) as err:
            _LOGGER.error("Error in battery pilot update: %s", err)

    async def _get_combined_soc(self) -> float:
        """Get combined SOC from coordinator data."""
        if not self.coordinator.data:
            return 0.0

        soc_value = self.coordinator.data.get(SAX_COMBINED_SOC, 0)
        try:
            return float(soc_value)
        except (ValueError, TypeError):
            return 0.0

    async def _apply_soc_constraints(self, power_value: float) -> float:
        """Apply SOC constraints using coordinator's SOC manager.

        Deprecated:
            Use coordinator.soc_manager.apply_constraints() directly
            Kept for backward compatibility
        """
        result = await self.coordinator.soc_manager.apply_constraints(power_value)
        return result.constrained_value

    async def set_solar_charging(self, enabled: bool) -> None:
        """Enable or disable solar charging."""
        self.solar_charging_enabled = enabled

        # Only trigger automatic calculations if NOT in manual mode
        if enabled and not self.entry.data.get(CONF_MANUAL_CONTROL, False):
            # Recalculate and send current value (automatic mode only)
            await self._async_update_pilot()
        elif not enabled:
            # Always send 0 to stop charging, regardless of mode
            await self.send_power_command(0, 1.0)

        _LOGGER.info("Solar charging %s", "enabled" if enabled else "disabled")

    async def set_manual_power(self, power_value: float) -> None:
        """Set a manual power value."""
        # Store the value
        self.calculated_power = power_value

        # If in manual mode, apply constraints and send immediately
        if self.entry.data.get(CONF_MANUAL_CONTROL, False):
            constrained_power = await self._apply_soc_constraints(power_value)
            await self.send_power_command(constrained_power, 1.0)
            _LOGGER.debug("Manual power set to %sW", constrained_power)
        else:
            _LOGGER.debug(
                "Manual power stored: %sW (will be used when manual mode is enabled)",
                power_value,
            )

    async def set_interval(self, interval: float) -> None:
        """Set the pilot update interval."""
        self.update_interval = int(interval)

        # Restart the timer with new interval
        if self._running and self._remove_interval_update is not None:
            self._remove_interval_update()
            self._remove_interval_update = async_track_time_interval(
                self.hass,
                self._async_update_pilot,
                timedelta(seconds=self.update_interval),
            )

        _LOGGER.debug("Pilot update interval changed to %ss", self.update_interval)

    async def set_min_soc(self, min_soc: float) -> None:
        """Set the minimum SOC constraint."""
        self.min_soc = min_soc

        # Apply new constraint immediately if running
        if self._running:
            await self._async_update_pilot()

        _LOGGER.debug("Minimum SOC changed to %s%%", self.min_soc)

    async def _apply_manual_power_with_constraints(self) -> None:
        """Apply the stored manual power value with current SOC constraints."""
        # Use the current calculated power as the manual power value
        power_value = self.calculated_power
        adjusted_power: float = 0.0

        # Apply SOC constraints
        power_value = await self._apply_soc_constraints(power_value)

        # Send the power command with a default power factor of 1.0
        await self.send_power_command(power_value, 1.0)
        self.calculated_power = power_value
        _LOGGER.info("Manual power set to %sW", power_value)

    async def set_charge_power_limit(self, power_limit: int) -> bool:
        """Set the maximum charge power limit using coordinator."""
        try:
            _LOGGER.debug("Setting charge power limit to %s W", power_limit)

            # Find the charge power limit item using updated constant
            charge_item = self._get_modbus_item_by_name(SAX_MAX_CHARGE)

            if not charge_item:
                _LOGGER.error("Could not find charge power limit item")
                return False

            # Use coordinator's write method
            success = await self.coordinator.async_write_number_value(
                charge_item, float(power_limit)
            )

            if success:
                _LOGGER.debug("Charge power limit set successfully")
            else:
                _LOGGER.error("Failed to send power command: %sW", power)

        except TimeoutError:
            _LOGGER.error("Timeout sending power command: %sW (took >10s)", power)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error sending power command: %sW - %s", power, err)


class SAXBatteryPilotPowerEntity(NumberEntity):
    """Entity showing current calculated pilot power."""

    def __init__(self, pilot: SAXBatteryPilot) -> None:
        """Initialize the entity."""
        self._pilot = pilot
        self._attr_unique_id = f"{DOMAIN}_pilot_power_{self._pilot.sax_data.device_id}"
        self._attr_name = "Battery Pilot Power"
        self._attr_native_min_value = -self._pilot.max_discharge_power
        self._attr_native_max_value = self._pilot.max_charge_power
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_should_poll = True
        self._attr_mode = NumberMode.BOX

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._pilot.sax_data.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def native_value(self) -> float | None:
        """Return the current calculated power."""
        return (
            float(self._pilot.calculated_power)
            if self._pilot.calculated_power is not None
            else None
        )

    @property
    def icon(self) -> str | None:
        """Return the icon to use for the entity."""
        if self._pilot.calculated_power > 0:
            return "mdi:battery-charging"
        if self._pilot.calculated_power < 0:
            return "mdi:battery-minus"
        return "mdi:battery"

    async def async_set_native_value(self, value: float) -> None:
        """Handle manual override of calculated power."""
        _LOGGER.debug("Setting manual power to %sW via pilot entity", value)

        # Store the manual power value in the pilot
        self._pilot.calculated_power = value

    def get_solar_charging_enabled(self) -> bool:
        """Get solar charging state."""
        # ✅ Only enable if both pilot and solar charging are enabled
        pilot_enabled = bool(self.entry.data.get(CONF_PILOT_FROM_HA, False))
        solar_enabled = bool(
            self.entry.data.get(CONF_ENABLE_SOLAR_CHARGING, False)
        )  # Changed default to False
        return pilot_enabled and solar_enabled

        # Log to confirm it was set
        _LOGGER.debug(
            "Pilot calculated_power updated to: %sW", self._pilot.calculated_power
        )

        # If we're in manual mode, send the command immediately
        if self._pilot.entry.data.get(CONF_MANUAL_CONTROL, False):
            # Apply SOC constraints
            constrained_value = await self._pilot._apply_soc_constraints(value)  # noqa: SLF001
            await self._pilot.send_power_command(constrained_value, 1.0)

            # Log what actually happened
            if constrained_value != value:
                _LOGGER.info(
                    "Manual power requested: %sW, actually sent: %sW (constrained by SOC)",
                    value,
                    constrained_value,
                )
            else:
                _LOGGER.debug(
                    "Manual power set to %sW via pilot entity", constrained_value
                )
        else:
            _LOGGER.debug("Power value stored: %sW (manual mode not active)", value)


class SAXBatterySolarChargingSwitch(SwitchEntity):
    """Switch to enable/disable solar charging."""

    def __init__(self, pilot: SAXBatteryPilot) -> None:
        """Initialize the switch."""
        self._pilot = pilot
        self._attr_unique_id = (
            f"{DOMAIN}_solar_charging_{self._pilot.sax_data.device_id}"
        )
        self._attr_name = "Solar Charging"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._pilot.sax_data.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if solar charging is enabled."""
        return (
            bool(self._pilot.solar_charging_enabled)
            if self._pilot.solar_charging_enabled is not None
            else None
        )

    @property
    def icon(self) -> str | None:
        """Return the icon to use for the switch."""
        return "mdi:solar-power" if self.is_on else "mdi:solar-power-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on solar charging."""
        await self._pilot.set_solar_charging(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off solar charging."""
        await self._pilot.set_solar_charging(False)
