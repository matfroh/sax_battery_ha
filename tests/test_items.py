"""Test items.py functionality."""

from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ApiItem, ModbusItem, SAXItem, StatusItem
from homeassistant.components.sensor import SensorEntityDescription

# mypy: disable-error-code="arg-type"


class TestStatusItem:
    """Test StatusItem dataclass."""

    def test_status_item_init_defaults(self) -> None:
        """Test StatusItem initialization with defaults."""
        item = StatusItem()

        assert item.number == 0
        assert item.text == ""
        assert item.name == ""

    def test_status_item_init_with_params(self) -> None:
        """Test StatusItem initialization with parameters."""
        item = StatusItem(
            number=1,
            text="Test Status",
            name="test_status",
        )

        assert item.number == 1
        assert item.text == "Test Status"
        assert item.name == "test_status"


class TestBaseItem:
    """Test BaseItem functionality through concrete implementations."""

    def test_base_item_state_management(self) -> None:
        """Test BaseItem state property management."""
        item = ApiItem(
            name="test_item",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        # Test initial state
        assert item.state is None
        assert item.is_invalid is False

        # Test state setter
        item.state = 42.5
        assert item.state == 42.5

        # Test invalid state
        item.is_invalid = True
        assert item.is_invalid is True


class TestApiItem:
    """Test ApiItem dataclass."""

    def test_api_item_init_required_params(self) -> None:
        """Test ApiItem initialization with required parameters."""
        item = ApiItem(
            name="test_item",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        assert item.name == "test_item"
        assert item.mformat == FormatConstants.NUMBER
        assert item.mtype == TypeConstants.SENSOR
        assert item.device == DeviceConstants.SYS
        assert item.translation_key == ""
        assert not item.params
        assert item.address == 0
        assert item.battery_slave_id == 1
        assert item.divider == 1.0
        assert item.entitydescription is None
        assert item.resultlist is None

    def test_api_item_init_with_optional_params(self) -> None:
        """Test ApiItem initialization with optional parameters."""
        status_list = [StatusItem(1, "Status One", "status_one")]
        params = {"param1": "value1", "param2": 42}
        entity_desc = SensorEntityDescription(key="test_sensor")

        item = ApiItem(
            name="test_item",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            translation_key="test_translation",
            params=params,
            address=100,
            battery_slave_id=2,
            divider=10.0,
            entitydescription=entity_desc,
            resultlist=status_list,
        )

        assert item.name == "test_item"
        assert item.translation_key == "test_translation"
        assert item.params == params
        assert item.address == 100
        assert item.battery_slave_id == 2
        assert item.divider == 10.0
        assert item.entitydescription == entity_desc
        assert item.resultlist == status_list

    def test_api_item_convert_raw_value_number(self) -> None:
        """Test ApiItem convert_raw_value for number format."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=10.0,
        )

        # Test positive number
        assert item.convert_raw_value(1500) == 150.0

        # Test signed 16-bit conversion (value > 32767)
        assert item.convert_raw_value(65000) == -53.6  # (65000 - 65536) / 10

        # Test negative number (already negative)
        assert item.convert_raw_value(500) == 50.0

    def test_api_item_convert_raw_value_other_formats(self) -> None:
        """Test ApiItem convert_raw_value for other formats."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=2.0,
        )

        # Test percentage format (no signed conversion)
        assert item.convert_raw_value(200) == 100.0

    def test_api_item_convert_raw_value_zero_divider(self) -> None:
        """Test ApiItem convert_raw_value with zero divider."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=0.0,
        )

        # Should return raw value when divider is 0
        assert item.convert_raw_value(1500) == 1500

    def test_api_item_convert_to_raw_value_number(self) -> None:
        """Test ApiItem convert_to_raw_value for number format."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=10.0,
        )

        # Test normal conversion
        assert item.convert_to_raw_value(150.0) == 1500

        # Test constraint limits
        assert item.convert_to_raw_value(5000.0) == 32767  # Clamped to max
        assert item.convert_to_raw_value(-5000.0) == -32768  # Clamped to min

    def test_api_item_convert_to_raw_value_percentage(self) -> None:
        """Test ApiItem convert_to_raw_value for percentage format."""
        item = ApiItem(
            name="test",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=1.0,
        )

        # Test normal conversion
        assert item.convert_to_raw_value(50.0) == 50

        # Test constraint limits
        assert item.convert_to_raw_value(150.0) == 100  # Clamped to max
        assert item.convert_to_raw_value(-10.0) == 0  # Clamped to min


