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

            # Use executor for async Modbus operations
            async def _async_write_register() -> bool:
                """Write register using async executor."""
                try:
                    _LOGGER.debug(
                        "Writing to address 49, value: %s, slave: 64", int(value)
                    )

                    # Call the write_register method
                    result = client.write_register(
                        address=49,  # Max charge power register
                        value=int(value),
                        slave=64,
                    )

                    # If it returns a coroutine, await it
                    import asyncio

                    if asyncio.iscoroutine(result):
                        _LOGGER.debug("write_register returned coroutine, awaiting")
                        result = await result
                    else:
                        _LOGGER.debug("write_register returned synchronous result")

                    _LOGGER.debug("Modbus write result: %s", result)

                    # Check if the write was successful
                    if hasattr(result, "isError") and result.isError():
                        _LOGGER.error(
                            "Failed to write max charge value: Modbus error: %s", result
                        )
                        return False
                    elif hasattr(result, "function_code"):
                        _LOGGER.debug("Successfully wrote max charge value: %s", value)
                        return True
                    else:
                        _LOGGER.error(
                            "Failed to write max charge value: Unexpected result format: %s",
                            type(result),
                        )
                        return False

                except Exception as exc:
                    _LOGGER.error("Exception in write_register: %s", exc, exc_info=True)
                    return False

            # Execute the write operation
            success = await _async_write_register()

            if success:
                self._attr_native_value = value
                self._last_written_value = value
                self.async_write_ha_state()

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

            # Use executor for async Modbus operations
            async def _async_write_register() -> bool:
                """Write register using async executor."""
                try:
                    _LOGGER.debug(
                        "Writing to address 50, value: %s, slave: 64", int(value)
                    )

                    # Call the write_register method
                    result = client.write_register(
                        address=50,  # Max discharge power register
                        value=int(value),
                        slave=64,
                    )

                    # If it returns a coroutine, await it
                    import asyncio

                    if asyncio.iscoroutine(result):
                        _LOGGER.debug("write_register returned coroutine, awaiting")
                        result = await result
                    else:
                        _LOGGER.debug("write_register returned synchronous result")

                    _LOGGER.debug("Modbus write result: %s", result)

                    # Check if the write was successful
                    if hasattr(result, "isError") and result.isError():
                        _LOGGER.error(
                            "Failed to write max discharge value: Modbus error: %s",
                            result,
                        )
                        return False
                    elif hasattr(result, "function_code"):
                        _LOGGER.debug(
                            "Successfully wrote max discharge value: %s", value
                        )
                        return True
                    else:
                        _LOGGER.error(
                            "Failed to write max discharge value: Unexpected result format: %s",
                            type(result),
                        )
                        return False

                except Exception as exc:
                    _LOGGER.error("Exception in write_register: %s", exc, exc_info=True)
                    return False

            # Execute the write operation
            success = await _async_write_register()

            if success:
                self._attr_native_value = value
                self._last_written_value = value
                self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error("Failed to write max discharge value: %s", err, exc_info=True)


class SAXBatteryPilotIntervalNumber(NumberEntity):
    """SAX Battery Pilot Interval number."""

    def __init__(self, coordinator: SAXBatteryCoordinator, entry: ConfigEntry) -> None:
        """Initialize the SAX Battery Pilot Interval number."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_pilot_interval"
        self._attr_name = "Pilot Interval"
        self._attr_native_min_value = 1
        self._attr_native_max_value = 60  # Max 60 minutes
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "min"
        self._attr_native_value = entry.options.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )
        self._attr_mode = NumberMode.SLIDER

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the pilot interval value."""
        await self._write_value(value)

    async def _write_value(self, value: float) -> None:
        """Write the pilot interval value to the coordinator."""
        _LOGGER.debug("Setting pilot interval to: %s", value)
        self._attr_native_value = value
        self.async_write_ha_state()

        # Update the coordinator's auto pilot interval
        self._coordinator.auto_pilot_interval = value

        # Optionally, you can also call a method on the coordinator to handle the update
        # await self._coordinator.update_pilot_interval(value)


class SAXBatteryMinSOCNumber(NumberEntity):
    """SAX Battery Minimum State of Charge (SoC) number."""

    def __init__(self, coordinator: SAXBatteryCoordinator, entry: ConfigEntry) -> None:
        """Initialize the SAX Battery Minimum SoC number."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_min_soc"
        self._attr_name = "Minimum State of Charge"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_value = entry.options.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self._attr_mode = NumberMode.SLIDER

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the minimum SoC value."""
        await self._write_value(value)

    async def _write_value(self, value: float) -> None:
        """Write the minimum SoC value to the coordinator."""
        _LOGGER.debug("Setting minimum SoC to: %s", value)
        self._attr_native_value = value
        self.async_write_ha_state()

        # Update the coordinator's min SoC
        self._coordinator.min_soc = value

        # Optionally, you can also call a method on the coordinator to handle the update
        # await self._coordinator.update_min_soc(value)


class SAXBatteryManualPowerEntity(NumberEntity):
    """SAX Battery Manual Power Control number."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the SAX Battery Manual Power Control number."""
        self._coordinator = coordinator
        # Match the unique ID from pilot.py
        self._attr_unique_id = f"{DOMAIN}_pilot_power_{coordinator.device_id}"
        self._attr_name = "Manual Power Control"
        self._attr_native_min_value = (
            -coordinator.batteries.__len__() * 3600
        )  # Max discharge
        self._attr_native_max_value = (
            coordinator.batteries.__len__() * 4500
        )  # Max charge
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = 0.0  # Start at 0
        self._attr_mode = NumberMode.BOX

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def native_value(self) -> float | None:
        """Return the current manual power setting."""
        # Get the value from the pilot if available
        sax_data = self.hass.data[DOMAIN][self._coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            return (
                float(sax_data.pilot.calculated_power)
                if sax_data.pilot.calculated_power is not None
                else 0.0
            )
        return self._attr_native_value

    @property
    def icon(self) -> str | None:
        """Return the icon to use for the entity."""
        current_value = self.native_value or 0
        if current_value > 0:
            return "mdi:battery-charging"
        elif current_value < 0:
            return "mdi:battery-minus"
        return "mdi:battery"

    async def async_set_native_value(self, value: float) -> None:
        """Update the manual power value."""
        _LOGGER.debug("Setting manual power to %sW", value)

        # Update the stored value
        self._attr_native_value = value

        # Get the pilot instance and update its calculated power
        sax_data = self.hass.data[DOMAIN][self._coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            await sax_data.pilot.set_manual_power(value)
        else:
            _LOGGER.warning("Pilot not available to set manual power")
