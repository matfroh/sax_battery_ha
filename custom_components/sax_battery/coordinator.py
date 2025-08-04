"""SAX Battery data update coordinator."""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import operator
from typing import Any

from pymodbus import ModbusException

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BATTERY_POLL_INTERVAL, DOMAIN
from .items import ApiItem, ModbusItem, SAXItem
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
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{battery_id}",
            update_interval=timedelta(seconds=BATTERY_POLL_INTERVAL),
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
                    # Convert ModbusItem to ApiItem for compatibility
                    api_item = self._convert_modbus_to_api_item(item)
                    self._modbus_objects[item.name] = ModbusObject(
                        self.modbus_api, api_item
                    )

            # Read data from modbus
            data: dict[str, Any] = {}
            for item_name, modbus_obj in self._modbus_objects.items():
                try:
                    raw_value = await modbus_obj.async_read_value()
                    if raw_value is not None:
                        converted_value = modbus_obj.item.convert_raw_value(raw_value)
                        data[item_name] = converted_value
                    else:
                        data[item_name] = None
                except (ModbusException, OSError, TimeoutError) as err:
                    _LOGGER.debug("Failed to read %s: %s", item_name, err)
                    data[item_name] = None

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

    def _convert_modbus_to_api_item(self, modbus_item: ModbusItem) -> ApiItem:
        """Convert ModbusItem to ApiItem for backward compatibility."""
        return ApiItem(
            name=modbus_item.name,
            mformat=modbus_item.mformat,
            mtype=modbus_item.mtype,
            device=modbus_item.device,
            translation_key=modbus_item.translation_key,
            params=modbus_item.params,
            address=modbus_item.address,
            battery_slave_id=modbus_item.battery_slave_id,
            divider=modbus_item.divider,
            entitydescription=modbus_item.entitydescription,
            resultlist=modbus_item.resultlist,
        )

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
                        converted_value = item.convert_raw_value(raw_values[0])
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

    def _calculate_sax_value(self, item: SAXItem) -> float | None:
        """Calculate value for SAX calculated items."""
        if not item.params or "calculation" not in item.params:
            return None

        try:
            # Prepare variables for calculation
            calc_vars: dict[str, float] = {}
            for i in range(9):  # val_0 to val_8
                val_key = f"val_{i}"
                if val_key in item.params:
                    source_key = item.params[val_key]
                    # Get value from appropriate source
                    if source_key.startswith("smartmeter_"):
                        value = (
                            self.sax_data.smart_meter_data.get_value(source_key)
                            if self.sax_data.smart_meter_data
                            else 0
                        )
                    else:
                        # Get from battery data
                        battery = self.sax_data.batteries.get(self.battery_id)
                        value = battery.get_value(source_key) if battery else 0
                    calc_vars[val_key] = float(value or 0)

            # Execute calculation safely using AST
            calculation = item.params["calculation"]
            return self._safe_eval_expression(calculation, calc_vars)

        except (ValueError, KeyError, TypeError) as err:
            _LOGGER.debug("Failed to calculate %s: %s", item.name, err)
            return None

    async def async_write_number_value(
        self, item: ModbusItem | ApiItem, value: float
    ) -> bool:
        """Write a number value to modbus register."""
        try:
            # Convert to ModbusItem for consistent handling
            if isinstance(item, ApiItem):
                modbus_item = self._convert_api_to_modbus_item(item)
            else:
                modbus_item = item

            # Get or create ModbusObject for this item
            if modbus_item.name not in self._modbus_objects:
                api_item = self._convert_modbus_to_api_item(modbus_item)
                self._modbus_objects[modbus_item.name] = ModbusObject(
                    self.modbus_api, api_item
                )

            modbus_obj = self._modbus_objects[modbus_item.name]
            raw_value = modbus_item.convert_to_raw_value(value)

            success = await modbus_obj.async_write_value(raw_value)

            if success:
                # Update local data
                if battery := self.sax_data.batteries.get(self.battery_id):
                    battery.set_value(modbus_item.name, value)
                # Note: We don't set state on ApiItem since it shouldn't have setters

            return success  # noqa: TRY300

        except (ModbusException, OSError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Failed to write %s: %s", item.name, err)
            return False

    def _convert_api_to_modbus_item(self, api_item: ApiItem) -> ModbusItem:
        """Convert ApiItem to ModbusItem for write operations."""
        return ModbusItem(
            name=api_item.name,
            mformat=api_item.mformat,
            mtype=api_item.mtype,
            device=api_item.device,
            translation_key=api_item.translation_key,
            params=api_item.params,
            address=api_item.address,
            battery_slave_id=api_item.battery_slave_id,
            divider=api_item.divider,
            entitydescription=api_item.entitydescription,
            resultlist=list(api_item.resultlist) if api_item.resultlist else [],
        )

    async def async_write_switch_value(
        self, item: ModbusItem | ApiItem, value: bool
    ) -> bool:
        """Write a switch value to modbus register."""
        return await self.async_write_number_value(item, float(value))

    async def async_write_int_value(
        self, item: ModbusItem | ApiItem, value: int
    ) -> bool:
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
