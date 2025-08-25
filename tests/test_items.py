"""Test items.py functionality."""

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem

# mypy: disable-error-code="arg-type"


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
        assert item.factor == 1.0

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
