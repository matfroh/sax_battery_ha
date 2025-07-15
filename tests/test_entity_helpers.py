"""Test entity helpers for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.sax_battery.entity_helpers import build_entity_list
from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.utils import (
    determine_entity_category,
    should_include_entity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity


class TestEntityHelpers:
    """Test entity helper functions."""

    def test_should_include_entity_master_only_true(self) -> None:
        """Test should_include_entity with master_only entity for master battery."""
        item = ModbusItem(
            battery_slave_id=1,
            address=100,
            name="test_sensor",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )
        item.master_only = True

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {"batteries": {"battery_1": {"role": "master"}}}

        result = should_include_entity(item, config_entry, "battery_1")
        assert result is True

    def test_should_include_entity_master_only_false(self) -> None:
        """Test should_include_entity with master_only entity for slave battery."""
        item = ModbusItem(
            battery_slave_id=1,
            address=100,
            name="test_sensor",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )
        item.master_only = True

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {"batteries": {"battery_1": {"role": "slave"}}}

        result = should_include_entity(item, config_entry, "battery_1")
        assert result is False

    def test_determine_entity_category_diagnostic(self) -> None:
        """Test determine_entity_category returns diagnostic category."""
        item = ModbusItem(
            battery_slave_id=1,
            address=100,
            name="debug_sensor",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        result = determine_entity_category(item)
        assert result is not None
        assert result.value == "diagnostic"

    def test_determine_entity_category_config(self) -> None:
        """Test determine_entity_category returns config category."""
        item = ModbusItem(
            battery_slave_id=1,
            address=100,
            name="config_setting",
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
        )

        result = determine_entity_category(item)
        assert result is not None
        assert result.value == "config"

    @patch("custom_components.sax_battery.sensor.SAXBatterySensor")
    async def test_build_entity_list_sensors(self, mock_sensor: MagicMock) -> None:
        """Test build_entity_list creates sensor entities."""
        entries: list[Entity] = []

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {}

        api_items = [
            ModbusItem(
                battery_slave_id=1,
                address=100,
                name="test_sensor",
                mformat=FormatConstants.NUMBER,
                mtype=TypeConstants.SENSOR,
                device=DeviceConstants.SYS,
            )
        ]

        coordinator = MagicMock()

        await build_entity_list(
            entries=entries,
            config_entry=config_entry,
            api_items=api_items,
            item_type=TypeConstants.SENSOR,
            coordinator=coordinator,
            battery_id="battery_1",
        )

        assert len(entries) == 1

    @patch("custom_components.sax_battery.switch.SAXBatterySwitch")
    async def test_build_entity_list_switches(self, mock_switch: MagicMock) -> None:
        """Test build_entity_list creates switch entities."""
        entries: list[Entity] = []

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {}

        api_items = [
            ModbusItem(
                battery_slave_id=1,
                address=100,
                name="test_switch",
                mformat=FormatConstants.STATUS,
                mtype=TypeConstants.SWITCH,
                device=DeviceConstants.SYS,
            )
        ]

        coordinator = MagicMock()

        await build_entity_list(
            entries=entries,
            config_entry=config_entry,
            api_items=api_items,
            item_type=TypeConstants.SWITCH,
            coordinator=coordinator,
            battery_id="battery_1",
        )

        assert len(entries) == 1
