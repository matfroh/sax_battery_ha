"""Data update coordinator for SAX Battery integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_DEVICE_ID
from .hub import HubConnectionError, HubException, SAXBatteryHub

_LOGGER = logging.getLogger(__name__)


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
        self.entry = entry
        self.device_id = entry.data.get(CONF_DEVICE_ID)

        # Add other attributes that platforms might expect
        self.power_sensor_entity_id = entry.data.get("power_sensor_entity_id")
        self.pf_sensor_entity_id = entry.data.get("pf_sensor_entity_id")

        # Add batteries dict for multi-battery support
        self.batteries = {}
        for battery_id, battery in hub.batteries.items():
            self.batteries[battery_id] = battery
            # Set each battery's _data_manager reference to this coordinator
            battery._data_manager = self  # noqa: SLF001

        # Add master_battery attribute for compatibility (use first battery)
        self.master_battery = (
            next(iter(hub.batteries.values())) if hub.batteries else None
        )

        # Add other attributes that might be expected
        self.modbus_clients = hub._clients  # noqa: SLF001

        # Add more compatibility attributes that might be expected
        self.last_updates: dict[str, Any] = {}

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

        # Add global modbus lock for write operations
        self._write_lock = asyncio.Lock()

    async def async_write_modbus_registers(
        self, battery_id: str, address: int, values: list[int], device_id: int = 64
    ) -> bool:
        """Write to Modbus registers with proper locking to prevent conflicts."""
        async with self._write_lock:
            try:
                # Add delay to avoid conflicts with other integrations
                await asyncio.sleep(0.5)

                # Use hub's write method if available, otherwise direct client access
                if hasattr(self._hub, "write_registers"):
                    success = await self._hub.write_registers(
                        battery_id, address, values, device_id
                    )
                else:
                    # Fallback to direct client access with retries
                    client = self.modbus_clients.get(battery_id)
                    if not client:
                        _LOGGER.error(
                            "No Modbus client found for battery %s", battery_id
                        )
                        return False

                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            if not client.connected:
                                await client.connect()
                                await asyncio.sleep(0.1)

                            result = await client.write_registers(
                                address, values, device_id=device_id
                            )

                            if result.isError():
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(1.0 * (2**attempt))
                                    continue
                                _LOGGER.error(
                                    "Modbus write failed after %d attempts", max_retries
                                )
                                return False

                            _LOGGER.debug(
                                "Successfully wrote to battery %s, address %d, values %s",
                                battery_id,
                                address,
                                values,
                            )
                            return True  # noqa: TRY300

                        except Exception as err:  # noqa: BLE001
                            _LOGGER.warning(
                                "Attempt %d failed for battery %s: %s",
                                attempt + 1,
                                battery_id,
                                err,
                            )
                            if attempt == max_retries - 1:
                                return False
                            await asyncio.sleep(1.0 * (2**attempt))

                return success if hasattr(self._hub, "write_registers") else False

            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Error writing Modbus registers: %s", err)
                return False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the hub with timeout and sequential processing."""
        # Prevent concurrent data fetching
        if hasattr(self, "_fetching_lock"):
            if self._fetching_lock.locked():
                _LOGGER.debug("Data fetch already in progress, using cached data")
                return self.data or {}
        else:
            self._fetching_lock = asyncio.Lock()

        async with self._fetching_lock:
            try:
                # Reduce timeout to prevent HA coordinator timeouts
                raw_data = await asyncio.wait_for(
                    self._hub.read_data(),
                    timeout=20.0,  # Reduced from 25 to 20 seconds
                )

                # Calculate combined values for multi-battery systems
                combined_data = self._calculate_combined_values(raw_data)

                # Merge raw data with combined values
                raw_data.update(combined_data)

                return raw_data  # noqa: TRY300

            except TimeoutError:
                _LOGGER.warning("Data fetch timed out after 20 seconds")
                # Return last known data if available
                return self.data or {}
            except Exception as error:
                _LOGGER.error("Error communicating with API: %s", error)
                raise UpdateFailed(f"Error communicating with API: {error}") from error

    def _calculate_combined_values(self, data: dict[str, Any]) -> dict[str, Any]:
        """Calculate combined values from all batteries."""
        combined = {}

        # Calculate combined SOC (average of all batteries)
        soc_sum = 0.0
        soc_count = 0

        # Calculate combined power (sum of all batteries)
        power_sum = 0.0

        # Iterate through all configured batteries
        for battery_id in self.batteries:
            # Get SOC for this battery
            soc_key = f"{battery_id}_soc"
            if soc_key in data and data[soc_key] is not None:
                soc_sum += data[soc_key]
                soc_count += 1

            # Get power for this battery
            power_key = f"{battery_id}_power"
            if power_key in data and data[power_key] is not None:
                power_sum += data[power_key]

        # Calculate average SOC
        if soc_count > 0:
            combined["combined_soc"] = round(soc_sum / soc_count, 1)
        else:
            combined["combined_soc"] = None

        # Set combined power
        combined["combined_power"] = round(power_sum, 1) if power_sum != 0 else 0.0

        _LOGGER.debug(
            "Calculated combined values: SOC=%s%% (from %d batteries), Power=%sW",
            combined["combined_soc"],
            soc_count,
            combined["combined_power"],
        )

        return combined

    @property
    def combined_data(self) -> dict[str, Any]:
        """Return combined data for backward compatibility."""
        if not hasattr(self, "_combined_data"):
            self._combined_data = {}
        return self._combined_data

    @combined_data.setter
    def combined_data(self, value: dict[str, Any]) -> None:
        """Set combined data."""
        self._combined_data = value

    async def _refresh_modbus_data_with_retry(
        self,
        ex_type: type[Exception] = Exception,
        limit: int = 2,
    ) -> dict[str, float | int | None]:
        """Refresh modbus data with retries."""
        for i in range(limit):
            try:
                data = await self._hub.read_data()  # Changed back to existing method
            except (HubException, HubConnectionError) as err:
                if i == limit - 1:  # Last attempt
                    raise ex_type("Error refreshing data: %s", err) from err
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
