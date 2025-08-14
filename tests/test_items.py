"""Test items.py functionality."""

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem, StatusItem
from homeassistant.components.number import NumberEntityDescription
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
        item = ModbusItem(
            name="test_item",
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


class TestModbusItem:
    """Test ModbusItem dataclass."""

    def test_modbus_item_init_required_params(self) -> None:
        """Test ModbusItem initialization with required parameters."""
        item = ModbusItem(
            name="test_modbus",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        assert item.name == "test_modbus"
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
        entity_desc = SensorEntityDescription(key="test_sensor")
        item = ModbusItem(
            name="test",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=100.0,
            entitydescription=entity_desc,
        )

        # Test conversion
        assert item.convert_raw_value(2300) == 23.0

        # Test signed conversion for large values
        assert item.convert_raw_value(65000) == -5.36  # (65000 - 65536) / 100

    def test_modbus_item_convert_to_raw_value(self) -> None:
        """Test ModbusItem convert_to_raw_value method."""
        entity_desc = NumberEntityDescription(key="test_number")
        item = ModbusItem(
            name="test",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            divider=10.0,
            entitydescription=entity_desc,
        )

        # Test conversion
        assert item.convert_to_raw_value(23.0) == 230

    def test_modbus_item_state_management(self) -> None:
        """Test ModbusItem state management (inherited from BaseItem)."""
        item = ModbusItem(
            name="test",
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
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )

        assert item.name == "test_sax (Calculated)"
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

    def test_all_items_share_common_interface(self) -> None:
        """Test that all item types share common BaseItem interface."""
        items = [
            ModbusItem(
                name="modbus_test",
                mtype=TypeConstants.SENSOR,
                device=DeviceConstants.SYS,
            ),
            SAXItem(
                name="sax_test",
                mtype=TypeConstants.SENSOR_CALC,
                device=DeviceConstants.SYS,
            ),
        ]

        for item in items:
            # All should have common BaseItem properties
            assert hasattr(item, "name")
            assert hasattr(item, "state")
            assert hasattr(item, "is_invalid")
            assert hasattr(item, "mtype")
            assert hasattr(item, "device")

            # Test state management
            item.state = f"test_state_{item.name}"
            assert item.state == f"test_state_{item.name}"

            item.is_invalid = True
            assert item.is_invalid is True
