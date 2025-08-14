"""SAX Battery data update coordinator."""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import operator
import re
from typing import Any

from pymodbus import ModbusException

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BATTERY_POLL_INTERVAL, DOMAIN, WRITE_ONLY_REGISTERS
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
        self._first_update_done = False
        self._modbus_objects: dict[str, ModbusObject] = {}
        self.last_update_success_time: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data from battery."""
        try:
            # Get modbus items for this battery
            modbus_items = self.sax_data.get_modbus_items_for_battery(self.battery_id)

            # Create ModbusObjects if not already created
            for item in modbus_items:
                if item.name not in self._modbus_objects:
                    self._modbus_objects[item.name] = ModbusObject(
                        self.modbus_api, item
                    )

            # Read data from modbus
            data: dict[str, Any] = {}
            failed_reads = 0
            total_items = len(self._modbus_objects)

            for item_name, modbus_obj in self._modbus_objects.items():
                # Skip read for write-only registers (e.g., 41, 42, 43, 44)
                if getattr(modbus_obj.item, "address", None) in WRITE_ONLY_REGISTERS:
                    data[item_name] = None
                    continue
                try:
                    raw_value = await modbus_obj.async_read_value()
                    if raw_value is not None:
                        converted_value = modbus_obj.item.convert_raw_value(raw_value)
                        data[item_name] = converted_value
                    else:
                        data[item_name] = None
                        failed_reads += 1
                except (
                    ModbusException,
                    OSError,
                    TimeoutError,
                    asyncio.CancelledError,
                ) as err:
                    _LOGGER.debug("Failed to read %s: %s", item_name, err)
                    data[item_name] = None
                    failed_reads += 1

            # If too many reads failed, consider it a connection issue
            if failed_reads > total_items * 0.5:  # More than 50% failed
                if not self._first_update_done:
                    raise ConfigEntryNotReady(
                        f"Too many failed reads ({failed_reads}/{total_items}) for battery {self.battery_id}"
                    )
                else:  # noqa: RET506
                    _LOGGER.warning(
                        "High failure rate (%d/%d) for battery %s, continuing with partial data",
                        failed_reads,
                        total_items,
                        self.battery_id,
                    )

            # Handle smart meter data if this is the master battery
            if self.sax_data.should_poll_smart_meter(self.battery_id):
                await self._update_smart_meter_data(data)

            # Update battery in sax_data
            if battery := self.sax_data.batteries.get(self.battery_id):
                battery.update_data(data)

            # Handle calculated SAX items
            sax_items = self.sax_data.get_sax_items_for_battery(self.battery_id)
            for sax_item in sax_items:
                if (
                    hasattr(sax_item.mtype, "name")
                    and sax_item.mtype.name == "SENSOR_CALC"
                ):
                    calculated_value = self._calculate_sax_value(sax_item)
                    data[sax_item.name] = calculated_value

            self._first_update_done = True
            self.last_update_success_time = datetime.now()
            return data  # noqa: TRY300

        except (ModbusException, OSError, TimeoutError) as err:
            if not self._first_update_done:
                raise ConfigEntryNotReady(
                    f"Failed to setup battery {self.battery_id}: {err}"
                ) from err

            raise UpdateFailed(
                f"Error communicating with battery {self.battery_id}: {err}"
            ) from err

    async def _update_smart_meter_data(self, data: dict[str, Any]) -> None:
        """Update smart meter data (only for master battery)."""
        try:
            smart_meter_items = self.sax_data.get_smart_meter_items()
            for item in smart_meter_items:
                try:
                    raw_values = await self.modbus_api.read_holding_registers(
                        item.address, 1, item.battery_slave_id
                    )
                    if raw_values:
                        converted_value = item.convert_raw_value(raw_values)
                        data[item.name] = converted_value
                        # Update smart meter data in sax_data
                        if self.sax_data.smart_meter_data:
                            self.sax_data.smart_meter_data.set_value(
                                item.name, converted_value
                            )
                except (ModbusException, OSError, TimeoutError) as err:
                    _LOGGER.debug("Failed to read smart meter %s: %s", item.name, err)
                    data[item.name] = None
        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.debug("Failed to update smart meter data: %s", err)

    def _safe_eval_expression(
        self, expr: str, variables: dict[str, float]
    ) -> float | None:
        """Safely evaluate mathematical expressions using AST."""
        try:
            # Parse the expression
            tree = ast.parse(expr, mode="eval")

            def _eval_node(node: ast.AST) -> float:
                if isinstance(node, ast.Expression):
                    return _eval_node(node.body)
                elif isinstance(node, ast.Constant):  # Numbers  # noqa: RET505
                    if isinstance(node.value, (int, float)):
                        return float(node.value)
                    raise ValueError(f"Unsupported constant type: {type(node.value)}")  # noqa: TRY301
                elif isinstance(node, ast.Name):  # Variables
                    if node.id in variables:
                        return float(variables[node.id])
                    raise ValueError(f"Unknown variable: {node.id}")  # noqa: TRY301
                elif isinstance(node, ast.BinOp):  # Binary operations
                    if type(node.op) in SAFE_OPERATIONS:
                        left = _eval_node(node.left)
                        right = _eval_node(node.right)
                        op_func = SAFE_OPERATIONS[type(node.op)]
                        return float(op_func(left, right))
                    raise ValueError(f"Unsupported operation: {type(node.op)}")  # noqa: TRY301
                elif isinstance(node, ast.UnaryOp):  # Unary operations
                    if type(node.op) in SAFE_OPERATIONS:
                        operand = _eval_node(node.operand)
                        op_func = SAFE_OPERATIONS[type(node.op)]
                        return float(op_func(operand))
                    raise ValueError(f"Unsupported unary operation: {type(node.op)}")  # noqa: TRY301
                else:
                    raise ValueError(f"Unsupported node type: {type(node)}")  # noqa: TRY004, TRY301

            return _eval_node(tree)

        except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as err:
            _LOGGER.debug("Failed to evaluate expression '%s': %s", expr, err)
            return None

    def _calculate_sax_value(self, sax_item: SAXItem) -> float | None:
        """Calculate value for a SAXItem using its calculation expression."""
        params = sax_item.params
        if not params or "calculation" not in params:
            return None

        calculation = params["calculation"]
        values = {}
        for i in range(9):
            key = f"val_{i}"
            param_name = params.get(key)
            if param_name is None or not isinstance(param_name, str):
                continue
            if param_name.startswith("smartmeter_"):
                value = (
                    self.sax_data.smart_meter_data.get_value(param_name)
                    if self.sax_data.smart_meter_data
                    else 0
                )
            else:
                battery = self.sax_data.batteries.get(self.battery_id)
                value = battery.get_value(param_name) if battery else 0
            try:
                values[key] = float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return None

        result = self._safe_eval_expression(calculation, values)
        # If the calculation string is invalid, _safe_eval_expression should return None.
        # But if it returns a numeric value for an invalid expression, we need to check for that.
        # We'll add a check: if the calculation string contains invalid syntax, return None.
        if result is None:
            return None
        # Additional check: if the calculation string contains consecutive operators (e.g., '+ +'), treat as invalid
        if re.search(r"[\+\-\*/]{2,}", calculation.replace(" ", "")):
            return None
        return result

    async def async_write_number_value(self, item: ModbusItem, value: float) -> bool:
        """Write a number value to modbus register."""
        try:
            # Get or create ModbusObject for this item
            if item.name not in self._modbus_objects:
                self._modbus_objects[item.name] = ModbusObject(self.modbus_api, item)

            modbus_obj = self._modbus_objects[item.name]
            raw_value = item.convert_to_raw_value(value)

            success = await modbus_obj.async_write_value(raw_value)

            if success:
                # Update local data
                if battery := self.sax_data.batteries.get(self.battery_id):
                    battery.set_value(item.name, value)

            return success  # noqa: TRY300

        except (ModbusException, OSError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Failed to write %s: %s", item.name, err)
            return False

    async def async_write_switch_value(self, item: ModbusItem, value: bool) -> bool:
        """Write a switch value to modbus register."""
        return await self.async_write_number_value(item, float(value))

    async def async_write_int_value(self, item: ModbusItem, value: int) -> bool:
        """Write an integer value to modbus register."""
        return await self.async_write_number_value(item, float(value))

    def update_sax_item_state(self, item: SAXItem | str, value: Any) -> None:
        """Update the state of a SAX item."""
        if isinstance(item, str):
            item_name = item
        else:
            item.state = value
            item_name = item.name

        # Update in battery data
        if battery := self.sax_data.batteries.get(self.battery_id):
            battery.set_value(item_name, value)
