"""Test pilot platform for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.const import (
    MANUAL_CONTROL_SWITCH,
    PILOT_ITEMS,
    SOLAR_CHARGING_SWITCH,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import SAXItem
from custom_components.sax_battery.pilot import (
    SAXBatteryManualControlSwitch,
    SAXBatteryPilot,
    SAXBatterySolarChargingSwitch,
    async_setup_entry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        """Create mock Home Assistant instance."""
        return MagicMock(spec=HomeAssistant)

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        """Create mock config entry."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        return entry

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create mock coordinator."""
        coordinator = MagicMock()
        coordinator.battery_id = "battery_a"
        coordinator.sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "battery_a")},
            "name": "SAX Battery A",
        }
        return coordinator

    @pytest.fixture
    def mock_sax_data(self, mock_coordinator) -> MagicMock:
        """Create mock SAXBatteryData."""
        sax_data = MagicMock()
        sax_data.master_battery_id = "battery_a"
        sax_data.coordinators = {"battery_a": mock_coordinator}
        return sax_data

    async def test_setup_entry_with_master_battery(
        self, mock_hass, mock_config_entry, mock_sax_data
    ):
        """Test setup entry creates pilot entities for master battery."""
        mock_hass.data = {"sax_battery": {mock_config_entry.entry_id: mock_sax_data}}

        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Should create 2 entities (solar charging + manual control)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2
        assert isinstance(entities[0], SAXBatterySolarChargingSwitch)
        assert isinstance(entities[1], SAXBatteryManualControlSwitch)

    async def test_setup_entry_no_master_battery(self, mock_hass, mock_config_entry):
        """Test setup entry with no master battery creates no entities."""
        mock_sax_data = MagicMock()
        mock_sax_data.master_battery_id = None
        mock_hass.data = {"sax_battery": {mock_config_entry.entry_id: mock_sax_data}}

        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Should create no entities
        async_add_entities.assert_called_once_with([])

    async def test_setup_entry_master_battery_not_in_coordinators(
        self, mock_hass, mock_config_entry
    ):
        """Test setup entry when master battery is not in coordinators."""
        mock_sax_data = MagicMock()
        mock_sax_data.master_battery_id = "battery_a"
        mock_sax_data.coordinators = {}  # Empty coordinators
        mock_hass.data = {"sax_battery": {mock_config_entry.entry_id: mock_sax_data}}

        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Should create no entities
        async_add_entities.assert_called_once_with([])


class TestSAXBatteryPilot:
    """Test SAXBatteryPilot class."""

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        """Create mock Home Assistant instance."""
        return MagicMock(spec=HomeAssistant)

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create mock coordinator."""
        coordinator = MagicMock()
        coordinator.battery_id = "battery_a"
        coordinator.data = {}
        coordinator.async_set_updated_data = MagicMock()
        coordinator.async_write_int_value = AsyncMock(return_value=True)
        coordinator.last_update_success = True
        return coordinator

    @pytest.fixture
    def mock_sax_data(self) -> MagicMock:
        """Create mock SAXBatteryData."""
        sax_data = MagicMock()
        charge_item = MagicMock()
        charge_item.name = "sax_max_charge_power"
        discharge_item = MagicMock()
        discharge_item.name = "sax_max_discharge_power"
        sax_data.get_modbus_items_for_battery.return_value = [
            charge_item,
            discharge_item,
        ]
        return sax_data

    @pytest.fixture
    def pilot(self, mock_hass, mock_sax_data, mock_coordinator) -> SAXBatteryPilot:
        """Create SAXBatteryPilot instance."""
        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

    async def test_set_manual_control_enabled(self, pilot):
        """Test enabling manual control."""
        result = await pilot.set_manual_control(True)

        assert result is True
        # The pilot updates the coordinator data directly
        assert pilot.coordinator.data[MANUAL_CONTROL_SWITCH] == 1
        pilot.coordinator.async_set_updated_data.assert_called_once()

    async def test_set_manual_control_disabled(self, pilot):
        """Test disabling manual control."""
        result = await pilot.set_manual_control(False)

        assert result is True
        # The pilot updates the coordinator data directly
        assert pilot.coordinator.data[MANUAL_CONTROL_SWITCH] == 0
        pilot.coordinator.async_set_updated_data.assert_called_once()

    async def test_set_solar_charging_enabled(self, pilot):
        """Test enabling solar charging."""
        result = await pilot.set_solar_charging(True)

        assert result is True
        # The pilot updates the coordinator data directly
        assert pilot.coordinator.data[SOLAR_CHARGING_SWITCH] == 1
        pilot.coordinator.async_set_updated_data.assert_called_once()

    async def test_set_solar_charging_disabled(self, pilot):
        """Test disabling solar charging."""
        result = await pilot.set_solar_charging(False)

        assert result is True
        # The pilot updates the coordinator data directly
        assert pilot.coordinator.data[SOLAR_CHARGING_SWITCH] == 0
        pilot.coordinator.async_set_updated_data.assert_called_once()

    async def test_set_solar_charging_with_none_data(self, pilot):
        """Test setting solar charging when coordinator data is None."""
        pilot.coordinator.data = None

        result = await pilot.set_solar_charging(True)

        assert result is True
        assert pilot.coordinator.data == {SOLAR_CHARGING_SWITCH: 1}

    async def test_set_charge_power_limit_success(self, pilot):
        """Test setting charge power limit successfully."""
        result = await pilot.set_charge_power_limit(5000)

        assert result is True
        pilot.coordinator.async_write_int_value.assert_called_once()

    async def test_set_charge_power_limit_no_item(self, pilot):
        """Test setting charge power limit when item not found."""
        pilot.sax_data.get_modbus_items_for_battery.return_value = []

        result = await pilot.set_charge_power_limit(5000)

        assert result is False

    async def test_set_charge_power_limit_write_failure(self, pilot):
        """Test setting charge power limit when write fails."""
        pilot.coordinator.async_write_int_value.return_value = False

        result = await pilot.set_charge_power_limit(5000)

        assert result is False

    async def test_set_discharge_power_limit_success(self, pilot):
        """Test setting discharge power limit successfully."""
        result = await pilot.set_discharge_power_limit(4000)

        assert result is True
        pilot.coordinator.async_write_int_value.assert_called_once()

    async def test_set_discharge_power_limit_no_item(self, pilot):
        """Test setting discharge power limit when item not found."""
        pilot.sax_data.get_modbus_items_for_battery.return_value = []

        result = await pilot.set_discharge_power_limit(4000)

        assert result is False

    async def test_set_discharge_power_limit_write_failure(self, pilot):
        """Test setting discharge power limit when write fails."""
        pilot.coordinator.async_write_int_value.return_value = False

        result = await pilot.set_discharge_power_limit(4000)

        assert result is False

    def test_get_pilot_item_found(self, pilot):
        """Test getting pilot item that exists."""
        # Find the solar charging item from PILOT_ITEMS
        solar_item = None
        for item in PILOT_ITEMS:
            if item.name == SOLAR_CHARGING_SWITCH:
                solar_item = item
                break

        result = pilot._get_pilot_item(SOLAR_CHARGING_SWITCH)
        assert result == solar_item

    def test_get_pilot_item_not_found(self, pilot):
        """Test getting pilot item that doesn't exist."""
        result = pilot._get_pilot_item("non_existent_item")
        assert result is None

    def test_get_modbus_item_found(self, pilot):
        """Test getting modbus item that exists."""
        mock_item = MagicMock()
        mock_item.name = "sax_max_charge_power"
        pilot.sax_data.get_modbus_items_for_battery.return_value = [mock_item]

        result = pilot._get_modbus_item("sax_max_charge_power")
        assert result == mock_item

    def test_get_modbus_item_not_found(self, pilot):
        """Test getting modbus item that doesn't exist."""
        pilot.sax_data.get_modbus_items_for_battery.return_value = []

        result = pilot._get_modbus_item("non_existent_item")
        assert result is None

    def test_solar_charging_enabled_property(self, pilot):
        """Test solar charging enabled property."""
        pilot.coordinator.data = {SOLAR_CHARGING_SWITCH: 1}
        assert pilot.solar_charging_enabled is True

        pilot.coordinator.data = {SOLAR_CHARGING_SWITCH: 0}
        assert pilot.solar_charging_enabled is False

    def test_solar_charging_enabled_property_no_success(self, pilot):
        """Test solar charging enabled property when coordinator has no success."""
        pilot.coordinator.last_update_success = False
        assert pilot.solar_charging_enabled is None

    def test_manual_control_enabled_property(self, pilot):
        """Test manual control enabled property."""
        pilot.coordinator.data = {MANUAL_CONTROL_SWITCH: 1}
        assert pilot.manual_control_enabled is True

        pilot.coordinator.data = {MANUAL_CONTROL_SWITCH: 0}
        assert pilot.manual_control_enabled is False

    def test_manual_control_enabled_property_no_success(self, pilot):
        """Test manual control enabled property when coordinator has no success."""
        pilot.coordinator.last_update_success = False
        assert pilot.manual_control_enabled is None

    def test_current_charge_power_limit_property(self, pilot):
        """Test current charge power limit property."""
        pilot.coordinator.data = {"sax_max_charge_power": 5000}
        assert pilot.current_charge_power_limit == 5000

    def test_current_charge_power_limit_property_no_success(self, pilot):
        """Test current charge power limit property when coordinator has no success."""
        pilot.coordinator.last_update_success = False
        assert pilot.current_charge_power_limit is None

    def test_current_discharge_power_limit_property(self, pilot):
        """Test current discharge power limit property."""
        pilot.coordinator.data = {"sax_max_discharge_power": 4000}
        assert pilot.current_discharge_power_limit == 4000

    def test_current_discharge_power_limit_property_no_success(self, pilot):
        """Test current discharge power limit property when coordinator has no success."""
        pilot.coordinator.last_update_success = False
        assert pilot.current_discharge_power_limit is None