class TestModbusItem:
    """Test ModbusItem dataclass."""

    def test_modbus_item_init_required_params(self) -> None:
        """Test ModbusItem initialization with required parameters."""
        item = ModbusItem(
            name="test_modbus",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        assert item.name == "test_modbus"
        assert item.mformat == FormatConstants.NUMBER
        assert item.mtype == TypeConstants.SENSOR
        assert item.device == DeviceConstants.SYS
        assert item.address == 0
        assert item.battery_slave_id == 0
        assert item.divider == 1.0
        assert not item.resultlist

    def test_modbus_item_init_with_optional_params(self) -> None:
        """Test ModbusItem initialization with optional parameters."""
        status_list = [StatusItem(1, "Status One", "status_one")]
        params = {"modbus_param": "value"}

        item = ModbusItem(
            name="test_modbus",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            address=200,
            battery_slave_id=3,
            divider=100.0,
            resultlist=status_list,
            params=params,
        )

        assert item.address == 200
        assert item.battery_slave_id == 3
        assert item.divider == 100.0
        assert item.resultlist == status_list
        assert item.params == params

    def test_modbus_item_convert_raw_value(self) -> None:
        """Test ModbusItem convert_raw_value method."""
        item = ModbusItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=100.0,
        )

        # Test conversion
        assert item.convert_raw_value(2300) == 23.0

        # Test signed conversion for large values
        assert item.convert_raw_value(65000) == -5.36  # (65000 - 65536) / 100

    def test_modbus_item_convert_to_raw_value(self) -> None:
        """Test ModbusItem convert_to_raw_value method."""
        item = ModbusItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=10.0,
        )

        # Test conversion
        assert item.convert_to_raw_value(23.0) == 230

    def test_modbus_item_state_management(self) -> None:
        """Test ModbusItem state management (inherited from BaseItem)."""
        item = ModbusItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        # Test state setter/getter
        item.state = 42.5
        assert item.state == 42.5

        # Test invalid flag
        item.is_invalid = True
        assert item.is_invalid is True


