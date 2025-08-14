"""Test SAX Battery data update coordinator."""

from __future__ import annotations

import ast
from unittest.mock import AsyncMock, MagicMock, patch

from pymodbus import ModbusException
import pytest

from custom_components.sax_battery.coordinator import (
    SAFE_OPERATIONS,
    SAXBatteryCoordinator,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.modbusobject import ModbusAPI
from custom_components.sax_battery.models import SAXBatteryData
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestSAXBatteryCoordinator:
    """Test SAX Battery data update coordinator."""

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        """Create mock Home Assistant instance."""
        return MagicMock(spec=HomeAssistant)

    @pytest.fixture
    def mock_modbus_api(self) -> MagicMock:
        """Create mock Modbus API."""
        api = MagicMock(spec=ModbusAPI)
        api.read_holding_registers = AsyncMock(return_value=[1500])
        return api

    @pytest.fixture
    def mock_smart_meter_data(self) -> MagicMock:
        """Create mock smart meter data."""
        smart_meter = MagicMock()
        smart_meter.get_value.return_value = 1000.0
        smart_meter.set_value = MagicMock()
        return smart_meter

    @pytest.fixture
    def mock_sax_data(self, mock_smart_meter_data) -> MagicMock:
        """Create mock SAX battery data."""
        sax_data = MagicMock(spec=SAXBatteryData)
        sax_data.smart_meter_data = mock_smart_meter_data
        sax_data.should_poll_smart_meter.return_value = True
        sax_data.get_modbus_items_for_battery.return_value = []
        sax_data.get_sax_items_for_battery.return_value = []
        sax_data.get_smart_meter_items.return_value = []
        sax_data.batteries = {}
        return sax_data

    @pytest.fixture
    def coordinator(
        self, mock_hass, mock_sax_data, mock_modbus_api
    ) -> SAXBatteryCoordinator:
        """Create coordinator instance."""
        return SAXBatteryCoordinator(
            mock_hass,
            "battery_a",
            mock_sax_data,
            mock_modbus_api,
            config_entry=MagicMock(),
        )

    @pytest.fixture
    def smart_meter_item(self) -> ModbusItem:
        """Create smart meter modbus item."""
        return ModbusItem(
            name="smartmeter_power",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=1000,
            battery_slave_id=1,
            divider=1.0,
        )

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        """Create mock config entry."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        entry.data = {
            "host": "192.168.1.100",
            "port": 502,
            "battery_id": "battery_a",
            "device_type": DeviceConstants.SYS,
            "batteries": {
                "battery_a": {"role": "master"},
                "battery_b": {"role": "slave"},
            },
            "features": ["smart_meter", "power_control"],
        }
        entry.options = {}
        return entry

    async def test_update_smart_meter_data_success(
        self, coordinator, mock_sax_data, mock_modbus_api, smart_meter_item
    ):
        """Test successful smart meter data update."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_item]
        mock_modbus_api.read_holding_registers.return_value = 1500

        data = {}
        await coordinator._update_smart_meter_data(data)

        # Verify data was updated
        assert data["smartmeter_power"] == 1500.0

        # Verify modbus API was called correctly
        mock_modbus_api.read_holding_registers.assert_called_once_with(1000, 1, 1)

        # Verify smart meter data was updated
        mock_sax_data.smart_meter_data.set_value.assert_called_once_with(
            "smartmeter_power", 1500.0
        )

    async def test_update_smart_meter_data_modbus_exception(
        self, coordinator, mock_sax_data, mock_modbus_api, smart_meter_item
    ):
        """Test smart meter data update with modbus exception."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_item]
        mock_modbus_api.read_holding_registers.side_effect = ModbusException(
            "Connection failed"
        )

        data = {}
        await coordinator._update_smart_meter_data(data)

        # Should set None value on error
        assert data["smartmeter_power"] is None

    async def test_update_smart_meter_data_no_smart_meter(
        self, coordinator, mock_sax_data
    ):
        """Test smart meter data update when no smart meter data exists."""
        mock_sax_data.smart_meter_data = None
        mock_sax_data.get_smart_meter_items.return_value = []

        data = {}
        await coordinator._update_smart_meter_data(data)

        # Should not crash and data should remain empty
        assert data == {}

    async def test_update_smart_meter_data_empty_response(
        self, coordinator, mock_sax_data, mock_modbus_api, smart_meter_item
    ):
        """Test smart meter data update with empty modbus response."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_item]
        mock_modbus_api.read_holding_registers.return_value = None

        data = {}
        await coordinator._update_smart_meter_data(data)

        # Should not add item to data when response is None
        assert "smartmeter_power" not in data

    async def test_update_smart_meter_data_with_divider(
        self, coordinator, mock_sax_data, mock_modbus_api
    ):
        """Test smart meter data update with divider applied."""
        item_with_divider = ModbusItem(
            name="smartmeter_voltage",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=1001,
            battery_slave_id=1,
            divider=10.0,
        )

        mock_sax_data.get_smart_meter_items.return_value = [item_with_divider]
        mock_modbus_api.read_holding_registers.return_value = 2300

        data = {}
        await coordinator._update_smart_meter_data(data)

        # Should apply divider: 2300 / 10.0 = 230.0
        assert data["smartmeter_voltage"] == 230.0

    async def test_update_smart_meter_data_oserror(
        self, coordinator, mock_sax_data, mock_modbus_api, smart_meter_item
    ):
        """Test smart meter data update with OSError."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_item]
        mock_modbus_api.read_holding_registers.side_effect = OSError("Network error")

        data = {}
        await coordinator._update_smart_meter_data(data)

        # Should set None value on error
        assert data["smartmeter_power"] is None

    async def test_update_smart_meter_data_timeout_error(
        self, coordinator, mock_sax_data, mock_modbus_api, smart_meter_item
    ):
        """Test smart meter data update with TimeoutError."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_item]
        mock_modbus_api.read_holding_registers.side_effect = TimeoutError("Timeout")

        data = {}
        await coordinator._update_smart_meter_data(data)

        # Should set None value on error
        assert data["smartmeter_power"] is None


class TestSafeEvalExpression:
    """Test safe expression evaluation."""

    @pytest.fixture
    def coordinator(self) -> SAXBatteryCoordinator:
        """Create minimal coordinator for testing _safe_eval_expression."""
        mock_hass = MagicMock(spec=HomeAssistant)
        mock_sax_data = MagicMock(spec=SAXBatteryData)
        mock_modbus_api = MagicMock(spec=ModbusAPI)
        return SAXBatteryCoordinator(
            mock_hass,
            "battery_a",
            mock_sax_data,
            mock_modbus_api,
            config_entry=MagicMock(),
        )

    def test_safe_eval_simple_addition(self, coordinator):
        """Test safe evaluation of simple addition."""
        result = coordinator._safe_eval_expression(
            "val_0 + val_1", {"val_0": 10, "val_1": 5}
        )
        assert result == 15.0

    def test_safe_eval_simple_subtraction(self, coordinator):
        """Test safe evaluation of simple subtraction."""
        result = coordinator._safe_eval_expression(
            "val_0 - val_1", {"val_0": 10, "val_1": 3}
        )
        assert result == 7.0

    def test_safe_eval_multiplication(self, coordinator):
        """Test safe evaluation of multiplication."""
        result = coordinator._safe_eval_expression(
            "val_0 * val_1", {"val_0": 6, "val_1": 7}
        )
        assert result == 42.0

    def test_safe_eval_division(self, coordinator):
        """Test safe evaluation of division."""
        result = coordinator._safe_eval_expression(
            "val_0 / val_1", {"val_0": 20, "val_1": 4}
        )
        assert result == 5.0

    def test_safe_eval_unary_minus(self, coordinator):
        """Test safe evaluation of unary minus."""
        result = coordinator._safe_eval_expression("-val_0", {"val_0": 15})
        assert result == -15.0

    def test_safe_eval_unary_plus(self, coordinator):
        """Test safe evaluation of unary plus."""
        result = coordinator._safe_eval_expression("+val_0", {"val_0": 15})
        assert result == 15.0

    def test_safe_eval_complex_expression(self, coordinator):
        """Test safe evaluation of complex expression."""
        result = coordinator._safe_eval_expression(
            "val_0 + val_1 * val_2 - val_3",
            {"val_0": 10, "val_1": 2, "val_2": 5, "val_3": 3},
        )
        assert result == 17.0  # 10 + (2 * 5) - 3

    def test_safe_eval_with_constants(self, coordinator):
        """Test safe evaluation with numeric constants."""
        result = coordinator._safe_eval_expression("val_0 + 5", {"val_0": 10})
        assert result == 15.0

    def test_safe_eval_parentheses(self, coordinator):
        """Test safe evaluation with parentheses."""
        result = coordinator._safe_eval_expression(
            "(val_0 + val_1) * val_2", {"val_0": 3, "val_1": 2, "val_2": 4}
        )
        assert result == 20.0  # (3 + 2) * 4 = 20

    def test_safe_eval_nested_operations(self, coordinator):
        """Test safe evaluation with nested operations."""
        result = coordinator._safe_eval_expression(
            "val_0 - (val_1 + val_2) / val_3",
            {"val_0": 20, "val_1": 6, "val_2": 4, "val_3": 2},
        )
        assert result == 15.0  # 20 - (6 + 4) / 2 = 20 - 5 = 15

    def test_safe_eval_division_by_zero(self, coordinator):
        """Test safe evaluation handles division by zero."""
        result = coordinator._safe_eval_expression(
            "val_0 / val_1", {"val_0": 10, "val_1": 0}
        )
        assert result is None

    def test_safe_eval_unknown_variable(self, coordinator):
        """Test safe evaluation handles unknown variables."""
        result = coordinator._safe_eval_expression("val_0 + unknown_var", {"val_0": 10})
        assert result is None

    def test_safe_eval_syntax_error(self, coordinator):
        """Test safe evaluation handles syntax errors."""
        result = coordinator._safe_eval_expression("val_0 + +", {"val_0": 10})
        assert result is None

    def test_safe_eval_empty_expression(self, coordinator):
        """Test safe evaluation handles empty expressions."""
        result = coordinator._safe_eval_expression("", {"val_0": 10})
        assert result is None

    def test_safe_eval_non_numeric_constant(self, coordinator):
        """Test safe evaluation rejects non-numeric constants."""
        result = coordinator._safe_eval_expression("'string'", {})
        assert result is None

    def test_safe_eval_float_conversion(self, coordinator):
        """Test safe evaluation converts integer results to float."""
        result = coordinator._safe_eval_expression("5", {})
        assert result == 5.0
        assert isinstance(result, float)

    def test_safe_eval_float_variables(self, coordinator):
        """Test safe evaluation with float variables."""
        result = coordinator._safe_eval_expression(
            "val_0 + val_1", {"val_0": 10.5, "val_1": 5.3}
        )
        assert result == 15.8

    def test_safe_eval_type_error_handling(self, coordinator):
        """Test safe evaluation handles type errors."""
        # Mock ast.parse to raise TypeError for testing error handling
        with patch("ast.parse", side_effect=TypeError("Type error")):
            result = coordinator._safe_eval_expression("val_0 + val_1", {"val_0": 10})
            assert result is None

    def test_safe_operations_mapping(self):
        """Test that SAFE_OPERATIONS contains expected operations."""
        expected_ops = {
            ast.Add: "add",
            ast.Sub: "sub",
            ast.Mult: "mul",
            ast.Div: "truediv",
            ast.USub: "neg",
            ast.UAdd: "pos",
        }

        for ast_op, expected_name in expected_ops.items():
            assert ast_op in SAFE_OPERATIONS
            # Verify the operation function is correct
            assert SAFE_OPERATIONS[ast_op].__name__ == expected_name


class TestCalculateSaxValue:
    """Test SAX value calculation."""

    @pytest.fixture
    def mock_battery(self) -> MagicMock:
        """Create mock battery."""
        battery = MagicMock()
        battery.get_value.side_effect = lambda key: {
            "sax_discharge_power": 1500,
            "sax_charge_power": 500,
            "sax_voltage": 48.5,
            "sax_current": 30.0,
        }.get(key, 0)
        return battery

    @pytest.fixture
    def coordinator_with_battery(
        self, mock_battery, mock_config_entry
    ) -> SAXBatteryCoordinator:
        """Create coordinator with battery data."""
        mock_hass = MagicMock(spec=HomeAssistant)
        mock_sax_data = MagicMock(spec=SAXBatteryData)
        mock_sax_data.batteries = {"battery_a": mock_battery}
        mock_sax_data.smart_meter_data = MagicMock()
        mock_sax_data.smart_meter_data.get_value.side_effect = lambda key: {
            "smartmeter_total_power": 2000,
            "smartmeter_grid_frequency": 50.0,
        }.get(key, 0)
        mock_modbus_api = MagicMock(spec=ModbusAPI)
        return SAXBatteryCoordinator(
            hass=mock_hass,
            config_entry=mock_config_entry,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

    def test_calculate_sax_value_simple_calculation(self, coordinator_with_battery):
        """Test simple SAX value calculation."""
        sax_item = SAXItem(
            name="total_power",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 - val_1",
                "val_0": "sax_discharge_power",
                "val_1": "sax_charge_power",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result == 1000.0  # 1500 - 500

    def test_calculate_sax_value_with_smart_meter(self, coordinator_with_battery):
        """Test SAX value calculation using smart meter data."""
        sax_item = SAXItem(
            name="total_system_power",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 + val_1",
                "val_0": "smartmeter_total_power",
                "val_1": "sax_discharge_power",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result == 3500.0  # 2000 + 1500

    def test_calculate_sax_value_complex_calculation(self, coordinator_with_battery):
        """Test complex SAX value calculation with multiple variables."""
        sax_item = SAXItem(
            name="power_efficiency",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "(val_0 * val_1) / val_2",
                "val_0": "sax_voltage",
                "val_1": "sax_current",
                "val_2": "sax_discharge_power",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        # (48.5 * 30.0) / 1500 = 1455 / 1500 = 0.97
        assert result == 0.97

    def test_calculate_sax_value_no_calculation_param(self, coordinator_with_battery):
        """Test SAX value calculation with missing calculation parameter."""
        sax_item = SAXItem(
            name="test_item",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "val_0": "sax_voltage",
                # No calculation parameter
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result is None

    def test_calculate_sax_value_no_params(self, coordinator_with_battery):
        """Test SAX value calculation with no parameters."""
        sax_item = SAXItem(
            name="test_item",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params=None,
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result is None

    def test_calculate_sax_value_missing_battery_data(self, coordinator_with_battery):
        """Test SAX value calculation with missing battery data."""
        coordinator_with_battery.sax_data.batteries = {}  # Remove battery

        sax_item = SAXItem(
            name="test_power",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 + val_1",
                "val_0": "sax_discharge_power",
                "val_1": "sax_charge_power",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result == 0.0  # Should default to 0 when battery data missing

    def test_calculate_sax_value_missing_smart_meter_data(
        self, coordinator_with_battery
    ):
        """Test SAX value calculation with missing smart meter data."""
        coordinator_with_battery.sax_data.smart_meter_data = None

        sax_item = SAXItem(
            name="grid_power",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 * 2",
                "val_0": "smartmeter_total_power",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result == 0.0  # Should default to 0 when smart meter data missing

    def test_calculate_sax_value_with_none_values(self, coordinator_with_battery):
        """Test SAX value calculation handles None values from data sources."""
        # Mock battery to return None for some values
        coordinator_with_battery.sax_data.batteries[
            "battery_a"
        ].get_value.side_effect = lambda key: None if key == "sax_voltage" else 1000

        sax_item = SAXItem(
            name="test_calc",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 + val_1",
                "val_0": "sax_voltage",  # Will return None
                "val_1": "sax_current",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result == 1000.0  # None converted to 0, so 0 + 1000 = 1000

    def test_calculate_sax_value_invalid_expression(self, coordinator_with_battery):
        """Test SAX value calculation with invalid expression."""
        sax_item = SAXItem(
            name="invalid_calc",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 + + val_1",  # Invalid syntax
                "val_0": "sax_voltage",
                "val_1": "sax_current",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result is None

    def test_calculate_sax_value_consecutive_operators(self, coordinator_with_battery):
        """Test SAX value calculation rejects consecutive operators."""
        sax_item = SAXItem(
            name="invalid_calc",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 ++ val_1",  # Consecutive operators
                "val_0": "sax_voltage",
                "val_1": "sax_current",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result is None

    def test_calculate_sax_value_all_val_parameters(self, coordinator_with_battery):
        """Test SAX value calculation using all val_0 to val_8 parameters."""
        # Create comprehensive params using all possible val_ keys
        params = {
            "calculation": "val_0 + val_1 + val_2 + val_3 + val_4 + val_5 + val_6 + val_7 + val_8"
        }
        for i in range(9):
            params[f"val_{i}"] = (
                "sax_discharge_power"  # All reference same value (1500)
            )

        sax_item = SAXItem(
            name="sum_all_vals",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params=params,
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result == 13500.0  # 1500 * 9

    def test_calculate_sax_value_type_conversion_error(self, coordinator_with_battery):
        """Test SAX value calculation handles type conversion errors."""
        # Mock battery to return non-numeric value
        coordinator_with_battery.sax_data.batteries[
            "battery_a"
        ].get_value.side_effect = (
            lambda key: "invalid_number" if key == "sax_voltage" else 1000
        )

        sax_item = SAXItem(
            name="type_error_calc",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 + val_1",
                "val_0": "sax_voltage",  # Will return "invalid_number"
                "val_1": "sax_current",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result is None  # Should return None on type conversion error

    def test_calculate_sax_value_partial_parameters(self, coordinator_with_battery):
        """Test SAX value calculation with only some val_ parameters defined."""
        sax_item = SAXItem(
            name="partial_calc",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 + val_2 + val_5",  # Skip val_1, val_3, val_4
                "val_0": "sax_discharge_power",
                "val_2": "sax_voltage",
                "val_5": "sax_current",
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        # 1500 + 48.5 + 30.0 = 1578.5
        assert result == 1578.5

    def test_calculate_sax_value_mixed_data_sources(self, coordinator_with_battery):
        """Test SAX value calculation mixing battery and smart meter data."""
        sax_item = SAXItem(
            name="mixed_calc",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 + val_1 - val_2",
                "val_0": "smartmeter_total_power",  # Smart meter data
                "val_1": "sax_discharge_power",  # Battery data
                "val_2": "smartmeter_grid_frequency",  # Smart meter data
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        # 2000 + 1500 - 50.0 = 3450.0
        assert result == 3450.0

    def test_calculate_sax_value_zero_values(self, coordinator_with_battery):
        """Test SAX value calculation with zero values."""
        # Mock battery to return zero for some values
        coordinator_with_battery.sax_data.batteries[
            "battery_a"
        ].get_value.side_effect = lambda key: 0 if key == "sax_charge_power" else 1500

        sax_item = SAXItem(
            name="zero_calc",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
            params={
                "calculation": "val_0 - val_1",
                "val_0": "sax_discharge_power",  # 1500
                "val_1": "sax_charge_power",  # 0
            },
        )

        result = coordinator_with_battery._calculate_sax_value(sax_item)
        assert result == 1500.0  # 1500 - 0 = 1500
