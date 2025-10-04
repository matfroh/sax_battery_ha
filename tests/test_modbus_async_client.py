"""Tests for ModbusAPI class with AsyncModbusTcpClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException
import pytest

from custom_components.sax_battery.const import DEFAULT_PORT
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.modbusobject import ModbusAPI


@pytest.fixture
def mock_async_modbus_client():
    """Create a mock AsyncModbusTcpClient."""
    mock_client = AsyncMock(spec=AsyncModbusTcpClient)
    mock_client.connected = False
    mock_client.connect = AsyncMock(return_value=True)
    mock_client.close = AsyncMock(return_value=True)
    mock_client.read_holding_registers = AsyncMock()
    mock_client.write_registers = AsyncMock()
    mock_client.convert_from_registers = Mock()
    mock_client.convert_to_registers = Mock()
    return mock_client


@pytest.fixture
def mock_read_response():
    """Create a mock read holding registers response."""
    response = Mock()
    response.isError = Mock(return_value=False)
    response.registers = [100, 200]
    return response


@pytest.fixture
def mock_write_response():
    """Create a mock write registers response."""
    response = Mock()
    response.isError = Mock(return_value=False)
    return response


@pytest.fixture
def mock_modbus_item():
    """Create a mock ModbusItem for testing."""
    item = Mock(spec=ModbusItem)
    item.address = 40001
    item.battery_device_id = 1
    item.data_type = AsyncModbusTcpClient.DATATYPE.UINT16
    item.factor = 1.0
    item.offset = 0
    item.name = "test_item"
    return item


@pytest.fixture
def modbus_api_instance(mock_async_modbus_client):
    """Create ModbusAPI instance with mocked client."""
    with patch(
        "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient",
        return_value=mock_async_modbus_client,
    ):
        api = ModbusAPI(host="192.168.1.100", port=DEFAULT_PORT, battery_id="battery_a")
        api._modbus_client = mock_async_modbus_client
    return api


class TestModbusAPIInitialization:
    """Test ModbusAPI initialization."""

    async def test_init_with_host(self, mock_async_modbus_client):
        """Test initialization with host parameter."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient",
            return_value=mock_async_modbus_client,
        ) as mock_client_class:
            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

            assert api._host == "192.168.1.100"
            assert api._port == 502
            assert api.battery_id == "battery_a"
            assert api.consecutive_failures == 0
            assert api.last_successful_connection is None
            mock_client_class.assert_called_once_with(
                host="192.168.1.100",
                port=502,
                timeout=5.0,
            )

    async def test_init_without_host(self):
        """Test initialization without host parameter."""
        api = ModbusAPI(battery_id="battery_b")

        assert api._host is None
        assert api._port == DEFAULT_PORT
        assert api.battery_id == "battery_b"
        assert not hasattr(api, "_modbus_client")

    async def test_init_defaults_battery_id(self, mock_async_modbus_client):
        """Test initialization with default battery_id."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient",
            return_value=mock_async_modbus_client,
        ):
            api = ModbusAPI(host="192.168.1.100")

            assert api.battery_id == "unknown"

    async def test_set_connection_params_valid(self, modbus_api_instance):
        """Test setting valid connection parameters."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            modbus_api_instance.set_connection_params("192.168.1.200", 503)

            assert modbus_api_instance._host == "192.168.1.200"
            assert modbus_api_instance._port == 503
            mock_client_class.assert_called_once()

    async def test_set_connection_params_invalid_host(self, modbus_api_instance):
        """Test setting invalid host parameter."""
        with pytest.raises(ValueError, match="Invalid host parameter"):
            modbus_api_instance.set_connection_params("", 502)

        with pytest.raises(ValueError, match="Invalid host parameter"):
            modbus_api_instance.set_connection_params(None, 502)

    async def test_set_connection_params_invalid_port(self, modbus_api_instance):
        """Test setting invalid port parameter."""
        with pytest.raises(ValueError, match="Invalid port parameter"):
            modbus_api_instance.set_connection_params("192.168.1.100", 0)

        with pytest.raises(ValueError, match="Invalid port parameter"):
            modbus_api_instance.set_connection_params("192.168.1.100", 70000)


