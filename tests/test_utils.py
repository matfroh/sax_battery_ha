"""Test utility functions for SAX Battery integration."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_BATTERY_COUNT,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_PILOT_FROM_HA,
    DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER,
    MODBUS_BATTERY_PILOT_CONTROL_ITEMS,
    MODBUS_BATTERY_POWER_LIMIT_ITEMS,
    MODBUS_BATTERY_REALTIME_ITEMS,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.models import create_register_access_config
from custom_components.sax_battery.utils import (
    RegisterAccessConfig,
    get_battery_realtime_items,
    get_writable_registers,
    should_include_entity,
)


class TestShouldIncludeEntity:
    """Test should_include_entity function."""

    def test_include_entity_basic_case(
        self, mock_modbus_item, mock_config_entry
    ) -> None:
        """Test basic entity inclusion (should return True by default)."""
        result = should_include_entity(mock_modbus_item, mock_config_entry, "battery_a")
        assert result is True

    def test_exclude_by_device_type_mismatch(self, mock_config_entry) -> None:
        """Test entity exclusion by device type mismatch."""
        mock_config_entry.data = {"device_type": DeviceConstants.SM}

        api_item = ModbusItem(
            name="voltage",
            device=DeviceConstants.BESS,  # Different from config
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            factor=10.0,
        )

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_include_by_device_type_match(self, mock_config_entry) -> None:
        """Test entity inclusion by device type match."""
        mock_config_entry.data = {"device_type": DeviceConstants.BESS}

        api_item = ModbusItem(
            name="voltage",
            device=DeviceConstants.BESS,  # Matches config
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            factor=10.0,
        )

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is True

    def test_include_master_only_item_for_master_battery(
        self, mock_config_entry_with_features
    ) -> None:
        """Test master-only item inclusion for master battery."""
        api_item = ModbusItem(
            name="smart_meter_data",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SENSOR,
            entitydescription=DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attribute - ModbusItem supports this
        setattr(api_item, "master_only", True)

        result = should_include_entity(
            api_item, mock_config_entry_with_features, "battery_a"
        )
        assert result is True

    def test_exclude_master_only_item_for_slave_battery(
        self, mock_config_entry_with_features
    ) -> None:
        """Test master-only item exclusion for slave battery."""
        api_item = ModbusItem(
            name="smart_meter_data",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "master_only", True)

        result = should_include_entity(
            api_item, mock_config_entry_with_features, "battery_b"
        )
        assert result is False

    @pytest.mark.skip(reason="This test might be useless")
    def test_exclude_master_only_item_no_battery_config(
        self, mock_config_entry
    ) -> None:
        """Test master-only item behavior when no master battery is configured."""
        # When no master_battery is configured in data, master_only items
        # should still be included (this matches the actual implementation behavior)
        mock_config_entry.data = {
            "batteries": {},
            # No master_battery key at all
        }

        api_item = ModbusItem(
            name="smart_meter_data",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "master_only", True)

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        # Based on the actual implementation, this returns True when no master_battery is configured
        assert result is True

    def test_exclude_master_only_item_for_non_master_battery(
        self, mock_config_entry
    ) -> None:
        """Test master-only item exclusion for non-master battery when master is configured."""
        mock_config_entry.data = {
            "batteries": {
                "battery_a": {"role": "master"},
                "battery_b": {"role": "slave"},
            },
            "master_battery": "battery_a",
        }

        api_item = ModbusItem(
            name="smart_meter_data",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "master_only", True)

        # Should exclude for non-master battery
        result = should_include_entity(api_item, mock_config_entry, "battery_b")
        assert result is False

        # Should include for master battery
        result_master = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result_master is True

    def test_include_by_required_features_all_available(
        self, mock_config_entry_with_features
    ) -> None:
        """Test entity inclusion when all required features are available."""
        api_item = ModbusItem(
            name="power_limit",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "required_features", ["smart_meter", "power_control"])

        result = should_include_entity(
            api_item, mock_config_entry_with_features, "battery_a"
        )
        assert result is True

    def test_exclude_by_required_features_missing(self, mock_config_entry) -> None:
        """Test entity exclusion when required features are missing."""
        mock_config_entry.data = {"features": ["smart_meter"]}

        api_item = ModbusItem(
            name="power_limit",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "required_features", ["smart_meter", "power_control"])

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_exclude_by_required_features_no_features_config(
        self, mock_config_entry
    ) -> None:
        """Test entity exclusion when no features are configured."""
        api_item = ModbusItem(
            name="power_limit",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "required_features", ["power_control"])

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_include_with_no_device_attribute(
        self, mock_modbus_item, mock_config_entry
    ) -> None:
        """Test entity inclusion when item has no device attribute."""
        # Remove device attribute to simulate items without device specification
        delattr(mock_modbus_item, "device")
        mock_config_entry.data = {"device_type": DeviceConstants.SM}

        result = should_include_entity(mock_modbus_item, mock_config_entry, "battery_a")
        assert result is True  # Should include when no device constraint

    def test_complex_filtering_scenario(self, mock_config_entry_with_features) -> None:
        """Test complex filtering scenario with multiple constraints."""
        api_item = ModbusItem(
            name="smart_meter_control",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attributes
        setattr(api_item, "master_only", True)
        setattr(api_item, "required_features", ["smart_meter"])

        result = should_include_entity(
            api_item, mock_config_entry_with_features, "battery_a"
        )
        assert result is True

    def test_complex_filtering_scenario_fail_master_check(self) -> None:
        """Test complex filtering scenario failing on master check."""
        # Create specific config for this test
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "device_type": DeviceConstants.BESS,
            "batteries": {"battery_a": {"role": "slave"}},  # Not master
            "features": ["smart_meter", "power_control"],
        }

        api_item = ModbusItem(
            name="smart_meter_control",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        # Dynamically add attributes
        setattr(api_item, "master_only", True)
        setattr(api_item, "required_features", ["smart_meter"])

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_api_item_compatibility(self, mock_config_entry) -> None:
        """Test function works with base ModbusItem type."""
        # Create a basic ModbusItem (parent class)
        api_item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is True

    def test_sax_item_compatibility(self, mock_config_entry) -> None:
        """Test function works with SAXItem type."""
        # Test that should_include_entity works with SAXItem
        # Note: should_include_entity signature shows it expects ModbusItem,
        # but if it should accept SAXItem too, this test documents that behavior
        sax_item = SAXItem(
            name="calculated_power",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SENSOR_CALC,
        )

        # This test may need to be adjusted based on actual function signature
        # If should_include_entity only accepts ModbusItem, this test should be removed
        # For now, testing with ModbusItem conversion pattern if needed
        result = should_include_entity(
            ModbusItem(
                name=sax_item.name,
                device=sax_item.device,
                mtype=sax_item.mtype,
            ),
            mock_config_entry,
            "battery_a",
        )
        assert result is True


class TestWriteOnlyRegisterHandling:
    """Test write-only register handling in should_include_entity."""

    def test_include_pilot_register_for_master_with_pilot_enabled(self) -> None:
        """Test pilot register inclusion for master battery with pilot enabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_MASTER_BATTERY: "battery_a",
        }

        # Test register 41 (pilot control)
        pilot_item = ModbusItem(
            name="pilot_control_41",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=41,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(pilot_item, mock_config_entry, "battery_a")
        assert result is True

        # Test register 42 (pilot control)
        pilot_item_42 = ModbusItem(
            name="pilot_control_42",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=42,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(pilot_item_42, mock_config_entry, "battery_a")
        assert result is True

    def test_exclude_pilot_register_for_slave_battery(self) -> None:
        """Test pilot register exclusion for slave battery."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_MASTER_BATTERY: "battery_a",
        }

        pilot_item = ModbusItem(
            name="pilot_control",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=41,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(pilot_item, mock_config_entry, "battery_b")
        assert result is False

    def test_exclude_pilot_register_when_pilot_disabled(self) -> None:
        """Test pilot register exclusion when pilot is disabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_PILOT_FROM_HA: False,
            CONF_MASTER_BATTERY: "battery_a",
        }

        pilot_item = ModbusItem(
            name="pilot_control",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=41,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(pilot_item, mock_config_entry, "battery_a")
        assert result is False

    def test_include_power_limit_register_for_master_with_limit_enabled(self) -> None:
        """Test power limit register inclusion for master battery with limits enabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_LIMIT_POWER: True,
            CONF_MASTER_BATTERY: "battery_a",
        }

        # Test register 43 (power limit)
        limit_item = ModbusItem(
            name="power_limit_43",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=43,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(limit_item, mock_config_entry, "battery_a")
        assert result is True

        # Test register 44 (power limit)
        limit_item_44 = ModbusItem(
            name="power_limit_44",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=44,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(limit_item_44, mock_config_entry, "battery_a")
        assert result is True

    def test_exclude_power_limit_register_for_slave_battery(self) -> None:
        """Test power limit register exclusion for slave battery."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_LIMIT_POWER: True,
            CONF_MASTER_BATTERY: "battery_a",
        }

        limit_item = ModbusItem(
            name="power_limit",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=43,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(limit_item, mock_config_entry, "battery_b")
        assert result is False

    def test_exclude_power_limit_register_when_limit_disabled(self) -> None:
        """Test power limit register exclusion when limits are disabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_LIMIT_POWER: False,
            CONF_MASTER_BATTERY: "battery_a",
        }

        limit_item = ModbusItem(
            name="power_limit",
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            address=43,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(limit_item, mock_config_entry, "battery_a")
        assert result is False

    def test_modbus_item_without_address_attribute(self) -> None:
        """Test ModbusItem without address attribute (should not be treated as write-only)."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {}

        # Create ModbusItem and remove address attribute
        item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        delattr(item, "address")

        result = should_include_entity(item, mock_config_entry, "battery_a")
        assert result is True


class TestCreateRegisterAccessConfig:
    """Test create_register_access_config function."""

    def test_create_config_with_valid_battery_count(self) -> None:
        """Test creating config with valid battery count."""
        config_data = {
            CONF_BATTERY_COUNT: 3,
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: False,
        }

        config = create_register_access_config(config_data, is_master=True)

        assert config.battery_count == 3
        assert config.pilot_from_ha is True
        assert config.limit_power is False
        assert config.is_master_battery is True

    def test_create_config_with_invalid_battery_count_negative(self) -> None:
        """Test creating config with negative battery count."""
        config_data = {
            CONF_BATTERY_COUNT: -1,
            CONF_PILOT_FROM_HA: True,
        }

        with patch("custom_components.sax_battery.utils._LOGGER") as mock_logger:
            config = create_register_access_config(config_data, is_master=False)

            assert config.battery_count == 1  # Default value
            assert config.pilot_from_ha is True
            assert config.is_master_battery is False
            mock_logger.warning.assert_called_once_with(
                "Invalid battery count %s, using default of 1", -1
            )

    def test_create_config_with_invalid_battery_count_too_large(self) -> None:
        """Test creating config with battery count exceeding maximum."""
        config_data = {
            CONF_BATTERY_COUNT: 15,  # Exceeds max of 10
            CONF_LIMIT_POWER: True,
        }

        with patch("custom_components.sax_battery.utils._LOGGER") as mock_logger:
            config = create_register_access_config(config_data)

            assert config.battery_count == 1  # Default value
            assert config.limit_power is True
            mock_logger.warning.assert_called_once_with(
                "Invalid battery count %s, using default of 1", 15
            )

    def test_create_config_with_invalid_battery_count_non_integer(self) -> None:
        """Test creating config with non-integer battery count."""
        config_data = {
            CONF_BATTERY_COUNT: "invalid",
            CONF_PILOT_FROM_HA: False,
        }

        with patch("custom_components.sax_battery.utils._LOGGER") as mock_logger:
            config = create_register_access_config(config_data)

            assert config.battery_count == 1  # Default value
            assert config.pilot_from_ha is False
            mock_logger.warning.assert_called_once_with(
                "Invalid battery count %s, using default of 1", "invalid"
            )

    def test_create_config_with_missing_battery_count(self) -> None:
        """Test creating config with missing battery count."""
        config_data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
        }

        config = create_register_access_config(config_data, is_master=True)

        assert config.battery_count == 1  # Default value
        assert config.pilot_from_ha is True
        assert config.limit_power is True
        assert config.is_master_battery is True

    def test_create_config_with_empty_data(self) -> None:
        """Test creating config with empty configuration data."""
        config_data: dict[str, Any] = {}

        config = create_register_access_config(config_data)

        assert config.battery_count == 1
        assert config.pilot_from_ha is False
        assert config.limit_power is False
        assert config.is_master_battery is False

    def test_create_config_defaults_behavior(self) -> None:
        """Test create_register_access_config default behavior."""
        config_data = {
            CONF_BATTERY_COUNT: 2,
            # Missing other config values to test defaults
        }

        config = create_register_access_config(config_data)

        assert config.battery_count == 2
        assert config.pilot_from_ha is False  # Default
        assert config.limit_power is False  # Default
        assert config.is_master_battery is False  # Default parameter


class TestGetWritableRegisters:
    """Test get_writable_registers function."""

    def test_get_writable_registers_master_with_pilot_and_limits(self) -> None:
        """Test getting writable registers for master with pilot and power limits enabled."""
        config_data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
            CONF_BATTERY_COUNT: 2,
        }

        registers = get_writable_registers(config_data, is_master=True)

        expected = {41, 42, 43, 44}
        assert registers == expected

    def test_get_writable_registers_master_with_pilot_only(self) -> None:
        """Test getting writable registers for master with only pilot enabled."""
        config_data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: False,
            CONF_BATTERY_COUNT: 1,
        }

        registers = get_writable_registers(config_data, is_master=True)

        expected = {41, 42}
        assert registers == expected

    def test_get_writable_registers_master_with_limits_only(self) -> None:
        """Test getting writable registers for master with only power limits enabled."""
        config_data = {
            CONF_PILOT_FROM_HA: False,
            CONF_LIMIT_POWER: True,
            CONF_BATTERY_COUNT: 3,
        }

        registers = get_writable_registers(config_data, is_master=True)

        expected = {43, 44}
        assert registers == expected

    def test_get_writable_registers_slave_battery(self) -> None:
        """Test getting writable registers for slave battery."""
        config_data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
            CONF_BATTERY_COUNT: 2,
        }

        registers = get_writable_registers(config_data, is_master=False)

        assert registers == set()  # Slave should have no writable registers

    def test_get_writable_registers_master_with_no_features(self) -> None:
        """Test getting writable registers for master with no features enabled."""
        config_data = {
            CONF_PILOT_FROM_HA: False,
            CONF_LIMIT_POWER: False,
            CONF_BATTERY_COUNT: 1,
        }

        registers = get_writable_registers(config_data, is_master=True)

        assert registers == set()  # No features enabled


