"""Tests for ModbusAPI in the SAX battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock

from pymodbus import ModbusException
import pytest

from custom_components.sax_battery.enums import TypeConstants
from custom_components.sax_battery.modbusobject import ModbusObject


@pytest.fixture
def mock_modbus_object(mock_modbus_api, mock_modbus_item):
    """Fixture for ModbusObject."""
    return ModbusObject(mock_modbus_api, mock_modbus_item)


class TestModbusObject:
    """Test ModbusObject value reading and writing."""

    @pytest.mark.asyncio
    async def test_async_read_value_success(self, mock_modbus_object, mock_modbus_api):
        """Test successful async_read_value."""
        mock_modbus_api.read_holding_registers = AsyncMock(return_value=1500)
        result = await mock_modbus_object.async_read_value()
        assert result == 1500

    @pytest.mark.asyncio
    async def test_async_read_value_no_data(self, mock_modbus_object, mock_modbus_api):
        """Test async_read_value with no data returned."""
        mock_modbus_api.read_holding_registers = AsyncMock(return_value=None)
        result = await mock_modbus_object.async_read_value()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_read_value_validation_fail(
        self, mock_modbus_object, mock_modbus_api
    ):
        """Test async_read_value when validation returns None."""
        # Mark the item as invalid
        mock_modbus_object._modbus_item.is_invalid = True
        result = await mock_modbus_object.async_read_value()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_read_value_modbus_exception(
        self, mock_modbus_object, mock_modbus_api
    ):
        """Test async_read_value with ModbusException."""
        mock_modbus_api.read_holding_registers = AsyncMock(
            side_effect=ModbusException("fail")
        )
        result = await mock_modbus_object.async_read_value()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_write_value_success(self, mock_modbus_object, mock_modbus_api):
        """Test successful async_write_value."""
        mock_modbus_api.write_holding_register = AsyncMock(return_value=True)
        mock_modbus_object._modbus_item.mtype = TypeConstants.NUMBER
        result = await mock_modbus_object.async_write_value(1234)
        assert result is True

    @pytest.mark.asyncio
    async def test_async_write_value_read_only(
        self, mock_modbus_object, mock_modbus_api
    ):
        """Test async_write_value to read-only register."""
        mock_modbus_api.write_holding_register = AsyncMock(return_value=True)
        mock_modbus_object._modbus_item.mtype = TypeConstants.SENSOR
        result = await mock_modbus_object.async_write_value(1234)
        assert result is False

    @pytest.mark.asyncio
    async def test_async_write_value_modbus_exception(
        self, mock_modbus_object, mock_modbus_api
    ):
        """Test async_write_value with ModbusException."""
        mock_modbus_api.write_holding_register = AsyncMock(
            side_effect=ModbusException("fail")
        )
        mock_modbus_object._modbus_item.mtype = TypeConstants.NUMBER
        result = await mock_modbus_object.async_write_value(1234)
        assert result is False
