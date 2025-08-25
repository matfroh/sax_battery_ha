"""SAX Battery integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .modbusobject import ModbusAPI
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)

# Platforms to set up
PLATFORMS: list[Platform] = [
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

type SAXBatteryConfigEntry = ConfigEntry[dict[str, SAXBatteryCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: SAXBatteryConfigEntry) -> bool:
    """Set up SAX Battery from a config entry."""
    try:
        # Initialize SAX Battery Data
        sax_data = SAXBatteryData(hass, entry)

        # Create coordinators for each battery configured
        coordinators: dict[str, SAXBatteryCoordinator] = {}

        battery_count = entry.data.get("battery_count", 1)

        for i in range(1, int(battery_count) + 1):
            battery_id = f"battery_{chr(96 + i)}"  # battery_a, battery_b, battery_c

            # Get battery-specific host and port from config (matching old implementation)
            host = entry.data.get(f"{battery_id}_host")
            port = entry.data.get(f"{battery_id}_port")

            _LOGGER.debug("Setting up battery %s at %s:%s", battery_id, host, port)

            # Validate host configuration
            host = str(entry.data.get(f"{battery_id}_host", ""))
            port = int(entry.data.get(f"{battery_id}_port", 502))

            if not host:
                _LOGGER.error(
                    "No host configuration found for %s in entry data: %s",
                    battery_id,
                    list(entry.data.keys()),
                )
                raise ConfigEntryNotReady(f"No host configured for {battery_id}")  # noqa: TRY301

            # Initialize Modbus API for this battery
            modbus_api = ModbusAPI(
                host=host,
                port=port,
                battery_id=battery_id,
            )

            # Test connection for this battery - use correct method name
            if not await modbus_api.connect():
                msg = f"Could not connect to {host}:{port}"
                raise ConfigEntryNotReady(msg)  # noqa: TRY301

            # Create coordinator for this battery
            coordinator = SAXBatteryCoordinator(
                hass=hass,
                battery_id=battery_id,
                sax_data=sax_data,
                modbus_api=modbus_api,
                config_entry=entry,
            )

            # Perform initial data fetch
            await coordinator.async_config_entry_first_refresh()

            coordinators[battery_id] = coordinator

            _LOGGER.info(
                "Successfully setup coordinator for %s at %s:%s", battery_id, host, port
            )

        # Store sax_data reference for platforms to access
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinators": coordinators,
            "sax_data": sax_data,
        }

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info(
            "SAX Battery integration setup complete with %d batteries: %s",
            len(coordinators),
            list(coordinators.keys()),
        )
        return True  # noqa: TRY300

    except Exception as err:
        _LOGGER.exception("Failed to setup SAX Battery integration")
        raise ConfigEntryNotReady(f"Failed to setup SAX Battery: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: SAXBatteryConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up stored data
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            data = hass.data[DOMAIN].pop(entry.entry_id)

            # Close modbus connections for all batteries
            if coordinators := data.get("coordinators"):
                for battery_id, coordinator in coordinators.items():
                    if hasattr(coordinator, "modbus_api"):
                        # Use correct method name for disconnection
                        coordinator.modbus_api.close()
                        _LOGGER.debug(
                            "Disconnected modbus connection for %s", battery_id
                        )

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: SAXBatteryConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
