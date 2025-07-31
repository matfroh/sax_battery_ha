"""SAX Battery integration."""

from __future__ import annotations

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


def _raise_config_not_ready(message: str) -> None:
    """Raise ConfigEntryNotReady with the given message."""
    raise ConfigEntryNotReady(message)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the SAX Battery integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAX Battery from a config entry."""
    try:
        # Validate configuration before proceeding
        if not _validate_config_entry(entry):
            _raise_config_not_ready("Invalid configuration data")

        # Create SAX Battery data instance
        sax_battery_data = SAXBatteryData(entry)

        # Initialize batteries and modbus connections
        # This creates ModbusAPI instances for each battery internally
        initialization_success = await sax_battery_data.async_initialize()

        if not initialization_success:
            _raise_config_not_ready("Failed to initialize battery connections")

        # Verify at least one battery is connected
        connected_batteries = [
            battery_id
            for battery_id in sax_battery_data.batteries
            if sax_battery_data.is_battery_connected(battery_id)
        ]

        if not connected_batteries:
            _raise_config_not_ready("No battery connections available")

        _LOGGER.debug("Connected batteries: %s", connected_batteries)

        # Create coordinators for each battery
        coordinators = {}
        update_interval = timedelta(
            seconds=max(5, entry.data.get(CONF_AUTO_PILOT_INTERVAL, 30))
        )

        for battery_id in sax_battery_data.batteries:
            modbus_api = sax_battery_data.get_modbus_api(battery_id)
            if not modbus_api:
                _LOGGER.warning("No ModbusAPI found for battery %s", battery_id)
                continue

            coordinator = SAXBatteryCoordinator(
                hass=hass,
                sax_data=sax_battery_data,
                modbus_api=modbus_api,
                battery_id=battery_id,
                update_interval=update_interval,
            )
            coordinators[battery_id] = coordinator

            # Perform first update for this coordinator
            await coordinator.async_config_entry_first_refresh()

        if not coordinators:
            _raise_config_not_ready("No coordinators could be created")

        # Store coordinators in SAX data for easy access
        sax_battery_data.coordinators = coordinators

        # Store data in hass
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sax_battery_data

        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Initialize pilot functionality if enabled
        if entry.data.get(CONF_PILOT_FROM_HA, False):
            _LOGGER.debug(
                "Pilot functionality enabled - entities will be created via platforms"
            )
            # Pilot entities are created through the entity_helpers in each platform
            # No separate setup needed - the SAXBatteryData already contains pilot items

        _LOGGER.info(
            "Successfully set up SAX Battery integration with %d batteries",
            len(coordinators),
        )

    except (ConnectionError, TimeoutError) as err:
        _LOGGER.error("Connection error during SAX Battery setup: %s", err)
        raise ConfigEntryNotReady from err
    except ValueError as err:
        _LOGGER.error("Configuration error in SAX Battery setup: %s", err)
        raise ConfigEntryNotReady from err
    except Exception as err:
        _LOGGER.error("Unexpected error during SAX Battery setup: %s", err)
        raise ConfigEntryNotReady from err

    return True


def _validate_config_entry(entry: ConfigEntry) -> bool:
    """Validate configuration entry has required data."""
    if not entry.data:
        _LOGGER.error("Config entry has no data")
        return False

    # Check for battery configurations
    batteries_config = entry.data.get("batteries", {})
    if not batteries_config:
        _LOGGER.error("No battery configurations found")
        return False

    # Validate each battery configuration
    for battery_id, battery_config in batteries_config.items():
        if not isinstance(battery_config, dict):
            _LOGGER.error("Invalid battery config for %s", battery_id)
            return False

        # Check required fields
        required_fields = ["host", "port"]
        for field in required_fields:
            if field not in battery_config:
                _LOGGER.error("Missing %s in battery config for %s", field, battery_id)
                return False

        # Validate host is not empty
        if not battery_config["host"].strip():
            _LOGGER.error("Empty host for battery %s", battery_id)
            return False

        # Validate port is numeric
        try:
            port = int(battery_config["port"])
            if not (1 <= port <= 65535):
                _LOGGER.error("Invalid port %s for battery %s", port, battery_id)
                return False
        except (ValueError, TypeError):
            _LOGGER.error("Non-numeric port for battery %s", battery_id)
            return False

    _LOGGER.debug(
        "Configuration validation passed for %d batteries", len(batteries_config)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        sax_battery_data = hass.data[DOMAIN][entry.entry_id]

        # Stop pilot service if running
        if hasattr(sax_battery_data, "pilot"):
            await sax_battery_data.pilot.async_stop()

        # Close all Modbus connections gracefully
        await sax_battery_data.async_close_connections()

        # Clean up coordinator references
        if hasattr(sax_battery_data, "coordinators"):
            for coordinator in sax_battery_data.coordinators.values():
                await coordinator.async_shutdown()

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
