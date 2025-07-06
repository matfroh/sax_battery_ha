"""Test items.py functionality."""

from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ApiItem, ModbusItem, StatusItem


class TestStatusItem:
    """Test StatusItem class."""

    def test_status_item_init_defaults(self) -> None:
        """Test StatusItem initialization with defaults."""
        item = StatusItem(1, "Test Status")

        assert item.number == 1
        assert item.text == "Test Status"
        assert item.description == ""
        assert item.translation_key == ""

    def test_status_item_init_with_optional_params(self) -> None:
        """Test StatusItem initialization with optional parameters."""
        item = StatusItem(
            number=2,
            text="Warning Status",
            translation_key="warning_status",
            description="This is a warning status",
        )

        assert item.number == 2
        assert item.text == "Warning Status"
        assert item.description == "This is a warning status"
        assert item.translation_key == "warning_status"

    def test_status_item_setters(self) -> None:
        """Test StatusItem property setters."""
        item = StatusItem(1, "Initial")

        # Test number setter
        item.number = 5
        assert item.number == 5

        # Test text setter
        item.text = "Updated Text"
        assert item.text == "Updated Text"

        # Test description setter
        item.description = "Updated Description"
        assert item.description == "Updated Description"

        # Test translation_key setter
        item.translation_key = "updated_key"
        assert item.translation_key == "updated_key"

    def test_status_item_none_values(self) -> None:
        """Test StatusItem with None values."""
        item = StatusItem(1, "Test")
        item._number = None
        item._text = None
        item._description = None

        assert item.number == 0  # Should return 0 when None
        assert item.text == ""   # Should return empty string when None
        assert item.description == ""  # Should return empty string when None


