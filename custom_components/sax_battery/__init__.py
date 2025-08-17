"""Integration for SAX Battery."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PILOT_FROM_HA, DOMAIN
from .coordinator import SAXBatteryCoordinator
from .hub import create_hub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAX Battery from a config entry."""
    try:
        # Create the hub
        hub = await create_hub(hass, dict(entry.data))

        # Create the coordinator
        coordinator = SAXBatteryCoordinator(hass, hub, 30)

        # Initial data fetch
        await coordinator.async_config_entry_first_refresh()

        # Store coordinator in hass.data
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Set up pilot service if enabled
        if entry.data.get(CONF_PILOT_FROM_HA, False):
            from .pilot import async_setup_pilot  # noqa: PLC0415

            await async_setup_pilot(hass, entry.entry_id)

    except Exception as err:
        _LOGGER.error("Failed to setup SAX Battery: %s", err)
        raise ConfigEntryNotReady from err
    else:
        return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN][entry.entry_id]

        # Stop pilot service if running
        if hasattr(coordinator.hub, "pilot"):
            await coordinator.hub.pilot.async_stop()

        # Disconnect the hub
        await coordinator.hub.disconnect()

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
