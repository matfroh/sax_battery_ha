"""Data update coordinator for SAX Battery integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any, NoReturn

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .enums import FormatConstants
from .items import ApiItem, SAXItem
from .modbusobject import ModbusObject
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)


class SAXBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for individual SAX Battery with Modbus operations."""

    def __init__(
        self,
        hass: HomeAssistant,
        battery_id: str,
        sax_data: SAXBatteryData,
        modbus_api: Any,
        update_interval: timedelta = timedelta(seconds=10),
    ) -> None:
        """Initialize coordinator for specific battery."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{battery_id}",
            update_interval=update_interval,
        )
        self.battery_id = battery_id
        self.sax_data = sax_data
        self.modbus_api = modbus_api
        self._first_update_done = False
        self._last_write_time: dict[int, float] = {}
        self._sax_item_states: dict[str, Any] = {}

    def update_sax_item_state(self, item_name: str, value: Any) -> None:
        """Update SAX item state."""
        self._sax_item_states[item_name] = value

    @property
    def last_update_success_time(self) -> float | None:
        """Return the time of the last successful update."""
        if hasattr(self, "last_update_success") and self.last_update_success:
            return time.time()
        return None

    def _should_immediate_refresh(self, modbus_item: ApiItem) -> bool:
        """Determine if immediate refresh is needed after write."""
        critical_items = {
            "sax_max_charge_power",
            "sax_max_discharge_power",
            "sax_solar_charging",
            "sax_pilot_enabled",
        }
        return modbus_item.name in critical_items

    def _convert_value_for_writing(
        self, modbus_item: ApiItem | SAXItem, value: float
    ) -> int:
        """Convert value according to Modbus item configuration."""
        # Apply divider if specified
        divider = getattr(modbus_item, "divider", 1)
        if divider and divider != 1:
            value = value * divider

        # Apply format-specific conversions
        item_format = getattr(modbus_item, "mformat", None) or getattr(
            modbus_item, "mformat", None
        )
        if item_format == FormatConstants.PERCENTAGE:
            value = max(0, min(100, value))

        # Ensure we return an integer value within valid Modbus range
        return int(max(-32768, min(32767, value)))

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from specific battery and update SAX items."""
        try:
            battery = self.sax_data.batteries.get(self.battery_id)
            if not battery:
                self._raise_battery_not_found_error()

            # Type assertion to help MyPy understand battery is not None
            assert battery is not None

            # Update Modbus data from battery
            await battery.async_update()

            # Update SAX items for this battery
            await self._update_sax_items()

            # For master battery, also update smart meter data
            if self.sax_data.should_poll_smart_meter(self.battery_id):
                await self._update_smart_meter_data()

            self._first_update_done = True
        except (OSError, ValueError, TypeError, AttributeError) as err:
            return self._handle_update_error(err)
        else:
            return battery.data or {}

    def _raise_battery_not_found_error(self) -> NoReturn:
        """Raise appropriate error when battery is not found."""
        raise UpdateFailed(f"Battery {self.battery_id} not found")

    def _handle_update_error(self, err: Exception) -> dict[str, Any]:
        """Handle update errors appropriately."""
        if not self._first_update_done:
            raise ConfigEntryNotReady(
                f"Failed to setup battery {self.battery_id}: {err}"
            ) from err

        raise UpdateFailed(
            f"Error communicating with battery {self.battery_id}: {err}"
        ) from err

    async def _update_sax_items(self) -> None:
        """Update all SAX items for this battery."""
        # Get SAX items from the data model
        sax_items = self.sax_data.get_sax_items_for_battery(self.battery_id)

        # Update each SAX item
        for sax_item in sax_items:
            await self._refresh_sax_item(sax_item)

    async def _refresh_sax_item(self, sax_item: SAXItem) -> None:
        """Refresh a specific SAX item's state."""
        try:
            # For pilot functionality, manage state locally
            if "pilot" in sax_item.name.lower():
                current_state = await self._get_pilot_state(sax_item.name)
                self._sax_item_states[sax_item.name] = current_state
            elif "solar_charging" in sax_item.name.lower():
                current_state = await self._get_solar_charging_state()
                self._sax_item_states[sax_item.name] = current_state
            elif "manual_control" in sax_item.name.lower():
                current_state = await self._get_manual_control_state()
                self._sax_item_states[sax_item.name] = current_state

            _LOGGER.debug("Refreshed SAX item: %s", sax_item.name)

        except (OSError, ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Failed to refresh SAX item %s: %s", sax_item.name, err)

    async def _get_pilot_state(self, item_name: str) -> int:
        """Get current pilot state from system."""
        stored_state = self._sax_item_states.get(item_name, 0)
        return int(stored_state) if stored_state is not None else 0

    async def _get_solar_charging_state(self) -> int:
        """Get current solar charging state from system."""
        stored_state = self._sax_item_states.get("solar_charging", 0)
        return int(stored_state) if stored_state is not None else 0

    async def _get_manual_control_state(self) -> int:
        """Get current manual control state from system."""
        stored_state = self._sax_item_states.get("manual_control", 0)
        return int(stored_state) if stored_state is not None else 0

    async def _update_smart_meter_data(self) -> None:
        """Update smart meter data (master battery only)."""
        try:
            # Get smart meter items for this battery
            smart_meter_items = self.sax_data.get_modbus_items_for_battery(
                self.battery_id
            )

            # Filter for smart meter specific items
            smartmeter_items = [
                item for item in smart_meter_items if "smartmeter" in item.name.lower()
            ]

            # Read smart meter data in parallel for efficiency
            tasks = [self._read_smart_meter_item(item) for item in smartmeter_items]

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except (OSError, ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Smart meter update failed: %s", err)

    async def _read_smart_meter_item(self, item: ApiItem) -> None:
        """Read a single smart meter item."""
        try:
            values = await self.modbus_api.read_holding_registers(
                item.address, 1, self.battery_id
            )
            if values and len(values) > 0:
                self._update_smart_meter_value(item, values[0])
        except (OSError, ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Failed to read smart meter item %s: %s", item.name, err)

    def _update_smart_meter_value(self, item: ApiItem, value: int) -> None:
        """Update smart meter data based on item name."""
        smart_meter_mapping = {
            "smartmeter_total_power": "total_power",
            "smartmeter_grid_frequency": "grid_frequency",
            "smartmeter_voltage_l1": "voltage_l1",
            "smartmeter_voltage_l2": "voltage_l2",
            "smartmeter_voltage_l3": "voltage_l3",
            "smartmeter_current_l1": "current_l1",
            "smartmeter_current_l2": "current_l2",
            "smartmeter_current_l3": "current_l3",
            "smartmeter_import_power": "import_power",
            "smartmeter_export_power": "export_power",
        }

        attr_name = smart_meter_mapping.get(item.name)
        if attr_name and hasattr(self.sax_data.smart_meter_data, attr_name):
            # Apply divider if specified
            converted_value = float(value)
            divider = getattr(item, "divider", 1)
            if divider and divider != 1:
                converted_value = float(value) / divider

            setattr(self.sax_data.smart_meter_data, attr_name, converted_value)
            self.sax_data.smart_meter_data.last_update = time.time()

    async def async_write_switch_value(self, modbus_item: ApiItem, value: bool) -> bool:
        """Write a boolean switch value to a Modbus register for this battery."""
        try:
            # Get the ModbusObject for this item
            modbus_object = ModbusObject(
                modbus_api=self.modbus_api,
                modbus_item=modbus_item,
                config_entry=self.sax_data,
                battery_id=self.battery_id,
            )

            # Write the boolean value using ModbusObject abstraction
            success = await modbus_object.async_write_switch_value(value)

            if success:
                # Update the last write time for rate limiting
                self._last_write_time[modbus_item.address] = time.time()

                # Trigger immediate refresh for critical items
                if self._should_immediate_refresh(modbus_item):
                    await self.async_request_refresh()

        except (OSError, ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to write switch value %s for %s on battery %s: %s",
                value,
                modbus_item.name,
                self.battery_id,
                err,
            )
            return False
        else:
            return success

    async def async_write_number_value(
        self, modbus_item: ApiItem, value: float
    ) -> bool:
        """Write a numeric value to a Modbus register for this battery."""
        try:
            # Convert float value to appropriate Modbus format
            converted_value = self._convert_value_for_writing(modbus_item, value)

            # Get the ModbusObject for this item
            modbus_object = ModbusObject(
                modbus_api=self.modbus_api,
                modbus_item=modbus_item,
                config_entry=self.sax_data,
                battery_id=self.battery_id,
            )

            # Get battery slave ID from modbus item or use battery configuration
            slave_id = getattr(modbus_item, "battery_slave_id", None)
            if slave_id is None:
                # Fallback to battery configuration
                battery = self.sax_data.batteries.get(self.battery_id)
                slave_id = getattr(battery, "slave_id", 1) if battery else 1

            # Write the numeric value using ModbusObject abstraction
            success = await modbus_object.async_write_value(
                slave_id=slave_id, value=converted_value
            )

            if success:
                # Update the last write time for rate limiting
                self._last_write_time[modbus_item.address] = time.time()

                # Trigger immediate refresh for critical items
                if self._should_immediate_refresh(modbus_item):
                    await self.async_request_refresh()

        except (OSError, ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to write numeric value %s for %s on battery %s: %s",
                value,
                modbus_item.name,
                self.battery_id,
                err,
            )
            return False
        else:
            return success

    async def async_write_int_value(self, modbus_item: ApiItem, value: int) -> bool:
        """Write an integer value to a Modbus register for this battery."""
        try:
            # Convert and clamp int value to 16-bit signed range
            converted_value = int(max(-32768, min(32767, value)))

            # Get the ModbusObject for this item
            modbus_object = ModbusObject(
                modbus_api=self.modbus_api,
                modbus_item=modbus_item,
                config_entry=self.sax_data,
                battery_id=self.battery_id,
            )

            # Get battery slave ID from modbus item or use battery configuration
            slave_id = getattr(modbus_item, "battery_slave_id", None)
            if slave_id is None:
                # Fallback to battery configuration
                battery = self.sax_data.batteries.get(self.battery_id)
                slave_id = getattr(battery, "slave_id", 1) if battery else 1

            # Write the integer value using ModbusObject abstraction
            success = await modbus_object.async_write_value(
                slave_id=slave_id, value=converted_value
            )

            if success:
                # Update the last write time for rate limiting
                self._last_write_time[modbus_item.address] = time.time()

                # Trigger immediate refresh for critical items
                if self._should_immediate_refresh(modbus_item):
                    await self.async_request_refresh()

        except (OSError, ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to write integer value %s for %s on battery %s: %s",
                value,
                modbus_item.name,
                self.battery_id,
                err,
            )
            return False
        else:
            return success
