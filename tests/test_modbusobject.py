"""Test modbusobject.py functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

from pymodbus import ExceptionResponse, ModbusException
import pytest

from custom_components.sax_battery.const import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.modbusobject import ModbusAPI, ModbusObject
from custom_components.sax_battery.models import SAXBatteryData


@pytest.fixture(name="mock_config_entry")
def mock_config_entry_fixture():
    """Mock config entry for tests."""
    mock_entry = MagicMock()
    mock_entry.data = {
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "battery_count": 1,
    }
    return mock_entry


@pytest.fixture(name="mock_sax_battery_data")
def mock_sax_battery_data_fixture(mock_config_entry):
    """Mock SAXBatteryData for modbus tests."""
    # Create actual SAXBatteryData instance with mocked entry
    return SAXBatteryData(entry=mock_config_entry)


@pytest.fixture(name="mock_modbus_item")
def mock_modbus_item_fixture():
    """Mock ModbusItem for tests."""
    return ModbusItem(
        name="test_item",
        address=100,
        mtype=TypeConstants.SENSOR,
        mformat=FormatConstants.TEMPERATURE,
        translation_key="test_key",
        device=DeviceConstants.SYS,
    )


# Mock the AsyncModbusTcpClient globally to prevent event loop issues
@pytest.fixture(autouse=True)
def mock_modbus_client():
    """Mock AsyncModbusTcpClient to prevent event loop issues."""
    with patch(
        "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
    ) as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock all the properties and methods we need
        type(mock_client).connected = PropertyMock(return_value=False)
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = Mock()
        mock_client.read_input_registers = AsyncMock()
        mock_client.read_holding_registers = AsyncMock()
        mock_client.write_register = AsyncMock()

        yield mock_client


class TestModbusAPI:
    """Test ModbusAPI class."""

    def test_modbus_api_init(self, mock_sax_battery_data, mock_modbus_client) -> None:
        """Test ModbusAPI initialization."""
        api = ModbusAPI(mock_sax_battery_data)

        assert api._connected is False
        assert api._connect_pending is False
        assert api._failed_reconnect_counter == 0
        assert api.entry == mock_sax_battery_data.entry
        assert api._modbus_client == mock_modbus_client

    def test_modbus_api_init_with_missing_host_data(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test ModbusAPI initialization with missing host data."""
        # Remove host data to test defaults
        mock_sax_battery_data.entry.data = {}
        api = ModbusAPI(mock_sax_battery_data)

        assert api._connected is False
        assert api._modbus_client == mock_modbus_client

    def test_modbus_api_init_with_none_host_data(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test ModbusAPI initialization with None host data."""
        mock_sax_battery_data.entry.data = {
            "battery_a_host": None,
            "battery_a_port": None,
        }
        api = ModbusAPI(mock_sax_battery_data)

        assert api._connected is False
        assert api._modbus_client == mock_modbus_client

    async def test_connect_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test successful connection."""
        api = ModbusAPI(mock_sax_battery_data)

        # Mock successful connection
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        mock_modbus_client.connect.return_value = True

        result = await api.connect()

        assert result is True
        assert api._failed_reconnect_counter == 0
        assert api._connect_pending is False
        mock_modbus_client.connect.assert_called_once()

    async def test_connect_failure(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test connection failure."""
        api = ModbusAPI(mock_sax_battery_data)

        # Mock failed connection
        type(mock_modbus_client).connected = PropertyMock(return_value=False)
        mock_modbus_client.connect.return_value = False

        result = await api.connect()

        assert result is False
        assert api._failed_reconnect_counter == 1
        assert api._connect_pending is False
        mock_modbus_client.connect.assert_called_once()
        mock_modbus_client.close.assert_called_once()

    async def test_connect_modbus_exception(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test connection with ModbusException."""
        api = ModbusAPI(mock_sax_battery_data)

        # Mock ModbusException
        type(mock_modbus_client).connected = PropertyMock(return_value=False)
        mock_modbus_client.connect.side_effect = ModbusException("Connection failed")

        result = await api.connect()

        assert result is False
        assert api._failed_reconnect_counter == 1
        assert api._connect_pending is False
        mock_modbus_client.connect.assert_called_once()
        mock_modbus_client.close.assert_called_once()

    async def test_connect_pending_prevents_duplicate(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test that connection pending prevents duplicate connection attempts."""
        api = ModbusAPI(mock_sax_battery_data)
        api._connect_pending = True
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        result = await api.connect()

        assert result is True
        mock_modbus_client.connect.assert_not_called()

    async def test_connect_with_failed_reconnect_counter(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test connection with high failed reconnect counter (non-startup)."""
        api = ModbusAPI(mock_sax_battery_data)
        api._failed_reconnect_counter = 3

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            type(mock_modbus_client).connected = PropertyMock(return_value=True)
            mock_modbus_client.connect.return_value = True

            result = await api.connect(startup=False)

            assert result is True
            mock_sleep.assert_called_once_with(300)  # 15 minutes -> 300 seconds
            mock_modbus_client.connect.assert_called_once()

    async def test_connect_startup_bypasses_wait(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test that startup=True bypasses the failed reconnect wait."""
        api = ModbusAPI(mock_sax_battery_data)
        api._failed_reconnect_counter = 3

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            type(mock_modbus_client).connected = PropertyMock(return_value=True)
            mock_modbus_client.connect.return_value = True

            result = await api.connect(startup=True)

            assert result is True
            mock_sleep.assert_not_called()  # Should not wait on startup
            mock_modbus_client.connect.assert_called_once()

    def test_close_success(self, mock_sax_battery_data, mock_modbus_client) -> None:
        """Test successful close operation."""
        api = ModbusAPI(mock_sax_battery_data)

        result = api.close()

        assert result is True
        mock_modbus_client.close.assert_called_once()

    def test_close_modbus_exception(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test close operation with ModbusException."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_modbus_client.close.side_effect = ModbusException("Close failed")

        result = api.close()

        assert result is False
        mock_modbus_client.close.assert_called_once()

    def test_get_device(self, mock_sax_battery_data, mock_modbus_client) -> None:
        """Test get_device returns modbus client."""
        api = ModbusAPI(mock_sax_battery_data)

        device = api.get_device()

        assert device is mock_modbus_client


class TestModbusObject:
    """Test ModbusObject class."""

    def test_modbus_object_init(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test ModbusObject initialization."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item, no_connect_warn=True)

        assert obj._modbus_item == mock_modbus_item
        assert obj._modbus_client == mock_modbus_client
        assert obj._no_connect_warn is True

    def test_modbus_object_init_default_warn(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test ModbusObject initialization with default warn setting."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        assert obj._no_connect_warn is False

    def test_check_valid_result_temperature(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_valid_result with temperature format."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        with patch.object(obj, "check_temperature", return_value=250) as mock_check:
            result = obj.check_valid_result(1000)

            assert result == 250
            mock_check.assert_called_once_with(1000)

    def test_check_valid_result_percentage(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test check_valid_result with percentage format."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.PERCENTAGE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)

        with patch.object(obj, "check_percentage", return_value=75) as mock_check:
            result = obj.check_valid_result(75)

            assert result == 75
            mock_check.assert_called_once_with(75)

    def test_check_valid_result_status(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test check_valid_result with status format."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.STATUS,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)

        with patch.object(obj, "check_status", return_value=1) as mock_check:
            result = obj.check_valid_result(1)

            assert result == 1
            mock_check.assert_called_once_with(1)

    def test_check_valid_result_default(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test check_valid_result with unknown format."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.UNKNOWN,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)

        result = obj.check_valid_result(42)

        assert result == 42
        assert obj._modbus_item.is_invalid is False

    def test_check_temperature_no_sensor(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_temperature with no sensor installed (-32768)."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        result = obj.check_temperature(-32768)

        assert result is None
        assert obj._modbus_item.is_invalid is True

    def test_check_temperature_zero_case(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_temperature with zero case (32768)."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        result = obj.check_temperature(32768)

        assert result is None
        assert obj._modbus_item.is_invalid is True

    def test_check_temperature_sensor_broken(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_temperature with broken sensor (-32767)."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        result = obj.check_temperature(-32767)

        assert result == -999
        assert obj._modbus_item.is_invalid is False

    def test_check_temperature_normal_positive(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_temperature with normal positive value."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        result = obj.check_temperature(250)

        assert result == 250
        assert obj._modbus_item.is_invalid is False

    def test_check_temperature_negative_complement(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_temperature with negative value needing complement conversion."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        # Test value > 32768 (needs complement conversion)
        result = obj.check_temperature(65000)  # Should convert to negative

        expected = 65000 - 65536  # = -536
        assert result == expected
        assert obj._modbus_item.is_invalid is False

    def test_check_percentage_invalid(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_percentage with invalid value (65535)."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        result = obj.check_percentage(65535)

        assert result is None
        assert obj._modbus_item.is_invalid is True

    def test_check_percentage_valid(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_percentage with valid value."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        result = obj.check_percentage(75)

        assert result == 75
        assert obj._modbus_item.is_invalid is False

    def test_check_status(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_status always returns value and sets valid."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        result = obj.check_status(42)

        assert result == 42
        assert obj._modbus_item.is_invalid is False

    def test_check_valid_response_temperature_negative(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test check_valid_response with negative temperature."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)

        result = obj.check_valid_response(-100)

        expected = -100 + 65536
        assert result == expected

    def test_check_valid_response_temperature_positive(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test check_valid_response with positive temperature."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)

        result = obj.check_valid_response(100)

        assert result == 100

    def test_check_valid_response_other_format(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test check_valid_response with non-temperature format."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.PERCENTAGE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)

        result = obj.check_valid_response(75)

        assert result == 75

    def test_validate_modbus_answer_error(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test validate_modbus_answer with error response."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        # Mock modbus response with error
        mock_response = MagicMock()
        mock_response.isError.return_value = True
        mock_response.exception_code = 2

        result = obj.validate_modbus_answer(mock_response)

        assert result is None
        assert obj._modbus_item.is_invalid is True

    def test_validate_modbus_answer_error_other_code(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test validate_modbus_answer with error response (non-code 2)."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        # Mock modbus response with error
        mock_response = MagicMock()
        mock_response.isError.return_value = True
        mock_response.exception_code = 5

        result = obj.validate_modbus_answer(mock_response)

        assert result is None

    def test_validate_modbus_answer_exception_response(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test validate_modbus_answer with ExceptionResponse."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        # Mock ExceptionResponse
        mock_response = ExceptionResponse(1)
        with patch.object(mock_response, "isError", return_value=False):
            result = obj.validate_modbus_answer(mock_response)

        assert result is None

    def test_validate_modbus_answer_success(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test validate_modbus_answer with successful response."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        # Mock successful modbus response
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        mock_response.registers = [42]

        with patch.object(obj, "check_valid_result", return_value=42) as mock_check:
            result = obj.validate_modbus_answer(mock_response)

            assert result == 42
            mock_check.assert_called_once_with(42)

    def test_validate_modbus_answer_no_registers(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test validate_modbus_answer with empty registers."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)

        # Mock response with no registers
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        mock_response.registers = []

        result = obj.validate_modbus_answer(mock_response)

        assert result is None

    async def test_value_not_connected_with_warning(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test value property when not connected (with warning)."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item, no_connect_warn=False)
        type(mock_modbus_client).connected = PropertyMock(return_value=False)

        result = await obj.value

        assert result is None

    async def test_value_not_connected_no_warning(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test value property when not connected (no warning)."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item, no_connect_warn=True)
        type(mock_modbus_client).connected = PropertyMock(return_value=False)

        result = await obj.value

        assert result is None

    async def test_value_item_invalid(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test value property when item is invalid."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = True

        result = await obj.value

        assert result is None

    async def test_value_sensor_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test value property for sensor type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = False

        mock_response = MagicMock()
        mock_response.registers = [250]
        mock_modbus_client.read_input_registers.return_value = mock_response

        with patch.object(obj, "validate_modbus_answer", return_value=250):
            result = await obj.value

            assert result == 250
            mock_modbus_client.read_input_registers.assert_called_once_with(
                100, slave=1
            )

    async def test_value_sensor_calc_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test value property for sensor calc type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR_CALC,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = False

        mock_response = MagicMock()
        mock_modbus_client.read_input_registers.return_value = mock_response

        with patch.object(obj, "validate_modbus_answer", return_value=300):
            result = await obj.value

            assert result == 300
            mock_modbus_client.read_input_registers.assert_called_once_with(
                100, slave=1
            )

    async def test_value_number_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test value property for number type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.NUMBER,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = False

        mock_response = MagicMock()
        mock_modbus_client.read_holding_registers.return_value = mock_response

        with patch.object(obj, "validate_modbus_answer", return_value=500):
            result = await obj.value

            assert result == 500
            mock_modbus_client.read_holding_registers.assert_called_once_with(
                100, slave=1
            )

    async def test_value_select_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test value property for select type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SELECT,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = False

        mock_response = MagicMock()
        mock_modbus_client.read_holding_registers.return_value = mock_response

        with patch.object(obj, "validate_modbus_answer", return_value=2):
            result = await obj.value

            assert result == 2
            mock_modbus_client.read_holding_registers.assert_called_once_with(
                100, slave=1
            )

    async def test_value_number_ro_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test value property for read-only number type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.NUMBER_RO,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = False

        mock_response = MagicMock()
        mock_modbus_client.read_holding_registers.return_value = mock_response

        with patch.object(obj, "validate_modbus_answer", return_value=600):
            result = await obj.value

            assert result == 600
            mock_modbus_client.read_holding_registers.assert_called_once_with(
                100, slave=1
            )

    async def test_value_modbus_exception(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test value property with ModbusException."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = False

        mock_modbus_client.read_input_registers.side_effect = ModbusException(
            "Read failed"
        )

        result = await obj.value

        assert result is None

    async def test_setvalue_not_connected(
        self, mock_sax_battery_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test setvalue when not connected."""
        api = ModbusAPI(mock_sax_battery_data)
        obj = ModbusObject(api, mock_modbus_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=False)

        # Should return early without doing anything
        await obj.setvalue(100)

        # No assertions needed, just verify it doesn't crash

    async def test_setvalue_sensor_readonly(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test setvalue for read-only sensor type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        await obj.setvalue(100)

        # Should not write for read-only sensor
        mock_modbus_client.write_register.assert_not_called()

    async def test_setvalue_sensor_calc_readonly(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test setvalue for read-only sensor calc type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SENSOR_CALC,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        await obj.setvalue(100)

        # Should not write for read-only sensor calc
        mock_modbus_client.write_register.assert_not_called()

    async def test_setvalue_number_ro_readonly(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test setvalue for read-only number type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.NUMBER_RO,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        await obj.setvalue(100)

        # Should not write for read-only number
        mock_modbus_client.write_register.assert_not_called()

    async def test_setvalue_number_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test setvalue for writable number type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.NUMBER,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        with patch.object(obj, "check_valid_response", return_value=100):
            await obj.setvalue(100)

            mock_modbus_client.write_register.assert_called_once_with(100, 100, slave=1)

    async def test_setvalue_select_success(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test setvalue for select type."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.SELECT,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        with patch.object(obj, "check_valid_response", return_value=2):
            await obj.setvalue(2)

            mock_modbus_client.write_register.assert_called_once_with(100, 2, slave=1)

    async def test_setvalue_modbus_exception(
        self, mock_sax_battery_data, mock_modbus_client
    ) -> None:
        """Test setvalue with ModbusException."""
        api = ModbusAPI(mock_sax_battery_data)
        mock_item = ModbusItem(
            name="test_item",
            address=100,
            mtype=TypeConstants.NUMBER,
            mformat=FormatConstants.TEMPERATURE,
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(api, mock_item)
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        with patch.object(obj, "check_valid_response", return_value=100):
            mock_modbus_client.write_register.side_effect = ModbusException(
                "Write failed"
            )

            # Should not raise exception, just log warning
            await obj.setvalue(100)

            mock_modbus_client.write_register.assert_called_once()
