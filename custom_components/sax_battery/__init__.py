"""Integration for SAX Battery."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_AUTO_PILOT_INTERVAL, CONF_PILOT_FROM_HA, DOMAIN
from .coordinator import SAXBatteryCoordinator
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the SAX Battery integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAX Battery from a config entry."""
    try:
        # Create SAX Battery data instance
        sax_battery_data = SAXBatteryData(entry)

        # Create coordinator with appropriate interval
        update_interval = timedelta(
            seconds=max(5, entry.data.get(CONF_AUTO_PILOT_INTERVAL, 30))
        )
        coordinator = SAXBatteryCoordinator(hass, sax_battery_data, update_interval)
        sax_battery_data.coordinator = coordinator

        # Perform first update
        await coordinator.async_config_entry_first_refresh()

        # Store data
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sax_battery_data

        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Set up pilot service if enabled
        if entry.data.get(CONF_PILOT_FROM_HA, False):
            # Import here to avoid circular import issues
            from .pilot import async_setup_pilot  # noqa: PLC0415

            await async_setup_pilot(hass, entry.entry_id)

    except (ConnectionError, TimeoutError, ValueError) as err:
        _LOGGER.error("Failed to initialize SAX Battery: %s", err)
        raise ConfigEntryNotReady from err

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        sax_battery_data = hass.data[DOMAIN][entry.entry_id]

        # Stop pilot service if running
        if hasattr(sax_battery_data, "pilot"):
            await sax_battery_data.pilot.async_stop()

        # Close all Modbus connections
        for battery in sax_battery_data.batteries.values():
            if hasattr(battery, "client") and battery.client:
                battery.client.close()

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