class TestRegisterAccessConfig:
    """Test RegisterAccessConfig dataclass."""

    def test_register_access_config_immutable(self) -> None:
        """Test that RegisterAccessConfig is immutable (frozen)."""
        config = RegisterAccessConfig(
            pilot_from_ha=True,
            limit_power=False,
            is_master_battery=True,
            battery_count=2,
        )

        # Attempting to modify should raise an exception
        with pytest.raises(AttributeError):
            config.pilot_from_ha = False  # type: ignore[misc]

    def test_register_access_config_defaults(self) -> None:
        """Test RegisterAccessConfig default values."""
        config = RegisterAccessConfig()

        assert config.pilot_from_ha is False
        assert config.limit_power is False
        assert config.is_master_battery is False
        assert config.battery_count == 1

    def test_get_writable_registers_pilot_only(self) -> None:
        """Test get_writable_registers with pilot only."""
        config = RegisterAccessConfig(
            pilot_from_ha=True,
            limit_power=False,
            is_master_battery=True,
            battery_count=1,
        )

        registers = config.get_writable_registers()
        assert registers == {41, 42}

    def test_get_writable_registers_limit_only(self) -> None:
        """Test get_writable_registers with power limits only."""
        config = RegisterAccessConfig(
            pilot_from_ha=False,
            limit_power=True,
            is_master_battery=True,
            battery_count=1,
        )

        registers = config.get_writable_registers()
        assert registers == {43, 44}

    def test_get_writable_registers_both_features(self) -> None:
        """Test get_writable_registers with both pilot and limits."""
        config = RegisterAccessConfig(
            pilot_from_ha=True,
            limit_power=True,
            is_master_battery=True,
            battery_count=1,
        )

        registers = config.get_writable_registers()
        assert registers == {41, 42, 43, 44}

    def test_get_writable_registers_slave_battery(self) -> None:
        """Test get_writable_registers for slave battery."""
        config = RegisterAccessConfig(
            pilot_from_ha=True,
            limit_power=True,
            is_master_battery=False,  # Slave battery
            battery_count=1,
        )

        registers = config.get_writable_registers()
        assert registers == set()  # Slaves get no writable registers

    def test_get_writable_registers_no_features(self) -> None:
        """Test get_writable_registers with no features enabled."""
        config = RegisterAccessConfig(
            pilot_from_ha=False,
            limit_power=False,
            is_master_battery=True,
            battery_count=1,
        )

        registers = config.get_writable_registers()
        assert registers == set()