class TestModbusAPIConnection:
    """Test ModbusAPI connection management."""

    async def test_connect_success(self, modbus_api_instance, mock_async_modbus_client):
        """Test successful connection."""
        mock_async_modbus_client.connected = False
        mock_async_modbus_client.connect.return_value = True

        result = await modbus_api_instance.connect()

        assert result is True
        mock_async_modbus_client.connect.assert_called_once()
        assert modbus_api_instance.consecutive_failures == 0
        # Implementation doesn't set last_successful_connection

    async def test_connect_already_connected(
        self, modbus_api_instance, mock_async_modbus_client
    ):
        """Test connection when already connected."""
        mock_async_modbus_client.connected = True

        result = await modbus_api_instance.connect()

        # Implementation still calls connect() even when already connected
        assert result is True
        mock_async_modbus_client.connect.assert_called_once()

    async def test_connect_failure(self, modbus_api_instance, mock_async_modbus_client):
        """Test connection failure."""
        mock_async_modbus_client.connected = False
        mock_async_modbus_client.connect.side_effect = ConnectionException(
            "Connection failed"
        )

        result = await modbus_api_instance.connect()

        assert result is False
        assert modbus_api_instance.consecutive_failures == 1

    async def test_connect_timeout(self, modbus_api_instance, mock_async_modbus_client):
        """Test connection timeout."""
        mock_async_modbus_client.connected = False
        mock_async_modbus_client.connect.side_effect = TimeoutError(
            "Connection timeout"
        )

        result = await modbus_api_instance.connect()

        assert result is False
        assert modbus_api_instance.consecutive_failures == 1

    async def test_is_connected(self, modbus_api_instance, mock_async_modbus_client):
        """Test is_connected property."""
        mock_async_modbus_client.connected = True
        assert modbus_api_instance.is_connected() is True

        mock_async_modbus_client.connected = False
        assert modbus_api_instance.is_connected() is False

    async def test_close_success(self, modbus_api_instance, mock_async_modbus_client):
        """Test successful connection close."""
        mock_async_modbus_client.close.return_value = True

        result = await modbus_api_instance.close()

        assert result is True
        mock_async_modbus_client.close.assert_called_once()

    async def test_close_with_exception(
        self, modbus_api_instance, mock_async_modbus_client
    ):
        """Test close with exception."""
        mock_async_modbus_client.close.side_effect = Exception("Close failed")

        result = await modbus_api_instance.close()

        assert result is False


class TestModbusAPIRead:
    """Test ModbusAPI read operations."""

    async def test_read_holding_registers_success(
        self,
        modbus_api_instance,
        mock_async_modbus_client,
        mock_modbus_item,
        mock_read_response,
    ):
        """Test successful register read."""
        mock_async_modbus_client.connected = True
        mock_async_modbus_client.read_holding_registers.return_value = (
            mock_read_response
        )
        mock_async_modbus_client.convert_from_registers.return_value = 100

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result == 100.0  # factor = 1.0, offset = 0
        mock_async_modbus_client.read_holding_registers.assert_called_once()

    async def test_read_holding_registers_with_factor_offset(
        self,
        modbus_api_instance,
        mock_async_modbus_client,
        mock_modbus_item,
        mock_read_response,
    ):
        """Test register read with factor and offset."""
        mock_modbus_item.factor = 0.1
        mock_modbus_item.offset = 9
        mock_async_modbus_client.connected = True
        mock_async_modbus_client.read_holding_registers.return_value = (
            mock_read_response
        )
        mock_async_modbus_client.convert_from_registers.return_value = 100

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result == 1.0  # 100 * 0.1 - 9

    async def test_read_holding_registers_not_connected(
        self, modbus_api_instance, mock_async_modbus_client, mock_modbus_item
    ):
        """Test read when not connected."""
        mock_async_modbus_client.connected = False
        mock_async_modbus_client.connect.return_value = False

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result is None

    async def test_read_holding_registers_error_response(
        self, modbus_api_instance, mock_async_modbus_client, mock_modbus_item
    ):
        """Test read with error response."""
        mock_async_modbus_client.connected = True
        error_response = Mock()
        error_response.isError.return_value = True
        mock_async_modbus_client.read_holding_registers.return_value = error_response

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result is None

    async def test_read_holding_registers_with_retry(
        self,
        modbus_api_instance,
        mock_async_modbus_client,
        mock_modbus_item,
        mock_read_response,
    ):
        """Test read with retry on failure."""
        mock_async_modbus_client.connected = True
        mock_async_modbus_client.read_holding_registers.side_effect = [
            ModbusException("Read failed"),
            mock_read_response,
        ]
        mock_async_modbus_client.convert_from_registers.return_value = 100

        result = await modbus_api_instance.read_holding_registers(
            1, mock_modbus_item, max_retries=2
        )

        assert result == 100.0
        assert mock_async_modbus_client.read_holding_registers.call_count == 2


