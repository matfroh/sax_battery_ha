"""Data update coordinator for SAX Battery integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_DEVICE_ID
from .hub import SAXBatteryHub, HubException, HubConnectionError

_LOGGER = logging.getLogger(__name__)


class DataUpdateFailed(Exception):
    """Exception for data update failures."""


class SAXBatteryCoordinator(DataUpdateCoordinator):
    """SAX Battery data update coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: SAXBatteryHub,
        scan_interval: int,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="SAX Battery Coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._hub = hub
        self.entry = entry  # Add entry attribute
        self.device_id = entry.data.get(CONF_DEVICE_ID)  # Add device_id attribute

        # Add other attributes that platforms might expect
        self.power_sensor_entity_id = entry.data.get("power_sensor_entity_id")
        self.pf_sensor_entity_id = entry.data.get("pf_sensor_entity_id")

        # Add batteries dict for multi-battery support
        self.batteries = {}
        for battery_id, battery in hub.batteries.items():
            self.batteries[battery_id] = battery
            # Set each battery's _data_manager reference to this coordinator
            battery._data_manager = self

        # Add master_battery attribute for compatibility (use first battery)
        self.master_battery = (
            next(iter(hub.batteries.values())) if hub.batteries else None
        )

        # Add other attributes that might be expected
        self.modbus_clients = hub._clients

        # Add more compatibility attributes that might be expected
        self.last_updates: dict[
            str, Any
        ] = {}  # Initialize empty dictionary for last updates

        # Add modbus_registers for compatibility with switch platform
        self.modbus_registers = {}
        for battery_id in self.batteries:
            self.modbus_registers[battery_id] = {
                "sax_status": {
                    "address": 45,
                    "count": 1,
                    "data_type": "int",
                    "slave": 64,
                    "scan_interval": 60,
                    "state_on": 3,
                    "state_off": 1,
                    "command_on": 2,
                    "command_off": 1,
                }
            }

    async def _async_update_data(self) -> dict[str, float | int | None]:
        """Update data via library."""
        try:
            data = await self._refresh_modbus_data_with_retry(
                ex_type=DataUpdateFailed,
                limit=3,
            )
        except Exception as err:
            raise DataUpdateFailed(f"Error communicating with hub: {err}") from err
        else:
            return data or {}

    async def _refresh_modbus_data_with_retry(
        self,
        ex_type: type[Exception] = Exception,
        limit: int = 2,
    ) -> dict[str, float | int | None]:
        """Refresh modbus data with retries."""
        for i in range(limit):
            try:
                data = await self._hub.read_data()
            except (HubException, HubConnectionError) as err:
                if i == limit - 1:  # Last attempt
                    raise ex_type(f"Error refreshing data: {err}") from err
                _LOGGER.warning(
                    "Retry %s/%s - Error refreshing data: %s", i + 1, limit, err
                )
                await asyncio.sleep(1)  # Wait before retry
            else:
                return data or {}

        return {}

    @property
    def hub(self) -> SAXBatteryHub:
        """Return the hub."""
        return self._hub
