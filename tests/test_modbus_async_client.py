"""Tests for ModbusAPI class with AsyncModbusTcpClient."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from pymodbus import ModbusException
from pymodbus.client import AsyncModbusTcpClient
import pytest

from custom_components.sax_battery.const import DEFAULT_PORT
from custom_components.sax_battery.modbusobject import ModbusAPI

_LOGGER = logging.getLogger(__name__)


class TestModbusAPIInitialization:
    """Test ModbusAPI initialization."""

    @pytest.mark.timeout(60)
    async def test_init_with_host(self):
        """Test initialization with host parameter."""
        # Patch AsyncModbusTcpClient to prevent real socket creation
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client = AsyncMock(spec=AsyncModbusTcpClient)
            mock_client_class.return_value = mock_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="bess_a")

            assert api._host == "192.168.1.100"
            assert api._port == 502
            assert api.battery_id == "bess_a"
            assert api.consecutive_failures == 0
            assert api._modbus_client is not None  # Check what actually exists

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
        mock_client.close = MagicMock()

        # Mock comm_params for timeout scaling tests
        mock_comm_params = MagicMock()
        mock_comm_params.timeout_connect = 4.0
        mock_client.comm_params = mock_comm_params

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

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="bess_a")
            # Ensure mocked client is used
            api._modbus_client = mock_modbus_client

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
        mock_modbus_client.close = MagicMock()
        mock_modbus_client.connect = AsyncMock(return_value=True)

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.connect()

        assert result is True

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
        assert modbus_api_instance.is_connected() is True

        mock_modbus_client.connected = False
        assert modbus_api_instance.is_connected() is False


class TestModbusAPIRead:
    """Test ModbusAPI read operations."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = True
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = MagicMock()

        # Mock comm_params for timeout scaling tests
        mock_comm_params = MagicMock()
        mock_comm_params.timeout_connect = 4.0
        mock_client.comm_params = mock_comm_params
        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="bess_a")
            api._modbus_client = mock_modbus_client

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
        mock_modbus_client.connect = AsyncMock(return_value=False)

        result = await modbus_api_instance.read_holding_registers(1, mock_modbus_item)

        assert result is None

    @pytest.mark.enable_socket
    async def test_read_holding_registers_error_response(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test read with error response."""
        mock_modbus_client.connected = True
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
        mock_modbus_client.read_holding_registers = AsyncMock(
            side_effect=ModbusException("Modbus error")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.read_holding_registers(
                1, mock_modbus_item
            )

            assert result is None


class TestModbusAPIWrite:
    """Test ModbusAPI write operations."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = True
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = MagicMock()

        # Mock comm_params for timeout scaling tests
        mock_comm_params = MagicMock()
        mock_comm_params.timeout_connect = 4.0
        mock_client.comm_params = mock_comm_params

        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="bess_a")
            api._modbus_client = mock_modbus_client

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
        mock_modbus_client.write_registers = AsyncMock(return_value=mock_write_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[100])

        with caplog.at_level(logging.DEBUG):
            result = await modbus_api_instance.write_registers(100, mock_modbus_item)

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
        mock_modbus_client.write_registers = AsyncMock(return_value=mock_write_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[90])

        result = await modbus_api_instance.write_registers(100, mock_modbus_item)

        assert result is True

    @pytest.mark.enable_socket
    async def test_write_registers_not_connected(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test write when not connected."""
        mock_modbus_client.connected = False
        mock_modbus_client.connect = AsyncMock(return_value=False)

        result = await modbus_api_instance.write_registers(100, mock_modbus_item)

        assert result is False

    @pytest.mark.enable_socket
    async def test_write_registers_error_response_ignored(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test that error responses are ignored due to hardware bug.

        SAX Battery hardware has a known issue where write_registers returns
        responses with incorrect transaction IDs. To work around this, the
        implementation uses no_response_expected=True, which causes pymodbus
        to ignore response validation and always return success unless an
        exception is raised.

        This test verifies the workaround behavior: even when the mock returns
        an error response, the implementation returns True because response
        validation is bypassed.

        Security:
            OWASP A05: Documents known hardware behavior and implementation workaround
        """
        mock_modbus_client.connected = True

        # Create mock error response matching pymodbus structure
        # The response object itself needs function_code attribute for the check:
        # if hasattr(result, "function_code") and result.function_code == 255:
        error_response = Mock()
        error_response.isError.return_value = True
        error_response.function_code = 255  # Set on response directly, not nested

        mock_modbus_client.write_registers = AsyncMock(return_value=error_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[100])

        result = await modbus_api_instance.write_registers(100, mock_modbus_item)

        # Verify workaround: returns True despite error response
        # because no_response_expected=True bypasses response validation
        assert result is True

        # Verify write was attempted
        mock_modbus_client.write_registers.assert_called_once()

    @pytest.mark.enable_socket
    async def test_write_registers_modbus_exception(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test write with ModbusException returns False.

        The implementation catches ModbusException and logs the error,
        returning False instead of re-raising the exception.

        Security:
            OWASP A03: Validates proper exception handling for Modbus errors
        """
        mock_modbus_client.connected = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=ModbusException("Connection lost")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_registers(100, mock_modbus_item)

            assert result is False
            assert "Modbus exception writing" in caplog.text
            assert "Connection lost" in caplog.text

    @pytest.mark.enable_socket
    async def test_write_registers_network_error(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test write with network OSError returns False.

        The implementation catches OSError and logs the error,
        returning False instead of re-raising the exception.

        Security:
            OWASP A03: Validates proper exception handling for network errors
        """
        mock_modbus_client.connected = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=OSError("Network unreachable")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_registers(100, mock_modbus_item)

            assert result is False
            assert "Network error writing" in caplog.text
            assert "Network unreachable" in caplog.text

    @pytest.mark.enable_socket
    async def test_write_registers_modbus_exception_returns_false(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item
    ):
        """Test write with ModbusException returns False.

        Security:
            OWASP A05: Validates exception handling for hardware failures
        """
        mock_modbus_client.connected = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=ModbusException("Hardware communication error")
        )

        result = await modbus_api_instance.write_registers(100, mock_modbus_item)

        assert result is False

    @pytest.mark.enable_socket
    async def test_write_registers_connection_error_detected(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test that real connection errors are detected and return False.

        Security:
            OWASP A03: Validates proper error detection for network failures
        """
        mock_modbus_client.connected = True

        # Create error response with "connection" in error string
        error_response = Mock()
        error_response.isError.return_value = True
        error_response.function_code = 129  # Not 255
        error_response.__str__ = Mock(return_value="Connection lost to device")

        mock_modbus_client.write_registers = AsyncMock(return_value=error_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[100])

        with caplog.at_level(logging.WARNING):
            result = await modbus_api_instance.write_registers(100, mock_modbus_item)

            assert result is False
            assert "Real write error" in caplog.text
            assert "Connection lost" in caplog.text

    @pytest.mark.enable_socket
    async def test_write_registers_timeout_error_detected(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test that timeout errors are detected and return False.

        Security:
            OWASP A03: Validates proper error detection for timeouts
        """
        mock_modbus_client.connected = True

        # Create error response with "timeout" in error string
        error_response = Mock()
        error_response.isError.return_value = True
        error_response.function_code = 129
        error_response.__str__ = Mock(return_value="Request timeout after 5 seconds")

        mock_modbus_client.write_registers = AsyncMock(return_value=error_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[100])

        with caplog.at_level(logging.WARNING):
            result = await modbus_api_instance.write_registers(100, mock_modbus_item)

            assert result is False
            assert "Real write error" in caplog.text

    @pytest.mark.enable_socket
    async def test_write_registers_exception(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test write with exception and logging."""
        mock_modbus_client.connected = True
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=ModbusException("Write failed")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_registers(100, mock_modbus_item)

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
        mock_modbus_client.write_registers = AsyncMock(
            side_effect=ModbusException("Write failed")
        )

        with caplog.at_level(logging.ERROR):
            result = await modbus_api_instance.write_nominal_power(
                1000.0, 95, mock_modbus_item
            )

            assert result is False

    @pytest.mark.enable_socket
    async def test_write_registers_illegal_function_error_detected(
        self, modbus_api_instance, mock_modbus_client, mock_modbus_item, caplog
    ):
        """Test that illegal function errors are detected and return False.

        Security:
            OWASP A03: Validates proper error detection for Modbus protocol violations
        """
        mock_modbus_client.connected = True

        # Create error response with "illegal function" in error string
        error_response = Mock()
        error_response.isError.return_value = True
        error_response.function_code = 129
        error_response.__str__ = Mock(
            return_value="Modbus Error: Illegal function code 0x10"
        )

        mock_modbus_client.write_registers = AsyncMock(return_value=error_response)
        mock_modbus_client.convert_to_registers = Mock(return_value=[100])

        with caplog.at_level(logging.WARNING):
            result = await modbus_api_instance.write_registers(100, mock_modbus_item)

            assert result is False
            assert "Real write error" in caplog.text


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

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="bess_a")
            api._modbus_client = mock_modbus_client

            yield api

    async def test_connected_property(self, modbus_api_instance, mock_modbus_client):
        """Test connected property alias."""
        mock_modbus_client.connected = True
        assert modbus_api_instance.connected is True

        mock_modbus_client.connected = False
        assert modbus_api_instance.connected is False


class TestModbusAPIEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def mock_modbus_client(self):
        """Create a fully mocked AsyncModbusTcpClient."""
        mock_client = AsyncMock(spec=AsyncModbusTcpClient)
        mock_client.connected = False
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = MagicMock()

        # Mock comm_params for timeout scaling tests
        mock_comm_params = MagicMock()
        mock_comm_params.timeout_connect = 4.0
        mock_client.comm_params = mock_comm_params

        return mock_client

    @pytest.fixture
    def modbus_api_instance(self, mock_modbus_client):
        """Create ModbusAPI instance with mocked client."""
        with patch(
            "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
        ) as mock_client_class:
            mock_client_class.return_value = mock_modbus_client

            api = ModbusAPI(host="192.168.1.100", port=502, battery_id="bess_a")
            api._modbus_client = mock_modbus_client

            yield api

    @pytest.mark.enable_socket
    async def test_consecutive_failures_increment(
        self, modbus_api_instance, mock_modbus_client, caplog
    ):
        """Test consecutive failures increment correctly."""
        mock_modbus_client.connected = False
        mock_modbus_client.connect = AsyncMock(return_value=False)

        initial_failures = modbus_api_instance.consecutive_failures

        with caplog.at_level(logging.WARNING):
            await modbus_api_instance.connect()

        assert modbus_api_instance.consecutive_failures == initial_failures + 1

    @pytest.mark.enable_socket
    async def test_write_with_none_value(self, modbus_api_instance, mock_modbus_client):
        """Test write with None value handles gracefully."""
        mock_modbus_client.connected = True
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


class TestReconnectionBackoff:
    """Test exponential backoff reconnection logic."""

    @pytest.fixture
    async def modbus_api_instance(self):
        """Create ModbusAPI instance for testing."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="bess_a")
        yield api
        await api.close()

    @pytest.mark.enable_socket
    async def test_exponential_backoff_delays(self, modbus_api_instance):
        """Test reconnection delays increase exponentially.

        Security:
            OWASP A05: Validates backoff prevents resource exhaustion
        """
        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            # Reset consecutive_failures to simulate fresh reconnection sequence
            modbus_api_instance.consecutive_failures = 0

            # Simulate 3 consecutive reconnection attempts
            for attempt in range(1, 4):
                # Mock connect to fail
                with patch.object(modbus_api_instance, "connect", return_value=False):
                    await modbus_api_instance._attempt_reconnection(MagicMock())

                # Verify exponential backoff (2^attempt with jitter)
                # After _attempt_reconnection(), consecutive_failures has been incremented
                actual_delay = mock_sleep.call_args[0][0]
                expected_min = 2**attempt
                expected_max = min(expected_min * 1.3, 15.0)

                assert expected_min <= actual_delay <= expected_max, (
                    f"Attempt {attempt}: delay {actual_delay:.2f}s not in range "
                    f"[{expected_min}, {expected_max}] "
                    f"(consecutive_failures={modbus_api_instance.consecutive_failures})"
                )

    @pytest.mark.enable_socket
    async def test_connection_verification_prevents_broken_operations(
        self, modbus_api_instance
    ):
        """Test connection verification prevents operations on broken connections.

        Security:
            OWASP A05: Validates connection state before operations
        """
        # Mock successful connect but failed verification
        with patch.object(modbus_api_instance, "connect", return_value=True):  # noqa: SIM117
            with patch.object(
                modbus_api_instance, "_verify_connection", return_value=False
            ):
                result = await modbus_api_instance._attempt_reconnection(MagicMock())

                assert result is False
                assert modbus_api_instance._modbus_client is None

    @pytest.mark.enable_socket
    async def test_write_nominal_power_no_retry_loop(self, modbus_api_instance):
        """Test write_nominal_power() has no manual retry loop.

        Performance:
            Validates single write operation without retry loops
        """
        modbus_item = MagicMock()
        modbus_item.address = 43
        modbus_item.battery_device_id = 1

        # Mock successful write
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_client.close = MagicMock()
        mock_result = MagicMock()
        mock_result.isError = MagicMock(return_value=False)
        mock_client.write_registers = AsyncMock(return_value=mock_result)
        modbus_api_instance._modbus_client = mock_client

        # Execute write
        result = await modbus_api_instance.write_nominal_power(
            value=1000,
            power_factor=9500,
            modbus_item=modbus_item,
        )

        # Verify single write call (no retries)
        assert result is True
        assert mock_client.write_registers.call_count == 1
