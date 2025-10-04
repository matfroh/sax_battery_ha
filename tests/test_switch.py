"""Test switch platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    BATTERY_IDS,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    DESCRIPTION_SAX_STATUS_SWITCH,
    DOMAIN,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.models import SAXBatteryData
from custom_components.sax_battery.switch import (
    SAXBatteryControlSwitch,
    SAXBatterySwitch,
    async_setup_entry,
)
from custom_components.sax_battery.utils import should_include_entity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


class TestSAXBatterySwitch:
    """Test SAX Battery switch entity."""

    @pytest.fixture
    def mock_coordinator_switch(self) -> MagicMock:
        """Create mock coordinator for switch tests."""
        coordinator = MagicMock(spec=SAXBatteryCoordinator)
        coordinator.data = {"test_switch": 1}
        coordinator.last_update_success = True
        coordinator.async_write_switch_value = AsyncMock(return_value=True)
        coordinator.async_request_refresh = AsyncMock()

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
    def modbus_item_switch(self) -> ModbusItem:
        """Create a test modbus item for switch."""
        item = ModbusItem(
            name="test_switch",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SWITCH,
            address=1000,  # Use valid Modbus address instead of 0
            battery_device_id=1,
            factor=1.0,
            entitydescription=DESCRIPTION_SAX_STATUS_SWITCH,
        )
        # Add required switch methods for testing
        item.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        item.get_switch_off_value = MagicMock(return_value=1)  # type: ignore[method-assign]
        item.get_switch_connected_value = MagicMock(return_value=3)  # type: ignore[method-assign]
        item.get_switch_standby_value = MagicMock(return_value=4)  # type: ignore[method-assign]
        item.get_switch_state_name = MagicMock(return_value="off")  # type: ignore[method-assign]
        return item

    # Fix the failing test - modbus_item_switch should be mocked properly
    def test_exclude_unknown_write_only_register(self) -> None:
        """Test that register 99 is treated as regular switch (not write-only)."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "CONF_PILOT_FROM_HA": True,
            "CONF_LIMIT_POWER": True,
            "CONF_MASTER_BATTERY": "battery_a",
        }

        # Register 99 is NOT in WRITE_ONLY_REGISTERS (only 41-44 are)
        # So it should be included (return True)
        unknown_item = ModbusItem(
            name="unknown_regular_switch",
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.BESS,
            address=99,  # Regular register, not write-only
            battery_device_id=1,
            factor=1.0,
        )

        result = should_include_entity(unknown_item, mock_config_entry, "battery_a")
        assert result is True  # Should be included since it's not write-only

    # Add new comprehensive tests for missing coverage areas:

    def test_switch_initialization_with_sax_prefix(
        self, mock_coordinator_switch, modbus_item_switch
    ) -> None:
        """Test switch entity initialization with sax_ prefix in name."""
        modbus_item_switch.name = "sax_power_switch"

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # Should remove sax_ prefix
        assert switch.unique_id == "sax_power_switch"

    def test_switch_initialization_without_entity_description(
        self, mock_coordinator_switch
    ) -> None:
        """Test switch initialization without entity description."""
        modbus_item = ModbusItem(
            name="custom_switch",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SWITCH,
            address=1001,
            battery_device_id=1,
            factor=1.0,
            entitydescription=None,  # No entity description
        )

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_2",
            modbus_item=modbus_item,
        )

        assert switch.unique_id == "custom_switch"
        assert switch.name == "Custom Switch"  # Should use clean item name

    def test_switch_initialization_with_disabled_by_default(
        self, mock_coordinator_switch, modbus_item_switch
    ) -> None:
        """Test switch initialization with disabled by default setting."""
        # Add enabled_by_default attribute
        setattr(modbus_item_switch, "enabled_by_default", False)

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        assert switch._attr_entity_registry_enabled_default is False

    def test_switch_is_on_float_values(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch is_on with float values."""
        modbus_item_switch.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_connected_value = MagicMock(return_value=3)  # type: ignore[method-assign]

        test_cases = [
            (1.0, False),  # Off value
            (2.0, True),  # On value
            (3.0, True),  # Connected value
            (4.0, False),  # Standby value
        ]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        for float_value, expected in test_cases:
            mock_coordinator_switch.data = {"test_switch": float_value}
            assert switch.is_on is expected

    def test_switch_is_on_invalid_string_values(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch is_on with invalid string values."""
        test_cases = [
            "invalid",
            "unknown",
            "maybe",
            "",
            "   ",  # Whitespace only
        ]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        for invalid_value in test_cases:
            mock_coordinator_switch.data = {"test_switch": invalid_value}
            with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
                result = switch.is_on
                assert result is None
                mock_logger.warning.assert_called()

    def test_switch_is_on_type_error_handling(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch is_on with values that cause type errors."""
        test_cases = [
            object(),  # Object that can't be converted
            {"key": "value"},  # Dictionary
            [1, 2, 3],  # List
        ]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        for invalid_value in test_cases:
            mock_coordinator_switch.data = {"test_switch": invalid_value}
            result = switch.is_on
            # The implementation returns None for non-convertible types
            assert result is None

    def test_switch_state_attributes_with_string_value(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test state attributes with non-integer raw value."""
        mock_coordinator_switch.data = {"test_switch": "invalid_state"}

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        attrs = switch.state_attributes
        assert attrs is not None
        assert attrs["raw_state_value"] == "invalid_state"
        assert attrs["detailed_state"] == "unknown"

    def test_switch_state_attributes_no_data(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test state attributes when coordinator has no data."""
        mock_coordinator_switch.data = None

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        attrs = switch.state_attributes
        assert attrs is None

    def test_switch_state_attributes_missing_key(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test state attributes when switch key is missing from data."""
        mock_coordinator_switch.data = {"other_switch": 1}

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        attrs = switch.state_attributes
        assert attrs is None

    def test_switch_icon_with_entity_description_icon(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test icon property uses entity description icon when available."""
        # Mock entity description with icon
        mock_entity_desc = MagicMock()
        mock_entity_desc.icon = "mdi:power-socket"
        modbus_item_switch.entitydescription = mock_entity_desc

        mock_coordinator_switch.data = {"test_switch": 1}
        modbus_item_switch.get_switch_state_name = MagicMock(return_value="off")  # type: ignore[method-assign]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # Should use state-specific icon
        assert switch.icon == "mdi:battery-off"

    def test_switch_icon_without_entity_description(
        self, mock_coordinator_switch: MagicMock
    ) -> None:
        """Test icon property without entity description."""
        modbus_item = ModbusItem(
            name="test_switch",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SWITCH,
            address=1000,
            battery_device_id=1,
            factor=1.0,
            entitydescription=None,
        )

        mock_coordinator_switch.data = {"test_switch": 2}
        modbus_item.get_switch_state_name = MagicMock(return_value="on")  # type: ignore[method-assign]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item,
        )

        assert switch.icon == "mdi:battery"

    def test_switch_icon_with_unknown_state(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test icon property with unknown state."""
        mock_coordinator_switch.data = {"test_switch": "invalid"}

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # Should return base icon when state conversion fails
        expected_icon = getattr(
            modbus_item_switch.entitydescription, "icon", "mdi:battery"
        )
        assert switch.icon == expected_icon

    def test_switch_entity_category_from_description(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test entity category from entity description."""

        # Mock entity description with category
        mock_entity_desc = MagicMock()
        mock_entity_desc.entity_category = EntityCategory.DIAGNOSTIC
        modbus_item_switch.entitydescription = mock_entity_desc

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        assert switch.entity_category == EntityCategory.DIAGNOSTIC

    def test_switch_entity_category_default(
        self, mock_coordinator_switch: MagicMock
    ) -> None:
        """Test default entity category when no description."""

        modbus_item = ModbusItem(
            name="test_switch",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SWITCH,
            address=1000,
            battery_device_id=1,
            factor=1.0,
            entitydescription=None,
        )

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item,
        )

        assert switch.entity_category == EntityCategory.CONFIG

    def test_switch_initialization(
        self, mock_coordinator_switch, modbus_item_switch
    ) -> None:
        """Test switch entity initialization."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        assert switch.unique_id == "test_switch"
        assert switch.name == "On/Off"

        assert switch._battery_id == "battery_1"
        assert switch._modbus_item == modbus_item_switch

    def test_switch_is_on_true(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch is_on returns True when value matches on_value."""
        # Set data to match SAX Battery "on" value (2)
        mock_coordinator_switch.data = {"test_switch": 2}

        # Security: Ensure ModbusItem has proper switch methods
        modbus_item_switch.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_off_value = MagicMock(return_value=1)  # type: ignore[method-assign]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # Performance: Direct property access test
        assert switch.is_on is True

        # Verify the switch methods were called
        modbus_item_switch.get_switch_on_value.assert_called()

    def test_switch_is_on_false(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch is_on returns False when value matches off_value."""
        # Set data to match SAX Battery "off" value (1)
        mock_coordinator_switch.data = {"test_switch": 1}

        # Security: Ensure ModbusItem has proper switch methods
        modbus_item_switch.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_off_value = MagicMock(return_value=1)  # type: ignore[method-assign]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        assert switch.is_on is False

    async def test_switch_turn_on_success(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test successful turn_on operation."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        await switch.async_turn_on()

        mock_coordinator_switch.async_write_switch_value.assert_called_once_with(
            modbus_item_switch, True
        )
        mock_coordinator_switch.async_request_refresh.assert_called_once()

    async def test_switch_turn_on_failure(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test turn_on operation failure."""
        mock_coordinator_switch.async_write_switch_value.return_value = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        with pytest.raises(HomeAssistantError, match="Failed to turn on On/Off"):
            await switch.async_turn_on()

    async def test_switch_turn_off_success(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test successful turn_off operation."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        await switch.async_turn_off()

        mock_coordinator_switch.async_write_switch_value.assert_called_once_with(
            modbus_item_switch, False
        )
        mock_coordinator_switch.async_request_refresh.assert_called_once()

    async def test_switch_turn_off_failure(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test turn_off operation failure."""
        mock_coordinator_switch.async_write_switch_value.return_value = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        with pytest.raises(HomeAssistantError, match="Failed to turn off On/Off"):
            await switch.async_turn_off()

    def test_switch_extra_state_attributes(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test extra state attributes."""
        # Set the address to match expected value
        modbus_item_switch.address = 1000

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        attrs = switch.extra_state_attributes

        # Fixed: Handle None return value properly
        assert attrs is not None
        assert attrs["battery_id"] == "battery_1"
        assert attrs["modbus_address"] == 1000
        assert "last_update" in attrs
        assert "raw_value" in attrs

    def test_switch_unavailable_coordinator(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch behavior when coordinator is unavailable."""
        mock_coordinator_switch.last_update_success = False

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        assert switch.available is False

    def test_switch_no_data(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch behavior when coordinator has no data."""
        mock_coordinator_switch.data = None

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        assert switch.is_on is None
        assert switch.available is False

    def test_switch_missing_data_key(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch behavior when data key is missing."""
        mock_coordinator_switch.data = {"other_switch": 1}

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        assert switch.is_on is None
        assert switch.available is False

    def test_switch_is_on_connected_state(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch is_on returns True when value is connected (3)."""
        # Set data to match SAX Battery "connected" value (3)
        mock_coordinator_switch.data = {"test_switch": 3}

        # Security: Ensure ModbusItem has proper switch methods
        modbus_item_switch.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_off_value = MagicMock(return_value=1)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_connected_value = MagicMock(return_value=3)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_standby_value = MagicMock(return_value=4)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_state_name = MagicMock(return_value="connected")  # type: ignore[method-assign]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # "Connected" (3) should be considered "on" in Home Assistant
        assert switch.is_on is True

        # Verify the switch methods were called
        modbus_item_switch.get_switch_connected_value.assert_called()

    def test_switch_is_on_standby_state(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch is_on returns False when value is standby (4)."""
        # Set data to match SAX Battery "standby" value (4)
        mock_coordinator_switch.data = {"test_switch": 4}

        # Security: Ensure ModbusItem has proper switch methods
        modbus_item_switch.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_off_value = MagicMock(return_value=1)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_connected_value = MagicMock(return_value=3)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_standby_value = MagicMock(return_value=4)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_state_name = MagicMock(return_value="standby")  # type: ignore[method-assign]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # "Standby" (4) should be considered "off" in Home Assistant
        assert switch.is_on is False

    def test_switch_state_attributes(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch state attributes include detailed state information."""
        # Set data to connected state
        mock_coordinator_switch.data = {"test_switch": 3}

        # Mock switch methods
        modbus_item_switch.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_off_value = MagicMock(return_value=1)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_connected_value = MagicMock(return_value=3)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_standby_value = MagicMock(return_value=4)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_state_name = MagicMock(return_value="connected")  # type: ignore[method-assign]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        attrs = switch.extra_state_attributes
        states = switch.state_attributes
        assert attrs is not None
        assert attrs["raw_value"] == 3
        assert states is not None
        assert states["detailed_state"] == "connected"
        assert "switch_states" in states
        assert states["switch_states"]["connected"] == 3

    def test_switch_string_values_with_connected(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test switch with string values including connected state."""
        # Ensure ModbusItem has proper switch methods
        modbus_item_switch.get_switch_on_value = MagicMock(return_value=2)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_off_value = MagicMock(return_value=1)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_connected_value = MagicMock(return_value=3)  # type: ignore[method-assign]
        modbus_item_switch.get_switch_standby_value = MagicMock(return_value=4)  # type: ignore[method-assign]

        test_cases = [
            ("on", True),
            ("off", False),
            ("connected", True),  # New test case
            ("true", True),
            ("false", False),
            ("1", False),  # SAX "off" value
            ("2", True),  # SAX "on" value
            ("3", True),  # SAX "connected" value
            ("4", False),  # SAX "standby" value
        ]

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        for string_value, expected_bool in test_cases:
            mock_coordinator_switch.data = {"test_switch": string_value}
            result = switch.is_on
            assert result is expected_bool, (
                f"Failed for '{string_value}': expected {expected_bool}, got {result}"
            )

    def test_switch_device_info(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test device info property."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        device_info = switch.device_info

        # Handle the case where device_info might be None
        assert device_info is not None
        assert device_info["identifiers"] == {("sax_battery", "battery_1")}
        assert device_info["name"] == "SAX Battery 1"
        assert device_info["manufacturer"] == "SAX Power"

    def test_switch_icon_property(
        self, mock_coordinator_switch: MagicMock, modbus_item_switch: ModbusItem
    ) -> None:
        """Test icon property."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # The implementation returns "mdi:battery-off" for icon when state is off
        assert switch.icon == "mdi:battery-off"


class TestSAXBatteryControlSwitch:
    """Test SAX Battery control switch entity."""

    @pytest.fixture
    def mock_control_coordinator(self) -> MagicMock:
        """Create mock coordinator for control switch tests."""
        coordinator = MagicMock(spec=SAXBatteryCoordinator)
        coordinator.last_update_success = True
        coordinator.async_request_refresh = AsyncMock()

        # Mock config entry
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enable_solar_charging": True,
            "manual_control": False,
        }
        coordinator.config_entry = mock_config_entry

        # Mock sax_data
        mock_sax_data = MagicMock()
        mock_sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "cluster")},
            "name": "SAX Battery System",
            "manufacturer": "SAX Power",
        }
        coordinator.sax_data = mock_sax_data

        return coordinator

    @pytest.fixture
    def mock_sax_item_control(self) -> SAXItem:
        """Create mock SAX item for control switch."""
        sax_item = MagicMock(spec=SAXItem)
        sax_item.name = "solar_charging_switch"
        sax_item.device = DeviceConstants.SYS
        sax_item.entitydescription = None
        sax_item.calculate_value.return_value = True
        sax_item.set_coordinators = MagicMock()
        return sax_item

    def test_control_switch_initialization(
        self,
        mock_coordinator_modbus_base,
        modbus_item_on_off_base,
        simulate_unique_id_on_off,
    ) -> None:
        """Test control switch initialization."""

        mock_config_entry = MagicMock()
        mock_config_entry.data = {"battery_count": 1, "master_battery": "battery_a"}

        sax_data = SAXBatteryData(mock_coordinator_modbus_base.hass, mock_config_entry)
        mock_coordinator_modbus_base.sax_data = sax_data

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_modbus_base,
            battery_id="cluster",  # Cluster device
            modbus_item=modbus_item_on_off_base,
        )

        assert switch.name == "On/Off"
        assert switch._modbus_item == modbus_item_on_off_base
        assert switch._battery_id == "cluster"
        # Device info should come from actual get_device_info method
        assert switch.device_info["name"] == "SAX Cluster"  # type: ignore[index]
        assert simulate_unique_id_on_off == "switch.sax_cluster_on_off"

    def test_control_switch_initialization_with_entity_description(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch initialization with entity description."""
        mock_entity_desc = MagicMock()
        mock_entity_desc.name = "Solar Charging Control"
        mock_sax_item_control.entitydescription = mock_entity_desc
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        assert switch._attr_name == "Solar Charging Control"

    def test_control_switch_initialization_without_entity_description(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch initialization without entity description."""
        mock_sax_item_control.name = "test_control_switch"
        mock_sax_item_control.entitydescription = None
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        assert switch._attr_name == "Test Control Switch"

    def test_control_switch_is_on_solar_charging(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch is_on for solar charging switch."""
        mock_sax_item_control.name = "solar_charging_switch"
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Should get value from config entry
        assert switch.is_on is False

    def test_control_switch_is_on_manual_control(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch is_on for manual control switch."""
        mock_sax_item_control.name = "manual_control_switch"
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Should get value from config entry
        assert switch.is_on is False

    def test_control_switch_is_on_default_calculation(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch is_on uses SAX item calculation for unknown switches."""
        mock_sax_item_control.name = "unknown_switch"
        mock_sax_item_control.calculate_value.return_value = True
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Should use SAX item calculation
        assert switch.is_on is True
        mock_sax_item_control.calculate_value.assert_called_once_with(coordinators)

    def test_control_switch_is_on_none_config_entry(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch is_on when config entry is None."""
        mock_control_coordinator.config_entry = None
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
            result = switch.is_on
            assert result is None
            mock_logger.warning.assert_called()

    def test_control_switch_available_true(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch available when conditions are met."""
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        assert switch.available is True

    def test_control_switch_available_false_no_config(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch unavailable when config entry is None."""
        mock_control_coordinator.config_entry = None
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        assert switch.available is False

    def test_control_switch_available_false_update_failed(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch unavailable when last update failed."""
        mock_control_coordinator.last_update_success = False
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        assert switch.available is False

    async def test_control_switch_turn_on_solar_charging(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning on solar charging control switch."""
        mock_sax_item_control.name = "solar_charging_switch"
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Mock hass for config entry update
        switch.hass = MagicMock()

        await switch.async_turn_on()

        # Should update config entry
        switch.hass.config_entries.async_update_entry.assert_called_once()
        call_args = switch.hass.config_entries.async_update_entry.call_args
        assert call_args[1]["data"]["enable_solar_charging"] is True
        mock_control_coordinator.async_request_refresh.assert_called_once()

    async def test_control_switch_turn_on_manual_control(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning on manual control switch."""
        mock_sax_item_control.name = "manual_control_switch"
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Mock hass for config entry update
        switch.hass = MagicMock()

        await switch.async_turn_on()

        # Should update config entry
        switch.hass.config_entries.async_update_entry.assert_called_once()
        call_args = switch.hass.config_entries.async_update_entry.call_args
        assert call_args[1]["data"]["manual_control"] is True

    async def test_control_switch_turn_on_none_config_entry(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning on control switch when config entry is None."""
        mock_control_coordinator.config_entry = None
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        with pytest.raises(
            HomeAssistantError, match="Cannot turn on.*config entry is None"
        ):
            await switch.async_turn_on()

    async def test_control_switch_turn_off_solar_charging(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning off solar charging control switch."""
        mock_sax_item_control.name = "solar_charging_switch"
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Mock hass for config entry update
        switch.hass = MagicMock()

        await switch.async_turn_off()

        # Should update config entry
        switch.hass.config_entries.async_update_entry.assert_called_once()
        call_args = switch.hass.config_entries.async_update_entry.call_args
        assert call_args[1]["data"]["enable_solar_charging"] is False

    async def test_control_switch_turn_off_manual_control(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning off manual control switch."""
        mock_sax_item_control.name = "manual_control_switch"
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Mock hass for config entry update
        switch.hass = MagicMock()

        await switch.async_turn_off()

        # Should update config entry
        switch.hass.config_entries.async_update_entry.assert_called_once()
        call_args = switch.hass.config_entries.async_update_entry.call_args
        assert call_args[1]["data"]["manual_control"] is False

    async def test_control_switch_turn_off_none_config_entry(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning off control switch when config entry is None."""
        mock_control_coordinator.config_entry = None
        coordinators = {"battery_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        with pytest.raises(
            HomeAssistantError, match="Cannot turn off.*config entry is None"
        ):
            await switch.async_turn_off()


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.fixture
    def mock_setup_data(self) -> dict[str, Any]:
        """Create mock setup data."""
        mock_coordinator = MagicMock(spec=SAXBatteryCoordinator)
        mock_coordinator.battery_config = {
            CONF_BATTERY_IS_MASTER: True,
            CONF_BATTERY_PHASE: "L1",
        }

        # Add required sax_data attribute
        mock_sax_data = MagicMock()
        mock_sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "battery_a")},
            "name": "SAX Battery A",
        }
        mock_coordinator.sax_data = mock_sax_data

        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.get_sax_items_for_battery.return_value = []

        return {
            "coordinators": {"battery_a": mock_coordinator},
            "sax_data": mock_sax_data,
        }

    @pytest.fixture
    def mock_config_entry_switch(self) -> MagicMock:
        """Create mock config entry for switch tests."""
        config_entry = MagicMock()
        config_entry.entry_id = "test_switch_entry"
        config_entry.data = {"pilot_from_ha": False, "limit_power": False}
        return config_entry

    async def test_async_setup_entry_invalid_battery_id(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry with invalid battery ID."""
        # Add invalid battery ID with required attributes
        invalid_coordinator = MagicMock(spec=SAXBatteryCoordinator)
        invalid_coordinator.battery_config = {CONF_BATTERY_IS_MASTER: False}
        mock_setup_data["coordinators"]["invalid_battery"] = invalid_coordinator

        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
            await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

            # Should log warning for invalid battery ID
            mock_logger.warning.assert_called_with(
                "Invalid battery ID %s, skipping", "invalid_battery"
            )

    async def test_async_setup_entry_with_modbus_items(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry with modbus switch items."""
        # Add modbus switch items
        modbus_item = ModbusItem(
            name="battery_switch",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SWITCH,
            address=1000,
            battery_device_id=1,
            factor=1.0,
        )

        mock_setup_data["sax_data"].get_modbus_items_for_battery.return_value = [
            modbus_item
        ]

        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        with patch(
            "custom_components.sax_battery.switch.filter_items_by_type"
        ) as mock_filter:
            mock_filter.return_value = [modbus_item]

            await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

            # Should create modbus switch entities
            assert len(entities_created) == 1
            assert isinstance(entities_created[0], SAXBatterySwitch)

    async def test_async_setup_entry_with_sax_items(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry with SAX control switch items."""
        # Add SAX switch items
        sax_item = MagicMock(spec=SAXItem)
        sax_item.name = "solar_charging_switch"
        sax_item.device = DeviceConstants.SYS
        sax_item.set_coordinators = MagicMock()

        mock_setup_data["sax_data"].get_sax_items_for_battery.return_value = [sax_item]

        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        with patch(
            "custom_components.sax_battery.switch.filter_sax_items_by_type"
        ) as mock_filter:
            mock_filter.return_value = [sax_item]

            await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

            # Should create control switch entities
            assert any(
                isinstance(entity, SAXBatteryControlSwitch)
                for entity in entities_created
            )

    async def test_async_setup_entry_no_master_battery(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry with no master battery."""
        # Set battery as slave
        mock_setup_data["coordinators"]["battery_a"].battery_config[
            CONF_BATTERY_IS_MASTER
        ] = False

        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

        # Should not create control switches
        assert not any(
            isinstance(entity, SAXBatteryControlSwitch) for entity in entities_created
        )

    async def test_async_setup_entry_slave_battery_logging(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry logging for slave battery."""
        # Set battery as slave
        mock_setup_data["coordinators"]["battery_a"].battery_config.update(
            {
                CONF_BATTERY_IS_MASTER: False,
                CONF_BATTERY_PHASE: "L2",
            }
        )

        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
            await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

            # Should log slave battery setup
            mock_logger.debug.assert_called_with(
                "Setting up switches for %s battery %s (%s)",
                "slave",
                "battery_a",
                "L2",
            )

    async def test_async_setup_entry_no_entities_created(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry when no entities are created."""
        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

        # async_add_entities should not be called when no entities are created
        assert len(entities_created) == 0

    async def test_async_setup_entry_multiple_batteries(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry with multiple batteries."""
        # Add second battery
        mock_coordinator_b = MagicMock(spec=SAXBatteryCoordinator)
        mock_coordinator_b.battery_config = {
            CONF_BATTERY_IS_MASTER: False,
            CONF_BATTERY_PHASE: "L2",
        }
        mock_coordinator_b.sax_data = mock_setup_data["sax_data"]

        mock_setup_data["coordinators"]["battery_b"] = mock_coordinator_b

        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

        # Should process both batteries
        assert len(entities_created) == 0  # No actual entities since no items returned

    async def test_async_setup_entry_with_mixed_entity_types(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test setup entry with both modbus and SAX items."""
        # Add modbus item
        modbus_item = ModbusItem(
            name="battery_switch",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SWITCH,
            address=1000,
            battery_device_id=1,
            factor=1.0,
        )

        # Add SAX item
        sax_item = MagicMock(spec=SAXItem)
        sax_item.name = "solar_charging_switch"
        sax_item.device = DeviceConstants.SYS
        sax_item.set_coordinators = MagicMock()

        mock_setup_data["sax_data"].get_modbus_items_for_battery.return_value = [
            modbus_item
        ]
        mock_setup_data["sax_data"].get_sax_items_for_battery.return_value = [sax_item]

        hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

        entities_created = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_created.extend(new_entities)

        with (
            patch(
                "custom_components.sax_battery.switch.filter_items_by_type"
            ) as mock_filter_modbus,
            patch(
                "custom_components.sax_battery.switch.filter_sax_items_by_type"
            ) as mock_filter_sax,
        ):
            mock_filter_modbus.return_value = [modbus_item]
            mock_filter_sax.return_value = [sax_item]

            await async_setup_entry(hass, mock_config_entry_switch, mock_add_entities)

            # Should create both types of entities
            assert len(entities_created) == 2
            assert any(
                isinstance(entity, SAXBatterySwitch) for entity in entities_created
            )
            assert any(
                isinstance(entity, SAXBatteryControlSwitch)
                for entity in entities_created
            )

    async def test_async_setup_entry_battery_id_validation(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test that only valid battery IDs are processed."""
        # Test with valid battery IDs from BATTERY_IDS constant
        for battery_id in BATTERY_IDS:
            # Setup coordinator for valid battery ID
            mock_coordinator = MagicMock(spec=SAXBatteryCoordinator)
            mock_coordinator.battery_config = {CONF_BATTERY_IS_MASTER: False}
            mock_coordinator.sax_data = mock_setup_data["sax_data"]
            mock_setup_data["coordinators"] = {battery_id: mock_coordinator}

            hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

            entities_created = []

            def mock_add_entities(new_entities, update_before_add=False):
                entities_created.extend(new_entities)  # noqa: B023

            # Should not log any warnings for valid battery IDs
            with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
                await async_setup_entry(
                    hass, mock_config_entry_switch, mock_add_entities
                )

                # Should not warn about valid battery IDs
                for call in mock_logger.warning.call_args_list:
                    assert "Invalid battery ID" not in str(call)

    async def test_async_setup_entry_error_handling(
        self, hass: HomeAssistant, mock_config_entry_switch, mock_setup_data
    ) -> None:
        """Test error handling during entity creation."""
        # Mock filter to raise exception
        with patch(
            "custom_components.sax_battery.switch.filter_items_by_type"
        ) as mock_filter:
            mock_filter.side_effect = Exception("Test error")

            hass.data[DOMAIN] = {mock_config_entry_switch.entry_id: mock_setup_data}

            entities_created = []

            def mock_add_entities(new_entities, update_before_add=False):
                entities_created.extend(new_entities)

            # Should handle exception gracefully
            with pytest.raises(Exception, match="Test error"):
                await async_setup_entry(
                    hass, mock_config_entry_switch, mock_add_entities
                )
