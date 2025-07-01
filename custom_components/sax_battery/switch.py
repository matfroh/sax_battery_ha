"""Switch platform for SAX Battery integration."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    CONF_PILOT_FROM_HA,
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
    #    if entry.data.get(CONF_PILOT_FROM_HA, False):
    #        entities.append(SAXBatterySolarChargingSwitch(sax_battery_data, entry))
    #        entities.append(SAXBatteryManualControlSwitch(sax_battery_data, entry))

    if entry.data.get(CONF_PILOT_FROM_HA, False):
        # Create both switches
        solar_charging_switch = SAXBatterySolarChargingSwitch(sax_battery_data, entry)
        manual_control_switch = SAXBatteryManualControlSwitch(sax_battery_data, entry)

        # Set references to each other
        solar_charging_switch.set_other_switch(manual_control_switch)
        manual_control_switch.set_other_switch(solar_charging_switch)

        entities.extend([solar_charging_switch, manual_control_switch])

    for battery in sax_battery_data.batteries.values():
        entities.append(SAXBatteryOnOffSwitch(battery))

    async_add_entities(entities)


class SAXBatteryOnOffSwitch(SwitchEntity):
    """SAX Battery On/Off switch."""

    def __init__(self, battery: Any) -> None:
        """Initialize the switch."""
        self.battery = battery
        self._attr_unique_id = f"{DOMAIN}_{battery.battery_id}_switch"
        self._attr_name = f"Sax {battery.battery_id.replace('_', ' ').title()} On/Off"
#        self._attr_has_entity_name = True
        self._registers = self.battery._data_manager.modbus_registers[  # noqa: SLF001
            battery.battery_id
        ][SAX_STATUS]

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.battery._data_manager.device_id)},  # noqa: SLF001
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        status = self.battery.data.get(SAX_STATUS)
        return status == self._registers["state_on"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            client = self.battery._data_manager.modbus_clients[self.battery.battery_id]  # noqa: SLF001
            slave_id = self._registers.get("slave", 64)

            import asyncio

            await asyncio.sleep(0.1)

            _LOGGER.debug(
                "Turning ON battery %s - Writing %s to register %s",
                self.battery.battery_id,
                self._registers["command_on"],
                self._registers["address"],
            )

            # Use write_registers (plural) instead of write_register
            result = await self.battery.hass.async_add_executor_job(
                lambda: client.write_registers(
                    self._registers["address"],
                    [self._registers["command_on"]],  # Note the list format
                    slave=slave_id,
                )
            )

            await asyncio.sleep(180)
            await self.async_update()

        except (ConnectionError, ValueError) as err:
            _LOGGER.error(
                "Failed to turn on battery %s: %s", self.battery.battery_id, err
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            client = self.battery._data_manager.modbus_clients[self.battery.battery_id]  # noqa: SLF001
            slave_id = self._registers.get("slave", 64)

            import asyncio

            await asyncio.sleep(0.1)

            _LOGGER.debug(
                "Turning OFF battery %s - Writing %s to register %s",
                self.battery.battery_id,
                self._registers["command_off"],
                self._registers["address"],
            )

            # Use write_registers (plural) instead of write_register
            result = await self.battery.hass.async_add_executor_job(
                lambda: client.write_registers(
                    self._registers["address"],
                    [self._registers["command_off"]],  # Note the list format
                    slave=slave_id,
                )
            )

            await asyncio.sleep(120)
            await self.async_update()

        except (ConnectionError, ValueError) as err:
            _LOGGER.error(
                "Failed to turn off battery %s: %s", self.battery.battery_id, err
            )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return SAX_STATUS in self.battery.data

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    async def async_update(self) -> None:
        """Update the switch state."""
        await self.battery.async_update()


class SAXBatterySolarChargingSwitch(SwitchEntity):
    """Switch to control solar charging for SAX Battery."""

    def __init__(self, sax_battery_data, entry) -> None:
        """Initialize the switch."""
        self._data_manager = sax_battery_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_solar_charging"
        self._attr_name = "Solar Charging"
        self._attr_is_on = entry.data.get(CONF_ENABLE_SOLAR_CHARGING, True)
        self._other_switch = None  # Reference to the manual control switch

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    def set_other_switch(self, other_switch):
        """Set reference to the other switch (manual control)."""
        self._other_switch = other_switch

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on solar charging."""
        try:
            # Turn off manual control if it's on
            if self._other_switch and self._other_switch.is_on:
                await self._other_switch.async_turn_off()

            # Call the pilot's set_solar_charging method
            await self._data_manager.pilot.set_solar_charging(True)

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
            await self._data_manager.pilot.set_solar_charging(False)

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

    def __init__(self, sax_battery_data, entry) -> None:
        """Initialize the switch."""
        self._data_manager = sax_battery_data
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_manual_control"
        self._attr_name = "Manual Control"
        self._attr_is_on = False  # Default to off
        self._other_switch = None  # Reference to the solar charging switch

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    def set_other_switch(self, other_switch):
        """Set reference to the other switch (solar charging)."""
        self._other_switch = other_switch

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on manual control."""
        try:
            # Turn off solar charging switch if it's on
            if self._other_switch and self._other_switch.is_on:
                await self._other_switch.async_turn_off()
            elif hasattr(self._data_manager, "pilot"):
                # Directly turn off solar charging if the switch isn't available
                await self._data_manager.pilot.set_solar_charging(False)

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
            if hasattr(self._data_manager, "pilot"):
                await self._data_manager.pilot.set_solar_charging(True)

            self._attr_is_on = False
            self.async_write_ha_state()

            # Update configuration entry data
            data = dict(self._entry.data)
            data[CONF_MANUAL_CONTROL] = False
            self.hass.config_entries.async_update_entry(self._entry, data=data)

        except (ConnectionError, ValueError) as err:
            _LOGGER.error("Failed to disable manual control: %s", err)
