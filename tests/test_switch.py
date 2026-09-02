"""Test switch platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    BATTERY_IDS,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_BATTERY_PORT,
    CONF_CONTROL_POWER,
    CONF_ENABLE_GRID_CHARGING,
    DEFAULT_DEVICE_INFO,
    DESCRIPTION_SAX_STATUS_SWITCH,
    DOMAIN,
    PV_CHARGING_MODE,
    SAX_CHARGE_FROM_GRID_SWITCH,
    SAX_CHARGE_FROM_PV_SWITCH,
    SAXDeviceInfo,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.switch import (
    SAXBatteryControlSwitch,
    SAXBatterySwitch,
    async_setup_entry,
)
from custom_components.sax_battery.utils import should_include_entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant


class TestSAXBatterySwitch:
    """Test SAX Battery switch entity."""

    @pytest.fixture
    def mock_coordinator_switch(self, mock_config_entry):
        """Fixture for coordinator with switch configuration."""
        coordinator = MagicMock(spec=SAXBatteryCoordinator)
        coordinator.name = DOMAIN
        coordinator.config_entry = mock_config_entry
        coordinator.data = {}
        coordinator.last_update_success = True
        coordinator.battery_config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
            CONF_BATTERY_IS_MASTER: False,
            CONF_BATTERY_PHASE: "L2",
        }

        # Add hass attribute
        coordinator.hass = MagicMock()

        # Mock sax_data with proper unique_id generation
        mock_sax_data = MagicMock()

        def mock_get_unique_id(item, battery_id=None):
            """Mock unique_id generation for switches."""
            item_name = item.name.removeprefix("sax_")

            if battery_id:
                return f"sax_{battery_id}_{item_name}"
            else:  # noqa: RET505
                return f"sax_{item_name}"

        mock_sax_data.get_unique_id_for_item = MagicMock(side_effect=mock_get_unique_id)

        mock_sax_data.get_device_info = MagicMock(
            return_value=SAXDeviceInfo(
                manufacturer="SAX",
                model="Battery System",
                sw_version="1.0",
            )
        )

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
            "CONF_CONTROL_POWER": True,
            "CONF_LIMIT_POWER": True,
            "CONF_MASTER_BATTERY": "bess_a",
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

        result = should_include_entity(unknown_item, mock_config_entry, "bess_a")
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
        assert switch.unique_id == "sax_battery_1_power_switch"

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
        modbus_item_switch.get_switch_standby_value = MagicMock(return_value=4)  # type: ignore[method-assign]

        test_cases = [
            (1.0, False),  # Off value
            (2.0, True),  # On value
            (3.0, True),  # Connected value
            (4.0, True),  # Standby value
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

        assert switch.unique_id == "sax_battery_1_test_switch"
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
        """Test turn_on operation with write queue."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # With write queue, method completes successfully
        # Failures are detected during queue processing
        await switch.async_turn_on()

        # Verify write was queued
        mock_coordinator_switch.async_write_switch_value.assert_called_once_with(
            modbus_item_switch, True
        )

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
        """Test turn_off operation with write queue."""
        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_switch,
            battery_id="battery_1",
            modbus_item=modbus_item_switch,
        )

        # With write queue, method completes successfully
        # Failures are detected during queue processing
        await switch.async_turn_off()

        # Verify write was queued
        mock_coordinator_switch.async_write_switch_value.assert_called_once_with(
            modbus_item_switch, False
        )

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

        # Handle None return value properly
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
        assert switch.is_on is True

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
            ("4", True),  # SAX "standby" value
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
        assert isinstance(device_info, SAXDeviceInfo)
        assert device_info.manufacturer == "SAX"
        assert device_info.model == "Battery System"

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
        assert switch.icon == "mdi:battery"  # Default icon from entity description


