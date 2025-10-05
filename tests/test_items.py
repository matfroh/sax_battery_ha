"""Comprehensive tests for items module."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, Mock

from pymodbus.client.mixin import ModbusClientMixin
from pymodbus.exceptions import ModbusException
import pytest

from custom_components.sax_battery.entity_keys import (
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CONSUMED,
    SAX_CUMULATIVE_ENERGY_PRODUCED,
    SAX_MIN_SOC,
    SAX_PILOT_POWER,
    SAX_SMARTMETER_ENERGY_CONSUMED,
    SAX_SMARTMETER_ENERGY_PRODUCED,
    SAX_SOC,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem, WebAPIItem


@pytest.fixture
def mock_modbus_api_for_items():
    """Create mock ModbusAPI for item tests."""
    api = AsyncMock()
    api.read_holding_registers = AsyncMock()
    api.write_registers = AsyncMock()
    return api


@pytest.fixture
def modbus_item_fixture(mock_modbus_api_for_items):
    """Create ModbusItem fixture."""
    item = ModbusItem(
        name="test_item",
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.BESS,
        address=40001,
        battery_device_id=1,
        data_type=ModbusClientMixin.DATATYPE.UINT16,
    )
    item.modbus_api = mock_modbus_api_for_items
    return item


@pytest.fixture
def sax_item_fixture():
    """Create SAXItem fixture."""
    return SAXItem(
        name=SAX_COMBINED_SOC,
        mtype=TypeConstants.SENSOR_CALC,
        device=DeviceConstants.SYS,
    )


class TestModbusItemRead:
    """Test ModbusItem read operations."""

    async def test_read_when_invalid(self, modbus_item_fixture):
        """Test read returns None when item is invalid."""
        modbus_item_fixture.is_invalid = True
        result = await modbus_item_fixture.async_read_value()
        assert result is None

    async def test_read_write_only_item(self, modbus_item_fixture):
        """Test read skips write-only items."""
        modbus_item_fixture.mtype = TypeConstants.NUMBER_WO
        result = await modbus_item_fixture.async_read_value()
        assert result is None

    async def test_read_without_api(self, modbus_item_fixture, caplog):
        """Test read fails without ModbusAPI."""
        modbus_item_fixture._modbus_api = None
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_read_value()
            assert result is None
            assert "ModbusAPI not set" in caplog.text

    async def test_read_success(self, modbus_item_fixture, mock_modbus_api_for_items):
        """Test successful read operation."""
        mock_modbus_api_for_items.read_holding_registers.return_value = 100
        result = await modbus_item_fixture.async_read_value()
        assert result == 100

    async def test_read_modbus_exception(
        self, modbus_item_fixture, mock_modbus_api_for_items, caplog
    ):
        """Test read handles ModbusException."""
        mock_modbus_api_for_items.read_holding_registers.side_effect = ModbusException(
            "Read failed"
        )
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_read_value()
            assert result is None
            assert "Failed to read value" in caplog.text


class TestModbusItemWrite:
    """Test ModbusItem write operations."""

    async def test_write_read_only_sensor(self, modbus_item_fixture, caplog):
        """Test write fails for read-only SENSOR type."""
        modbus_item_fixture.mtype = TypeConstants.SENSOR
        with caplog.at_level(logging.WARNING):
            result = await modbus_item_fixture.async_write_value(100)
            assert result is False
            assert "read-only" in caplog.text

    async def test_write_read_only_number_ro(self, modbus_item_fixture, caplog):
        """Test write fails for NUMBER_RO type."""
        modbus_item_fixture.mtype = TypeConstants.NUMBER_RO
        with caplog.at_level(logging.WARNING):
            result = await modbus_item_fixture.async_write_value(100)
            assert result is False

    async def test_write_read_only_sensor_calc(self, modbus_item_fixture, caplog):
        """Test write fails for SENSOR_CALC type."""
        modbus_item_fixture.mtype = TypeConstants.SENSOR_CALC
        with caplog.at_level(logging.WARNING):
            result = await modbus_item_fixture.async_write_value(100)
            assert result is False

    async def test_write_without_api(self, modbus_item_fixture, caplog):
        """Test write fails without ModbusAPI."""
        modbus_item_fixture._modbus_api = None
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value(100)
            assert result is False
            assert "ModbusAPI not set" in caplog.text

    async def test_write_bool_true(
        self, modbus_item_fixture, mock_modbus_api_for_items
    ):
        """Test write boolean true value."""
        mock_modbus_api_for_items.write_registers.return_value = True
        result = await modbus_item_fixture.async_write_value(True)
        assert result is True
        mock_modbus_api_for_items.write_registers.assert_called_once_with(
            value=2, modbus_item=modbus_item_fixture
        )

    async def test_write_bool_false(
        self, modbus_item_fixture, mock_modbus_api_for_items
    ):
        """Test write boolean false value."""
        mock_modbus_api_for_items.write_registers.return_value = True
        result = await modbus_item_fixture.async_write_value(False)
        assert result is True
        mock_modbus_api_for_items.write_registers.assert_called_once_with(
            value=1, modbus_item=modbus_item_fixture
        )

    async def test_write_uint16_valid_range(
        self, modbus_item_fixture, mock_modbus_api_for_items
    ):
        """Test write UINT16 in valid range."""
        mock_modbus_api_for_items.write_registers.return_value = True
        result = await modbus_item_fixture.async_write_value(100.5)
        assert result is True
        mock_modbus_api_for_items.write_registers.assert_called_once_with(
            value=100, modbus_item=modbus_item_fixture
        )

    async def test_write_uint16_out_of_range_low(self, modbus_item_fixture, caplog):
        """Test write UINT16 below valid range."""
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value(-1)
            assert result is False
            assert "out of range for UINT16" in caplog.text

    async def test_write_uint16_out_of_range_high(self, modbus_item_fixture, caplog):
        """Test write UINT16 above valid range."""
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value(70000)
            assert result is False
            assert "out of range for UINT16" in caplog.text

    async def test_write_int16_valid_range(
        self, modbus_item_fixture, mock_modbus_api_for_items
    ):
        """Test write INT16 in valid range."""
        modbus_item_fixture.data_type = ModbusClientMixin.DATATYPE.INT16
        mock_modbus_api_for_items.write_registers.return_value = True
        result = await modbus_item_fixture.async_write_value(-100.5)
        assert result is True
        mock_modbus_api_for_items.write_registers.assert_called_once_with(
            value=-100, modbus_item=modbus_item_fixture
        )

    async def test_write_int16_out_of_range_low(self, modbus_item_fixture, caplog):
        """Test write INT16 below valid range."""
        modbus_item_fixture.data_type = ModbusClientMixin.DATATYPE.INT16
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value(-40000)
            assert result is False
            assert "out of range for INT16" in caplog.text

    async def test_write_int16_out_of_range_high(self, modbus_item_fixture, caplog):
        """Test write INT16 above valid range."""
        modbus_item_fixture.data_type = ModbusClientMixin.DATATYPE.INT16
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value(40000)
            assert result is False
            assert "out of range for INT16" in caplog.text

    async def test_write_uint32_supported(
        self, modbus_item_fixture, mock_modbus_api_for_items
    ):
        """Test write UINT32 is supported."""
        modbus_item_fixture.data_type = ModbusClientMixin.DATATYPE.UINT32
        mock_modbus_api_for_items.write_registers.return_value = True
        result = await modbus_item_fixture.async_write_value(100000)
        assert result is True

    async def test_write_int32_supported(
        self, modbus_item_fixture, mock_modbus_api_for_items
    ):
        """Test write INT32 is supported."""
        modbus_item_fixture.data_type = ModbusClientMixin.DATATYPE.INT32
        mock_modbus_api_for_items.write_registers.return_value = True
        result = await modbus_item_fixture.async_write_value(-100000)
        assert result is True

    async def test_write_unsupported_datatype(self, modbus_item_fixture, caplog):
        """Test write fails for unsupported data type."""
        modbus_item_fixture.data_type = "INVALID_TYPE"
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value(100)
            assert result is False
            assert "Unsupported data type" in caplog.text

    async def test_write_value_error(self, modbus_item_fixture, caplog):
        """Test write handles ValueError."""
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value("invalid")
            assert result is False
            assert "Invalid value" in caplog.text

    async def test_write_modbus_exception(
        self, modbus_item_fixture, mock_modbus_api_for_items, caplog
    ):
        """Test write handles ModbusException."""
        mock_modbus_api_for_items.write_registers.side_effect = ModbusException(
            "Write failed"
        )
        with caplog.at_level(logging.ERROR):
            result = await modbus_item_fixture.async_write_value(100)
            assert result is False
            assert "Modbus error" in caplog.text

    async def test_write_returns_none(
        self, modbus_item_fixture, mock_modbus_api_for_items
    ):
        """Test write handles None return from API."""
        mock_modbus_api_for_items.write_registers.return_value = None
        result = await modbus_item_fixture.async_write_value(100)
        assert result is False


class TestModbusItemSwitchMethods:
    """Test ModbusItem switch helper methods."""

    def test_get_switch_on_value_default(self, modbus_item_fixture):
        """Test get_switch_on_value returns default."""
        assert modbus_item_fixture.get_switch_on_value() == 2

    def test_get_switch_on_value_custom(self, modbus_item_fixture):
        """Test get_switch_on_value with custom value."""
        modbus_item_fixture.switch_on_value = 5
        assert modbus_item_fixture.get_switch_on_value() == 5

    def test_get_switch_off_value_default(self, modbus_item_fixture):
        """Test get_switch_off_value returns default."""
        assert modbus_item_fixture.get_switch_off_value() == 1

    def test_get_switch_off_value_custom(self, modbus_item_fixture):
        """Test get_switch_off_value with custom value."""
        modbus_item_fixture.switch_off_value = 0
        assert modbus_item_fixture.get_switch_off_value() == 0

    def test_get_switch_connected_value(self, modbus_item_fixture):
        """Test get_switch_connected_value."""
        assert modbus_item_fixture.get_switch_connected_value() == 3

    def test_get_switch_standby_value(self, modbus_item_fixture):
        """Test get_switch_standby_value."""
        assert modbus_item_fixture.get_switch_standby_value() == 4

    def test_is_tri_state_switch_default(self, modbus_item_fixture):
        """Test is_tri_state_switch default."""
        assert modbus_item_fixture.is_tri_state_switch() is True

    def test_is_tri_state_switch_false(self, modbus_item_fixture):
        """Test is_tri_state_switch when disabled."""
        modbus_item_fixture.supports_connected_state = False
        assert modbus_item_fixture.is_tri_state_switch() is False

    def test_get_switch_state_name_on(self, modbus_item_fixture):
        """Test get_switch_state_name for on state."""
        assert modbus_item_fixture.get_switch_state_name(2) == "on"

    def test_get_switch_state_name_off(self, modbus_item_fixture):
        """Test get_switch_state_name for off state."""
        assert modbus_item_fixture.get_switch_state_name(1) == "off"

    def test_get_switch_state_name_connected(self, modbus_item_fixture):
        """Test get_switch_state_name for connected state."""
        assert modbus_item_fixture.get_switch_state_name(3) == "connected"

    def test_get_switch_state_name_standby(self, modbus_item_fixture):
        """Test get_switch_state_name for standby state."""
        assert modbus_item_fixture.get_switch_state_name(4) == "standby"

    def test_get_switch_state_name_unknown(self, modbus_item_fixture):
        """Test get_switch_state_name for unknown value."""
        assert modbus_item_fixture.get_switch_state_name(99) == "unknown"

    def test_get_switch_state_name_invalid_type(self, modbus_item_fixture):
        """Test get_switch_state_name with invalid type."""
        assert modbus_item_fixture.get_switch_state_name("invalid") == "unknown"

    def test_is_read_only_sensor(self, modbus_item_fixture):
        """Test is_read_only for SENSOR type."""
        modbus_item_fixture.mtype = TypeConstants.SENSOR
        assert modbus_item_fixture.is_read_only() is True

    def test_is_read_only_number_ro(self, modbus_item_fixture):
        """Test is_read_only for NUMBER_RO type."""
        modbus_item_fixture.mtype = TypeConstants.NUMBER_RO
        assert modbus_item_fixture.is_read_only() is True

    def test_is_read_only_sensor_calc(self, modbus_item_fixture):
        """Test is_read_only for SENSOR_CALC type."""
        modbus_item_fixture.mtype = TypeConstants.SENSOR_CALC
        assert modbus_item_fixture.is_read_only() is True

    def test_is_read_only_writable(self, modbus_item_fixture):
        """Test is_read_only for writable type."""
        modbus_item_fixture.mtype = TypeConstants.NUMBER
        assert modbus_item_fixture.is_read_only() is False

    def test_is_read_only_custom_attribute(self, modbus_item_fixture):
        """Test is_read_only with custom read_only attribute."""
        modbus_item_fixture.read_only = True
        assert modbus_item_fixture.is_read_only() is True


class TestSAXItemRead:
    """Test SAXItem read operations."""

    async def test_read_combined_soc(self, sax_item_fixture):
        """Test read combined SOC calculation."""
        coordinators = {
            "battery_a": Mock(data={SAX_SOC: 80.0}),
            "battery_b": Mock(data={SAX_SOC: 90.0}),
        }
        sax_item_fixture.set_coordinators(coordinators)
        result = await sax_item_fixture.async_read_value()
        assert result == 85.0

    async def test_read_combined_soc_empty(self, sax_item_fixture):
        """Test read combined SOC with no data."""
        sax_item_fixture.set_coordinators({})
        result = await sax_item_fixture.async_read_value()
        assert result is None

    async def test_read_cumulative_energy_produced(self):
        """Test read cumulative energy produced."""
        item = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_PRODUCED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )
        coordinators = {
            "battery_a": Mock(data={SAX_SMARTMETER_ENERGY_PRODUCED: 100.0}),
            "battery_b": Mock(data={SAX_SMARTMETER_ENERGY_PRODUCED: 150.0}),
        }
        item.set_coordinators(coordinators)
        result = await item.async_read_value()
        assert result == 250.0

    async def test_read_cumulative_energy_consumed(self):
        """Test read cumulative energy consumed."""
        item = SAXItem(
            name=SAX_CUMULATIVE_ENERGY_CONSUMED,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )
        coordinators = {
            "battery_a": Mock(data={SAX_SMARTMETER_ENERGY_CONSUMED: 80.0}),
            "battery_b": Mock(data={SAX_SMARTMETER_ENERGY_CONSUMED: 120.0}),
        }
        item.set_coordinators(coordinators)
        result = await item.async_read_value()
        assert result == 200.0

    async def test_read_pilot_power(self):
        """Test read pilot power value."""
        item = SAXItem(
            name=SAX_PILOT_POWER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )
        mock_pilot = Mock()
        mock_pilot.calculated_power = 500.0
        mock_sax_data = Mock(pilot=mock_pilot)
        coordinators = {"battery_a": Mock(sax_data=mock_sax_data)}
        item.set_coordinators(coordinators)
        result = await item.async_read_value()
        assert result == 500.0

    async def test_read_pilot_power_no_pilot(self):
        """Test read pilot power when no pilot service."""
        item = SAXItem(
            name=SAX_PILOT_POWER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )
        item.set_coordinators({})
        result = await item.async_read_value()
        assert result == 0.0

    async def test_read_unknown_calculation(self, caplog):
        """Test read with unknown calculation type."""
        item = SAXItem(
            name="unknown_calc",
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )
        item.set_coordinators({})
        with caplog.at_level(logging.WARNING):
            result = await item.async_read_value()
            assert result is None
            assert "Unknown calculation type" in caplog.text

    async def test_read_min_soc_no_warning(self):
        """Test SAX_MIN_SOC doesn't log warning."""
        item = SAXItem(
            name=SAX_MIN_SOC,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
        )
        item.set_coordinators({})
        result = await item.async_read_value()
        assert result is None


