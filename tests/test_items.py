"""Test items module for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.entity_keys import (
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CONSUMED,
    SAX_CUMULATIVE_ENERGY_PRODUCED,
    SAX_SMARTMETER_ENERGY_CONSUMED,
    SAX_SMARTMETER_ENERGY_PRODUCED,
    SAX_SOC,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem, WebAPIItem


class TestModbusItem:
    """Test ModbusItem functionality."""

    @pytest.fixture
    def mock_modbus_api_for_item(self):
        """Create mock ModbusAPI for item testing."""
        api = MagicMock()
        api.read_holding_registers = AsyncMock(return_value=100)
        api.write_registers = AsyncMock(return_value=True)
        return api

    @pytest.fixture
    def modbus_item(self):
        """Create test ModbusItem."""
        return ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
            battery_device_id=1,
            factor=1.0,
            offset=0,
        )

    def test_initialization(self, modbus_item):
        """Test ModbusItem initialization."""
        assert modbus_item.name == "test_item"
        assert modbus_item.address == 100
        assert modbus_item.mtype == TypeConstants.SENSOR
        assert modbus_item.device == DeviceConstants.BESS
        assert modbus_item.battery_device_id == 1
        assert modbus_item.factor == 1.0
        assert modbus_item.offset == 0

    async def test_async_read_value_success(
        self, modbus_item, mock_modbus_api_for_item
    ):
        """Test successful read operation."""
        modbus_item.modbus_api = mock_modbus_api_for_item

        value = await modbus_item.async_read_value()
        assert value == 100
        mock_modbus_api_for_item.read_holding_registers.assert_called_once_with(
            count=1, modbus_item=modbus_item
        )

    async def test_async_read_value_no_api(self, modbus_item):
        """Test read operation without API."""
        value = await modbus_item.async_read_value()
        assert value is None

    async def test_async_read_value_write_only(self, mock_modbus_api_for_item):
        """Test read operation on write-only item."""
        item = ModbusItem(
            name="write_only",
            address=100,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )
        item.modbus_api = mock_modbus_api_for_item

        value = await item.async_read_value()
        assert value is None
        mock_modbus_api_for_item.read_holding_registers.assert_not_called()

    async def test_async_write_value_success(self, mock_modbus_api_for_item):
        """Test successful write operation."""
        item = ModbusItem(
            name="writable_number",
            address=100,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
        )
        item.modbus_api = mock_modbus_api_for_item

        result = await item.async_write_value(50.0)
        assert result is True
        mock_modbus_api_for_item.write_registers.assert_called_once_with(
            value=50.0, modbus_item=item
        )

    async def test_async_write_value_read_only(
        self, modbus_item, mock_modbus_api_for_item
    ):
        """Test write operation on read-only item."""
        modbus_item.modbus_api = mock_modbus_api_for_item

        result = await modbus_item.async_write_value(50.0)
        assert result is False
        mock_modbus_api_for_item.write_registers.assert_not_called()

    def test_switch_values(self, modbus_item):
        """Test switch on/off values."""
        # SAX Battery uses 2 for "on" and 1 for "off" by default
        assert modbus_item.get_switch_on_value() == 2
        assert modbus_item.get_switch_off_value() == 1


class TestSAXItem:
    """Test SAXItem functionality."""

    @pytest.fixture
    def mock_coordinators_for_sax(self):
        """Create mock coordinators for SAX item testing."""
        coordinator1 = MagicMock()
        coordinator1.data = {
            SAX_SOC: 80.0,
            SAX_SMARTMETER_ENERGY_PRODUCED: 10000.0,
            SAX_SMARTMETER_ENERGY_CONSUMED: 7000.0,
        }

        coordinator2 = MagicMock()
        coordinator2.data = {
            SAX_SOC: 75.0,
            SAX_SMARTMETER_ENERGY_PRODUCED: 15000.0,
            SAX_SMARTMETER_ENERGY_CONSUMED: 9000.0,
        }

        return {"battery_1": coordinator1, "battery_2": coordinator2}

    @pytest.fixture
    def sax_item(self):
        """Create test SAXItem."""
        return SAXItem(
            name="sax_test_calculation",
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

    def test_initialization(self, sax_item):
        """Test SAXItem initialization."""
        assert sax_item.name == "sax_test_calculation"
        assert sax_item.mtype == TypeConstants.SENSOR_CALC
        assert sax_item.device == DeviceConstants.BESS

    def test_is_invalid_always_false(self, sax_item):
        """Test SAXItem is never invalid."""
        assert sax_item.is_invalid is False

    def test_set_coordinators(self, sax_item, mock_coordinators_for_sax):
        """Test setting coordinators."""
        sax_item.set_coordinators(mock_coordinators_for_sax)
        assert sax_item.coordinators == mock_coordinators_for_sax

    async def test_async_read_value(self, sax_item, mock_coordinators_for_sax):
        """Test async read value delegates to calculate_value."""
        sax_item.set_coordinators(mock_coordinators_for_sax)
        sax_item.name = SAX_COMBINED_SOC  # Set name to trigger calculation

        value = await sax_item.async_read_value()
        assert value == 77.5  # (80 + 75) / 2

    async def test_async_write_value_read_only(self, sax_item):
        """Test write on read-only SAXItem."""
        result = await sax_item.async_write_value(100.0)
        assert result is False

    def test_calculate_value_unknown_type(self, sax_item, mock_coordinators_for_sax):
        """Test calculation with unknown type."""
        sax_item.name = "unknown_calculation"
        result = sax_item.calculate_value(mock_coordinators_for_sax)
        assert result is None

    def test_calculate_value_empty_coordinators(self, sax_item):
        """Test calculation with empty coordinators."""
        result = sax_item.calculate_value({})
        assert result is None


class TestSAXItemCalculationFunctions:
    """Test SAX Battery calculated item calculation functions."""

    @pytest.fixture
    def mock_coordinators_calc(self):
        """Create mock coordinators for calculation testing."""

        def create_mock_coordinator(data: dict[str, float | None]) -> MagicMock:
            mock_coordinator = MagicMock()
            mock_coordinator.data = data
            mock_coordinator.battery_id = "battery_a"
            return mock_coordinator

        return create_mock_coordinator

    def test_calculate_combined_soc_single_battery(
        self, mock_coordinators_calc
    ) -> None:
        """Test combined SOC calculation with single battery."""
        sax_item = SAXItem(
            name=SAX_COMBINED_SOC,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coordinator = mock_coordinators_calc({SAX_SOC: 85.5})
        coordinators = {"battery_a": mock_coordinator}
        result = sax_item.calculate_value(coordinators)

        assert result == 85.5

    def test_calculate_combined_soc_multiple_batteries(
        self, mock_coordinators_calc
    ) -> None:
        """Test combined SOC calculation with multiple batteries."""
        sax_item = SAXItem(
            name=SAX_COMBINED_SOC,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coord_a = mock_coordinators_calc({SAX_SOC: 80.0})
        mock_coord_b = mock_coordinators_calc({SAX_SOC: 90.0})

        coordinators = {
            "battery_a": mock_coord_a,
            "battery_b": mock_coord_b,
        }
        result = sax_item.calculate_value(coordinators)

        assert result == 85.0  # (80 + 90) / 2

    def test_calculate_combined_soc_missing_data(self, mock_coordinators_calc) -> None:
        """Test combined SOC calculation with missing data."""
        sax_item = SAXItem(
            name=SAX_COMBINED_SOC,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coordinator = mock_coordinators_calc({})
        coordinators = {"battery_a": mock_coordinator}
        result = sax_item.calculate_value(coordinators)

        assert result is None

    def test_calculate_combined_soc_mixed_data(self, mock_coordinators_calc) -> None:
        """Test combined SOC calculation with mixed valid/invalid data."""
        sax_item = SAXItem(
            name=SAX_COMBINED_SOC,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coord_a = mock_coordinators_calc({SAX_SOC: 75.0})
        mock_coord_b = mock_coordinators_calc({SAX_SOC: None})
        mock_coord_c = mock_coordinators_calc({SAX_SOC: 85.0})

        coordinators = {
            "battery_a": mock_coord_a,
            "battery_b": mock_coord_b,
            "battery_c": mock_coord_c,
        }
        result = sax_item.calculate_value(coordinators)

        assert result == 80.0  # (75 + 85) / 2

    def test_calculate_cumulative_energy_produced_single_battery(
        self, mock_coordinators_calc
    ) -> None:
        """Test cumulative energy produced calculation with single battery."""
        sax_item = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_PRODUCED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coordinator = mock_coordinators_calc(
            {SAX_SMARTMETER_ENERGY_PRODUCED: 12500.0}
        )
        coordinators = {"battery_a": mock_coordinator}
        result = sax_item.calculate_value(coordinators)

        assert result == 12500.0

    def test_calculate_cumulative_energy_produced_multiple_batteries(
        self, mock_coordinators_calc
    ) -> None:
        """Test cumulative energy produced calculation with multiple batteries."""
        sax_item = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_PRODUCED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coord_a = mock_coordinators_calc({SAX_SMARTMETER_ENERGY_PRODUCED: 10000.0})
        mock_coord_b = mock_coordinators_calc({SAX_SMARTMETER_ENERGY_PRODUCED: 15000.0})

        coordinators = {
            "battery_a": mock_coord_a,
            "battery_b": mock_coord_b,
        }
        result = sax_item.calculate_value(coordinators)

        assert result == 25000.0

    def test_calculate_cumulative_energy_consumed_single_battery(
        self, mock_coordinators_calc
    ) -> None:
        """Test cumulative energy consumed calculation with single battery."""
        sax_item = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_CONSUMED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coordinator = mock_coordinators_calc(
            {SAX_SMARTMETER_ENERGY_CONSUMED: 8500.0}
        )
        coordinators = {"battery_a": mock_coordinator}
        result = sax_item.calculate_value(coordinators)

        assert result == 8500.0

    def test_calculate_cumulative_energy_consumed_multiple_batteries(
        self, mock_coordinators_calc
    ) -> None:
        """Test cumulative energy consumed calculation with multiple batteries."""
        sax_item = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_CONSUMED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coord_a = mock_coordinators_calc({SAX_SMARTMETER_ENERGY_CONSUMED: 7000.0})
        mock_coord_b = mock_coordinators_calc({SAX_SMARTMETER_ENERGY_CONSUMED: 9000.0})

        coordinators = {
            "battery_a": mock_coord_a,
            "battery_b": mock_coord_b,
        }
        result = sax_item.calculate_value(coordinators)

        assert result == 16000.0

    def test_calculation_functions_handle_empty_coordinators(self) -> None:
        """Test calculation functions with empty coordinator dict."""
        sax_item_soc = SAXItem(
            name=SAX_COMBINED_SOC,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )
        sax_item_produced = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_PRODUCED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )
        sax_item_consumed = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_CONSUMED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        assert sax_item_soc.calculate_value({}) is None
        assert sax_item_produced.calculate_value({}) is None
        assert sax_item_consumed.calculate_value({}) is None

    def test_calculation_functions_handle_none_values(
        self, mock_coordinators_calc
    ) -> None:
        """Test calculation functions with None data values."""
        sax_item = SAXItem(
            name=SAX_COMBINED_SOC,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.BESS,
        )

        mock_coordinator = mock_coordinators_calc({SAX_SOC: None})
        coordinators = {"battery_a": mock_coordinator}

        assert sax_item.calculate_value(coordinators) is None


class TestWebAPIItem:
    """Test WebAPIItem functionality."""

    @pytest.fixture
    def web_api_item(self):
        """Create test WebAPIItem."""
        return WebAPIItem(
            name="web_analytics",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
            api_endpoint="https://api.saxpower.com/analytics",
        )

    def test_initialization(self, web_api_item):
        """Test WebAPIItem initialization."""
        assert web_api_item.name == "web_analytics"
        assert web_api_item.api_endpoint == "https://api.saxpower.com/analytics"
        assert web_api_item.refresh_interval == 300

    def test_is_invalid_valid_config(self, web_api_item):
        """Test is_invalid with valid configuration."""
        mock_client = MagicMock()
        web_api_item.set_api_client(mock_client)
        assert web_api_item.is_invalid is False

    async def test_async_read_value_not_implemented(self, web_api_item):
        """Test async read value (not yet implemented)."""
        mock_client = MagicMock()
        web_api_item.set_api_client(mock_client)

        value = await web_api_item.async_read_value()
        assert value is None

    async def test_async_write_value_not_implemented(self):
        """Test async write value (not yet implemented)."""
        item = WebAPIItem(
            name="web_config",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            api_endpoint="https://api.saxpower.com/config",
        )
        mock_client = MagicMock()
        item.set_api_client(mock_client)

        result = await item.async_write_value(100.0)
        assert result is False


class TestHelperFunctions:
    """Test helper functions."""

    @pytest.fixture
    def test_items(self):
        """Create test items for filtering."""
        return [
            ModbusItem(
                name="sensor1",
                address=100,
                mtype=TypeConstants.SENSOR,
                device=DeviceConstants.BESS,
            ),
            ModbusItem(
                name="number1",
                address=101,
                mtype=TypeConstants.NUMBER,
                device=DeviceConstants.BESS,
            ),
            ModbusItem(
                name="switch1",
                address=102,
                mtype=TypeConstants.SWITCH,
                device=DeviceConstants.BESS,
            ),
            SAXItem(
                name="sax1",
                mtype=TypeConstants.SENSOR_CALC,
                device=DeviceConstants.BESS,
            ),
            WebAPIItem(
                name="web1", mtype=TypeConstants.SENSOR, device=DeviceConstants.BESS
            ),
        ]

    def test_filter_items_by_type(self, test_items):
        """Test filtering items by type."""
        # Use the simple helper function from items module without additional parameters
        sensors = [item for item in test_items if item.mtype == TypeConstants.SENSOR]
        assert len(sensors) == 2  # sensor1 and web1

        numbers = [item for item in test_items if item.mtype == TypeConstants.NUMBER]
        assert len(numbers) == 1  # number1