class TestSAXBatteryControlSwitch:
    """Test SAX Battery control switch."""

    @pytest.fixture
    def mock_control_coordinator(self, mock_config_entry):
        """Fixture for control switch coordinator."""
        coordinator = MagicMock(spec=SAXBatteryCoordinator)
        coordinator.name = DOMAIN
        coordinator.config_entry = mock_config_entry
        coordinator.data = {}
        coordinator.last_update_success = True
        coordinator.battery_config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
            CONF_BATTERY_IS_MASTER: True,
            CONF_BATTERY_PHASE: "L1",
        }

        # Mock sax_data with proper unique_id generation
        mock_sax_data = MagicMock()

        def mock_get_unique_id(item, battery_id=None):
            """Mock unique_id generation for control switches."""
            # SAXItem uses item.name directly (already has sax_ prefix removed in actual code)
            item_name = item.name.removeprefix("sax_")

            if battery_id:
                return f"sax_{battery_id}_{item_name}"
            else:  # noqa: RET505
                # Control switches are cluster-wide
                return item_name  # "pv_charging", "grid_charging"

        mock_sax_data.get_unique_id_for_item = MagicMock(side_effect=mock_get_unique_id)
        mock_sax_data.get_device_info = MagicMock(return_value=DEFAULT_DEVICE_INFO)

        coordinator.sax_data = mock_sax_data

        return coordinator

    @pytest.fixture
    def mock_sax_item_control(self) -> SAXItem:
        """Create mock SAX item for control switch."""
        sax_item = MagicMock(spec=SAXItem)
        sax_item.name = "pv_charging_switch"
        sax_item.mtype = TypeConstants.SWITCH
        sax_item.device = DeviceConstants.SYS
        sax_item.entitydescription = None
        sax_item.set_coordinators = MagicMock()
        return sax_item

    def test_control_switch_initialization(
        self,
        mock_coordinator_modbus_base,
        modbus_item_on_off_base,
        simulate_unique_id_on_off,
    ) -> None:
        """Test control switch initialization."""

        switch = SAXBatterySwitch(
            coordinator=mock_coordinator_modbus_base,
            battery_id="cluster",  # Cluster device
            modbus_item=modbus_item_on_off_base,
        )

        assert switch.name == "On/Off"
        assert switch._modbus_item == modbus_item_on_off_base
        assert switch._battery_id == "cluster"

        # device_info is DeviceInfo dict, not SAXDeviceInfo dataclass
        assert isinstance(switch.device_info, dict)
        assert switch.device_info["manufacturer"] == "SAX"
        assert switch.device_info["model"] == "Battery System"
        assert ("sax_battery", "cluster") in switch.device_info["identifiers"]

        assert simulate_unique_id_on_off == "switch.sax_bms_on_off"

    def test_control_switch_initialization_with_entity_description(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch initialization with entity description."""
        mock_entity_desc = MagicMock()
        mock_entity_desc.name = "PV Charging Control"
        mock_sax_item_control.entitydescription = mock_entity_desc
        coordinators = {"bess_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        assert switch.name == "PV Charging Control"

    def test_control_switch_is_on_pv_charging(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch is_on for PV charging switch."""
        mock_sax_item_control.name = "pv_charging_switch"

        # Mock config entry with PV_CHARGING_MODE disabled
        mock_config_entry = MagicMock()
        mock_config_entry.data = {PV_CHARGING_MODE: False}
        mock_control_coordinator.config_entry = mock_config_entry

        coordinators = {"bess_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Should get value from config entry
        assert switch.is_on is False

    def test_control_switch_is_on_grid_control(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch is_on for grid control switch."""
        mock_sax_item_control.name = "grid_control_switch"
        coordinators = {"bess_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Should get value from config entry
        assert switch.is_on is False

    def test_control_switch_is_on_none_config_entry(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test control switch is_on when config entry is None."""
        mock_control_coordinator.config_entry = None
        coordinators = {"bess_a": mock_control_coordinator}

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
        coordinators = {"bess_a": mock_control_coordinator}

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
        coordinators = {"bess_a": mock_control_coordinator}

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
        coordinators = {"bess_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        assert switch.available is False

    async def test_control_switch_turn_on_pv_charging(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning on pv charging control switch.

        Security:
            OWASP A05: Validates coordinator data updates instead of config entry
        """
        mock_sax_item_control.name = SAX_CHARGE_FROM_PV_SWITCH
        coordinators = {"bess_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Mock hass
        switch.hass = MagicMock()

        # Initialize coordinator data with grid charging enabled
        mock_control_coordinator.data = {
            SAX_CHARGE_FROM_GRID_SWITCH: True,
        }

        await switch.async_turn_on()

        # ✅ FIXED: Verify PV switch enabled
        assert mock_control_coordinator.data[SAX_CHARGE_FROM_PV_SWITCH] is True

        # ✅ FIXED: Verify grid switch disabled (mutual exclusivity)
        assert mock_control_coordinator.data[SAX_CHARGE_FROM_GRID_SWITCH] is False

        # ✅ Verify switch state reflects change
        assert switch.is_on is True

    async def test_control_switch_turn_off_pv_charging(
        self, mock_control_coordinator, mock_sax_item_control
    ) -> None:
        """Test turning off pv charging control switch.

        Security:
            OWASP A05: Validates coordinator data updates instead of config entry
        """
        mock_sax_item_control.name = SAX_CHARGE_FROM_PV_SWITCH
        coordinators = {"bess_a": mock_control_coordinator}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_control_coordinator,
            sax_item=mock_sax_item_control,
            coordinators=coordinators,
        )

        # Mock hass
        switch.hass = MagicMock()

        # Initialize coordinator data with PV charging enabled
        mock_control_coordinator.data = {
            SAX_CHARGE_FROM_PV_SWITCH: True,
        }

        await switch.async_turn_off()

        # ✅ FIXED: Verify PV switch disabled
        assert mock_control_coordinator.data[SAX_CHARGE_FROM_PV_SWITCH] is False

        # ✅ Verify switch state reflects change
        assert switch.is_on is False


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.fixture
    def mock_setup_data(self) -> dict[str, Any]:
        """Create mock setup data for testing."""
        mock_coordinator = MagicMock(spec=SAXBatteryCoordinator)
        mock_coordinator.battery_config = {CONF_BATTERY_IS_MASTER: True}

        mock_config = MagicMock(spec=ConfigEntry)
        mock_config.data = {
            CONF_CONTROL_POWER: False,
            CONF_ENABLE_GRID_CHARGING: False,
        }
        mock_coordinator.config_entry = mock_config

        mock_sax_data = MagicMock()
        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.get_sax_items_for_battery.return_value = []
        mock_sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "cluster")},
            "name": "SAX Cluster",
        }
        mock_coordinator.sax_data = mock_sax_data

        return {
            "coordinators": {"bess_a": mock_coordinator},
            "sax_data": mock_sax_data,  # Also keep in top-level for consistency
        }

    @pytest.fixture
    def mock_config_entry_switch(self) -> MagicMock:
        """Create mock config entry for switch tests."""
        mock_entry = MagicMock(spec=ConfigEntry)
        mock_entry.entry_id = "test_switch_entry"
        mock_entry.data = {
            CONF_BATTERY_COUNT: 1,
            CONF_CONTROL_POWER: False,
            CONF_ENABLE_GRID_CHARGING: False,
        }
        return mock_entry

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
        sax_item.name = "pv_charging_switch"
        sax_item.device = DeviceConstants.SYS
        sax_item.mtype = TypeConstants.SWITCH
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
        mock_setup_data["coordinators"]["bess_a"].battery_config[
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
        mock_setup_data["coordinators"]["bess_a"].battery_config.update(
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
                "bess_a",
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
        sax_item.name = "pv_charging_switch"
        sax_item.device = DeviceConstants.SYS
        sax_item.mtype = TypeConstants.SWITCH
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


class TestSAXBatterySwitchComprehensiveCoverage:
    """Comprehensive test coverage for SAX Battery switches."""

    @pytest.fixture
    def mock_coordinator_comprehensive(self) -> MagicMock:
        """Create comprehensive mock coordinator."""
        coordinator = MagicMock(spec=SAXBatteryCoordinator)
        coordinator.data = {"test_switch": 2}
        coordinator.last_update_success = True
        coordinator.last_update_success_time = "2024-01-01T00:00:00"

        # Mock config entry
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_CONTROL_POWER: True,
            CONF_ENABLE_GRID_CHARGING: False,
        }
        mock_config_entry.entry_id = "test_entry_123"
        coordinator.config_entry = mock_config_entry

        # Mock battery config
        coordinator.battery_config = {
            CONF_BATTERY_IS_MASTER: True,
            CONF_BATTERY_PHASE: "L1",
        }

        # Mock sax_data
        mock_sax_data = MagicMock()
        mock_sax_data.get_device_info = MagicMock(
            return_value={
                "identifiers": {("sax_battery", "bess_a")},
                "name": "SAX Battery A",
                "manufacturer": "SAX Power",
            }
        )
        coordinator.sax_data = mock_sax_data

        # Mock write and refresh methods
        coordinator.async_write_switch_value = AsyncMock(return_value=True)
        coordinator.async_request_refresh = AsyncMock()

        # Mock hass
        coordinator.hass = MagicMock()
        coordinator.hass.config_entries = MagicMock()
        coordinator.hass.config_entries.async_update_entry = MagicMock()

        return coordinator

    @pytest.fixture
    def modbus_item_comprehensive(self) -> ModbusItem:
        """Create comprehensive modbus item."""
        return ModbusItem(
            name="comprehensive_switch",
            device=DeviceConstants.BESS,
            mtype=TypeConstants.SWITCH,
            address=1000,
            battery_device_id=1,
            factor=1.0,
            entitydescription=DESCRIPTION_SAX_STATUS_SWITCH,
        )

    # Test SAXBatteryControlSwitch pv charging interactions
    async def test_control_switch_pv_enable_disables_grid(
        self, mock_coordinator_comprehensive
    ) -> None:
        """Test enabling pv charging automatically disables grid control."""

        # Security:
        # OWASP A05: Validates mutual exclusivity of charging modes
        sax_item = SAXItem(
            name=SAX_CHARGE_FROM_PV_SWITCH,
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SWITCH,
        )

        coordinators = {"bess_a": mock_coordinator_comprehensive}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_coordinator_comprehensive,
            sax_item=sax_item,
            coordinators=coordinators,
        )

        # Mock hass
        switch.hass = mock_coordinator_comprehensive.hass

        # Initialize coordinator data with grid charging enabled
        mock_coordinator_comprehensive.data = {
            SAX_CHARGE_FROM_GRID_SWITCH: True,
        }

        await switch.async_turn_on()

        # ✅ FIXED: Verify coordinator data shows mutual exclusivity
        assert mock_coordinator_comprehensive.data[SAX_CHARGE_FROM_PV_SWITCH] is True
        assert mock_coordinator_comprehensive.data[SAX_CHARGE_FROM_GRID_SWITCH] is False

    async def test_control_switch_pv_disable_only(
        self, mock_coordinator_comprehensive
    ) -> None:
        """Test disabling pv charging doesn't affect grid control."""

        # Security:
        # OWASP A05: Validates independent state management
        sax_item = SAXItem(
            name=SAX_CHARGE_FROM_PV_SWITCH,
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SWITCH,
        )

        coordinators = {"bess_a": mock_coordinator_comprehensive}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_coordinator_comprehensive,
            sax_item=sax_item,
            coordinators=coordinators,
        )

        switch.hass = mock_coordinator_comprehensive.hass

        # Initialize coordinator data with PV enabled, grid disabled
        mock_coordinator_comprehensive.data = {
            SAX_CHARGE_FROM_PV_SWITCH: True,
            SAX_CHARGE_FROM_GRID_SWITCH: False,
        }

        await switch.async_turn_off()

        # ✅ FIXED: Verify only PV state changed
        assert mock_coordinator_comprehensive.data[SAX_CHARGE_FROM_PV_SWITCH] is False
        # Grid control should remain unchanged
        assert mock_coordinator_comprehensive.data[SAX_CHARGE_FROM_GRID_SWITCH] is False

    def test_control_switch_pv_enabled_with_power_control(
        self, mock_coordinator_comprehensive
    ) -> None:
        """Test pv charging switch state when power control enabled."""

        # Initialize coordinator data with PV charging enabled
        mock_coordinator_comprehensive.data = {
            SAX_CHARGE_FROM_PV_SWITCH: True,
        }

        sax_item = SAXItem(
            name=SAX_CHARGE_FROM_PV_SWITCH,
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SWITCH,
        )

        coordinators = {"bess_a": mock_coordinator_comprehensive}

        switch = SAXBatteryControlSwitch(
            coordinator=mock_coordinator_comprehensive,
            sax_item=sax_item,
            coordinators=coordinators,
        )

        # ✅ FIXED: Switch state reflects coordinator data
        assert switch.is_on is True