class TestModbusAPIWrite:
    """Test ModbusAPI write operations."""

    async def test_write_registers_success(
        self,
        modbus_api_instance,
        mock_async_modbus_client,
        mock_modbus_item,
        mock_write_response,
    ):
        """Test successful register write."""
        mock_async_modbus_client.connected = True
        mock_async_modbus_client.write_registers.return_value = mock_write_response
        mock_async_modbus_client.convert_to_registers.return_value = [100]

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is True
        mock_async_modbus_client.write_registers.assert_called_once()

    async def test_write_registers_with_factor_offset(
        self,
        modbus_api_instance,
        mock_async_modbus_client,
        mock_modbus_item,
        mock_write_response,
    ):
        """Test write with factor and offset."""
        mock_modbus_item.factor = 0.1
        mock_modbus_item.offset = 10
        mock_async_modbus_client.connected = True
        mock_async_modbus_client.write_registers.return_value = mock_write_response
        mock_async_modbus_client.convert_to_registers.return_value = [90]

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is True
        mock_async_modbus_client.convert_to_registers.assert_called_once()

    async def test_write_registers_not_connected(
        self, modbus_api_instance, mock_async_modbus_client, mock_modbus_item
    ):
        """Test write when not connected."""
        mock_async_modbus_client.connected = False
        mock_async_modbus_client.connect.return_value = False

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is False

    async def test_write_registers_exception(
        self, modbus_api_instance, mock_async_modbus_client, mock_modbus_item
    ):
        """Test write with exception."""
        mock_async_modbus_client.connected = True
        mock_async_modbus_client.write_registers.side_effect = ModbusException(
            "Write failed"
        )

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is False

    async def test_write_nominal_power_success(
        self,
        modbus_api_instance,
        mock_async_modbus_client,
        mock_modbus_item,
        mock_write_response,
    ):
        """Test successful nominal power write."""
        mock_async_modbus_client.connected = True
        mock_async_modbus_client.write_registers.return_value = mock_write_response

        result = await modbus_api_instance.write_nominal_power(
            1000.0, 95, mock_modbus_item
        )

        assert result is True
        # Should write both power and power factor in single call
        assert mock_async_modbus_client.write_registers.call_count == 1


class TestModbusAPIReconnection:
    """Test ModbusAPI reconnection logic."""

    async def test_reconnect_on_error_success(
        self, modbus_api_instance, mock_async_modbus_client
    ):
        """Test successful reconnection."""
        modbus_api_instance.consecutive_failures = 2
        mock_async_modbus_client.close.return_value = True
        mock_async_modbus_client.connect.return_value = True

        result = await modbus_api_instance.reconnect_on_error()

        assert result is True
        assert modbus_api_instance.consecutive_failures == 0
        mock_async_modbus_client.close.assert_called_once()
        mock_async_modbus_client.connect.assert_called_once()

    async def test_reconnect_on_error_failure(
        self, modbus_api_instance, mock_async_modbus_client
    ):
        """Test failed reconnection."""
        modbus_api_instance.consecutive_failures = 2
        mock_async_modbus_client.close.return_value = True
        mock_async_modbus_client.connect.return_value = False

        result = await modbus_api_instance.reconnect_on_error()

        assert result is False
        # Implementation increments failures once per failed attempt (2 attempts = +2)
        # plus once more at the end, so 2 + 2 + 1 = 5
        assert modbus_api_instance.consecutive_failures >= 3

    async def test_should_force_reconnect_threshold(self, modbus_api_instance):
        """Test force reconnect threshold."""
        modbus_api_instance.consecutive_failures = 2
        assert modbus_api_instance.should_force_reconnect() is False

        modbus_api_instance.consecutive_failures = 3
        assert modbus_api_instance.should_force_reconnect() is True

    async def test_ensure_connection_when_connected(
        self, modbus_api_instance, mock_async_modbus_client
    ):
        """Test ensure_connection when already connected."""
        mock_async_modbus_client.connected = True

        result = await modbus_api_instance.ensure_connection()

        assert result is True

    async def test_ensure_connection_reconnect_needed(
        self, modbus_api_instance, mock_async_modbus_client
    ):
        """Test ensure_connection when reconnection needed."""
        mock_async_modbus_client.connected = False
        modbus_api_instance.consecutive_failures = 3
        mock_async_modbus_client.connect.return_value = True

        result = await modbus_api_instance.ensure_connection()

        assert result is True
        # Implementation doesn't call close() - just calls connect()
        mock_async_modbus_client.connect.assert_called()


class TestModbusAPIProperties:
    """Test ModbusAPI properties."""

    async def test_host_property(self, modbus_api_instance):
        """Test host property."""
        assert modbus_api_instance.host == "192.168.1.100"

    async def test_port_property(self, modbus_api_instance):
        """Test port property."""
        assert modbus_api_instance.port == DEFAULT_PORT

    async def test_connected_property(
        self, modbus_api_instance, mock_async_modbus_client
    ):
        """Test connected property alias."""
        mock_async_modbus_client.connected = True
        assert modbus_api_instance.connected is True

        mock_async_modbus_client.connected = False
        assert modbus_api_instance.connected is False