class TestSAXItemWrite:
    """Test SAXItem write operations."""

    async def test_write_read_only(self, sax_item_fixture, caplog):
        """Test write fails for read-only SAX item."""
        with caplog.at_level(logging.WARNING):
            result = await sax_item_fixture.async_write_value(100)
            assert result is False
            assert "read-only SAX item" in caplog.text

    async def test_write_pilot_power_success(self):
        """Test write pilot power successfully."""
        item = SAXItem(
            name=SAX_PILOT_POWER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
        )
        mock_pilot = AsyncMock()
        mock_pilot.set_manual_power = AsyncMock()
        mock_sax_data = Mock(pilot=mock_pilot)
        coordinators = {"battery_a": Mock(sax_data=mock_sax_data)}
        item.set_coordinators(coordinators)

        result = await item.async_write_value(500.0)
        assert result is True
        mock_pilot.set_manual_power.assert_called_once_with(500.0)

    async def test_write_pilot_power_no_pilot(self, caplog):
        """Test write pilot power when no pilot service."""
        item = SAXItem(
            name=SAX_PILOT_POWER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
        )
        item.set_coordinators({})

        with caplog.at_level(logging.ERROR):
            result = await item.async_write_value(500.0)
            assert result is False
            assert "No pilot service found" in caplog.text

    async def test_write_pilot_power_exception(self, caplog):
        """Test write pilot power handles exceptions."""
        item = SAXItem(
            name=SAX_PILOT_POWER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
        )
        mock_pilot = AsyncMock()
        mock_pilot.set_manual_power.side_effect = Exception("Test error")
        mock_sax_data = Mock(pilot=mock_pilot)
        coordinators = {"battery_a": Mock(sax_data=mock_sax_data)}
        item.set_coordinators(coordinators)

        with caplog.at_level(logging.ERROR):
            result = await item.async_write_value(500.0)
            assert result is False
            assert "Failed to write pilot power" in caplog.text

    async def test_write_not_implemented(self):
        """Test write for non-pilot SAX items."""
        item = SAXItem(
            name="other_item",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
        )
        result = await item.async_write_value(100)
        assert result is False


