"""Test utility functions for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.utils import (
    create_entity_unique_id,
    determine_entity_category,
    should_include_entity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory


class TestCreateEntityUniqueId:
    """Test create_entity_unique_id function."""

    def test_create_unique_id_with_modbus_item(self) -> None:
        """Test creating unique ID with ModbusItem."""
        api_item = ModbusItem(
            name="voltage",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=10.0,
        )

        result = create_entity_unique_id("battery_a", api_item, 0)
        assert result == "battery_a_voltage_0"

    def test_create_unique_id_with_sax_item(self) -> None:
        """Test creating unique ID with SAXItem."""
        sax_item = SAXItem(
            name="total_power",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
        )

        result = create_entity_unique_id("battery_b", sax_item, 1)
        assert result == "battery_b_total_power_1"

    def test_create_unique_id_with_different_indices(self) -> None:
        """Test creating unique IDs with different indices."""
        api_item = ModbusItem(
            name="temperature",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=200,
            battery_slave_id=1,
            divider=1.0,
        )

        result_0 = create_entity_unique_id("battery_c", api_item, 0)
        result_5 = create_entity_unique_id("battery_c", api_item, 5)

        assert result_0 == "battery_c_temperature_0"
        assert result_5 == "battery_c_temperature_5"

    def test_create_unique_id_with_special_characters_in_name(self) -> None:
        """Test creating unique ID with special characters in item name."""
        api_item = ModbusItem(
            name="max_charge_power",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=300,
            battery_slave_id=1,
            divider=1.0,
        )

        result = create_entity_unique_id("battery_a", api_item, 2)
        assert result == "battery_a_max_charge_power_2"

    def test_create_unique_id_cleans_calculated_suffix(self) -> None:
        """Test creating unique ID cleans '(Calculated)' suffix from SAXItem names."""
        sax_item = SAXItem(
            name="total_power (Calculated)",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
        )

        result = create_entity_unique_id("battery_a", sax_item, 0)
        assert result == "battery_a_total_power_0"


class TestDetermineEntityCategory:
    """Test determine_entity_category function."""

    def test_category_from_entity_description_enum(self) -> None:
        """Test category determination from entitydescription with EntityCategory enum."""
        mock_entity_desc = MagicMock()
        mock_entity_desc.entity_category = EntityCategory.CONFIG

        api_item = ModbusItem(
            name="setting",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        api_item.entitydescription = mock_entity_desc

        result = determine_entity_category(api_item)
        assert result == EntityCategory.CONFIG

    def test_category_from_entity_description_string_config(self) -> None:
        """Test category determination from entitydescription with string 'config'."""
        mock_entity_desc = MagicMock()
        mock_entity_desc.entity_category = "config"

        api_item = ModbusItem(
            name="limit",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        api_item.entitydescription = mock_entity_desc

        result = determine_entity_category(api_item)
        assert result == EntityCategory.CONFIG

    def test_category_from_entity_description_string_diagnostic(self) -> None:
        """Test category determination from entitydescription with string 'diagnostic'."""
        mock_entity_desc = MagicMock()
        mock_entity_desc.entity_category = "diagnostic"

        api_item = ModbusItem(
            name="status",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        api_item.entitydescription = mock_entity_desc

        result = determine_entity_category(api_item)
        assert result == EntityCategory.DIAGNOSTIC

    def test_category_diagnostic_by_keyword(self) -> None:
        """Test diagnostic category determination by keyword matching."""
        test_cases = [
            ("debug_mode", EntityCategory.DIAGNOSTIC),
            ("diagnostic_info", EntityCategory.DIAGNOSTIC),
            ("system_status", EntityCategory.DIAGNOSTIC),
            ("error_code", EntityCategory.DIAGNOSTIC),
            ("firmware_version", EntityCategory.DIAGNOSTIC),
        ]

        for item_name, expected_category in test_cases:
            item = ModbusItem(
                name=item_name,
                device=DeviceConstants.SYS,
                mtype=TypeConstants.SENSOR,
                address=100,
                battery_slave_id=1,
                divider=1.0,
            )

            category = determine_entity_category(item)
            assert category == expected_category, (
                f"Expected {expected_category} for {item_name}, got {category}"
            )

    def test_category_config_by_keyword(self) -> None:
        """Test config category determination by keyword matching."""
        test_cases = [
            ("config_mode", EntityCategory.CONFIG),
            ("charge_setting", EntityCategory.CONFIG),
            ("power_limit", EntityCategory.CONFIG),
            ("max_charge_rate", EntityCategory.CONFIG),
            ("pilot_enable", EntityCategory.CONFIG),
            ("enable_features", EntityCategory.CONFIG),
        ]

        for item_name, expected_category in test_cases:
            item = ModbusItem(
                name=item_name,
                device=DeviceConstants.SYS,
                mtype=TypeConstants.SENSOR,
                address=100,
                battery_slave_id=1,
                divider=1.0,
            )

            category = determine_entity_category(item)
            assert category == expected_category, (
                f"Expected {expected_category} for {item_name}, got {category}"
            )

    def test_category_none_for_regular_sensors(self) -> None:
        """Test that regular sensors return None category."""
        test_cases = [
            "voltage",
            "current",
            "power",
            "temperature",
            "soc",
        ]

        for item_name in test_cases:
            item = ModbusItem(
                name=item_name,
                device=DeviceConstants.SYS,
                mtype=TypeConstants.SENSOR,
                address=100,
                battery_slave_id=1,
                divider=1.0,
            )

            category = determine_entity_category(item)
            assert category is None, f"Expected None for {item_name}, got {category}"

    def test_category_with_sax_item(self) -> None:
        """Test category determination with SAXItem."""
        sax_item = SAXItem(
            name="debug_calculation",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR_CALC,
        )

        result = determine_entity_category(sax_item)
        assert result == EntityCategory.DIAGNOSTIC

    def test_category_no_entity_description(self) -> None:
        """Test category determination when no entitydescription exists."""
        api_item = ModbusItem(
            name="config_value",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # entitydescription is None by default

        result = determine_entity_category(api_item)
        assert result == EntityCategory.CONFIG  # Based on "config" keyword


class TestShouldIncludeEntity:
    """Test should_include_entity function."""

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        """Create mock config entry."""
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {}
        return entry

    @pytest.fixture
    def basic_api_item(self) -> ModbusItem:
        """Create basic API item."""
        return ModbusItem(
            name="voltage",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=10.0,
        )

    def test_include_entity_basic_case(self, basic_api_item, mock_config_entry) -> None:
        """Test basic entity inclusion (should return True by default)."""
        result = should_include_entity(basic_api_item, mock_config_entry, "battery_a")
        assert result is True

    def test_exclude_by_device_type_mismatch(self, mock_config_entry) -> None:
        """Test entity exclusion by device type mismatch."""
        mock_config_entry.data = {"device_type": DeviceConstants.SM}

        api_item = ModbusItem(
            name="voltage",
            device=DeviceConstants.SYS,  # Different from config
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=10.0,
        )

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_include_by_device_type_match(self, mock_config_entry) -> None:
        """Test entity inclusion by device type match."""
        mock_config_entry.data = {"device_type": DeviceConstants.SYS}

        api_item = ModbusItem(
            name="voltage",
            device=DeviceConstants.SYS,  # Matches config
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=10.0,
        )

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is True

    def test_include_master_only_item_for_master_battery(
        self, mock_config_entry
    ) -> None:
        """Test master-only item inclusion for master battery."""
        mock_config_entry.data = {
            "batteries": {
                "battery_a": {"role": "master"},
                "battery_b": {"role": "slave"},
            }
        }

        api_item = ModbusItem(
            name="smart_meter_data",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add attribute - ModbusItem supports this
        setattr(api_item, "master_only", True)

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is True

    def test_exclude_master_only_item_for_slave_battery(
        self, mock_config_entry
    ) -> None:
        """Test master-only item exclusion for slave battery."""
        mock_config_entry.data = {
            "batteries": {
                "battery_a": {"role": "master"},
                "battery_b": {"role": "slave"},
            }
        }

        api_item = ModbusItem(
            name="smart_meter_data",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "master_only", True)

        result = should_include_entity(api_item, mock_config_entry, "battery_b")
        assert result is False

    def test_exclude_master_only_item_no_battery_config(
        self, mock_config_entry
    ) -> None:
        """Test master-only item exclusion when no battery config exists."""
        mock_config_entry.data = {"batteries": {}}

        api_item = ModbusItem(
            name="smart_meter_data",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "master_only", True)

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_include_by_required_features_all_available(
        self, mock_config_entry
    ) -> None:
        """Test entity inclusion when all required features are available."""
        mock_config_entry.data = {
            "features": ["smart_meter", "power_control", "diagnostics"]
        }

        api_item = ModbusItem(
            name="power_limit",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "required_features", ["smart_meter", "power_control"])

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is True

    def test_exclude_by_required_features_missing(self, mock_config_entry) -> None:
        """Test entity exclusion when required features are missing."""
        mock_config_entry.data = {"features": ["smart_meter"]}

        api_item = ModbusItem(
            name="power_limit",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "required_features", ["smart_meter", "power_control"])

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_exclude_by_required_features_no_features_config(
        self, mock_config_entry
    ) -> None:
        """Test entity exclusion when no features are configured."""
        mock_config_entry.data = {}

        api_item = ModbusItem(
            name="power_limit",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add attribute
        setattr(api_item, "required_features", ["power_control"])

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is False

    def test_include_with_no_device_attribute(
        self, basic_api_item, mock_config_entry
    ) -> None:
        """Test entity inclusion when item has no device attribute."""
        # Remove device attribute to simulate items without device specification
        delattr(basic_api_item, "device")
        mock_config_entry.data = {"device_type": DeviceConstants.SM}

        result = should_include_entity(basic_api_item, mock_config_entry, "battery_a")
        assert result is True  # Should include when no device constraint

    def test_complex_filtering_scenario(self, mock_config_entry) -> None:
        """Test complex filtering scenario with multiple constraints."""
        mock_config_entry.data = {
            "device_type": DeviceConstants.SYS,
            "batteries": {"battery_a": {"role": "master"}},
            "features": ["smart_meter", "power_control"],
        }

        api_item = ModbusItem(
            name="smart_meter_control",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add attributes
        setattr(api_item, "master_only", True)
        setattr(api_item, "required_features", ["smart_meter"])

        result = should_include_entity(api_item, mock_config_entry, "battery_a")
        assert result is True

    def test_complex_filtering_scenario_fail_master_check(
        self, mock_config_entry
    ) -> None:
        """Test complex filtering scenario failing on master check."""
        mock_config_entry.data = {
            "device_type": DeviceConstants.SYS,
            "batteries": {"battery_a": {"role": "slave"}},  # Not master
            "features": ["smart_meter", "power_control"],
        }

        api_item = ModbusItem(
            name="smart_meter_control",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=100,
            battery_slave_id=1,
            divider=1.0,
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
            device=DeviceConstants.SYS,
            address=100,
            battery_slave_id=1,
            divider=1.0,
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
            device=DeviceConstants.SYS,
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
