"""Data update coordinator for SAX Battery integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .hub import SAXBatteryHub, HubException, HubConnectionError

_LOGGER = logging.getLogger(__name__)


class DataUpdateFailed(Exception):
    """Exception for data update failures."""


class SAXBatteryCoordinator(DataUpdateCoordinator):
    """SAX Battery data update coordinator."""

    def __init__(
        self, hass: HomeAssistant, hub: SAXBatteryHub, scan_interval: int
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="SAX Battery Coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._hub = hub

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
                _LOGGER.warning("Retry %s/%s - Error refreshing data: %s", i + 1, limit, err)
                await asyncio.sleep(1)  # Wait before retry
            else:
                return data or {}
                
        return {}

    @property
    def hub(self) -> SAXBatteryHub:
        """Return the hub."""
        return self._hub
