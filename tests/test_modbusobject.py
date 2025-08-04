"""Test modbusobject.py functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from pymodbus import ModbusException

from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ApiItem, StatusItem
from custom_components.sax_battery.modbusobject import (
    ModbusAPI,
    ModbusItemValidator,
    ModbusObject,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription


class TestModbusAPI:
    """Test ModbusAPI class."""

    def test_modbus_api_init_required_params(self) -> None:
        """Test ModbusAPI initialization with required parameters."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        assert api._host == "192.168.1.100"
        assert api._port == 502
        assert api.battery_id == "battery_a"
        assert api._connected is False
        assert api._connect_pending is False
        assert api._failed_reconnect_counter == 0
        assert api._modbus_client is not None

    def test_modbus_api_init_custom_values(self) -> None:
        """Test ModbusAPI initialization with custom values."""
        api = ModbusAPI(host="10.0.0.50", port=503, battery_id="battery_b")

        assert api._host == "10.0.0.50"
        assert api._port == 503
        assert api.battery_id == "battery_b"

    @patch("custom_components.sax_battery.modbusobject.AsyncModbusTcpClient")
    async def test_connect_success_startup(self, mock_client_class) -> None:
        """Test successful connection on startup."""
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.connect = AsyncMock()
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
        result = await api.connect(startup=True)

        assert result is True
        assert api._failed_reconnect_counter == 0
        assert api._connect_pending is False
        mock_client.connect.assert_called_once()

    @patch("custom_components.sax_battery.modbusobject.AsyncModbusTcpClient")
    async def test_connect_failure(self, mock_client_class) -> None:
        """Test connection failure."""
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=False)
        mock_client.connect = AsyncMock()
        mock_client.close = MagicMock()
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
        result = await api.connect()

        assert result is False
        assert api._failed_reconnect_counter == 1
        assert api._connect_pending is False
        mock_client.close.assert_called_once()

    @patch("custom_components.sax_battery.modbusobject.AsyncModbusTcpClient")
    async def test_connect_modbus_exception(self, mock_client_class) -> None:
        """Test connection with ModbusException."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(
            side_effect=ModbusException("Connection failed")
        )
        mock_client.close = MagicMock()
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
        result = await api.connect()

        assert result is False
        assert api._failed_reconnect_counter == 1
        assert api._connect_pending is False
        mock_client.close.assert_called_once()

    @patch("custom_components.sax_battery.modbusobject.AsyncModbusTcpClient")
    async def test_connect_pending_connection(self, mock_client_class) -> None:
        """Test connect when connection is already pending."""
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client_class.return_value = mock_client

        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
        api._connect_pending = True

        result = await api.connect()

        assert result is True  # Returns current connection status

    @patch("custom_components.sax_battery.modbusobject.AsyncModbusTcpClient")
    @patch("custom_components.sax_battery.modbusobject.asyncio.sleep")
    async def test_connect_retry_limit_wait(
        self, mock_sleep, mock_client_class
    ) -> None:
        """Test connection retry limit triggers wait."""
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.connect = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_sleep.return_value = None

        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
        api._failed_reconnect_counter = 3  # Trigger wait condition

        result = await api.connect()

        assert result is True
        mock_sleep.assert_called_once_with(300)  # 5 minutes wait

    def test_close_success(self) -> None:
        """Test successful close."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        # Create a mock client with close method configured
        mock_client = MagicMock()
        mock_client.close.return_value = None
        api._modbus_client = mock_client

        result = api.close()

        assert result is True
        mock_client.close.assert_called_once()

    def test_close_modbus_exception(self) -> None:
        """Test close with ModbusException."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        # Create a mock client with close method configured to raise exception
        mock_client = MagicMock()
        mock_client.close.side_effect = ModbusException("Close failed")
        api._modbus_client = mock_client

        result = api.close()

        assert result is False

    def test_get_device(self) -> None:
        """Test get_device method."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        device = api.get_device()

        assert device is api._modbus_client

    async def test_write_holding_register_not_connected(self) -> None:
        """Test write_holding_register when not connected."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        # Mock the client with connected property
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=False)
        api._modbus_client = mock_client
        api.connect = AsyncMock(return_value=False)

        result = await api.write_holding_register(100, 1500, 1)

        assert result is False

    async def test_write_holding_register_success(self) -> None:
        """Test successful write_holding_register."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        # Mock the client with connected property and write method
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_client.write_register = AsyncMock(return_value=mock_result)
        api._modbus_client = mock_client

        result = await api.write_holding_register(100, 1500, 1)

        assert result is True
        mock_client.write_register.assert_called_once_with(
            address=100, value=1500, slave=1
        )

    async def test_write_holding_register_error_response(self) -> None:
        """Test write_holding_register with error response."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)

        mock_result = MagicMock()
        mock_result.isError.return_value = True
        mock_client.write_register = AsyncMock(return_value=mock_result)
        api._modbus_client = mock_client

        result = await api.write_holding_register(100, 1500, 1)

        assert result is False

    async def test_write_holding_register_no_result(self) -> None:
        """Test write_holding_register with no result."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.write_register = AsyncMock(return_value=None)
        api._modbus_client = mock_client

        result = await api.write_holding_register(100, 1500, 1)

        assert result is False

    async def test_write_holding_register_modbus_exception(self) -> None:
        """Test write_holding_register with ModbusException."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.write_register = AsyncMock(
            side_effect=ModbusException("Write failed")
        )
        api._modbus_client = mock_client

        result = await api.write_holding_register(100, 1500, 1)

        assert result is False

    async def test_read_holding_registers_success(self) -> None:
        """Test successful read_holding_registers."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = [1500, 2300]
        mock_client.read_holding_registers = AsyncMock(return_value=mock_result)
        api._modbus_client = mock_client

        result = await api.read_holding_registers(100, 2, 1)

        assert result == [1500, 2300]
        mock_client.read_holding_registers.assert_called_once_with(
            address=100, count=2, slave=1
        )

    async def test_read_holding_registers_error_response(self) -> None:
        """Test read_holding_registers with error response."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)

        mock_result = MagicMock()
        mock_result.isError.return_value = True
        mock_client.read_holding_registers = AsyncMock(return_value=mock_result)
        api._modbus_client = mock_client

        result = await api.read_holding_registers(100, 1, 1)

        assert result is None

    async def test_read_holding_registers_modbus_exception(self) -> None:
        """Test read_holding_registers with ModbusException."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.read_holding_registers = AsyncMock(
            side_effect=ModbusException("Read failed")
        )
        api._modbus_client = mock_client

        result = await api.read_holding_registers(100, 1, 1)

        assert result is None

    async def test_read_input_registers_success(self) -> None:
        """Test successful read_input_registers."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = [750]
        mock_client.read_input_registers = AsyncMock(return_value=mock_result)
        api._modbus_client = mock_client

        result = await api.read_input_registers(200, 1, 1)

        assert result == [750]
        mock_client.read_input_registers.assert_called_once_with(
            address=200, count=1, slave=1
        )

    async def test_read_input_registers_not_connected(self) -> None:
        """Test read_input_registers when not connected."""
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=False)
        api._modbus_client = mock_client
        api.connect = AsyncMock(return_value=False)

        result = await api.read_input_registers(200, 1, 1)

        assert result is None


class TestModbusItemValidator:
    """Test ModbusItemValidator class."""

    def test_validate_value_no_description(self) -> None:
        """Test validate_value with no entity description."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        result = ModbusItemValidator.validate_value(item, 1500)

        assert result == 1500

    def test_validate_value_no_device_class(self) -> None:
        """Test validate_value with no device class."""

        item = ApiItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            entitydescription=SensorEntityDescription(key="test"),
        )

        result = ModbusItemValidator.validate_value(item, 1500)

        assert result == 1500

    def test_validate_temperature_normal(self) -> None:
        """Test temperature validation with normal value."""
        result = ModbusItemValidator._validate_temperature(250)

        assert result == 250

    def test_validate_temperature_invalid_readings(self) -> None:
        """Test temperature validation with invalid readings."""
        # No sensor or invalid reading
        assert ModbusItemValidator._validate_temperature(-32768) is None
        assert ModbusItemValidator._validate_temperature(32768) is None

        # Sensor broken
        assert ModbusItemValidator._validate_temperature(-32767) == -999

    def test_validate_temperature_signed_conversion(self) -> None:
        """Test temperature validation with signed conversion."""
        # Large positive value should be converted to negative
        result = ModbusItemValidator._validate_temperature(65000)

        assert result == -536  # 65000 - 65536

    def test_validate_percentage_normal(self) -> None:
        """Test percentage validation with normal value."""
        result = ModbusItemValidator._validate_percentage(85)

        assert result == 85

    def test_validate_percentage_invalid(self) -> None:
        """Test percentage validation with invalid value."""
        result = ModbusItemValidator._validate_percentage(65535)

        assert result is None