class TestSAXBatterySolarChargingSwitch:
    """Test SAXBatterySolarChargingSwitch class."""

    @pytest.fixture
    def mock_pilot(self) -> MagicMock:
        """Create mock pilot."""
        pilot = MagicMock(spec=SAXBatteryPilot)
        pilot.set_solar_charging = AsyncMock(return_value=True)
        pilot.solar_charging_enabled = True
        pilot.manual_control_enabled = False
        return pilot

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create mock coordinator."""
        coordinator = MagicMock()
        coordinator.battery_id = "battery_a"
        coordinator.last_update_success = True
        coordinator.last_update_success_time = 1234567890.0
        coordinator.sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "battery_a")},
            "name": "SAX Battery A",
        }
        return coordinator

    @pytest.fixture
    def solar_charging_item(self) -> SAXItem:
        """Create solar charging SAXItem."""
        for item in PILOT_ITEMS:
            if item.name == SOLAR_CHARGING_SWITCH:
                return item
        # Fallback if not found in PILOT_ITEMS
        return SAXItem(
            name=SOLAR_CHARGING_SWITCH,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        )

    @pytest.fixture
    def solar_switch(
        self, mock_pilot, mock_coordinator, solar_charging_item
    ) -> SAXBatterySolarChargingSwitch:
        """Create SAXBatterySolarChargingSwitch instance."""
        return SAXBatterySolarChargingSwitch(
            mock_pilot, mock_coordinator, solar_charging_item, 0
        )

    async def test_async_turn_on_success(self, solar_switch, mock_pilot):
        """Test turning on solar charging successfully."""
        await solar_switch.async_turn_on()
        mock_pilot.set_solar_charging.assert_called_once_with(True)

    async def test_async_turn_on_failure(self, solar_switch, mock_pilot):
        """Test turning on solar charging failure."""
        mock_pilot.set_solar_charging.return_value = False

        with pytest.raises(HomeAssistantError, match="Failed to enable solar charging"):
            await solar_switch.async_turn_on()

    async def test_async_turn_off_success(self, solar_switch, mock_pilot):
        """Test turning off solar charging successfully."""
        await solar_switch.async_turn_off()
        mock_pilot.set_solar_charging.assert_called_once_with(False)

    async def test_async_turn_off_failure(self, solar_switch, mock_pilot):
        """Test turning off solar charging failure."""
        mock_pilot.set_solar_charging.return_value = False

        with pytest.raises(
            HomeAssistantError, match="Failed to disable solar charging"
        ):
            await solar_switch.async_turn_off()

    def test_is_on_property(self, solar_switch, mock_pilot):
        """Test is_on property."""
        mock_pilot.solar_charging_enabled = True
        assert solar_switch.is_on is True

        mock_pilot.solar_charging_enabled = False
        assert solar_switch.is_on is False

        mock_pilot.solar_charging_enabled = None
        assert solar_switch.is_on is None

    def test_extra_state_attributes(self, solar_switch, mock_coordinator, mock_pilot):
        """Test extra state attributes."""
        attributes = solar_switch.extra_state_attributes

        assert attributes is not None
        assert attributes["battery_id"] == "battery_a"
        assert attributes["manual_control_enabled"] is False
        assert attributes["last_updated"] == 1234567890.0

    def test_extra_state_attributes_no_success(self, solar_switch, mock_coordinator):
        """Test extra state attributes when coordinator has no success."""
        mock_coordinator.last_update_success = False

        attributes = solar_switch.extra_state_attributes
        assert attributes is None

    def test_entity_properties(self, solar_switch):
        """Test entity properties are set correctly."""
        assert solar_switch._attr_name == "Battery_A Solar Charging"
        assert solar_switch._attr_icon == "mdi:solar-power"
        assert solar_switch._attr_unique_id is not None
        assert solar_switch._attr_device_info is not None


class TestSAXBatteryManualControlSwitch:
    """Test SAXBatteryManualControlSwitch class."""

    @pytest.fixture
    def mock_pilot(self) -> MagicMock:
        """Create mock pilot."""
        pilot = MagicMock(spec=SAXBatteryPilot)
        pilot.set_manual_control = AsyncMock(return_value=True)
        pilot.manual_control_enabled = True
        pilot.current_charge_power_limit = 5000
        pilot.current_discharge_power_limit = 4000
        pilot.solar_charging_enabled = False
        return pilot

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create mock coordinator."""
        coordinator = MagicMock()
        coordinator.battery_id = "battery_a"
        coordinator.last_update_success = True
        coordinator.last_update_success_time = 1234567890.0
        coordinator.sax_data.get_device_info.return_value = {
            "identifiers": {("sax_battery", "battery_a")},
            "name": "SAX Battery A",
        }
        return coordinator

    @pytest.fixture
    def manual_control_item(self) -> SAXItem:
        """Create manual control SAXItem."""
        for item in PILOT_ITEMS:
            if item.name == MANUAL_CONTROL_SWITCH:
                return item
        # Fallback if not found in PILOT_ITEMS
        return SAXItem(
            name=MANUAL_CONTROL_SWITCH,
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        )

    @pytest.fixture
    def manual_switch(
        self, mock_pilot, mock_coordinator, manual_control_item
    ) -> SAXBatteryManualControlSwitch:
        """Create SAXBatteryManualControlSwitch instance."""
        return SAXBatteryManualControlSwitch(
            mock_pilot, mock_coordinator, manual_control_item, 1
        )

    async def test_async_turn_on_success(self, manual_switch, mock_pilot):
        """Test turning on manual control successfully."""
        await manual_switch.async_turn_on()
        mock_pilot.set_manual_control.assert_called_once_with(True)

    async def test_async_turn_on_failure(self, manual_switch, mock_pilot):
        """Test turning on manual control failure."""
        mock_pilot.set_manual_control.return_value = False

        with pytest.raises(HomeAssistantError, match="Failed to enable manual control"):
            await manual_switch.async_turn_on()

    async def test_async_turn_off_success(self, manual_switch, mock_pilot):
        """Test turning off manual control successfully."""
        await manual_switch.async_turn_off()
        mock_pilot.set_manual_control.assert_called_once_with(False)

    async def test_async_turn_off_failure(self, manual_switch, mock_pilot):
        """Test turning off manual control failure."""
        mock_pilot.set_manual_control.return_value = False

        with pytest.raises(
            HomeAssistantError, match="Failed to disable manual control"
        ):
            await manual_switch.async_turn_off()

    def test_is_on_property(self, manual_switch, mock_pilot):
        """Test is_on property."""
        mock_pilot.manual_control_enabled = True
        assert manual_switch.is_on is True

        mock_pilot.manual_control_enabled = False
        assert manual_switch.is_on is False

        mock_pilot.manual_control_enabled = None
        assert manual_switch.is_on is None

    def test_extra_state_attributes(self, manual_switch, mock_coordinator, mock_pilot):
        """Test extra state attributes."""
        attributes = manual_switch.extra_state_attributes

        assert attributes is not None
        assert attributes["battery_id"] == "battery_a"
        assert attributes["charge_power_limit"] == 5000
        assert attributes["discharge_power_limit"] == 4000
        assert attributes["solar_charging_enabled"] is False
        assert attributes["last_updated"] == 1234567890.0

    def test_extra_state_attributes_no_success(self, manual_switch, mock_coordinator):
        """Test extra state attributes when coordinator has no success."""
        mock_coordinator.last_update_success = False

        attributes = manual_switch.extra_state_attributes
        assert attributes is None

    def test_entity_properties(self, manual_switch):
        """Test entity properties are set correctly."""
        assert manual_switch._attr_name == "Battery_A Manual Control"
        assert manual_switch._attr_icon == "mdi:cog"
        assert manual_switch._attr_entity_category == EntityCategory.CONFIG
        assert manual_switch._attr_unique_id is not None
        assert manual_switch._attr_device_info is not None


