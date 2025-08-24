"""Number platform for SAX Battery integration."""

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_LIMIT_POWER,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_PILOT_FROM_HA,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DOMAIN,
)
from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the SAX Battery number entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Add power limiting entities if limit_power is enabled
    if entry.data.get(CONF_LIMIT_POWER, False):
        entities.extend(
            [
                SAXBatteryMaxChargeNumber(coordinator),
                SAXBatteryMaxDischargeNumber(coordinator),
            ]
        )

    # Add pilot-related number entities if pilot_from_ha is enabled
    if entry.data.get(CONF_PILOT_FROM_HA, False):
        entities.extend(
            [
                SAXBatteryPilotIntervalNumber(coordinator, entry),
                SAXBatteryMinSOCNumber(coordinator, entry),
                SAXBatteryManualPowerEntity(coordinator),  # Add this line
            ]
        )

    async_add_entities(entities)


class SAXBatteryMaxChargeNumber(NumberEntity):
    """SAX Battery Maximum Charge Power number."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the SAX Battery Maximum Charge Power number."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_max_charge_power"
        self._attr_name = "Maximum Charge Power"
        self._attr_native_min_value = 0

        # Calculate dynamic max value based on battery count
        battery_count = len(coordinator.batteries)
        self._attr_native_max_value = battery_count * 3500  # 3.5kW per battery
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = self._attr_native_max_value  # Start at max
        self._attr_mode = NumberMode.SLIDER
        self._last_written_value = self._attr_native_max_value

        # Set up periodic writes
        self._track_time_remove: Callable[[], None] | None = None

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_added_to_hass(self) -> None:
        """Set up periodic writes."""
        self._track_time_remove = async_track_time_interval(
            self.hass, self._periodic_write, timedelta(minutes=1)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._track_time_remove:
            self._track_time_remove()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._write_value(value)

    async def _periodic_write(self, _: Any) -> None:
        """Write the value periodically."""
        if self._attr_native_value is not None:
            if (
                self._attr_native_value == self._attr_native_max_value
                and self._last_written_value == self._attr_native_max_value
            ):
                # Skip periodic writes for max value
                return
            await self._write_value(self._attr_native_value)

    async def _write_value(self, value: float) -> None:
        """Write the value to the hardware."""
        _LOGGER.debug("Attempting to write max charge value: %s", value)

        try:
            # Get the modbus client from the master battery's data manager
            master_battery = self._coordinator.master_battery
            if not master_battery:
                _LOGGER.error("Master battery not available")
                return

            if not hasattr(master_battery, "_data_manager"):
                _LOGGER.error("Master battery data manager not available")
                return

            _LOGGER.debug("Master battery ID: %s", master_battery.battery_id)
            _LOGGER.debug(
                "Available modbus clients: %s",
                list(master_battery._data_manager.modbus_clients.keys()),
            )

            client = master_battery._data_manager.modbus_clients.get(
                master_battery.battery_id
            )

            if client is None:
                _LOGGER.error(
                    "No Modbus client found for battery %s", master_battery.battery_id
                )
                return

            _LOGGER.debug(
                "Modbus client found, connected: %s",
                getattr(client, "connected", "unknown"),
            )

            # Use executor job for synchronous modbus call
            def _write_register() -> tuple[bool, str | None]:
                """Write register synchronously."""
                try:
                    _LOGGER.debug(
                        "Writing to address 49, value: %s, slave: 64", int(value)
                    )
                    result = client.write_register(
                        address=49,  # Max charge power register
                        value=int(value),
                        slave=64,
                    )

                    _LOGGER.debug("Modbus write result: %s", result)

                    if hasattr(result, "isError") and result.isError():
                        return False, f"Modbus error: {result}"
                    elif hasattr(result, "function_code"):
                        return True, None
                    else:
                        return False, f"Unexpected result format: {type(result)}"

                except Exception as exc:
                    _LOGGER.debug("Exception in write_register: %s", exc, exc_info=True)
                    return False, f"Write exception: {exc}"

            success, error_msg = await self.hass.async_add_executor_job(_write_register)

            if success:
                self._attr_native_value = value
                self._last_written_value = value
                self.async_write_ha_state()
                _LOGGER.debug("Successfully wrote max charge value: %s", value)
            else:
                _LOGGER.error("Failed to write max charge value: %s", error_msg)

        except Exception as err:
            _LOGGER.error("Failed to write max charge value: %s", err, exc_info=True)


class SAXBatteryMaxDischargeNumber(NumberEntity):
    """SAX Battery Maximum Discharge Power number."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the SAX Battery Maximum Discharge Power number."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_max_discharge_power"
        self._attr_name = "Maximum Discharge Power"
        self._attr_native_min_value = 0

        # Calculate dynamic max value based on battery count
        battery_count = len(coordinator.batteries)
        self._attr_native_max_value = battery_count * 4600  # 4.6kW per battery
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = self._attr_native_max_value  # Start at max
        self._attr_mode = NumberMode.SLIDER
        self._last_written_value = self._attr_native_max_value

        # Set up periodic writes
        self._track_time_remove: Callable[[], None] | None = None

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_added_to_hass(self) -> None:
        """Set up periodic writes."""
        self._track_time_remove = async_track_time_interval(
            self.hass, self._periodic_write, timedelta(minutes=1)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._track_time_remove:
            self._track_time_remove()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._write_value(value)

    async def _periodic_write(self, _: Any) -> None:
        """Write the value periodically."""
        if self._attr_native_value is not None:
            if (
                self._attr_native_value == self._attr_native_max_value
                and self._last_written_value == self._attr_native_max_value
            ):
                # Skip periodic writes for max value
                return
            await self._write_value(self._attr_native_value)

    async def _write_value(self, value: float) -> None:
        """Write the value to the hardware."""
        _LOGGER.debug("Attempting to write max discharge value: %s", value)

        try:
            # Get the modbus client from the master battery's data manager
            master_battery = self._coordinator.master_battery
            if not master_battery:
                _LOGGER.error("Master battery not available")
                return

            if not hasattr(master_battery, "_data_manager"):
                _LOGGER.error("Master battery data manager not available")
                return

            _LOGGER.debug("Master battery ID: %s", master_battery.battery_id)
            _LOGGER.debug(
                "Available modbus clients: %s",
                list(master_battery._data_manager.modbus_clients.keys()),
            )

            client = master_battery._data_manager.modbus_clients.get(
                master_battery.battery_id
            )

            if client is None:
                _LOGGER.error(
                    "No Modbus client found for battery %s", master_battery.battery_id
                )
                return

            _LOGGER.debug(
                "Modbus client found, connected: %s",
                getattr(client, "connected", "unknown"),
            )

            # Use executor job for synchronous modbus call
            def _write_register() -> tuple[bool, str | None]:
                """Write register synchronously."""
                try:
                    _LOGGER.debug(
                        "Writing to address 50, value: %s, slave: 64", int(value)
                    )
                    result = client.write_register(
                        address=50,  # Max discharge power register
                        value=int(value),
                        slave=64,
                    )

                    _LOGGER.debug("Modbus write result: %s", result)

                    if hasattr(result, "isError") and result.isError():
                        return False, f"Modbus error: {result}"
                    elif hasattr(result, "function_code"):
                        return True, None
                    else:
                        return False, f"Unexpected result format: {type(result)}"

                except Exception as exc:
                    _LOGGER.debug("Exception in write_register: %s", exc, exc_info=True)
                    return False, f"Write exception: {exc}"

            success, error_msg = await self.hass.async_add_executor_job(_write_register)

            if success:
                self._attr_native_value = value
                self._last_written_value = value
                self.async_write_ha_state()
                _LOGGER.debug("Successfully wrote max discharge value: %s", value)
            else:
                _LOGGER.error("Failed to write max discharge value: %s", error_msg)

        except Exception as err:
            _LOGGER.error("Failed to write max discharge value: %s", err, exc_info=True)


class SAXBatteryPilotIntervalNumber(NumberEntity):
    """SAX Battery Auto Pilot Interval number."""

    def __init__(self, coordinator: SAXBatteryCoordinator, entry: ConfigEntry) -> None:
        """Initialize the SAX Battery Auto Pilot Interval number."""
        self._coordinator = coordinator
        self._data_manager = coordinator  # For compatibility
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_pilot_interval"
        self._attr_name = "Auto Pilot Interval"
        self._attr_native_min_value = 5
        self._attr_native_max_value = 300
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = "seconds"
        self._attr_native_value = self._entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )
        self._attr_mode = NumberMode.SLIDER

        # Add device info - pilot interval entity uses coordinator device_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the interval."""
        self._attr_native_value = value

        # Update pilot interval if available
        if hasattr(self._coordinator, "_pilot") and self._coordinator._pilot:
            await self._coordinator._pilot.set_interval(value)
        else:
            _LOGGER.warning("Pilot not available for interval update")

        self.async_write_ha_state()
        _LOGGER.debug("Pilot interval set to %s seconds", value)


