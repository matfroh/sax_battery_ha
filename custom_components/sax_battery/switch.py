"""Switch platform for SAX Battery integration."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    CONF_PILOT_FROM_HA,
    DEFAULT_DEVICE_INFO,
    DOMAIN,
    SAX_STATUS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the SAX Battery switches."""
    sax_battery_data = hass.data[DOMAIN][entry.entry_id]
    entities = []

    # Add pilot-related switches only if pilot control is enabled
    if entry.data.get(CONF_PILOT_FROM_HA, False):
        # Create both switches
        solar_charging_switch = SAXBatterySolarChargingSwitch(sax_battery_data, entry)
        manual_control_switch = SAXBatteryManualControlSwitch(sax_battery_data, entry)

        # Set references to each other
        solar_charging_switch.set_other_switch(manual_control_switch)
        manual_control_switch.set_other_switch(solar_charging_switch)

        entities.extend([solar_charging_switch, manual_control_switch])

    # Add on/off switches for each battery
    entities.extend(
        SAXBatteryOnOffSwitch(sax_battery_data, battery_id)
        for battery_id in sax_battery_data.batteries
    )

    async_add_entities(entities)


class SAXBatteryOnOffSwitch(SwitchEntity):
    """SAX Battery On/Off switch."""

    def __init__(self, sax_data: Any, battery_id: str) -> None:
        """Initialize the switch."""
        self._sax_data = sax_data
        self._battery_id = battery_id
        self._attr_unique_id = f"{DOMAIN}_{battery_id}_switch"
        self._attr_name = f"SAX {battery_id.replace('_', ' ').title()} On/Off"

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

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        if not self._sax_data.coordinator.data:
            return None

        battery_data = self._sax_data.coordinator.data.get(self._battery_id, {})
        status_data = battery_data.get(SAX_STATUS)

        if status_data is None:
            return None

        # Example: assuming status value indicates on/off state
        return bool(status_data.get("is_charging", False))  # Adjust this logic

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            # Use modbus API from the SAX data model
            if self._sax_data.modbus_api:
                battery_config = self._sax_data.battery_configs.get(self._battery_id)
                if battery_config:
                    await self._sax_data.modbus_api.write_battery_switch(
                        battery_config, True
                    )

            # Update coordinator data
            await self._sax_data.coordinator.async_request_refresh()

        except (ConnectionError, ValueError) as err:
            _LOGGER.error("Failed to turn on battery %s: %s", self._battery_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            # Use modbus API from the SAX data model
            if self._sax_data.modbus_api:
                battery_config = self._sax_data.battery_configs.get(self._battery_id)
                if battery_config:
                    await self._sax_data.modbus_api.write_battery_switch(
                        battery_config, False
                    )

            # Update coordinator data
            await self._sax_data.coordinator.async_request_refresh()

        except (ConnectionError, ValueError) as err:
            _LOGGER.error("Failed to turn off battery %s: %s", self._battery_id, err)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self._sax_data.coordinator.data is not None
            and self._battery_id in self._sax_data.coordinator.data
        )


class SAXBatterySolarChargingSwitch(SwitchEntity):
    """Switch to control solar charging for SAX Battery."""

    def __init__(self, sax_data: Any, entry: Any) -> None:
        """Initialize the switch."""
        self._sax_data = sax_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_solar_charging"
        self._attr_name = "Solar Charging"
        self._attr_is_on = entry.data.get(CONF_ENABLE_SOLAR_CHARGING, True)
        self._other_switch: SwitchEntity | None = (
            None  # Reference to the manual control switch
        )

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

    def set_other_switch(self, other_switch: Any) -> None:
        """Set reference to the other switch (manual control)."""
        self._other_switch = other_switch

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on solar charging."""
        try:
            # Turn off manual control if it's on
            if self._other_switch is not None and self._other_switch.is_on is True:
                await self._other_switch.async_turn_off()

            # Call the pilot's set_solar_charging method
            await self._sax_data.pilot.set_solar_charging(True)

            self._attr_is_on = True
            self.async_write_ha_state()

            # Update configuration entry data
            data = dict(self._entry.data)
            data[CONF_ENABLE_SOLAR_CHARGING] = True
            self.hass.config_entries.async_update_entry(self._entry, data=data)

        except (ConnectionError, ValueError) as err:
            _LOGGER.error("Failed to enable solar charging: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off solar charging."""
        try:
            # Call the pilot's set_solar_charging method
            await self._sax_data.pilot.set_solar_charging(False)

            self._attr_is_on = False
            self.async_write_ha_state()

            # Update configuration entry data
            data = dict(self._entry.data)
            data[CONF_ENABLE_SOLAR_CHARGING] = False
            self.hass.config_entries.async_update_entry(self._entry, data=data)

        except (ConnectionError, ValueError) as err:
            _LOGGER.error("Failed to disable solar charging: %s", err)


class SAXBatteryManualControlSwitch(SwitchEntity):
    """Switch to enable/disable manual control for SAX Battery."""

    def __init__(self, sax_data: Any, entry: Any) -> None:
        """Initialize the switch."""
        self._sax_data = sax_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_manual_control"
        self._attr_name = "Manual Control"
        self._attr_is_on = False  # Default to off
        self._other_switch: SwitchEntity | None = (
            None  # Reference to the solar charging switch
        )

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

    def set_other_switch(self, other_switch: Any) -> None:
        """Set reference to the other switch (solar charging)."""
        self._other_switch = other_switch

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on manual control."""
        try:
            # Turn off solar charging switch if it's on
            if self._other_switch is not None and self._other_switch.is_on is True:
                await self._other_switch.async_turn_off()
            elif hasattr(self._sax_data, "pilot"):
                # Directly turn off solar charging if the switch isn't available
                await self._sax_data.pilot.set_solar_charging(False)

            self._attr_is_on = True
            self.async_write_ha_state()

            # Update configuration entry data
            data = dict(self._entry.data)
            data[CONF_MANUAL_CONTROL] = True
            self.hass.config_entries.async_update_entry(self._entry, data=data)

        except (ConnectionError, ValueError) as err:
            _LOGGER.error("Failed to enable manual control: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off manual control."""
        try:
            # Turn on solar charging when manual control is disabled
            if hasattr(self._sax_data, "pilot"):
                await self._sax_data.pilot.set_solar_charging(True)

            self._attr_is_on = False
            self.async_write_ha_state()

            # Update configuration entry data
            data = dict(self._entry.data)
            data[CONF_MANUAL_CONTROL] = False
            self.hass.config_entries.async_update_entry(self._entry, data=data)

        except (ConnectionError, ValueError) as err:
            _LOGGER.error("Failed to disable manual control: %s", err)