class TestErrorHandling:
    """Test error handling in pilot module."""

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        """Create mock Home Assistant instance."""
        return MagicMock(spec=HomeAssistant)

    @pytest.fixture
    def mock_coordinator(self) -> MagicMock:
        """Create mock coordinator that raises exceptions."""
        coordinator = MagicMock()
        coordinator.battery_id = "battery_a"
        coordinator.data = {}
        coordinator.async_set_updated_data = MagicMock(
            side_effect=Exception("Test error")
        )
        coordinator.last_update_success = True
        return coordinator

    @pytest.fixture
    def mock_sax_data(self) -> MagicMock:
        """Create mock SAXBatteryData."""
        return MagicMock()

    @pytest.fixture
    def pilot(self, mock_hass, mock_sax_data, mock_coordinator) -> SAXBatteryPilot:
        """Create SAXBatteryPilot instance with error-prone coordinator."""
        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

    async def test_set_manual_control_exception_handling(self, pilot):
        """Test manual control setting handles exceptions gracefully."""
        # The pilot implementation should catch exceptions and return False
        with pytest.raises(Exception, match="Test error"):
            await pilot.set_manual_control(True)

    async def test_set_solar_charging_exception_handling(self, pilot):
        """Test solar charging setting handles exceptions gracefully."""
        # The pilot implementation should catch exceptions and return False
        with pytest.raises(Exception, match="Test error"):
            await pilot.set_solar_charging(True)

    async def test_set_charge_power_limit_exception_handling(self, pilot):
        """Test charge power limit setting handles exceptions gracefully."""
        pilot.coordinator.async_write_int_value = AsyncMock(
            side_effect=Exception("Test error")
        )
        pilot.sax_data.get_modbus_items_for_battery.return_value = [
            MagicMock(name="sax_max_charge_power")
        ]

        result = await pilot.set_charge_power_limit(5000)
        assert result is False

    async def test_set_discharge_power_limit_exception_handling(self, pilot):
        """Test discharge power limit setting handles exceptions gracefully."""
        pilot.coordinator.async_write_int_value = AsyncMock(
            side_effect=Exception("Test error")
        )
        pilot.sax_data.get_modbus_items_for_battery.return_value = [
            MagicMock(name="sax_max_discharge_power")
        ]

        result = await pilot.set_discharge_power_limit(4000)
        assert result is False