class SAXBatteryMinSOCNumber(NumberEntity):
    """SAX Battery Minimum State of Charge number."""

    def __init__(self, coordinator: SAXBatteryCoordinator, entry: ConfigEntry) -> None:
        """Initialize the SAX Battery Minimum State of Charge number."""
        self._coordinator = coordinator
        self._data_manager = coordinator  # For compatibility
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_min_soc"
        self._attr_name = "Minimum State of Charge"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_value = self._entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self._attr_mode = NumberMode.SLIDER

        # Add device info - min SOC entity uses coordinator device_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the minimum SOC."""
        self._attr_native_value = value

        # Update pilot minimum SOC if available
        if hasattr(self._coordinator, "_pilot") and self._coordinator._pilot:
            await self._coordinator._pilot.set_min_soc(value)
        else:
            _LOGGER.warning("Pilot not available for min SOC update")

        self.async_write_ha_state()
        _LOGGER.debug("Minimum SOC set to %s%%", value)


class SAXBatteryManualPowerEntity(NumberEntity):
    """Entity for setting manual power value."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_battery_manual_power"
        self._attr_name = "SAX Battery Manual Power"

        battery_count = len(coordinator.batteries)
        max_charge_power = battery_count * 3500  # 3.5kW per battery for charge
        max_discharge_power = battery_count * 4600  # 4.6kW per battery for discharge

        self._attr_native_min_value = -max_discharge_power  # max discharge power
        self._attr_native_max_value = max_charge_power  # max charge power
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = 0.0
        self._attr_mode = NumberMode.SLIDER
        self._attr_icon = "mdi:battery"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    def _update_icon(self) -> None:
        """Update the icon based on current value."""
        if self._attr_native_value and self._attr_native_value > 0:
            self._attr_icon = "mdi:battery-charging"
        elif self._attr_native_value and self._attr_native_value < 0:
            self._attr_icon = "mdi:battery-minus"
        else:
            self._attr_icon = "mdi:battery"

    async def async_set_native_value(self, value: float) -> None:
        """Set the manual power value."""
        self._attr_native_value = value
        self._update_icon()

        # Get the pilot instance
        sax_data = self.hass.data[DOMAIN][self._coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            _LOGGER.debug("Manual power changed to %sW, updating pilot", value)

            # Set the calculated_power in the pilot FIRST
            sax_data.pilot.calculated_power = value

            # If manual control is enabled, send the command immediately
            if self._coordinator.config_entry.data.get(CONF_MANUAL_CONTROL, False):
                # Apply SOC constraints and send to battery
                constrained_value = await sax_data.pilot._apply_soc_constraints(value)
                await sax_data.pilot.send_power_command(constrained_value, 1.0)

                if constrained_value != value:
                    _LOGGER.info(
                        "Manual power requested: %sW, actually sent: %sW (constrained by SOC)",
                        value,
                        constrained_value,
                    )
                else:
                    _LOGGER.debug(
                        "Manual power sent to battery: %sW", constrained_value
                    )
            else:
                _LOGGER.debug(
                    "Manual power stored: %sW (manual mode not active)", value
                )
        else:
            _LOGGER.warning("Pilot not available for manual power update")

        self.async_write_ha_state()
        _LOGGER.debug("Manual power set to %sW", value)
