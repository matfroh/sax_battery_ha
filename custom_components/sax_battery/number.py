"""Number platform for SAX Battery integration."""

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_LIMIT_POWER,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_PILOT_FROM_HA,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_DEVICE_INFO,
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
                SAXBatteryPilotIntervalNumber(sax_battery_data, entry),
                SAXBatteryMinSOCNumber(sax_battery_data, entry),
            ]
        )

    # Add manual control entity if manual_control is enabled
    if entry.data.get(CONF_MANUAL_CONTROL, False):
        entities.append(SAXBatteryManualPowerEntity(sax_battery_data))

    async_add_entities(entities)


class SAXBatteryMaxChargeNumber(NumberEntity):
    """SAX Battery Maximum Charge Power number."""

    def __init__(self, sax_data: Any, max_value: float) -> None:
        """Initialize the SAX Battery Maximum Charge Power number.

        Args:
            sax_data: The SAX Battery data structure.
            max_value: The maximum charge power value.

        """
        self._sax_data = sax_data
        self._attr_unique_id = f"{DOMAIN}_max_charge_power"
        self._attr_name = "Maximum Charge Power"
        self._attr_native_min_value = 0
        self._attr_native_max_value = max_value
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = max_value
        self._attr_mode = NumberMode.SLIDER
        self._last_written_value = max_value

        # Set up periodic writes
        self._write_task = None
        self._track_time_remove: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._sax_data.device_id or "unknown")},
            name=DEFAULT_DEVICE_INFO.name,
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )

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
        if value == self._attr_native_max_value and self._last_written_value == value:
            # Skip if value is at max and already set
            return

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
        try:
            # Use modbus API from the SAX data model
            if self._sax_data.modbus_api:
                success = await self._sax_data.modbus_api.write_max_charge_power(
                    int(value)
                )
                if success:
                    self._attr_native_value = value
                    self._last_written_value = value
                    self.async_write_ha_state()
                    _LOGGER.debug("Successfully wrote max charge value: %s", value)
                else:
                    _LOGGER.error("Failed to write max charge value")

        except (ConnectionError, TimeoutError, ValueError) as err:
            _LOGGER.error("Failed to write max charge value: %s", err)


class SAXBatteryMaxDischargeNumber(NumberEntity):
    """SAX Battery Maximum Discharge Power number."""

    def __init__(self, sax_data: Any, max_value: float) -> None:
        """Initialize the SAX Battery Maximum Discharge Power number.

        Args:
            sax_data: The SAX Battery data structure.
            max_value: The maximum discharge power value.

        """
        self._sax_data = sax_data
        self._attr_unique_id = f"{DOMAIN}_max_discharge_power"
        self._attr_name = "Maximum Discharge Power"
        self._attr_native_min_value = 0
        self._attr_native_max_value = max_value
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = max_value
        self._attr_mode = NumberMode.SLIDER
        self._last_written_value = max_value

        # Set up periodic writes
        self._write_task = None
        self._track_time_remove: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._sax_data.device_id or "unknown")},
            name=DEFAULT_DEVICE_INFO.name,
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )

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
        if value == self._attr_native_max_value and self._last_written_value == value:
            # Skip if value is at max and already set
            return

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
        try:
            # Use modbus API from the SAX data model
            if self._sax_data.modbus_api:
                success = await self._sax_data.modbus_api.write_max_discharge_power(
                    int(value)
                )
                if success:
                    self._attr_native_value = value
                    self._last_written_value = value
                    self.async_write_ha_state()
                    _LOGGER.debug("Successfully wrote max discharge value: %s", value)
                else:
                    _LOGGER.error("Failed to write max discharge value")

        except (ConnectionError, TimeoutError) as err:
            _LOGGER.error("Failed to write max discharge value: %s", err)


class SAXBatteryPilotIntervalNumber(NumberEntity):
    """SAX Battery Auto Pilot Interval number."""

    def __init__(self, sax_data: Any, entry: ConfigEntry) -> None:
        """Initialize the SAX Battery Auto Pilot Interval number."""
        self._sax_data = sax_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_pilot_interval"
        self._attr_name = "Pilot Interval"
        self._attr_native_min_value = 10
        self._attr_native_max_value = 300
        self._attr_native_step = 10
        self._attr_native_unit_of_measurement = "seconds"
        self._attr_native_value = self._entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )
        self._attr_mode = NumberMode.SLIDER

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._sax_data.device_id or "unknown")},
            name=DEFAULT_DEVICE_INFO.name,
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update the interval."""
        self._attr_native_value = value

        # Update config entry data
        data = dict(self._entry.data)
        data[CONF_AUTO_PILOT_INTERVAL] = int(value)
        self.hass.config_entries.async_update_entry(self._entry, data=data)

        # Update pilot interval if available
        if hasattr(self._sax_data, "pilot"):
            await self._sax_data.pilot.set_interval(value)
        self.async_write_ha_state()


class SAXBatteryMinSOCNumber(NumberEntity):
    """SAX Battery Minimum State of Charge number."""

    def __init__(self, sax_data: Any, entry: ConfigEntry) -> None:
        """Initialize the SAX Battery Minimum State of Charge number."""
        self._sax_data = sax_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_min_soc"
        self._attr_name = "Minimum State of Charge"
        self._attr_native_min_value = 5
        self._attr_native_max_value = 95
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_value = self._entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self._attr_mode = NumberMode.SLIDER

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._sax_data.device_id or "unknown")},
            name=DEFAULT_DEVICE_INFO.name,
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update the minimum SOC."""
        self._attr_native_value = value

        # Update config entry data
        data = dict(self._entry.data)
        data[CONF_MIN_SOC] = int(value)
        self.hass.config_entries.async_update_entry(self._entry, data=data)

        # Update pilot minimum SOC if available
        if hasattr(self._sax_data, "pilot"):
            await self._sax_data.pilot.set_min_soc(value)
        self.async_write_ha_state()


class SAXBatteryManualPowerEntity(NumberEntity):
    """Entity for setting manual power value."""

    def __init__(self, sax_data: Any) -> None:
        """Initialize the entity."""
        self._sax_data = sax_data
        self._attr_unique_id = f"{DOMAIN}_manual_power"
        self._attr_name = "Manual Power"

        battery_count = len(self._sax_data.batteries)
        max_charge_power = battery_count * 3500  # 3.5kW per battery for charge
        max_discharge_power = battery_count * 4600  # 4.6kW per battery for discharge

        self._attr_native_min_value = -max_discharge_power  # max discharge power
        self._attr_native_max_value = max_charge_power  # max charge power
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_value = 0  # Use _attr_native_value instead of _value
        self._attr_mode = NumberMode.SLIDER
        self._attr_icon = "mdi:battery"
        self._attr_available = self._sax_data.entry.data.get(CONF_MANUAL_CONTROL, False)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._sax_data.device_id or "unknown")},
            name=DEFAULT_DEVICE_INFO.name,
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        # Update icon based on value
        self._update_icon()

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
        if hasattr(self._sax_data, "pilot"):
            await self._sax_data.pilot.set_manual_power(value)
        self.async_write_ha_state()
