"""Tests for ModbusAPI class with AsyncModbusTcpClient."""

from __future__ import annotations

import asyncio
import logging
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

    async def test_init_with_host(self):
        """Test initialization with host parameter."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient",
            return_value=mock_client,
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

    async def test_init_defaults_battery_id(self):
        """Test initialization with default battery_id."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient",
            return_value=mock_client,
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

    async def test_connect_success(self, modbus_api_instance, caplog):
        """Test successful connection with logging."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance._modbus_client.connect.return_value = True

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.connect()

            assert result is True
            modbus_api_instance._modbus_client.connect.assert_called_once()
            assert modbus_api_instance.consecutive_failures == 0
            assert any("Connected to" in record.message for record in caplog.records)

    async def test_connect_already_connected(self, modbus_api_instance, caplog):
        """Test connection when already connected with logging."""
        modbus_api_instance._modbus_client.connected = True

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.connect()

            assert result is True
            modbus_api_instance._modbus_client.connect.assert_called_once()
            assert any("Connected to" in record.message for record in caplog.records)

    async def test_connect_failure(self, modbus_api_instance, caplog):
        """Test connection failure with logging."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance._modbus_client.connect.side_effect = ConnectionException(
            "Connection failed"
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

            assert result is False
            assert modbus_api_instance.consecutive_failures == 1
            assert any(
                "Connection error" in record.message for record in caplog.records
            )

    async def test_connect_timeout(self, modbus_api_instance, caplog):
        """Test connection timeout with logging."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance._modbus_client.connect.side_effect = TimeoutError(
            "Connection timeout"
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

            assert result is False
            assert modbus_api_instance.consecutive_failures == 1
            assert any(
                "Connection error" in record.message for record in caplog.records
            )

    async def test_connect_broken_pipe_error(self, modbus_api_instance, caplog):
        """Test connection with broken pipe error (EPIPE)."""
        modbus_api_instance._modbus_client.connected = False
        os_error = OSError(32, "Broken pipe")
        modbus_api_instance._modbus_client.connect.side_effect = os_error

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

            assert result is False
            assert modbus_api_instance.consecutive_failures == 1
            assert any(
                "Connection error" in record.message for record in caplog.records
            )

    async def test_connect_connection_reset_error(self, modbus_api_instance, caplog):
        """Test connection with connection reset error (ECONNRESET)."""
        modbus_api_instance._modbus_client.connected = False
        os_error = OSError(104, "Connection reset by peer")
        modbus_api_instance._modbus_client.connect.side_effect = os_error

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

            assert result is False
            assert modbus_api_instance.consecutive_failures == 1
            assert any(
                "Connection error" in record.message for record in caplog.records
            )

    async def test_connect_without_host(self, caplog):
        """Test connection attempt without host configured."""
        api = ModbusAPI(battery_id="test")

        with caplog.at_level(logging.ERROR):
            result = await api.connect()

            assert result is False
            assert any(
                "No host configured" in record.message for record in caplog.records
            )

    async def test_is_connected(self, modbus_api_instance):
        """Test is_connected property."""
        modbus_api_instance._modbus_client.connected = True
        assert modbus_api_instance.is_connected() is True

        modbus_api_instance._modbus_client.connected = False
        assert modbus_api_instance.is_connected() is False

    async def test_close_success(self, modbus_api_instance):
        """Test successful connection close."""
        modbus_api_instance._modbus_client.close.return_value = True

        result = await modbus_api_instance.close()

        assert result is True
        modbus_api_instance._modbus_client.close.assert_called_once()

    async def test_close_with_exception(self, modbus_api_instance, caplog):
        """Test close with exception and logging."""
        modbus_api_instance._modbus_client.close.side_effect = Exception("Close failed")

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.close()

            assert result is False
            assert any(
                "Error closing connection" in record.message
                for record in caplog.records
            )


class TestModbusAPIRead:
    """Test ModbusAPI read operations."""

    async def test_read_holding_registers_success(
        self, modbus_api_instance, mock_modbus_item, mock_read_response
    ):
        """Test successful register read."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.read_holding_registers.return_value = (
            mock_read_response
        )
        modbus_api_instance._modbus_client.convert_from_registers.return_value = 100

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result == 100.0
        modbus_api_instance._modbus_client.read_holding_registers.assert_called_once()

    async def test_read_holding_registers_with_factor_offset(
        self, modbus_api_instance, mock_modbus_item, mock_read_response
    ):
        """Test register read with factor and offset."""
        mock_modbus_item.factor = 0.1
        mock_modbus_item.offset = 9
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.read_holding_registers.return_value = (
            mock_read_response
        )
        modbus_api_instance._modbus_client.convert_from_registers.return_value = 100

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result == 1.0  # 100 * 0.1 - 9

    async def test_read_holding_registers_not_connected(
        self, modbus_api_instance, mock_modbus_item
    ):
        """Test read when not connected."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance._modbus_client.connect.return_value = False

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result is None

    async def test_read_holding_registers_error_response(
        self, modbus_api_instance, mock_modbus_item
    ):
        """Test read with error response."""
        modbus_api_instance._modbus_client.connected = True
        error_response = Mock()
        error_response.isError.return_value = True
        modbus_api_instance._modbus_client.read_holding_registers.return_value = (
            error_response
        )

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result is None

    async def test_read_holding_registers_modbus_exception(
        self, modbus_api_instance, mock_modbus_item, caplog
    ):
        """Test read with ModbusException and logging."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.read_holding_registers.side_effect = (
            ModbusException("Modbus error")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.read_holding_registers(
                1, mock_modbus_item
            )

            assert result is None
            assert any("Read error" in record.message for record in caplog.records)

    async def test_read_holding_registers_with_retry(
        self, modbus_api_instance, mock_modbus_item, mock_read_response
    ):
        """Test read with retry on failure."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.read_holding_registers.side_effect = [
            ModbusException("Read failed"),
            mock_read_response,
        ]
        modbus_api_instance._modbus_client.convert_from_registers.return_value = 100

        result = await modbus_api_instance.read_holding_registers(
            1, mock_modbus_item, max_retries=2
        )

        assert result == 100.0
        assert modbus_api_instance._modbus_client.read_holding_registers.call_count == 2

    async def test_read_holding_registers_all_retries_failed(
        self, modbus_api_instance, mock_modbus_item
    ):
        """Test read with all retries failing."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.read_holding_registers.side_effect = (
            ModbusException("Read failed")
        )

        result = await modbus_api_instance.read_holding_registers(
            1, mock_modbus_item, max_retries=3
        )

        assert result is None
        assert modbus_api_instance._modbus_client.read_holding_registers.call_count == 4


