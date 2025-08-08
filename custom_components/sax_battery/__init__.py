"""SAX Battery integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .modbusobject import ModbusAPI
from .models import BatteryModel, SAXBatteryData, SmartMeterModel

if TYPE_CHECKING:
    pass  # noqa: TC005

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAX Battery from a config entry."""
    # Initialize SAX Battery data structure
    sax_data = SAXBatteryData()

    # Initialize the data structure
    await sax_data.async_initialize()

    # Create battery models based on config entry data
    battery_count = entry.data.get("battery_count", 1)
    _LOGGER.debug("Setting up %d batteries", battery_count)

    modbus_apis: dict[str, ModbusAPI] = {}

    for i in range(battery_count):
        battery_letter = chr(ord("a") + i)
        battery_id = f"battery_{battery_letter}"

        # Get battery configuration from config entry
        battery_name = entry.data.get(
            f"battery_{battery_letter}_name", f"Battery {battery_letter.upper()}"
        )
        battery_host = entry.data.get(f"battery_{battery_letter}_host")
        battery_port = entry.data.get(f"battery_{battery_letter}_port", 502)

        if not battery_host:
            raise ConfigEntryNotReady(f"No host configured for {battery_name}")

        # Create individual Modbus API for each battery
        modbus_api = ModbusAPI(
            host=battery_host,
            port=battery_port,
            battery_id=battery_id,
        )
        modbus_apis[battery_id] = modbus_api

        # Create battery model
        battery_model = BatteryModel(
            device_id=battery_id,
            name=battery_name,
            slave_id=i + 1,
            host=battery_host,
            port=battery_port,
            is_master=(i == 0),  # First battery (Battery A) is master
        )

        sax_data.batteries[battery_id] = battery_model

        # Set master battery ID for smart meter coordination
        if battery_model.is_master:
            sax_data.master_battery_id = battery_id
            # Store the master's modbus API as the main one for smart meter access
            sax_data.modbus_api = modbus_api

    # Create smart meter model if we have a master battery
    if sax_data.master_battery_id:
        master_battery = sax_data.batteries[sax_data.master_battery_id]
        sax_data.smart_meter_data = SmartMeterModel(
            device_id=f"{sax_data.master_battery_id}_smartmeter",
            name=f"{master_battery.name} Smart Meter",
        )

    # Create coordinators for each battery with individual connections
    for battery_id, battery_model in sax_data.batteries.items():
        if not sax_data.is_battery_connected(battery_id):
            continue

        # Use the specific Modbus API for this battery
        battery_modbus_api = modbus_apis[battery_id]

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id=battery_id,
            sax_data=sax_data,
            modbus_api=battery_modbus_api,
            config_entry=entry,
        )

        # Test connection and perform first data update
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as err:
            _LOGGER.error(
                "Failed to connect to %s at %s:%d",
                battery_model.name,
                battery_model.host,
                battery_model.port,
            )
            raise ConfigEntryNotReady(
                f"Failed to connect to {battery_model.name}: {err}"
            ) from err

        sax_data.coordinators[battery_id] = coordinator

        _LOGGER.debug("Successfully initialized coordinator for %s", battery_model.name)

    # Verify we have at least one working battery
    if not sax_data.coordinators:
        raise ConfigEntryNotReady("No battery coordinators could be initialized")

    # Store in hass data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sax_data

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info(
        "SAX Battery integration setup complete with %d batteries",
        len(sax_data.coordinators),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up modbus connections
        sax_data = hass.data[DOMAIN].pop(entry.entry_id)

        # Close all modbus connections
        for coordinator in sax_data.coordinators.values():
            if hasattr(coordinator, "modbus_api"):
                coordinator.modbus_api.close()

        if sax_data.modbus_api:
            sax_data.modbus_api.close()

    return unload_ok
