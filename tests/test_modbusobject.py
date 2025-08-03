"""Test modbusobject.py functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

from custom_components.sax_battery.const import DeviceConstants
from custom_components.sax_battery.items import ApiItem
from custom_components.sax_battery.modbusobject import ModbusObject, SAXBatteryAPI


class TestSAXBatteryAPI:
    """Test SAXBatteryAPI class."""

    def test_modbus_api_init(self, mock_sax_data, mock_modbus_client) -> None:
        """Test SAXBatteryAPI initialization."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")

        assert api._connected is False
        assert api._connect_pending is False
        assert api._failed_reconnect_counter == 0
        assert api.entry == mock_sax_data.entry
        assert api.battery_id == "battery_a"
        assert api._modbus_client == mock_modbus_client

    def test_modbus_api_init_with_missing_host_data(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test SAXBatteryAPI initialization with missing host data."""
        # Remove host data to test defaults
        mock_sax_data.entry.data = {}
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")

        assert api._connected is False
        assert api._modbus_client == mock_modbus_client

    def test_modbus_api_init_with_none_host_data(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test SAXBatteryAPI initialization with None host data."""
        mock_sax_data.entry.data = {
            "battery_a_host": None,
            "battery_a_port": None,
        }
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")

        assert api._connected is False
        assert api._modbus_client == mock_modbus_client

    async def test_connect_success(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test successful connection."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")

        # Mock successful connection
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        mock_modbus_client.connect.return_value = True

        result = await api.connect()

        assert result is True
        assert api._failed_reconnect_counter == 0
        assert api._connect_pending is False
        mock_modbus_client.connect.assert_called_once()

    async def test_connect_failure(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test connection failure."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")

        # Mock failed connection
        type(mock_modbus_client).connected = PropertyMock(return_value=False)
        mock_modbus_client.connect.return_value = False

        result = await api.connect()

        assert result is False
        assert api._failed_reconnect_counter == 1
        assert api._connect_pending is False
        mock_modbus_client.connect.assert_called_once()
        mock_modbus_client.close.assert_called_once()

    def test_close_success(self, mock_sax_data, mock_modbus_client) -> None:
        """Test successful close operation."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")

        result = api.close()

        assert result is True
        mock_modbus_client.close.assert_called_once()

    def test_get_device(self, mock_sax_data, mock_modbus_client) -> None:
        """Test get_device returns modbus client."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")

        device = api.get_device()

        assert device is mock_modbus_client


