"""SAX Battery data update coordinator."""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import operator
from typing import Any

from pymodbus import ModbusException

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BATTERY_POLL_INTERVAL, DOMAIN
from .items import ModbusItem, SAXItem
from .modbusobject import ModbusAPI, ModbusObject
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)

# Safe operations for calculation evaluation
SAFE_OPERATIONS: dict[type[ast.AST], Callable[..., float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class SAXBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """SAX Battery data update coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        battery_id: str,
        sax_data: SAXBatteryData,
        modbus_api: ModbusAPI,
        config_entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{battery_id}",
            update_interval=timedelta(seconds=BATTERY_POLL_INTERVAL),
            config_entry=config_entry,
        )

        self.battery_id = battery_id
        self.sax_data = sax_data
        self.modbus_api = modbus_api
        self._modbus_objects: dict[str, ModbusObject] = {}
        self.last_update_success_time: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data from battery."""
        try:
            data: dict[str, Any] = {}

            # Update smart meter data if this is master battery
            if self.sax_data.should_poll_smart_meter(self.battery_id):
                await self._update_smart_meter_data(data)

            # Update battery data
            for item in self.sax_data.get_modbus_items_for_battery(self.battery_id):
                if item.name not in self._modbus_objects:
                    self._modbus_objects[item.name] = ModbusObject(
                        self.modbus_api, item
                    )

                modbus_obj = self._modbus_objects[item.name]
                value = await modbus_obj.async_read_value()
                data[item.name] = value

            # Update SAX calculated items
            for sax_item in self.sax_data.get_sax_items_for_battery(self.battery_id):
                calculated_value = self._calculate_sax_value(sax_item)
                data[sax_item.name] = calculated_value

            self.last_update_success_time = datetime.now()
            return data  # noqa: TRY300

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error("Error updating battery data: %s", err)
            raise UpdateFailed(
                f"Error communicating with battery {self.battery_id}"
            ) from err

    async def _update_smart_meter_data(self, data: dict[str, Any]) -> None:
        """Update smart meter data (only for master battery)."""
        try:
            if not self.sax_data.smart_meter_data:
                return

            for item in self.sax_data.get_smart_meter_items():
                try:
                    value = await self.modbus_api.read_holding_registers(
                        count=1, modbus_item=item
                    )
                    if value is not None:
                        data[item.name] = float(value)
                        self.sax_data.smart_meter_data.set_value(
                            item.name, float(value)
                        )
                    else:
                        data[item.name] = None
                except (ModbusException, OSError, TimeoutError) as err:
                    _LOGGER.error(
                        "Error reading smart meter data for %s: %s", item.name, err
                    )
                    data[item.name] = None
        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error("Error updating smart meter data: %s", err)

    def _calculate_sax_value(self, sax_item: SAXItem) -> float | None:
        """Calculate SAX item value using the item's own calculation method."""

        # ToDo: sax_cumulative_energy_produced, sax_cumulative_energy_consumed, sax_combined_soc
        # This is only relevant for multi-battery scenarios and can be implemented => requires sensor entity names and CONF_BATTERY_COUNT
        #
        # battery_count = entry.data.get("battery_count", 1)
        # Use the SAXItem's own calculation method
        return None

    async def async_write_number_value(self, item: ModbusItem, value: float) -> bool:
        """Write number value to modbus register."""
        if item.name not in self._modbus_objects:
            self._modbus_objects[item.name] = ModbusObject(self.modbus_api, item)

        modbus_obj = self._modbus_objects[item.name]
        return await modbus_obj.async_write_value(value)

    async def async_write_switch_value(self, item: ModbusItem, value: bool) -> bool:
        """Write switch value to modbus register."""
        if item.name not in self._modbus_objects:
            self._modbus_objects[item.name] = ModbusObject(self.modbus_api, item)

        modbus_obj = self._modbus_objects[item.name]

        # Convert boolean to appropriate switch value
        write_value = (
            modbus_obj.get_switch_on_value()
            if value
            else modbus_obj.get_switch_off_value()
        )
        return await modbus_obj.async_write_value(write_value)

    async def async_write_int_value(self, item: ModbusItem, value: int) -> bool:
        """Write integer value to modbus register."""
        if item.name not in self._modbus_objects:
            self._modbus_objects[item.name] = ModbusObject(self.modbus_api, item)

        modbus_obj = self._modbus_objects[item.name]
        return await modbus_obj.async_write_value(float(value))

    def update_sax_item_state(self, item: SAXItem | str, value: Any) -> None:
        """Update SAX item state in the coordinator data."""
        if isinstance(item, str):
            item_name = item
        else:
            item_name = item.name

        if self.data:
            self.data[item_name] = value
            self.async_update_listeners()
