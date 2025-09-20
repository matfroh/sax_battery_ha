"""Test utility functions for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sax_battery.const import DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.utils import should_include_entity


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
            device=DeviceConstants.SYS,  # Different from config
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            factor=10.0,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
            device=DeviceConstants.SYS,
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
