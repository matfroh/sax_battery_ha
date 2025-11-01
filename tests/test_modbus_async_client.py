"""Tests for ModbusAPI class with AsyncModbusTcpClient."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from pymodbus import ModbusException
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException
import pytest

from custom_components.sax_battery.const import DEFAULT_PORT
from custom_components.sax_battery.modbusobject import ModbusAPI

_LOGGER = logging.getLogger(__name__)


class TestModbusAPIInitialization:
    """Test ModbusAPI initialization."""

    async def test_init_with_host(self):
        """Test initialization with host parameter."""
        # Patch AsyncModbusTcpClient to prevent real socket creation
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client = AsyncMock(spec=AsyncModbusTcpClient)
            mock_client_class.return_value = mock_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

            assert api._host == "192.168.1.100"
            assert api._port == 502
            assert api.battery_id == "battery_a"
            assert api.consecutive_failures == 0
            assert api.last_successful_connection is None
            mock_client_class.assert_called_once_with(
                host="192.168.1.100",
                port=502,
                timeout=3.0,
                retries=0,
                reconnect_delay=0,
            )

    async def test_init_without_host(self):
        """Test initialization without host parameter."""
        api = ModbusAPI(battery_id="battery_b")

        assert api._host is None
        assert api._port == DEFAULT_PORT
        assert api.battery_id == "battery_b"
        assert hasattr(api, "_modbus_client")


class TestModbusAPIConnection:
    """Test ModbusAPI connection management."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient.

        Security:
            OWASP A05: Prevents real network connections in tests
        """
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = False
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client.

        Security:
            OWASP A05: Patches AsyncModbusTcpClient to prevent real network connections
        """
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
            # Ensure mocked client is used
            api._modbus_client = mock_modbus_client
            api._connection_validated = False

            yield api

    @pytest.mark.enable_socket
    async def test_connect_success(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test successful connection with logging."""
        mock_modbus_client.connected = False
        mock_modbus_client.connect = AsyncMock(return_value=True)

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.connect()

        assert result is True
        assert mock_modbus_client.connect.call_count >= 1

    @pytest.mark.enable_socket
    async def test_connect_already_connected(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test connection when already connected with logging."""
        # Set client to already connected and validated state
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.close = AsyncMock()
        mock_modbus_client.connect = AsyncMock(return_value=True)

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.connect()

        assert result is True

    @pytest.mark.enable_socket
    async def test_connect_failure(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test connection failure with logging."""
        mock_modbus_client.connected = False
        mock_modbus_client.connect = AsyncMock(
            side_effect=ConnectionException("Connection failed")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

        assert result is False
        assert modbus_api_instance.consecutive_failures > 0

    @pytest.mark.enable_socket
    async def test_connect_timeout(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test connection timeout with logging."""
        mock_modbus_client.connected = False
        mock_modbus_client.connect = AsyncMock(
            side_effect=TimeoutError("Connection timeout")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

        assert result is False

    @pytest.mark.enable_socket
    async def test_connect_broken_pipe_error(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test connection with broken pipe error (EPIPE)."""
        mock_modbus_client.connected = False
        os_error = OSError(32, "Broken pipe")
        mock_modbus_client.connect = AsyncMock(side_effect=os_error)

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

        assert result is False

    @pytest.mark.enable_socket
    async def test_connect_connection_reset_error(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test connection with connection reset error (ECONNRESET)."""
        mock_modbus_client.connected = False
        os_error = OSError(104, "Connection reset by peer")
        mock_modbus_client.connect = AsyncMock(side_effect=os_error)

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.connect()

        assert result is False

    async def test_is_connected(self, modbus_api_instance, mock_modbus_client):
        """Test is_connected property."""
        # Mock the connected property and validation state
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        assert modbus_api_instance.is_connected() is True

        mock_modbus_client.connected = False
        modbus_api_instance._connection_validated = False
        assert modbus_api_instance.is_connected() is False


class TestModbusAPIRead:
    """Test ModbusAPI read operations."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = True
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
            api._modbus_client = mock_modbus_client
            api._connection_validated = True

            yield api

    @pytest.fixture
    def mock_modbus_item(self):
        """Create mock ModbusItem."""
        item = MagicMock()
        item.address = 40001
        item.battery_device_id = 1
        item.data_type = AsyncModbusTcpClient.DATATYPE.UINT16
        item.factor = 1
        item.offset = 0
        item.name = "test_item"
        return item

    @pytest.fixture
    def mock_read_response(self):
        """Create mock read response."""
        response = Mock()
        response.isError.return_value = False
        response.registers = [100]
        return response

    @pytest.mark.enable_socket
    async def test_read_holding_registers_success(
        self,
        modbus_api_instance,
        mock_modbus_client,
        mock_modbus_item,
        mock_read_response,
    ):
        """Test successful register read."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=mock_read_response
        )
        mock_modbus_client.convert_from_registers = Mock(return_value=100)

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result == 100

    @pytest.mark.enable_socket
    async def test_read_holding_registers_with_factor_offset(
        self,
        modbus_api_instance,
        mock_modbus_client,
        mock_modbus_item,
        mock_read_response,
    ):
        """Test register read with factor and offset."""
        mock_modbus_item.factor = 0.1
        mock_modbus_item.offset = 9
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=mock_read_response
        )
        mock_modbus_client.convert_from_registers = Mock(return_value=100)

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result == 1.0

    @pytest.mark.enable_socket
    async def test_read_holding_registers_not_connected(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test read when not connected."""
        mock_modbus_client.connected = False
        modbus_api_instance._connection_validated = False
        mock_modbus_client.connect = AsyncMock(return_value=False)

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result is None

    @pytest.mark.enable_socket
    async def test_read_holding_registers_error_response(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test read with error response."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        error_response = Mock()
        error_response.isError.return_value = True
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=error_response
        )

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result is None

    @pytest.mark.enable_socket
    async def test_read_holding_registers_modbus_exception(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test read with ModbusException and logging."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.read_holding_registers = AsyncMock(
            side_effect=ModbusException("Modbus error")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.read_holding_registers(
                1, mock_modbus_item
            )

            assert result is None

    @pytest.mark.enable_socket
    async def test_read_holding_registers_with_retry(
        self,
        modbus_api_instance,
        mock_modbus_client,
        mock_modbus_item,
        mock_read_response,
    ):
        """Test read with retry on failure."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.read_holding_registers = AsyncMock(
            side_effect=[
                ModbusException("Read failed"),
                mock_read_response,
            ]
        )
        mock_modbus_client.convert_from_registers = Mock(return_value=100)

        result = await modbus_api_instance.read_holding_registers(
            1, mock_modbus_item, max_retries=2
        )

        assert result == 100.0
        assert mock_modbus_client.read_holding_registers.call_count == 2

    @pytest.mark.enable_socket
    async def test_read_holding_registers_all_retries_failed(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test read with all retries failing."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.read_holding_registers = AsyncMock(
            side_effect=ModbusException("Read failed")
        )

        result = await modbus_api_instance.read_holding_registers(
            1, mock_modbus_item, max_retries=3
        )

        assert result is None
        assert mock_modbus_client.read_holding_registers.call_count == 4


class TestModbusAPIWrite:
    """Test ModbusAPI write operations."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = True
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
            api._modbus_client = mock_modbus_client
            api._connection_validated = True

            yield api

    @pytest.fixture
    def mock_modbus_item(self):
        """Create mock ModbusItem."""
        item = MagicMock()
        item.address = 40001
        item.battery_device_id = 1
        item.data_type = AsyncModbusTcpClient.DATATYPE.UINT16
        item.factor = 1
        item.offset = 0
        item.name = "test_item"
        return item

    @pytest.fixture
    def mock_write_response(self):
        """Create mock write response."""
        response = Mock()
        response.isError.return_value = False
        return response

    @pytest.mark.enable_socket
    async def test_write_registers_success(
        self,
        modbus_api_instance,
        mock_modbus_client,
        mock_modbus_item,
        mock_write_response,
        caplog,
    ):
        """Test successful register write with logging."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.write_registers = AsyncMock(return_value=mock_write_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[100])

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

            assert result is True
            mock_modbus_client.write_registers.assert_called_once()

    @pytest.mark.enable_socket
    async def test_write_registers_with_factor_offset(
        self,
        modbus_api_instance,
        mock_modbus_client,
        mock_modbus_item,
        mock_write_response,
    ):
        """Test write with factor and offset."""
        mock_modbus_item.factor = 0.1
        mock_modbus_item.offset = 10
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.write_registers = AsyncMock(return_value=mock_write_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[90])

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is True

    @pytest.mark.enable_socket
    async def test_write_registers_not_connected(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test write when not connected."""
        mock_modbus_client.connected = False
        modbus_api_instance._connection_validated = False
        mock_modbus_client.connect = AsyncMock(return_value=False)

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is False

    @pytest.mark.enable_socket
    async def test_write_registers_error_response(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test write with error response.

        Note: SAX Battery has known issue with write_registers not returning
        correct response (wrong transaction ID). Implementation ignores response
        errors and returns True unless an exception is raised.

        Security:
            OWASP A05: Documents known hardware behavior for security review
        """
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        error_response = Mock()
        error_response.isError.return_value = True
        mock_modbus_client.write_registers = AsyncMock(return_value=error_response)

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        # SAX Battery hardware bug: write_registers response has wrong transaction ID
        # Implementation returns True unless an exception is raised
        assert result is True

    @pytest.mark.enable_socket
    async def test_write_registers_modbus_exception_returns_false(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test write with ModbusException returns False.

        Security:
            OWASP A05: Validates exception handling for hardware failures
        """
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=ModbusException("Hardware communication error")
        )

        result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

        assert result is False

    @pytest.mark.enable_socket
    async def test_write_registers_exception(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test write with exception and logging."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=ModbusException("Write failed")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_registers(100.0, mock_modbus_item)

            assert result is False

    @pytest.mark.enable_socket
    async def test_write_nominal_power_success(
        self,
        modbus_api_instance,
        mock_modbus_client,
        mock_modbus_item,
        mock_write_response,
    ):
        """Test successful nominal power write."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.write_registers = AsyncMock(return_value=mock_write_response)

        result = await modbus_api_instance.write_nominal_power(
            1000.0, 95, mock_modbus_item
        )

        assert result is True
        assert mock_modbus_client.write_registers.call_count == 1

    @pytest.mark.enable_socket
    async def test_write_nominal_power_failure(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test nominal power write failure with logging."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=ModbusException("Write failed")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_nominal_power(
                1000.0, 95, mock_modbus_item
            )

            assert result is False
            # With max_retries=2, we expect 3 attempts total (initial + 2 retries)
            assert mock_modbus_client.write_registers.await_count == 3

    @pytest.mark.enable_socket
    async def test_write_nominal_power_retry_success(
        self,
        modbus_api_instance,
        mock_modbus_client,
        mock_modbus_item,
        mock_write_response,
    ):
        """Test nominal power write succeeds after transient failure."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=[
                ModbusException("Transient failure"),
                mock_write_response,
            ]
        )

        result = await modbus_api_instance.write_nominal_power(
            1000.0, 95, mock_modbus_item
        )

        assert result is True
        assert mock_modbus_client.write_registers.await_count == 2


class TestModbusAPIProperties:
    """Test ModbusAPI property accessors."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = False
        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
            api._modbus_client = mock_modbus_client

            yield api

    async def test_connected_property(self, modbus_api_instance, mock_modbus_client):
        """Test connected property alias."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        assert modbus_api_instance.connected is True

        mock_modbus_client.connected = False
        modbus_api_instance._connection_validated = False
        assert modbus_api_instance.connected is False


class TestModbusAPIEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = False
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
            api._modbus_client = mock_modbus_client
            api._connection_validated = False

            yield api

    @pytest.mark.enable_socket
    async def test_concurrent_connections(
        self, modbus_api_instance, mock_modbus_client
    ):
        """Test concurrent connection attempts use lock correctly."""
        mock_modbus_client.connected = False
        modbus_api_instance._connection_validated = False
        mock_modbus_client.connect = AsyncMock(return_value=True)

        results = await asyncio.gather(
            modbus_api_instance.connect(),
            modbus_api_instance.connect(),
            modbus_api_instance.connect(),
        )

        assert all(results)
        # Due to locking, connect may be called less than 3 times
        assert mock_modbus_client.connect.call_count >= 1

    @pytest.mark.enable_socket
    async def test_consecutive_failures_increment(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test consecutive failures increment correctly."""
        mock_modbus_client.connected = False
        modbus_api_instance._connection_validated = False
        mock_modbus_client.connect = AsyncMock(return_value=False)

        initial_failures = modbus_api_instance.consecutive_failures

        with caplog.at_level(logging.WARNING):
            await modbus_api_instance.connect()

        assert modbus_api_instance.consecutive_failures == initial_failures + 1

    @pytest.mark.enable_socket
    async def test_write_with_none_value(self, modbus_api_instance, mock_modbus_client):
        """Test write with None value handles gracefully."""
        mock_modbus_client.connected = True
        modbus_api_instance._connection_validated = True
        mock_modbus_client.convert_to_registers = Mock(
            side_effect=TypeError("Cannot convert None to registers")
        )

        item = Mock()
        item.address = 40001
        item.battery_device_id = 1
        item.data_type = AsyncModbusTcpClient.DATATYPE.UINT16
        item.name = "test_item"

        result = await modbus_api_instance.write_registers(None, item)

        mock_modbus_client.write_registers.assert_not_called()
        assert result is False
