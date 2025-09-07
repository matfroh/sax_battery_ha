"""Integration for SAX Battery."""

from __future__ import annotations

import logging

import pymodbus
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_PILOT_FROM_HA,
    DOMAIN,
    SERVICE_SET_CHOKING_POWER,
)
from .coordinator import SAXBatteryCoordinator
from .hub import create_hub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

# Service schema
SET_CHOKING_POWER_SCHEMA = vol.Schema(
    {
        vol.Required("power_percentage"): vol.All(
            vol.Coerce(float), vol.Range(min=-100, max=100)
        ),
    }
)


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
        coordinator = SAXBatteryCoordinator(hass, hub, 30, entry)

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

        # Register services
        async def async_set_choking_power(call: ServiceCall) -> None:
            """Handle set choking power service call."""
            power_percentage = call.data["power_percentage"]

            try:
                coordinator = hass.data[DOMAIN][entry.entry_id]
                await coordinator.hub.async_write_choking_power(power_percentage)
                await coordinator.async_request_refresh()
            except Exception as err:
                _LOGGER.error("Error in set_choking_power service: %s", err)
                raise HomeAssistantError(f"Failed to set choking power: {err}") from err

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_CHOKING_POWER,
            async_set_choking_power,
            schema=SET_CHOKING_POWER_SCHEMA,
        )

    except Exception as err:
        _LOGGER.error("Failed to setup SAX Battery: %s", err)
        raise ConfigEntryNotReady from err
    else:
        return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.services.async_remove(DOMAIN, SERVICE_SET_CHOKING_POWER)
    return unload_ok
