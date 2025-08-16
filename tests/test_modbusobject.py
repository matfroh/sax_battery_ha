"""Test modbusobject.py functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

from pymodbus import ModbusException
from pymodbus.client.mixin import ModbusClientMixin
import pytest

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.modbusobject import ModbusAPI


@pytest.fixture
def mock_modbus_client():
    """Fixture for a mocked ModbusTcpClient."""
    client = MagicMock()
    type(client).connected = PropertyMock(return_value=True)
    client.connect.return_value = True
    client.close.return_value = None
    return client


@pytest.fixture
def modbus_api_obj(mock_modbus_client):
    """Fixture for ModbusAPI using a mocked ModbusTcpClient."""
    with patch(
        "custom_components.sax_battery.modbusobject.ModbusTcpClient",
        return_value=mock_modbus_client,
    ):
        yield ModbusAPI(host="127.0.0.1", port=502, battery_id="test_battery")


class TestModbusAPI:
    """Test ModbusAPI connection and register operations."""

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_connect_success(self, mock_client_class):
        """Test successful connection."""
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.connect.return_value = True
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        result = await api.connect()
        assert result is True

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_connect_failure(self, mock_client_class):
        """Test connection failure."""
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=False)
        mock_client.connect.return_value = False
        mock_client.close.return_value = None
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        result = await api.connect()
        assert result is False
        assert api._failed_reconnect_counter == 1
        assert api._connect_pending is False
        mock_client.close.assert_called_once()

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_connect_exception(self, mock_client_class):
        """Test ModbusException during connect."""
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=False)
        mock_client.connect.side_effect = ModbusException("fail")
        mock_client.close.return_value = None
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        result = await api.connect()
        assert result is False
        assert api._failed_reconnect_counter == 1
        mock_client.close.assert_called_once()

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    def test_close_success(self, mock_client_class):
        """Test successful close."""
        mock_client = MagicMock()
        mock_client.close.return_value = None
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        assert api.close() is True
        mock_client.close.assert_called_once()

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    def test_close_exception(self, mock_client_class):
        """Test ModbusException during close."""
        mock_client = MagicMock()
        mock_client.close.side_effect = ModbusException("fail")
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        assert api.close() is False

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_write_holding_register_success(self, mock_client_class):
        """Test successful write_holding_register."""

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_client.write_register.return_value = mock_result
        mock_client_class.return_value = mock_client

        # Create a proper ModbusItem
        modbus_item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=123,
            factor=1.0,
            battery_slave_id=1,  # Ensure slave ID is set
        )

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        result = await api.write_holding_register(value=10, modbus_item=modbus_item)
        assert result is True
        mock_client.write_register.assert_called_once()

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_write_holding_register_error(self, mock_client_class):
        """Test write_holding_register with error response."""

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_result = MagicMock()
        mock_result.isError.return_value = True
        mock_client.write_register.return_value = mock_result
        mock_client_class.return_value = mock_client

        modbus_item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=123,
            factor=1.0,
        )

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        result = await api.write_holding_register(value=10, modbus_item=modbus_item)
        assert result is False

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_write_holding_register_exception(self, mock_client_class):
        """Test ModbusException during write_holding_register."""

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.write_register.side_effect = ModbusException("fail")
        mock_client_class.return_value = mock_client

        modbus_item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=123,
            factor=1.0,
        )

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        result = await api.write_holding_register(value=10, modbus_item=modbus_item)
        assert result is False

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_read_holding_registers_success(self, mock_client_class):
        """Test successful read_holding_registers."""

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = [1500]
        mock_client.read_holding_registers.return_value = mock_result
        mock_client.convert_from_registers.return_value = [1500]
        mock_client_class.return_value = mock_client

        modbus_item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=10,
            data_type=ModbusClientMixin.DATATYPE.INT16,
        )

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        result = await api.read_holding_registers(count=1, modbus_item=modbus_item)
        assert result == 1500

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_read_holding_registers_error(self, mock_client_class):
        """Test read_holding_registers with error response."""

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_result = MagicMock()
        mock_result.isError.return_value = True
        mock_client.read_holding_registers.return_value = mock_result
        mock_client_class.return_value = mock_client

        modbus_item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=10,
        )

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        result = await api.read_holding_registers(count=1, modbus_item=modbus_item)
        assert result is None

    @patch("custom_components.sax_battery.modbusobject.ModbusTcpClient")
    async def test_read_holding_registers_exception(self, mock_client_class):
        """Test ModbusException during read_holding_registers."""

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.read_holding_registers.side_effect = ModbusException("fail")
        mock_client_class.return_value = mock_client

        modbus_item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=10,
        )

        api = ModbusAPI(host="127.0.0.1", port=502, battery_id="bat")
        # Set the client manually since we're not calling connect
        api._modbus_client = mock_client
        result = await api.read_holding_registers(count=1, modbus_item=modbus_item)
        assert result is None
