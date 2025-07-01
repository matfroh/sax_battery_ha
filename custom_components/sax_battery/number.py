"""Number platform for SAX Battery integration."""

import asyncio
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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the SAX Battery number entities."""
    sax_battery_data = hass.data[DOMAIN][entry.entry_id]
    battery_count = len(sax_battery_data.batteries)

    entities = []

    # Add power limiting entities if limit_power is enabled
    if entry.data.get(CONF_LIMIT_POWER, False):
        entities.extend(
            [
                SAXBatteryMaxChargeNumber(sax_battery_data, battery_count * 3500),
                SAXBatteryMaxDischargeNumber(sax_battery_data, battery_count * 4600),
            ]
        )

    # Add pilot-related number entities if pilot_from_ha is enabled
    if entry.data.get(CONF_PILOT_FROM_HA, False):
        entities.extend(
            [
                SAXBatteryMinSOCNumber(sax_battery_data, entry),
                SAXBatteryPilotIntervalNumber(sax_battery_data, entry),
                SAXBatteryManualPowerEntity(sax_battery_data),
            ]
        )

    async_add_entities(entities)


class SAXBatteryMaxChargeNumber(NumberEntity):
    """SAX Battery Maximum Charge Power number."""

    def __init__(self, sax_battery_data: Any, max_value: float) -> None:
        """Initialize the SAX Battery Maximum Charge Power number.

        Args:
            sax_battery_data: The data manager for SAX Battery.
            max_value: The maximum charge power value.

        """
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_max_charge"
        self._attr_name = "Maximum Charge Power"
        self._attr_native_min_value = 0
        self._attr_native_max_value = max_value
        self._attr_native_step = 50
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = max_value
        self._last_written_value: float | None = None  # Track the last written value
        self._remove_interval: Any = None  # Initialize the attribute

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_added_to_hass(self) -> None:
        """Set up periodic updates."""
        self._remove_interval = async_track_time_interval(
            self.hass, self._periodic_write, timedelta(minutes=2)
        )

    async def async_will_remove_from_hass(self):
        """Clean up on removal."""
        if hasattr(self, "_remove_interval"):
            self._remove_interval()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        if value == self._attr_native_max_value and self._last_written_value == value:
            # Skip if value is at max and already set
            return

        await self._write_value(value)

    async def _periodic_write(self, _):
        """Write the value periodically."""
        if self._attr_native_value is not None:
            if (
                self._attr_native_value == self._attr_native_max_value
                and self._last_written_value == self._attr_native_max_value
            ):
                # Skip periodic writes for max value
                return
            await self._write_value(self._attr_native_value)

    async def _write_value(self, value: float):
        """Write the value to the hardware."""
        try:
            client = self._data_manager.master_battery._data_manager.modbus_clients[  # noqa: SLF001
                self._data_manager.master_battery.battery_id
            ]

            # Get the battery count
            battery_count = len(self._data_manager.batteries)
            # Calculate the per-battery value
            per_battery_value = int(value / battery_count)

            import asyncio

            # Add a small delay before writing
            await asyncio.sleep(0.1)

            _LOGGER.debug("Setting maximum charge power to %sW", int(value))

            # Use write_registers with the slave parameter as a keyword argument
            result = await self._data_manager.hass.async_add_executor_job(
                lambda: client.write_registers(
                    44,  # Register for max charge
                    [per_battery_value],  # Pass value as a list
                    slave=64,
                )
            )

            _LOGGER.debug("Waiting for device to process the command...")  # pylint: disable=hass-logger-period
            # Add a longer delay for the device to process the command
            await asyncio.sleep(10)
            _LOGGER.debug("Resuming after wait period")

            self._attr_native_value = value
            self._last_written_value = value  # Update last written value

        except (ConnectionError, TimeoutError) as err:
            _LOGGER.error("Failed to write max charge value: %s", err)


class SAXBatteryMaxDischargeNumber(NumberEntity):
    """SAX Battery Maximum Discharge Power number."""

    def __init__(self, sax_battery_data, max_value) -> None:
        """Initialize the SAX Battery Maximum Discharge Power number."""
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_max_discharge"
        self._attr_name = "Maximum Discharge Power"
        self._attr_native_min_value = 0
        self._attr_native_max_value = max_value
        self._attr_native_step = 50
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = max_value
        self._last_written_value: float | None = None  # Track the last written value

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_added_to_hass(self) -> None:
        """Set up periodic updates."""
        self._remove_interval = async_track_time_interval(
            self.hass, self._periodic_write, timedelta(minutes=2)
        )

    async def async_will_remove_from_hass(self):
        """Clean up on removal."""
        if hasattr(self, "_remove_interval"):
            self._remove_interval()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        if value == self._attr_native_max_value and self._last_written_value == value:
            # Skip if value is at max and already set
            return

        await self._write_value(value)

    async def _periodic_write(self, _):
        """Write the value periodically."""
        if self._attr_native_value is not None:
            if (
                self._attr_native_value == self._attr_native_max_value
                and self._last_written_value == self._attr_native_max_value
            ):
                # Skip periodic writes for max value
                return
            await self._write_value(self._attr_native_value)

    async def _write_value(self, value: float):
        """Write the value to the hardware."""
        try:
            client = self._data_manager.master_battery._data_manager.modbus_clients[  # noqa: SLF001
                self._data_manager.master_battery.battery_id
            ]

            # Get the battery count
            battery_count = len(self._data_manager.batteries)
            # Calculate the per-battery value
            per_battery_value = int(value / battery_count)

            import asyncio  # pylint: disable=import-outside-toplevel

            # Add a small delay before writing
            await asyncio.sleep(0.1)

            _LOGGER.debug("Setting maximum charge power to %sW", int(value))

            # Use write_registers with the slave parameter as a keyword argument
            result = await self._data_manager.hass.async_add_executor_job(
                lambda: client.write_registers(
                    43,  # Register for max discharge
                    [per_battery_value],  # Pass value as a list
                    slave=64,
                )
            )

            _LOGGER.debug("Waiting for device to process the command...")  # pylint: disable=hass-logger-period
            # Add a longer delay for the device to process the command
            await asyncio.sleep(10)
            _LOGGER.debug("Resuming after wait period")

            self._attr_native_value = value
            self._last_written_value = value  # Update last written value

        except (ConnectionError, TimeoutError) as err:
            _LOGGER.error("Failed to write max charge value: %s", err)


class SAXBatteryPilotIntervalNumber(NumberEntity):
    """SAX Battery Auto Pilot Interval number."""

    def __init__(self, sax_battery_data, entry) -> None:
        """Initialize the SAX Battery Auto Pilot Interval number."""
        self._data_manager = sax_battery_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_pilot_interval"
        self._attr_name = "Auto Pilot Interval"
        self._attr_native_min_value = 5
        self._attr_native_max_value = 300
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = "s"  # seconds
        self._attr_native_value = entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        # No need to send to hardware since this is just a configuration value
        # for the Home Assistant integration itself
        self._attr_native_value = value

        # Update configuration entry data
        data = dict(self._entry.data)
        data[CONF_AUTO_PILOT_INTERVAL] = int(value)
        self.hass.config_entries.async_update_entry(self._entry, data=data)


class SAXBatteryMinSOCNumber(NumberEntity):
    """SAX Battery Minimum State of Charge number."""

    def __init__(self, sax_battery_data, entry) -> None:
        """Initialize the SAX Battery Minimum State of Charge number."""
        self._data_manager = sax_battery_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_min_soc"
        self._attr_name = "Minimum State of Charge"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_value = entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self._last_written_value = None

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        # No need to send to hardware since this is just a configuration value
        # for the Home Assistant integration itself
        self._attr_native_value = value

        # Update configuration entry data
        data = dict(self._entry.data)
        data[CONF_MIN_SOC] = int(value)
        self.hass.config_entries.async_update_entry(self._entry, data=data)


class SAXBatteryManualPowerEntity(NumberEntity):
    """Entity for setting manual power value."""

    def __init__(self, sax_battery_data) -> None:
        """Initialize the entity."""
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_manual_power_{self._data_manager.device_id}"
        self._attr_name = "Battery Manual Power"

        battery_count = len(self._data_manager.batteries)
        max_discharge_power = battery_count * 3600
        max_charge_power = battery_count * 4500

        self._attr_native_min_value = -max_discharge_power  # max discharge power
        self._attr_native_max_value = max_charge_power  # max charge power
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = 0  # Use _attr_native_value instead of _value
        self._attr_mode = "slider"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def icon(self):
        """Return the icon to use for the entity."""
        if self._attr_native_value > 0:
            return "mdi:battery-charging"
        if self._attr_native_value < 0:
            return "mdi:battery-minus"
        return "mdi:battery"

    @property
    def available(self):
        """Return true if the entity is available."""
        return self._data_manager.entry.data.get(CONF_MANUAL_CONTROL, False)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        # You might need to add a callback/update mechanism here

    async def async_set_native_value(self, value: float) -> None:
        """Set the manual power value."""
        self._attr_native_value = value
        if hasattr(self._data_manager, "pilot"):
            await self._data_manager.pilot.set_manual_power(value)
        self.async_write_ha_state()
