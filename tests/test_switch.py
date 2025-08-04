"""Test switch platform for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ApiItem
from custom_components.sax_battery.switch import SAXBatterySwitch
from homeassistant.exceptions import HomeAssistantError


class TestSAXBatterySwitch:
    """Test SAX Battery switch entity."""

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create mock coordinator."""
        coordinator = MagicMock()
        coordinator.data = {"test_switch": 1}
        coordinator.last_update_success = True
        coordinator.async_write_switch_value = AsyncMock(return_value=True)

        # Mock sax_data and device info
        mock_sax_data = MagicMock()
        mock_sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "battery_1")},
            "name": "SAX Battery 1",
            "manufacturer": "SAX Power",
            "model": "Battery System",
        }
        coordinator.sax_data = mock_sax_data

        return coordinator

    @pytest.fixture
    def modbus_item(self) -> ApiItem:
        """Create a test modbus item."""
        return ApiItem(
            name="test_switch",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.STATUS,
            mtype=TypeConstants.SWITCH,
        )

    def test_switch_initialization(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test switch entity initialization."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.unique_id == "battery_1_test_switch_0"
        assert switch.name == "Test Switch"
        assert switch._battery_id == "battery_1"
        assert switch._modbus_item == modbus_item

    def test_switch_is_on_true(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
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
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
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
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
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
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test turn_on operation failure."""
        mock_coordinator.async_write_switch_value.return_value = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        with pytest.raises(HomeAssistantError, match="Failed to turn on Test Switch"):
            await switch.async_turn_on()

    def test_switch_extra_state_attributes(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test extra state attributes."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        attrs = switch.extra_state_attributes

        assert attrs["battery_id"] == "battery_1"
        assert attrs["modbus_address"] == 1000
        assert "last_update" in attrs
        assert "raw_value" in attrs

    def test_switch_unavailable_coordinator(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test switch behavior when coordinator is unavailable."""
        mock_coordinator.last_update_success = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.available is False

    def test_switch_no_data(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test switch behavior when coordinator has no data."""
        mock_coordinator.data = None

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.is_on is None
        assert switch.available is False

    def test_switch_missing_data_key(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test switch behavior when data key is missing."""
        mock_coordinator.data = {"other_switch": 1}

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.is_on is None
        assert switch.available is False

    def test_switch_string_values(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test switch with string values."""
        test_cases = [
            ("on", True),
            ("off", False),
            ("true", True),
            ("false", False),
            ("1", True),
            ("0", False),
            ("yes", True),
            ("no", False),
            ("ON", True),
            ("OFF", False),
        ]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        for string_value, expected_bool in test_cases:
            mock_coordinator.data = {"test_switch": string_value}
            assert switch.is_on is expected_bool, f"Failed for '{string_value}'"

    async def test_switch_turn_off_success(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test successful turn_off operation."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        await switch.async_turn_off()

        mock_coordinator.async_write_switch_value.assert_called_once_with(
            modbus_item, False
        )

    async def test_switch_turn_off_failure(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test turn_off operation failure."""
        mock_coordinator.async_write_switch_value.return_value = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        with pytest.raises(HomeAssistantError, match="Failed to turn off Test Switch"):
            await switch.async_turn_off()

    def test_switch_device_info(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test device info property."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        device_info = switch.device_info

        assert device_info["identifiers"] == {("sax_battery", "battery_1")}
        assert device_info["name"] == "SAX Battery 1"
        assert device_info["manufacturer"] == "SAX Power"

    def test_switch_icon_property(
        self, mock_coordinator: MagicMock, modbus_item: ApiItem
    ) -> None:
        """Test icon property."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator,
            battery_id="battery_1",
            modbus_item=modbus_item,
            index=0,
        )

        assert switch.icon == "mdi:toggle-switch"