class TestApiItem:
    """Test ApiItem class."""

    def test_api_item_init_defaults(self) -> None:
        """Test ApiItem initialization with defaults."""
        item = ApiItem(
            name="test_item",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        assert item.name == "test_item"
        assert item.format == FormatConstants.TEMPERATURE
        assert item.type == TypeConstants.SENSOR
        assert item.device == DeviceConstants.UK
        assert item.resultlist is None
        assert item.state is None
        assert item.is_invalid is False
        assert item.translation_key == ""
        assert item.params == {}
        assert item.divider == 1

    def test_api_item_init_with_optional_params(self) -> None:
        """Test ApiItem initialization with optional parameters."""
        result_list = [StatusItem(1, "Test")]
        params = {"param1": "value1"}

        item = ApiItem(
            name="test_item",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.UK,
            translation_key="test_translation",
            resultlist=result_list,
            params=params,
        )

        assert item.name == "test_item"
        assert item.format == FormatConstants.PERCENTAGE
        assert item.type == TypeConstants.NUMBER
        assert item.device == DeviceConstants.UK
        assert item.resultlist == result_list
        assert item.translation_key == "test_translation"
        assert item.params == params

    def test_api_item_property_setters(self) -> None:
        """Test ApiItem property setters."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        # Test name setter
        item.name = "updated_name"
        assert item.name == "updated_name"

        # Test device setter
        item.device = DeviceConstants.UK
        assert item.device == DeviceConstants.UK

        # Test translation_key setter
        item.translation_key = "updated_key"
        assert item.translation_key == "updated_key"

        # Test is_invalid setter
        item.is_invalid = True
        assert item.is_invalid is True

        # Test state setter
        item.state = 42
        assert item.state == 42

        # Test params setter
        new_params = {"key": "value"}
        item.params = new_params
        assert item.params == new_params

        # Test divider setter
        item.divider = 10
        assert item.divider == 10

    def test_api_item_params_none(self) -> None:
        """Test ApiItem params property when None."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )
        item.params = None
        assert item.params == {}

    def test_get_text_from_number_no_resultlist(self) -> None:
        """Test get_text_from_number when resultlist is None."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        assert item.get_text_from_number(1) is None
        assert item.get_text_from_number(None) is None

    def test_get_text_from_number_with_resultlist(self) -> None:
        """Test get_text_from_number with resultlist."""
        result_list = [
            StatusItem(1, "Status One"),
            StatusItem(2, "Status Two"),
            StatusItem(3, "Status Three"),
        ]

        item = ApiItem(
            name="test",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
            resultlist=result_list,
        )

        assert item.get_text_from_number(1) == "Status One"
        assert item.get_text_from_number(2) == "Status Two"
        assert item.get_text_from_number(3) == "Status Three"
        assert item.get_text_from_number(999) == "unbekannt <999>"
        assert item.get_text_from_number(None) is None

    def test_get_number_from_text_no_resultlist(self) -> None:
        """Test get_number_from_text when resultlist is None."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        assert item.get_number_from_text("Status One") is None

    def test_get_number_from_text_with_resultlist(self) -> None:
        """Test get_number_from_text with resultlist."""
        result_list = [
            StatusItem(1, "Status One"),
            StatusItem(2, "Status Two"),
            StatusItem(3, "Status Three"),
        ]

        item = ApiItem(
            name="test",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
            resultlist=result_list,
        )

        assert item.get_number_from_text("Status One") == 1
        assert item.get_number_from_text("Status Two") == 2
        assert item.get_number_from_text("Status Three") == 3
        assert item.get_number_from_text("Unknown Status") == -1

    def test_get_translation_key_from_number_no_resultlist(self) -> None:
        """Test get_translation_key_from_number when resultlist is None."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        assert item.get_translation_key_from_number(1) is None
        assert item.get_translation_key_from_number(None) is None

    def test_get_translation_key_from_number_with_resultlist(self) -> None:
        """Test get_translation_key_from_number with resultlist."""
        result_list = [
            StatusItem(1, "Status One", "status_one"),
            StatusItem(2, "Status Two", "status_two"),
            StatusItem(3, "Status Three", "status_three"),
        ]

        item = ApiItem(
            name="test",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
            resultlist=result_list,
        )

        assert item.get_translation_key_from_number(1) == "status_one"
        assert item.get_translation_key_from_number(2) == "status_two"
        assert item.get_translation_key_from_number(3) == "status_three"
        assert item.get_translation_key_from_number(999) == "unbekannt <999>"
        assert item.get_translation_key_from_number(None) is None

    def test_get_number_from_translation_key_no_resultlist(self) -> None:
        """Test get_number_from_translation_key when resultlist is None."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        assert item.get_number_from_translation_key("status_one") is None
        assert item.get_number_from_translation_key(None) is None

    def test_get_number_from_translation_key_with_resultlist(self) -> None:
        """Test get_number_from_translation_key with resultlist."""
        result_list = [
            StatusItem(1, "Status One", "status_one"),
            StatusItem(2, "Status Two", "status_two"),
            StatusItem(3, "Status Three", "status_three"),
        ]

        item = ApiItem(
            name="test",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
            resultlist=result_list,
        )

        assert item.get_number_from_translation_key("status_one") == 1
        assert item.get_number_from_translation_key("status_two") == 2
        assert item.get_number_from_translation_key("status_three") == 3
        assert item.get_number_from_translation_key("unknown_key") == -1
        assert item.get_number_from_translation_key(None) is None


class TestModbusItem:
    """Test ModbusItem class."""

    def test_modbus_item_init_defaults(self) -> None:
        """Test ModbusItem initialization with defaults."""
        item = ModbusItem(
            address=100,
            name="test_modbus",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        assert item.address == 100
        assert item.name == "test_modbus"
        assert item.format == FormatConstants.TEMPERATURE
        assert item.type == TypeConstants.SENSOR
        assert item.device == DeviceConstants.UK
        assert item.translation_key == ""
        assert item.resultlist is None
        assert item.params == {}

    def test_modbus_item_init_with_optional_params(self) -> None:
        """Test ModbusItem initialization with optional parameters."""
        result_list = [StatusItem(1, "Test")]
        params = {"param1": "value1"}

        item = ModbusItem(
            address=200,
            name="test_modbus",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.UK,
            translation_key="test_translation",
            resultlist=result_list,
            slave=2,
            params=params,
        )

        assert item.address == 200
        assert item.name == "test_modbus"
        assert item.format == FormatConstants.PERCENTAGE
        assert item.type == TypeConstants.NUMBER
        assert item.device == DeviceConstants.UK
        assert item.translation_key == "test_translation"
        assert item.resultlist == result_list
        assert item.params == params

    def test_modbus_item_address_setter(self) -> None:
        """Test ModbusItem address setter."""
        item = ModbusItem(
            address=100,
            name="test",
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
        )

        item.address = 300
        assert item.address == 300

    def test_modbus_item_inherits_from_api_item(self) -> None:
        """Test that ModbusItem inherits all ApiItem functionality."""
        result_list = [
            StatusItem(1, "Status One", "status_one"),
            StatusItem(2, "Status Two", "status_two"),
        ]

        item = ModbusItem(
            address=100,
            name="test_modbus",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.UK,
            resultlist=result_list,
        )

        # Test inherited functionality
        assert item.get_text_from_number(1) == "Status One"
        assert item.get_number_from_text("Status Two") == 2
        assert item.get_translation_key_from_number(1) == "status_one"
        assert item.get_number_from_translation_key("status_two") == 2

        # Test property inheritance
        item.state = 42
        assert item.state == 42

        item.is_invalid = True
        assert item.is_invalid is True
