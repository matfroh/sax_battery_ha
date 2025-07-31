"""Test entity utilities for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sax_battery.entity_utils import filter_items_by_type
from custom_components.sax_battery.enums import TypeConstants
from custom_components.sax_battery.items import ModbusItem
from homeassistant.config_entries import ConfigEntry


class TestFilterItemsByType:
    """Test filter_items_by_type function."""

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        """Create mock config entry."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        return entry

    @pytest.fixture
    def mock_modbus_items(self) -> list[ModbusItem]:
        """Create mock modbus items."""
        items: list[ModbusItem] = []

        # Sensor item
        sensor_item = MagicMock(spec=ModbusItem)
        sensor_item.name = "voltage"
        sensor_item.mtype = TypeConstants.SENSOR
        items.append(sensor_item)

        # Number item
        number_item = MagicMock(spec=ModbusItem)
        number_item.name = "charge_limit"
        number_item.mtype = TypeConstants.NUMBER
        items.append(number_item)

        # Switch item
        switch_item = MagicMock(spec=ModbusItem)
        switch_item.name = "manual_control"
        switch_item.mtype = TypeConstants.SWITCH
        items.append(switch_item)

        return items

    def test_filter_sensor_items(self, mock_modbus_items, mock_config_entry):
        """Test filtering sensor items."""
        with pytest.patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=True,
        ):
            result = filter_items_by_type(
                mock_modbus_items,
                TypeConstants.SENSOR,
                mock_config_entry,
                "battery_a",
            )

            assert len(result) == 1
            assert result[0].name == "voltage"
            assert result[0].mtype == TypeConstants.SENSOR

    def test_filter_number_items(self, mock_modbus_items, mock_config_entry):
        """Test filtering number items."""
        with pytest.patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=True,
        ):
            result = filter_items_by_type(
                mock_modbus_items,
                TypeConstants.NUMBER,
                mock_config_entry,
                "battery_a",
            )

            assert len(result) == 1
            assert result[0].name == "charge_limit"
            assert result[0].mtype == TypeConstants.NUMBER

    def test_filter_switch_items(self, mock_modbus_items, mock_config_entry):
        """Test filtering switch items."""
        with pytest.patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=True,
        ):
            result = filter_items_by_type(
                mock_modbus_items,
                TypeConstants.SWITCH,
                mock_config_entry,
                "battery_a",
            )

            assert len(result) == 1
            assert result[0].name == "manual_control"
            assert result[0].mtype == TypeConstants.SWITCH

    def test_filter_excludes_items(self, mock_modbus_items, mock_config_entry):
        """Test filtering excludes items based on should_include_entity."""
        with pytest.patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=False,
        ):
            result = filter_items_by_type(
                mock_modbus_items,
                TypeConstants.SENSOR,
                mock_config_entry,
                "battery_a",
            )

            assert len(result) == 0

    def test_filter_no_matching_type(self, mock_modbus_items, mock_config_entry):
        """Test filtering with no matching type."""
        with pytest.patch(
            "custom_components.sax_battery.entity_utils.should_include_entity",
            return_value=True,
        ):
            result = filter_items_by_type(
                mock_modbus_items,
                TypeConstants.SENSOR_CALC,  # No calc sensors in mock data
                mock_config_entry,
                "battery_a",
            )

            assert len(result) == 0

    def test_filter_empty_items_list(self, mock_config_entry):
        """Test filtering with empty items list."""
        result = filter_items_by_type(
            [],
            TypeConstants.SENSOR,
            mock_config_entry,
            "battery_a",
        )

        assert len(result) == 0