class TestWebAPIItem:
    """Test WebAPIItem operations."""

    async def test_read_invalid(self):
        """Test read when invalid."""
        item = WebAPIItem(
            name="web_api_test",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
        )
        item.is_invalid = True
        result = await item.async_read_value()
        assert result is None

    async def test_read_not_implemented(self):
        """Test read returns None (not implemented)."""
        item = WebAPIItem(
            name="web_api_test",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
        )
        result = await item.async_read_value()
        assert result is None

    async def test_write_read_only(self):
        """Test write fails for read-only types."""
        item = WebAPIItem(
            name="web_api_test",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
        )
        result = await item.async_write_value(100)
        assert result is False

    async def test_write_invalid(self):
        """Test write fails when invalid."""
        item = WebAPIItem(
            name="web_api_test",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
        )
        item.is_invalid = True
        result = await item.async_write_value(100)
        assert result is False

    async def test_write_not_implemented(self):
        """Test write returns False (not implemented)."""
        item = WebAPIItem(
            name="web_api_test",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
        )
        result = await item.async_write_value(100)
        assert result is False

    def test_set_api_client(self):
        """Test set_api_client method."""
        item = WebAPIItem(
            name="web_api_test",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
        )
        mock_client = Mock()
        item.set_api_client(mock_client)
        assert item._web_api_client is mock_client
