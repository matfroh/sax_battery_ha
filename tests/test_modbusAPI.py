"""Tests for ModbusAPI in the SAX battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from pymodbus import ModbusException
from pymodbus.client.mixin import ModbusClientMixin  # For DATATYPE
import pytest

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.modbusobject import ModbusAPI, ModbusObject


@pytest.fixture
def mock_modbus_client():
    """Fixture for a mocked ModbusTcpClient."""
    client = MagicMock()
    type(client).connected = PropertyMock(return_value=True)
    client.connect.return_value = True
    client.close.return_value = None
    return client


@pytest.fixture
def mock_modbus_api_instance(mock_modbus_client):
    """Fixture for ModbusAPI using a mocked ModbusTcpClient."""
    with patch(
        "custom_components.sax_battery.modbusobject.ModbusTcpClient",
        return_value=mock_modbus_client,
    ):
        yield ModbusAPI(host="127.0.0.1", port=502, battery_id="test_battery")


@pytest.fixture
def mock_modbus_item():
    """Fixture for a basic ModbusItem."""
    return ModbusItem(
        name="test_sensor",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
        address=100,
        battery_slave_id=1,
        data_type=ModbusClientMixin.DATATYPE.INT16,
    )


@pytest.fixture
def mock_modbus_object(mock_modbus_api_instance, mock_modbus_item):
    """Fixture for ModbusObject."""
    return ModbusObject(mock_modbus_api_instance, mock_modbus_item)


class TestModbusObject:
    """Test ModbusObject value reading and writing."""

    @pytest.mark.asyncio
    async def test_async_read_value_success(
        self, mock_modbus_object, mock_modbus_api_instance
    ):
        """Test successful async_read_value."""
        mock_modbus_api_instance.get_device().connected = True
        mock_modbus_api_instance.read_holding_registers = AsyncMock(return_value=1500)
        result = await mock_modbus_object.async_read_value()
        assert result == 1500

    @pytest.mark.asyncio
    async def test_async_read_value_no_data(
        self, mock_modbus_object, mock_modbus_api_instance
    ):
        """Test async_read_value with no data returned."""
        mock_modbus_api_instance.get_device().connected = True
        mock_modbus_api_instance.read_holding_registers = AsyncMock(return_value=None)
        result = await mock_modbus_object.async_read_value()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_read_value_validation_fail(
        self, mock_modbus_object, mock_modbus_api_instance
    ):
        """Test async_read_value when validation returns None."""
        mock_modbus_api_instance.get_device().connected = True
        mock_modbus_api_instance.read_holding_registers = AsyncMock(return_value=None)

        # Create a mock entity description that will cause validation to fail
        mock_entity_desc = MagicMock()
        mock_entity_desc.device_class = "battery"
        mock_modbus_object._modbus_item.entitydescription = mock_entity_desc

        result = await mock_modbus_object.async_read_value()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_read_value_modbus_exception(
        self, mock_modbus_object, mock_modbus_api_instance
    ):
        """Test async_read_value with ModbusException."""
        mock_modbus_api_instance.get_device().connected = True
        mock_modbus_api_instance.read_holding_registers = AsyncMock(
            side_effect=ModbusException("fail")
        )
        result = await mock_modbus_object.async_read_value()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_write_value_success(
        self, mock_modbus_object, mock_modbus_api_instance
    ):
        """Test successful async_write_value."""
        mock_modbus_api_instance.write_holding_register = AsyncMock(return_value=True)
        mock_modbus_object._modbus_item.mtype = TypeConstants.NUMBER
        result = await mock_modbus_object.async_write_value(1234)
        assert result is True

    @pytest.mark.asyncio
    async def test_async_write_value_read_only(
        self, mock_modbus_object, mock_modbus_api_instance
    ):
        """Test async_write_value to read-only register."""
        mock_modbus_api_instance.write_holding_register = AsyncMock(return_value=True)
        mock_modbus_object._modbus_item.mtype = TypeConstants.SENSOR
        result = await mock_modbus_object.async_write_value(1234)
        assert result is False

    @pytest.mark.asyncio
    async def test_async_write_value_modbus_exception(
        self, mock_modbus_object, mock_modbus_api_instance
    ):
        """Test async_write_value with ModbusException."""
        mock_modbus_api_instance.write_holding_register = AsyncMock(
            side_effect=ModbusException("fail")
        )
        mock_modbus_object._modbus_item.mtype = TypeConstants.NUMBER
        result = await mock_modbus_object.async_write_value(1234)
        assert result is False