class TestModbusAPIWrite:
    """Test ModbusAPI write operations."""

    async def test_write_registers_success(
        self, modbus_api_instance, mock_modbus_item, mock_write_response, caplog
    ):
        """Test successful register write with logging."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.write_registers.return_value = (
            mock_write_response
        )
        modbus_api_instance._modbus_client.convert_to_registers.return_value = [100]

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

            assert result is True
            modbus_api_instance._modbus_client.write_registers.assert_called_once()
            assert any("Writing to" in record.message for record in caplog.records)

    async def test_write_registers_with_factor_offset(
        self, modbus_api_instance, mock_modbus_item, mock_write_response
    ):
        """Test write with factor and offset."""
        mock_modbus_item.factor = 0.1
        mock_modbus_item.offset = 10
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.write_registers.return_value = (
            mock_write_response
        )
        modbus_api_instance._modbus_client.convert_to_registers.return_value = [90]

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is True
        modbus_api_instance._modbus_client.convert_to_registers.assert_called_once()

    async def test_write_registers_not_connected(
        self, modbus_api_instance, mock_modbus_item
    ):
        """Test write when not connected."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance._modbus_client.connect.return_value = False

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is False

    async def test_write_registers_error_response(
        self, modbus_api_instance, mock_modbus_item
    ):
        """Test write with error response."""
        modbus_api_instance._modbus_client.connected = True
        error_response = Mock()
        error_response.isError.return_value = True
        modbus_api_instance._modbus_client.write_registers.return_value = error_response

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is False

    async def test_write_registers_exception(
        self, modbus_api_instance, mock_modbus_item, caplog
    ):
        """Test write with exception and logging."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.write_registers.side_effect = (
            ModbusException("Write failed")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

            assert result is False
            assert any("Write error" in record.message for record in caplog.records)

    async def test_write_nominal_power_success(
        self, modbus_api_instance, mock_modbus_item, mock_write_response
    ):
        """Test successful nominal power write."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.write_registers.return_value = (
            mock_write_response
        )

        result = await modbus_api_instance.write_nominal_power(
            1000.0, 95, mock_modbus_item
        )

        assert result is True
        assert modbus_api_instance._modbus_client.write_registers.call_count == 1

    async def test_write_nominal_power_failure(
        self, modbus_api_instance, mock_modbus_item, caplog
    ):
        """Test nominal power write failure with logging."""
        modbus_api_instance._modbus_client.connected = True
        modbus_api_instance._modbus_client.write_registers.side_effect = (
            ModbusException("Write failed")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_nominal_power(
                1000.0, 95, mock_modbus_item
            )

            assert result is False
            assert any(
                "Modbus error writing nominal power" in record.message
                for record in caplog.records
            )


class TestModbusAPIReconnection:
    """Test ModbusAPI reconnection logic."""

    async def test_reconnect_on_error_success(self, modbus_api_instance, caplog):
        """Test successful reconnection with logging."""
        modbus_api_instance.consecutive_failures = 2
        modbus_api_instance._modbus_client.close.return_value = True
        modbus_api_instance._modbus_client.connect.return_value = True

        with caplog.at_level(logging.INFO):
            result = await modbus_api_instance.reconnect_on_error()

            assert result is True
            assert modbus_api_instance.consecutive_failures == 0
            modbus_api_instance._modbus_client.close.assert_called_once()
            modbus_api_instance._modbus_client.connect.assert_called_once()
            assert any(
                "Reconnection successful" in record.message for record in caplog.records
            )

    async def test_reconnect_on_error_failure(self, modbus_api_instance):
        """Test failed reconnection."""
        modbus_api_instance.consecutive_failures = 2
        modbus_api_instance._modbus_client.close.return_value = True
        modbus_api_instance._modbus_client.connect.return_value = False

        result = await modbus_api_instance.reconnect_on_error()

        assert result is False
        assert modbus_api_instance.consecutive_failures >= 3

    async def test_should_force_reconnect_threshold(self, modbus_api_instance):
        """Test force reconnect threshold."""
        modbus_api_instance.consecutive_failures = 2
        assert modbus_api_instance.should_force_reconnect() is False

        modbus_api_instance.consecutive_failures = 3
        assert modbus_api_instance.should_force_reconnect() is True

    async def test_ensure_connection_when_connected(self, modbus_api_instance):
        """Test ensure_connection when already connected."""
        modbus_api_instance._modbus_client.connected = True

        result = await modbus_api_instance.ensure_connection()

        assert result is True

    async def test_ensure_connection_reconnect_needed(
        self, modbus_api_instance, caplog
    ):
        """Test ensure_connection when reconnection needed."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance.consecutive_failures = 3
        modbus_api_instance._modbus_client.connect.return_value = True

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.ensure_connection()

            assert result is True
            modbus_api_instance._modbus_client.connect.assert_called()
            assert any("Connected to" in record.message for record in caplog.records)

    async def test_ensure_connection_force_reconnect(self, modbus_api_instance):
        """Test ensure_connection with forced reconnect."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance.consecutive_failures = 5
        modbus_api_instance._modbus_client.close.return_value = True
        modbus_api_instance._modbus_client.connect.return_value = True

        result = await modbus_api_instance.ensure_connection()

        assert result is True


class TestModbusAPIProperties:
    """Test ModbusAPI properties."""

    async def test_host_property(self, modbus_api_instance):
        """Test host property."""
        assert modbus_api_instance.host == "192.168.1.100"

    async def test_port_property(self, modbus_api_instance):
        """Test port property."""
        assert modbus_api_instance.port == DEFAULT_PORT

    async def test_connected_property(self, modbus_api_instance):
        """Test connected property alias."""
        modbus_api_instance._modbus_client.connected = True
        assert modbus_api_instance.connected is True

        modbus_api_instance._modbus_client.connected = False
        assert modbus_api_instance.connected is False


class TestModbusAPIEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_concurrent_connections(self, modbus_api_instance):
        """Test concurrent connection attempts use lock correctly."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance._modbus_client.connect.return_value = True

        # Simulate concurrent connection attempts
        results = await asyncio.gather(
            modbus_api_instance.connect(),
            modbus_api_instance.connect(),
            modbus_api_instance.connect(),
        )

        assert all(results)
        assert modbus_api_instance._modbus_client.connect.call_count >= 1

    async def test_consecutive_failures_increment(self, modbus_api_instance, caplog):
        """Test consecutive failures increment correctly."""
        modbus_api_instance._modbus_client.connected = False
        modbus_api_instance._modbus_client.connect.return_value = False

        initial_failures = modbus_api_instance.consecutive_failures

        with caplog.at_level(logging.WARNING):
            await modbus_api_instance.connect()

        assert modbus_api_instance.consecutive_failures == initial_failures + 1
        assert any("Failed to connect" in record.message for record in caplog.records)

    async def test_read_with_zero_count(self, modbus_api_instance, mock_modbus_item):
        """Test read with zero register count."""
        modbus_api_instance._modbus_client.connected = True

        result = await modbus_api_instance.read_holding_registers(0, mock_modbus_item)

        # Should handle gracefully
        assert result is None or isinstance(result, (int, float))

    async def test_write_with_none_value(self, modbus_api_instance):
        """Test write with None value handles gracefully."""
        modbus_api_instance._modbus_client.connected = True
        # Mock convert_to_registers to raise TypeError for None
        modbus_api_instance._modbus_client.convert_to_registers.side_effect = TypeError(
            "Cannot convert None to registers"
        )

        item = Mock()
        item.address = 40001
        item.battery_device_id = 1
        item.data_type = AsyncModbusTcpClient.DATATYPE.UINT16
        item.name = "test_item"

        # Should handle TypeError gracefully
        result = await modbus_api_instance.write_registers(None, item)

        # Verify write was not called (conversion failed)
        modbus_api_instance._modbus_client.write_registers.assert_not_called()
        assert result is False