class TestModbusObject:
    """Test ModbusObject class."""

    def test_modbus_object_init(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test ModbusObject initialization."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            no_connect_warn=True,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        assert obj._modbus_item == mock_modbus_item
        assert obj._modbus_client == mock_modbus_client
        assert obj._no_connect_warn is True

    def test_modbus_object_init_default_warn(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test ModbusObject initialization with default warn setting."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        assert obj._no_connect_warn is False

    def test_check_valid_result_no_entitydescription(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test check_valid_result with no entitydescription."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        mock_item = ApiItem(
            name="test_item",
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        # Don't set entitydescription
        obj = ModbusObject(
            api, mock_item, battery_id="battery_a", config_entry=mock_sax_data
        )

        result = obj.check_valid_result(250)

        assert result == 250
        assert obj._modbus_item.is_invalid is False

    def test_check_valid_result_no_device_class(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test check_valid_result with no device_class."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        mock_item = ApiItem(
            name="test_item",
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        # Mock entitydescription without device_class
        mock_item.entitydescription = MagicMock()
        mock_item.entitydescription.device_class = None
        obj = ModbusObject(
            api, mock_item, config_entry=mock_sax_data, battery_id="battery_a"
        )

        result = obj.check_valid_result(250)

        assert result == 250
        assert obj._modbus_item.is_invalid is False

    def test_check_temperature_no_sensor(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_temperature with no sensor installed (-32768)."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        result = obj.check_temperature(-32768)

        assert result is None
        assert obj._modbus_item.is_invalid is True

    def test_check_temperature_normal_positive(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_temperature with normal positive value."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        result = obj.check_temperature(250)

        assert result == 250
        assert obj._modbus_item.is_invalid is False

    def test_check_percentage_valid(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_percentage with valid value."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        result = obj.check_percentage(75)

        assert result == 75
        assert obj._modbus_item.is_invalid is False

    def test_check_status(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test check_status always returns value and sets valid."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        result = obj.check_status(42)

        assert result == 42
        assert obj._modbus_item.is_invalid is False

    def test_check_valid_response_temperature_positive(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test check_valid_response with positive temperature."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        mock_item = ApiItem(
            name="test_item",
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(
            api, mock_item, config_entry=mock_sax_data, battery_id="battery_a"
        )

        result = obj.check_valid_response(100)

        assert result == 100

    def test_check_valid_response_other_format(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test check_valid_response with non-temperature format."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        mock_item = ApiItem(
            name="test_item",
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(
            api, mock_item, config_entry=mock_sax_data, battery_id="battery_a"
        )

        result = obj.check_valid_response(75)

        assert result == 75

    async def test_async_read_value_not_connected_no_warning(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test async_read_value when not connected (no warning)."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            no_connect_warn=True,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )
        type(mock_modbus_client).connected = PropertyMock(return_value=False)

        result = await obj.async_read_value(1)

        assert result is None

    async def test_async_read_value_item_invalid(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test async_read_value when item is invalid."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = True

        result = await obj.async_read_value(1)

        assert result is None

    async def test_async_read_value_sensor_success(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test async_read_value for sensor type."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        mock_item = ApiItem(
            name="test_item",
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(
            api, mock_item, config_entry=mock_sax_data, battery_id="battery_a"
        )
        type(mock_modbus_client).connected = PropertyMock(return_value=True)
        obj._modbus_item.is_invalid = False

        mock_response = MagicMock()
        mock_response.registers = [250]
        mock_modbus_client.read_input_registers.return_value = mock_response

        with patch.object(obj, "validate_modbus_answer", return_value=250):
            result = await obj.async_read_value(1)

            assert result == 250
            mock_modbus_client.read_input_registers.assert_called_once_with(
                100, slave=1
            )

    async def test_async_write_value_not_connected(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test async_write_value when not connected."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            battery_id="battery_a",
            config_entry=mock_sax_data,
        )
        type(mock_modbus_client).connected = PropertyMock(return_value=False)

        result = await obj.async_write_value(1, 100)

        assert result is False

    async def test_async_write_value_sensor_readonly(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test async_write_value for read-only sensor type."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        mock_item = ApiItem(
            name="test_item",
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(
            api, mock_item, config_entry=mock_sax_data, battery_id="battery_a"
        )
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        result = await obj.async_write_value(1, 100)

        assert result is False
        mock_modbus_client.write_register.assert_not_called()

    async def test_async_write_value_number_success(
        self, mock_sax_data, mock_modbus_client
    ) -> None:
        """Test async_write_value for writable number type."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        mock_item = ApiItem(
            name="test_item",
            translation_key="test_key",
            device=DeviceConstants.SYS,
        )
        obj = ModbusObject(
            api, mock_item, config_entry=mock_sax_data, battery_id="battery_a"
        )
        type(mock_modbus_client).connected = PropertyMock(return_value=True)

        with patch.object(obj, "check_valid_response", return_value=100):
            result = await obj.async_write_value(1, 100)

            assert result is True
            mock_modbus_client.write_register.assert_called_once_with(100, 100, slave=1)

    def test_get_on_value(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test get_on_value method."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        result = obj.get_on_value()

        assert isinstance(result, int)

    def test_get_off_value(
        self, mock_sax_data, mock_modbus_item, mock_modbus_client
    ) -> None:
        """Test get_off_value method."""
        api = SAXBatteryAPI(config_entry=mock_sax_data, battery_id="battery_a")
        obj = ModbusObject(
            api,
            mock_modbus_item,
            config_entry=mock_sax_data,
            battery_id="battery_a",
        )

        result = obj.get_off_value()

        assert isinstance(result, int)