class TestModbusObject:
    """Test ModbusObject class."""

    def test_modbus_object_init(self) -> None:
        """Test ModbusObject initialization."""
        mock_api = MagicMock()
        mock_item = ApiItem(
            name="test_item",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=100,
            battery_slave_id=1,
        )

        obj = ModbusObject(mock_api, mock_item)

        assert obj._modbus_api is mock_api
        assert obj._modbus_item is mock_item
        assert obj._validator is not None

    async def test_async_read_value_invalid_item(self) -> None:
        """Test async_read_value when item is invalid."""
        mock_api = MagicMock()
        mock_item = ApiItem(
            name="test_item",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )
        mock_item.is_invalid = True

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_read_value()

        assert result is None

    async def test_async_read_value_sensor_success(self) -> None:
        """Test successful async_read_value for sensor."""
        mock_api = MagicMock()
        mock_api.read_input_registers = AsyncMock(return_value=[1500])

        mock_item = ApiItem(
            name="test_sensor",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=100,
            battery_slave_id=1,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_read_value()

        assert result == 1500
        mock_api.read_input_registers.assert_called_once_with(100, slave=1)
        assert mock_item.is_invalid is False

    async def test_async_read_value_number_success(self) -> None:
        """Test successful async_read_value for number."""
        mock_api = MagicMock()
        mock_api.read_holding_registers = AsyncMock(return_value=[2300])

        mock_item = ApiItem(
            name="test_number",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=200,
            battery_slave_id=2,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_read_value()

        assert result == 2300
        mock_api.read_holding_registers.assert_called_once_with(200, slave=2)

    async def test_async_read_value_unsupported_type(self) -> None:
        """Test async_read_value with unsupported type."""
        mock_api = MagicMock()

        mock_item = ApiItem(
            name="test_unsupported",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SWITCH,  # Not handled in read
            device=DeviceConstants.SYS,
            address=100,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_read_value()

        assert result is None

    async def test_async_read_value_no_data(self) -> None:
        """Test async_read_value with no data returned."""
        mock_api = MagicMock()
        mock_api.read_input_registers = AsyncMock(return_value=None)

        mock_item = ApiItem(
            name="test_sensor",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=100,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_read_value()

        assert result is None

    async def test_async_read_value_validation_fail(self) -> None:
        """Test async_read_value when validation returns None."""
        mock_api = MagicMock()
        mock_api.read_input_registers = AsyncMock(return_value=[65535])

        mock_item = ApiItem(
            name="test_battery",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=100,
            entitydescription=SensorEntityDescription(
                key="battery", device_class=SensorDeviceClass.BATTERY
            ),
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_read_value()

        assert result is None
        assert mock_item.is_invalid is True

    async def test_async_read_value_modbus_exception(self) -> None:
        """Test async_read_value with ModbusException."""
        mock_api = MagicMock()
        mock_api.read_input_registers = AsyncMock(
            side_effect=ModbusException("Read failed")
        )

        mock_item = ApiItem(
            name="test_sensor",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=100,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_read_value()

        assert result is None

    async def test_async_write_value_readonly_sensor(self) -> None:
        """Test async_write_value to read-only sensor."""
        mock_api = MagicMock()

        mock_item = ApiItem(
            name="test_sensor",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=100,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_write_value(1500)

        assert result is False

    async def test_async_write_value_success(self) -> None:
        """Test successful async_write_value."""
        mock_api = MagicMock()
        mock_api.write_holding_register = AsyncMock(return_value=True)

        mock_item = ApiItem(
            name="test_number",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=100,
            battery_slave_id=1,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_write_value(1500)

        assert result is True
        mock_api.write_holding_register.assert_called_once_with(100, 1500, slave=1)

    async def test_async_write_value_modbus_exception(self) -> None:
        """Test async_write_value with ModbusException."""
        mock_api = MagicMock()
        mock_api.write_holding_register = AsyncMock(
            side_effect=ModbusException("Write failed")
        )

        mock_item = ApiItem(
            name="test_number",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=100,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = await obj.async_write_value(1500)

        assert result is False

    def test_prepare_write_value_temperature_negative(self) -> None:
        """Test _prepare_write_value for negative temperature."""

        mock_api = MagicMock()
        mock_item = ApiItem(
            name="test_temp",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            entitydescription=SensorEntityDescription(
                key="temp", device_class=SensorDeviceClass.TEMPERATURE
            ),
        )

        obj = ModbusObject(mock_api, mock_item)
        result = obj._prepare_write_value(-100)

        assert result == 65436  # -100 + 65536

    def test_prepare_write_value_normal(self) -> None:
        """Test _prepare_write_value for normal value."""
        mock_api = MagicMock()
        mock_item = ApiItem(
            name="test_number",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = obj._prepare_write_value(1500)

        assert result == 1500

    def test_get_switch_on_value_pilot_switch(self) -> None:
        """Test get_switch_on_value for pilot switch."""
        mock_api = MagicMock()
        mock_item = ApiItem(
            name="solar_charging",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        )

        obj = ModbusObject(mock_api, mock_item)
        result = obj.get_switch_on_value()

        assert result == 1

    def test_get_switch_on_value_with_resultlist(self) -> None:
        """Test get_switch_on_value with resultlist."""

        mock_api = MagicMock()
        mock_item = ApiItem(
            name="test_switch",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
            resultlist=[
                StatusItem(0, "off", "off"),
                StatusItem(1, "on", "on"),
                StatusItem(2, "connected", "connected"),
            ],
        )

        obj = ModbusObject(mock_api, mock_item)
        result = obj.get_switch_on_value()

        assert result == 1  # First match for "on"

    def test_get_switch_off_value_with_resultlist(self) -> None:
        """Test get_switch_off_value with resultlist."""

        mock_api = MagicMock()
        mock_item = ApiItem(
            name="test_switch",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
            resultlist=[
                StatusItem(0, "off", "off"),
                StatusItem(1, "on", "on"),
                StatusItem(2, "disconnected", "disconnected"),
            ],
        )

        obj = ModbusObject(mock_api, mock_item)
        result = obj.get_switch_off_value()

        assert result == 0  # First match for "off"

    def test_is_pilot_switch_true(self) -> None:
        """Test _is_pilot_switch returns True for pilot switches."""
        mock_api = MagicMock()

        # Test solar charging switch
        solar_item = ApiItem(
            name="solar_charging",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        )

        solar_obj = ModbusObject(mock_api, solar_item)
        assert solar_obj._is_pilot_switch() is True

        # Test manual control switch
        manual_item = ApiItem(
            name="manual_control",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        )

        manual_obj = ModbusObject(mock_api, manual_item)
        assert manual_obj._is_pilot_switch() is True

    def test_is_pilot_switch_false(self) -> None:
        """Test _is_pilot_switch returns False for non-pilot switches."""
        mock_api = MagicMock()
        mock_item = ApiItem(
            name="regular_switch",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        )

        obj = ModbusObject(mock_api, mock_item)
        assert obj._is_pilot_switch() is False

    def test_item_property(self) -> None:
        """Test item property."""
        mock_api = MagicMock()
        mock_item = ApiItem(
            name="test_item",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        obj = ModbusObject(mock_api, mock_item)

        assert obj.item is mock_item


class TestModbusIntegration:
    """Test integration between ModbusAPI and ModbusObject."""

    @patch("custom_components.sax_battery.modbusobject.AsyncModbusTcpClient")
    async def test_full_read_write_cycle(self, mock_client_class) -> None:
        """Test full read/write cycle integration."""
        # Setup mock client
        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=True)
        mock_client.connect = AsyncMock()
        mock_client.close.return_value = None
        mock_client_class.return_value = mock_client

        # Setup API
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
        await api.connect()

        # Setup item and object
        item = ApiItem(
            name="test_integration",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=100,
            battery_slave_id=1,
        )

        obj = ModbusObject(api, item)

        # Test write operation
        mock_write_result = MagicMock()
        mock_write_result.isError.return_value = False
        mock_client.write_register = AsyncMock(return_value=mock_write_result)

        write_result = await obj.async_write_value(1500)
        assert write_result is True

        # Test read operation
        mock_read_result = MagicMock()
        mock_read_result.isError.return_value = False
        mock_read_result.registers = [1500]
        mock_client.read_holding_registers = AsyncMock(return_value=mock_read_result)

        read_result = await obj.async_read_value()
        assert read_result == 1500

        # Cleanup
        api.close()

    async def test_error_handling_integration(self) -> None:
        """Test error handling across API and Object layers."""
        # Test with API that fails to connect
        api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")

        mock_client = MagicMock()
        type(mock_client).connected = PropertyMock(return_value=False)
        api._modbus_client = mock_client
        api.connect = AsyncMock(return_value=False)

        item = ApiItem(
            name="test_error",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=100,
            battery_slave_id=1,
        )

        obj = ModbusObject(api, item)

        # Should handle disconnected state gracefully
        read_result = await obj.async_read_value()
        assert read_result is None

        write_result = await obj.async_write_value(100)
        assert write_result is False
