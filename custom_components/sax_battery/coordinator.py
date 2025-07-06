"""Data update coordinator for SAX Battery integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)


class SAXBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching SAX Battery data."""

    def __init__(
        self,
        hass: HomeAssistant,
        sax_data: SAXBatteryData,
        update_interval: timedelta = timedelta(seconds=30),
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.sax_data = sax_data
        self._first_update_done = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from SAX Battery system."""

        def _raise_not_ready(msg: str) -> None:
            """Raise ConfigEntryNotReady exception."""
            raise ConfigEntryNotReady(msg)

        try:
            # Gather all battery updates concurrently
            update_tasks = [
                battery.async_update() for battery in self.sax_data.batteries.values()
            ]

            # Execute all updates concurrently
            results = await asyncio.gather(*update_tasks, return_exceptions=True)

            # Check for exceptions
            exceptions = [r for r in results if isinstance(r, Exception)]

            if exceptions and not self._first_update_done:
                # If first update fails completely, raise ConfigEntryNotReady
                _raise_not_ready(f"Failed to initialize SAX Battery: {exceptions}")

            if exceptions:
                _LOGGER.warning("Some battery updates failed: %s", exceptions)

        except Exception as err:
            if not self._first_update_done:
                raise ConfigEntryNotReady(
                    f"Failed to setup SAX Battery: {err}"
                ) from err
            raise UpdateFailed(f"Error communicating with SAX Battery: {err}") from err
        else:
            # Collect all data
            combined_data = {}
            for battery_id, battery in self.sax_data.batteries.items():
                if battery.data:
                    combined_data[battery_id] = battery.data

            # Add combined metrics
            master_battery = self.sax_data.get_master_battery()
            if (
                master_battery
                and hasattr(master_battery, "data_manager")
                and hasattr(master_battery.data_manager, "combined_data")
            ):
                combined_data["combined"] = master_battery.data_manager.combined_data

            self._first_update_done = True
            return combined_data