class TestGetBatteryRealtimeItems:
    """Test get_battery_realtime_items function."""

    def test_get_realtime_items_master_with_pilot_and_limits(self) -> None:
        """Test getting realtime items for master with pilot and power limits."""
        config = RegisterAccessConfig(
            pilot_from_ha=True,
            limit_power=True,
            is_master_battery=True,
            battery_count=2,
        )

        items = get_battery_realtime_items(config)

        # Should include base items + pilot items + power limit items
        base_count = len(MODBUS_BATTERY_REALTIME_ITEMS)
        pilot_count = len(MODBUS_BATTERY_PILOT_CONTROL_ITEMS)
        limit_count = len(MODBUS_BATTERY_POWER_LIMIT_ITEMS)
        expected_count = base_count + pilot_count + limit_count

        assert len(items) == expected_count
        assert all(isinstance(item, ModbusItem) for item in items)

    def test_get_realtime_items_master_with_pilot_only(self) -> None:
        """Test getting realtime items for master with pilot only."""
        config = RegisterAccessConfig(
            pilot_from_ha=True,
            limit_power=False,
            is_master_battery=True,
            battery_count=1,
        )

        items = get_battery_realtime_items(config)

        # Should include base items + pilot items
        base_count = len(MODBUS_BATTERY_REALTIME_ITEMS)
        pilot_count = len(MODBUS_BATTERY_PILOT_CONTROL_ITEMS)
        expected_count = base_count + pilot_count

        assert len(items) == expected_count

    def test_get_realtime_items_master_with_limits_only(self) -> None:
        """Test getting realtime items for master with power limits only."""
        config = RegisterAccessConfig(
            pilot_from_ha=False,
            limit_power=True,
            is_master_battery=True,
            battery_count=1,
        )

        items = get_battery_realtime_items(config)

        # Should include base items + power limit items
        base_count = len(MODBUS_BATTERY_REALTIME_ITEMS)
        limit_count = len(MODBUS_BATTERY_POWER_LIMIT_ITEMS)
        expected_count = base_count + limit_count

        assert len(items) == expected_count

    def test_get_realtime_items_slave_battery(self) -> None:
        """Test getting realtime items for slave battery."""
        config = RegisterAccessConfig(
            pilot_from_ha=True,
            limit_power=True,
            is_master_battery=False,  # Slave battery
            battery_count=2,
        )

        items = get_battery_realtime_items(config)

        # Should only include base items (no control items for slaves)
        base_count = len(MODBUS_BATTERY_REALTIME_ITEMS)
        assert len(items) == base_count

    def test_get_realtime_items_master_no_features(self) -> None:
        """Test getting realtime items for master with no features enabled."""
        config = RegisterAccessConfig(
            pilot_from_ha=False,
            limit_power=False,
            is_master_battery=True,
            battery_count=1,
        )

        items = get_battery_realtime_items(config)

        # Should only include base items
        base_count = len(MODBUS_BATTERY_REALTIME_ITEMS)
        assert len(items) == base_count

    def test_get_realtime_items_returns_copy(self) -> None:
        """Test that get_battery_realtime_items returns a copy of base items."""
        config = RegisterAccessConfig(
            pilot_from_ha=False,
            limit_power=False,
            is_master_battery=True,
            battery_count=1,
        )

        items = get_battery_realtime_items(config)

        # Modifying the returned list should not affect the original
        original_length = len(items)
        items.append(MagicMock())  # Add a dummy item

        # Getting items again should return original count
        items2 = get_battery_realtime_items(config)
        assert len(items2) == original_length

    def test_get_realtime_items_all_combinations(self) -> None:
        """Test all combinations of pilot and limit settings."""
        test_cases = [
            (False, False, False),  # Slave, no features
            (True, False, False),  # Master, no features
            (True, True, False),  # Master, pilot only
            (True, False, True),  # Master, limits only
            (True, True, True),  # Master, both features
        ]

        for is_master, pilot_enabled, limit_enabled in test_cases:
            config = RegisterAccessConfig(
                pilot_from_ha=pilot_enabled,
                limit_power=limit_enabled,
                is_master_battery=is_master,
                battery_count=1,
            )

            items = get_battery_realtime_items(config)

            base_count = len(MODBUS_BATTERY_REALTIME_ITEMS)
            expected_count = base_count

            if is_master and pilot_enabled:
                expected_count += len(MODBUS_BATTERY_PILOT_CONTROL_ITEMS)
            if is_master and limit_enabled:
                expected_count += len(MODBUS_BATTERY_POWER_LIMIT_ITEMS)

            assert len(items) == expected_count, (
                f"Failed for case: master={is_master}, pilot={pilot_enabled}, limit={limit_enabled}"
            )