class TestSAXItem:
    """Test SAXItem dataclass."""

    def test_sax_item_init_required_params(self) -> None:
        """Test SAXItem initialization with required parameters."""
        item = SAXItem(
            name="test_sax",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )

        assert item.name == "test_sax (Calculated)"
        assert item.mformat == FormatConstants.NUMBER
        assert item.mtype == TypeConstants.SENSOR_CALC
        assert item.device == DeviceConstants.SYS
        assert item.entitydescription is None

    def test_sax_item_init_with_optional_params(self) -> None:
        """Test SAXItem initialization with optional parameters."""
        entity_desc = SensorEntityDescription(key="calculated_sensor")
        params = {
            "calculation": "val_0 + val_1",
            "val_0": "power_l1",
            "val_1": "power_l2",
        }

        item = SAXItem(
            name="total_power",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
            entitydescription=entity_desc,
            params=params,
        )

        assert item.name == "total_power (Calculated)"
        assert item.entitydescription == entity_desc
        assert item.params == params

    def test_sax_item_calculate_value_no_calculation(self) -> None:
        """Test SAXItem calculate_value with no calculation parameter."""
        item = SAXItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )

        # No calculation parameter
        result = item.calculate_value({"val_0": 10.0})
        assert result is None

        # Empty params
        item.params = {}
        result = item.calculate_value({"val_0": 10.0})
        assert result is None

    def test_sax_item_calculate_value_with_coordinator(self) -> None:
        """Test SAXItem calculate_value with coordinator values."""
        item = SAXItem(
            name="combined_power",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
            params={
                "calculation": "val_1 + val_2 + val_3",
                "val_1": "battery_a_power",
                "val_2": "battery_b_power",
                "val_3": "battery_c_power",
            },
        )

        coordinator_values: dict[str, float] | None = {
            "battery_a_power": 1500.0,
            "battery_b_power": 2000.0,
            "battery_c_power": 1200.0,
        }

        result = item.calculate_value(coordinator_values)
        assert result == 4700.0  # 1500 + 2000 + 1200

    def test_sax_item_calculate_value_with_precision(self) -> None:
        """Test SAXItem calculate_value with display precision."""
        entity_desc = SensorEntityDescription(
            key="test_calc", suggested_display_precision=2
        )

        item = SAXItem(
            name="average_soc",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
            entitydescription=entity_desc,
            params={
                "calculation": "(val_1 + val_2) / 2",
                "val_1": "battery_a_soc",
                "val_2": "battery_b_soc",
            },
        )

        coordinator_values: dict[str, float] | None = {
            "battery_a_soc": 85.333,
            "battery_b_soc": 92.777,
        }

        result = item.calculate_value(coordinator_values)
        assert result == 89.06  # Rounded to 2 decimal places

    def test_sax_item_calculate_value_invalid_calculation(self) -> None:
        """Test SAXItem calculate_value with invalid calculation."""
        item = SAXItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
            params={"calculation": "invalid_syntax +"},
        )

        variables: dict[str, float] | None = {"val_0": 10.0}
        result = item.calculate_value(variables)
        assert result is None

    def test_sax_item_calculate_value_missing_variables(self) -> None:
        """Test SAXItem calculate_value with missing variables."""
        item = SAXItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
            params={"calculation": "val_0 + missing_var"},
        )

        variables: dict[str, float] | None = {"val_0": 10.0}
        result = item.calculate_value(variables)
        assert result is None

    def test_sax_item_calculate_value_division_by_zero(self) -> None:
        """Test SAXItem calculate_value with division by zero."""
        item = SAXItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
            params={"calculation": "val_0 / val_1"},
        )

        variables: dict[str, float] | None = {"val_0": 10.0, "val_1": 0.0}
        result = item.calculate_value(variables)
        assert result is None

    def test_sax_item_state_management(self) -> None:
        """Test SAXItem state management (inherited from BaseItem)."""
        item = SAXItem(
            name="test",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )

        # Test state setter/getter
        item.state = 100.5
        assert item.state == 100.5

        # Test invalid flag
        item.is_invalid = False
        assert item.is_invalid is False


class TestItemInteroperability:
    """Test interoperability between different item types."""

    def test_convert_api_to_modbus_item(self) -> None:
        """Test conversion patterns between ApiItem and ModbusItem."""
        api_item = ApiItem(
            name="test_conversion",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            address=300,
            battery_slave_id=2,
            divider=100.0,
        )

        # Test that both have compatible conversion methods
        raw_value = 23000
        api_converted = api_item.convert_raw_value(raw_value)

        modbus_item = ModbusItem(
            name=api_item.name,
            mformat=api_item.mformat,
            mtype=api_item.mtype,
            device=api_item.device,
            address=api_item.address,
            battery_slave_id=api_item.battery_slave_id,
            divider=api_item.divider,
        )

        modbus_converted = modbus_item.convert_raw_value(raw_value)

        assert api_converted == modbus_converted

    def test_all_items_share_common_interface(self) -> None:
        """Test that all item types share common BaseItem interface."""
        items = [
            ApiItem(
                name="api_test",
                mformat=FormatConstants.NUMBER,
                mtype=TypeConstants.SENSOR,
                device=DeviceConstants.SYS,
            ),
            ModbusItem(
                name="modbus_test",
                mformat=FormatConstants.NUMBER,
                mtype=TypeConstants.SENSOR,
                device=DeviceConstants.SYS,
            ),
            SAXItem(
                name="sax_test",
                mformat=FormatConstants.NUMBER,
                mtype=TypeConstants.SENSOR_CALC,
                device=DeviceConstants.SYS,
            ),
        ]

        for item in items:
            # All should have common BaseItem properties
            assert hasattr(item, "name")
            assert hasattr(item, "state")
            assert hasattr(item, "is_invalid")
            assert hasattr(item, "mformat")
            assert hasattr(item, "mtype")
            assert hasattr(item, "device")

            # Test state management
            item.state = f"test_state_{item.name}"
            assert item.state == f"test_state_{item.name}"

            item.is_invalid = True
            assert item.is_invalid is True
