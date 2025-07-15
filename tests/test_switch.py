"""Test switch platform for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.switch import SAXBatterySwitch
from homeassistant.exceptions import HomeAssistantError


class TestSAXBatterySwitch:
    """Test SAX Battery switch."""

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create mock coordinator."""
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.last_update_success_time = 1234567890.0
        coordinator.data = {"test_switch": 1}
        coordinator.sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "battery_1")},
            "name": "SAX Battery 1",
        }
        coordinator.async_write_switch_value = AsyncMock(return_value=True)
        return coordinator

    @pytest.fixture
    def modbus_item(self) -> ModbusItem:
        """Create test ModbusItem."""
        item = ModbusItem(
            battery_slave_id=1,
            address=100,
            name="test_switch",
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        )
        item.on_value = 1
        item.off_value = 0
        return item

    def test_switch_initialization(
        self, mock_coordinator: MagicMock, modbus_item: ModbusItem
    ) -> None:
        """Test switch entity initialization."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.unique_id == "battery_1_test_switch_0"
        assert switch.name == "Battery_1 Test Switch"

    def test_switch_is_on_true(
        self, mock_coordinator: MagicMock, modbus_item: ModbusItem
    ) -> None:
        """Test switch is_on returns True when value matches on_value."""
        mock_coordinator.data = {"test_switch": 1}

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.is_on is True

    def test_switch_is_on_false(
        self, mock_coordinator: MagicMock, modbus_item: ModbusItem
    ) -> None:
        """Test switch is_on returns False when value matches off_value."""
        mock_coordinator.data = {"test_switch": 0}

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.is_on is False

    async def test_switch_turn_on_success(
        self, mock_coordinator: MagicMock, modbus_item: ModbusItem
    ) -> None:
        """Test successful turn_on operation."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        await switch.async_turn_on()

        mock_coordinator.async_write_switch_value.assert_called_once_with(
            modbus_item, True
        )

    async def test_switch_turn_on_failure(
        self, mock_coordinator: MagicMock, modbus_item: ModbusItem
    ) -> None:
        """Test turn_on operation failure."""
        mock_coordinator.async_write_switch_value.return_value = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()

    def test_switch_extra_state_attributes(
        self, mock_coordinator: MagicMock, modbus_item: ModbusItem
    ) -> None:
        """Test extra state attributes."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        attributes = switch.extra_state_attributes
        assert attributes is not None
        assert attributes["battery_id"] == "battery_1"
        assert attributes["modbus_address"] == 100
        assert attributes["last_updated"] == 1234567890.0
        assert attributes["on_value"] == 1
        assert attributes["off_value"] == 0

    def test_switch_unavailable_coordinator(
        self, mock_coordinator: MagicMock, modbus_item: ModbusItem
    ) -> None:
        """Test switch behavior when coordinator is unavailable."""
        mock_coordinator.last_update_success = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.is_on is None
        assert switch.extra_state_attributes is None
