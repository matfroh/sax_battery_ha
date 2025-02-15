#### work in progress - not tested ###
"""
Custom component for SAX Batteries in Home Assistant.
This component sets up SAX battery devices, allowing configuration from the UI.
"""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import discovery
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.helpers.entity import Entity
from homeassistant.components.modbus import async_setup as modbus_setup
from homeassistant.components.modbus.const import CONF_TYPE, MODBUS_DOMAIN, CONF_DELAY, CONF_MESSAGE_WAIT_MILLIS, CONF_TIMEOUT
from homeassistant.helpers.selector import selector

_LOGGER = logging.getLogger(__name__)

DOMAIN = "sax_batteries"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

CONF_BATTERIES = "batteries"
CONF_MASTER_BATTERY = "master_battery"
CONF_SMARTMETER_POWER = "smartmeter_power"
CONF_SMARTMETER_PF = "smartmeter_pf"

BATTERY_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_PORT): int,
})

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_BATTERIES): vol.All(
                    vol.Length(min=1), vol.Schema({str: BATTERY_SCHEMA})
                ),
                vol.Optional(CONF_MASTER_BATTERY): str,
                vol.Optional(CONF_SMARTMETER_POWER): selector({"entity": {"domain": "sensor"}}),
                vol.Optional(CONF_SMARTMETER_PF): selector({"entity": {"domain": "sensor"}}),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the SAX Batteries component."""
    hass.data.setdefault(DOMAIN, {})

    # Load configuration
    conf = config.get(DOMAIN)
    if conf is None:
        return True

    batteries = conf[CONF_BATTERIES]
    master_battery = conf.get(CONF_MASTER_BATTERY, next(iter(batteries)))
    smartmeter_power = conf.get(CONF_SMARTMETER_POWER)
    smartmeter_pf = conf.get(CONF_SMARTMETER_PF)

    hass.data[DOMAIN][CONF_BATTERIES] = batteries
    hass.data[DOMAIN][CONF_MASTER_BATTERY] = master_battery
    hass.data[DOMAIN][CONF_SMARTMETER_POWER] = smartmeter_power
    hass.data[DOMAIN][CONF_SMARTMETER_PF] = smartmeter_pf

    # Set up Modbus connections for each battery
    for name, battery_config in batteries.items():
        modbus_config = {
            CONF_TYPE: "tcp",
            CONF_HOST: battery_config[CONF_HOST],
            CONF_PORT: battery_config[CONF_PORT],
            CONF_DELAY: 1,
            CONF_MESSAGE_WAIT_MILLIS: 30,
            CONF_TIMEOUT: 5,
        }
        await modbus_setup(hass, {MODBUS_DOMAIN: [modbus_config]})
        _LOGGER.info(f"Modbus connection established for battery: {name}")

    # Load platforms
    hass.config_entries.async_setup_platforms(ConfigEntry(domain=DOMAIN), PLATFORMS)

    _LOGGER.info("SAX Batteries setup complete.")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAX Batteries from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Forward the setup to the platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("SAX Batteries config entry setup complete.")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    _LOGGER.info("SAX Batteries config entry unloaded.")
    return unload_ok

class SaxBatteryEntity(Entity):
    """Base class for SAX Battery entities."""

    def __init__(self, hass: HomeAssistant, name: str, battery_config: dict):
        """Initialize the SAX Battery entity."""
        self._hass = hass
        self._name = name
        self._battery_config = battery_config

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def should_poll(self) -> bool:
        """Return whether this entity should be polled."""
        return True

    async def async_update(self):
        """Fetch new state data for the entity."""
        # Placeholder: Add Modbus communication logic here
        pass
