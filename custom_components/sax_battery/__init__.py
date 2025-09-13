"""Integration for SAX Battery."""

from __future__ import annotations

import logging

import pymodbus

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PILOT_FROM_HA, DOMAIN
from .coordinator import SAXBatteryCoordinator
from .hub import create_hub

_LOGGER = logging.getLogger(__name__)

# Reduce pymodbus logging noise for transaction ID mismatches
logging.getLogger("pymodbus.logging").setLevel(logging.WARNING)
logging.getLogger("pymodbus.client.tcp").setLevel(logging.WARNING)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


def get_device_id_parameter(unit_id: int) -> dict[str, int]:
    """Get the correct parameter name for device/slave ID based on pymodbus version.

    This provides backwards compatibility between pymodbus 3.10 and 3.11+.
    In 3.11+, 'slave' parameter was renamed to 'device_id'.
    """
    try:
        version = pymodbus.__version__
        major, minor = map(int, version.split(".")[:2])
    except (AttributeError, ValueError):
        # Fallback to old parameter name if version detection fails
        return {"slave": unit_id}
    else:
        if major > 3 or (major == 3 and minor >= 11):
            return {"device_id": unit_id}
        return {"slave": unit_id}


async def read_holding_registers_compat(client, address: int, count: int, unit_id: int):
    """Backwards compatible wrapper for reading holding registers.

    Handles the parameter name change from 'slave' to 'device_id' in pymodbus 3.11+.
    """
    params = get_device_id_parameter(unit_id)
    return await client.read_holding_registers(address, count, **params)


async def write_registers_compat(client, address: int, values, unit_id: int):
    """Backwards compatible wrapper for writing registers.

    Handles the parameter name change from 'slave' to 'device_id' in pymodbus 3.11+.
    """
    params = get_device_id_parameter(unit_id)
    return await client.write_registers(address, values, **params)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAX Battery from a config entry."""
    try:
        # Create the hub
        hub = await create_hub(hass, dict(entry.data))

        # Create the coordinator
        coordinator = SAXBatteryCoordinator(hass, hub, 60, entry)

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