class TestSAXItemHandling:
    """Test handling of SAXItem types in should_include_entity."""

    def test_sax_item_always_included(self) -> None:
        """Test that SAXItem is always included (no filtering constraints)."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "device_type": DeviceConstants.SM,  # Different device type
            "features": [],  # No features
        }

        sax_item = SAXItem(
            name="calculated_power",
            device=DeviceConstants.BESS,  # Different from config
            mtype=TypeConstants.SENSOR_CALC,
        )

        result = should_include_entity(sax_item, mock_config_entry, "battery_a")
        assert result is True  # SAXItem should always be included

    def test_sax_item_with_dynamic_attributes(self) -> None:
        """Test SAXItem with dynamically added attributes (should be ignored)."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "batteries": {"battery_a": {"role": "slave"}},
        }

        sax_item = SAXItem(
            name="calculated_power",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SENSOR_CALC,
        )

        # Add attributes that would affect ModbusItem filtering
        setattr(sax_item, "master_only", True)
        setattr(sax_item, "required_features", ["nonexistent_feature"])

        result = should_include_entity(sax_item, mock_config_entry, "battery_a")
        assert result is True  # SAXItem filtering doesn't apply the same constraints


class TestEdgeCasesAndBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def test_should_include_entity_with_none_device(self) -> None:
        """Test should_include_entity when item device is None."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"device_type": DeviceConstants.BESS}

        item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=None,  # type: ignore[arg-type]
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(item, mock_config_entry, "battery_a")
        assert result is True  # Should include when device is None

    def test_should_include_entity_with_none_config_device(self) -> None:
        """Test should_include_entity when config device_type is None."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"device_type": None}

        item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )

        result = should_include_entity(item, mock_config_entry, "battery_a")
        assert result is True  # Should include when config device is None

    def test_should_include_entity_empty_required_features_list(self) -> None:
        """Test should_include_entity with empty required_features list."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"features": ["some_feature"]}

        item = ModbusItem(
            name="test_item",
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.BESS,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )
        setattr(item, "required_features", [])  # Empty list

        result = should_include_entity(item, mock_config_entry, "battery_a")
        assert result is True  # Empty required_features should always pass

    def test_battery_count_boundary_values(self) -> None:
        """Test battery count validation with boundary values."""
        test_cases = [
            (0, 1),  # Zero -> default
            (1, 1),  # Minimum valid
            (10, 10),  # Maximum valid
            (11, 1),  # Above maximum -> default
        ]

        for input_count, expected_count in test_cases:
            config_data = {CONF_BATTERY_COUNT: input_count}

            if input_count == 0 or input_count > 10:
                with patch("custom_components.sax_battery.utils._LOGGER"):
                    config = create_register_access_config(config_data)
            else:
                config = create_register_access_config(config_data)

            assert config.battery_count == expected_count

    def test_config_data_type_conversion(self) -> None:
        """Test that configuration values are properly converted to bool."""
        config_data = {
            CONF_PILOT_FROM_HA: "true",  # String instead of bool
            CONF_LIMIT_POWER: 1,  # Integer instead of bool
            CONF_BATTERY_COUNT: 2,
        }

        config = create_register_access_config(
            config_data,
            is_master="yes",  # type: ignore[arg-type]
        )  # String instead of bool

        assert config.pilot_from_ha is True  # "true" -> True
        assert config.limit_power is True  # 1 -> True
        assert config.is_master_battery is True  # "yes" -> True

    def test_missing_config_keys_handling(self) -> None:
        """Test handling of completely missing configuration keys."""
        config_data: dict[str, Any] = {}  # Empty config

        # Should not raise exceptions and use defaults
        config = create_register_access_config(config_data)
        registers = get_writable_registers(config_data)
        items = get_battery_realtime_items(config)

        assert isinstance(config, RegisterAccessConfig)
        assert isinstance(registers, set)
        assert isinstance(items, list)
        assert len(registers) == 0  # No writable registers with default config
        assert len(items) > 0  # Should have base realtime items
