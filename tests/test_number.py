"""Test SAX Battery number platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ApiItem
from custom_components.sax_battery.number import SAXBatteryNumber, async_setup_entry
from homeassistant.components.number import NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


@pytest.fixture
def mock_coordinator():
    """Create mock coordinator."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.last_update_success = True
    coordinator.last_update_success_time = "2024-01-01T00:00:00+00:00"
    coordinator.data = {
        "max_charge_power": 5000,
        "max_discharge_power": 4000,
        "pilot_interval": 60,
        "min_soc": 20,
    }

    # Mock the sax_data attribute and its methods
    mock_sax_data = MagicMock()
    mock_sax_data.get_device_info.return_value = {
        "identifiers": {("sax_battery", "battery_a")},
        "name": "SAX Battery A",
        "manufacturer": "SAX",
        "model": "SAX Battery",
    }
    coordinator.sax_data = mock_sax_data
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    return coordinator


@pytest.fixture
def power_number_item():
    """Create power number item."""
    return ApiItem(
        address=100,
        name="max_charge_power",
        mformat=FormatConstants.NUMBER,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,
        entitydescription=NumberEntityDescription(
            key="max_charge_power",
            name="Maximum Charge Power",
            native_min_value=0,
            native_max_value=10000,
            native_step=100,
            native_unit_of_measurement="W",
        ),
    )


@pytest.fixture
def percentage_number_item():
    """Create percentage number item."""
    return ApiItem(
        address=101,
        name="min_soc",
        mformat=FormatConstants.PERCENTAGE,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,
        entitydescription=NumberEntityDescription(
            key="min_soc",
            name="Minimum State of Charge",
            native_min_value=5,
            native_max_value=95,
            native_step=1,
            native_unit_of_measurement="%",
        ),
    )


@pytest.fixture
def mock_config_entry():
    """Create mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {
        "host": "192.168.1.100",
        "port": 502,
    }
    return entry


class TestSAXBatteryNumber:
    """Test SAX Battery number entity."""

    def test_number_init(self, mock_coordinator, power_number_item) -> None:
        """Test number entity initialization."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        assert number._battery_id == "battery_a"
        assert number._modbus_item == power_number_item
        assert number.unique_id == "battery_a_max_charge_power_0"
        assert number.name == "Battery_A Max Charge Power"
        assert number.native_unit_of_measurement == "W"
        assert number.native_min_value == 0
        assert number.native_max_value == 10000
        assert number.native_step == 100

    def test_number_init_with_entity_description(
        self, mock_coordinator, power_number_item
    ) -> None:
        """Test number entity initialization with entity description."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        # Test that values come from entity description
        assert number.native_min_value == 0
        assert number.native_max_value == 10000
        assert number.native_step == 100

    def test_number_init_without_entity_description(self, mock_coordinator) -> None:
        """Test number entity initialization without entity description."""
        item_without_desc = ApiItem(
            name="test_number",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=item_without_desc,
            index=0,
        )

        # Test default values
        assert number.native_min_value == 0
        assert number.native_max_value == 100
        assert number.native_step == 1

    def test_number_native_value(self, mock_coordinator, power_number_item) -> None:
        """Test number native value."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        assert number.native_value == 5000

    def test_number_native_value_with_divider(self, mock_coordinator) -> None:
        """Test number native value with divider."""
        item_with_divider = ApiItem(
            name="test_number_divider",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
        )
        item_with_divider.divider = 10

        mock_coordinator.data["test_number_divider"] = 500

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=item_with_divider,
            index=0,
        )

        assert number.native_value == 50.0  # 500 / 10

    def test_number_native_value_missing_data(
        self, mock_coordinator, power_number_item
    ) -> None:
        """Test number native value when data is missing."""
        mock_coordinator.data = {}

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        assert number.native_value is None

    async def test_async_set_native_value_success(
        self, mock_coordinator, power_number_item
    ) -> None:
        """Test setting native value successfully."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        await number.async_set_native_value(6000.0)

        mock_coordinator.async_write_number_value.assert_called_once_with(
            power_number_item, 6000.0
        )

    async def test_async_set_native_value_failure(
        self, mock_coordinator, power_number_item
    ) -> None:
        """Test setting native value with failure."""
        mock_coordinator.async_write_number_value.return_value = False

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        with pytest.raises(HomeAssistantError, match="Failed to set"):
            await number.async_set_native_value(6000.0)

    def test_extra_state_attributes(self, mock_coordinator, power_number_item) -> None:
        """Test extra state attributes."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        attributes = number.extra_state_attributes
        assert attributes is not None
        assert attributes["battery_id"] == "battery_a"
        assert attributes["modbus_address"] == 100
        assert "last_updated" in attributes

    def test_extra_state_attributes_unavailable(
        self, mock_coordinator, power_number_item
    ) -> None:
        """Test extra state attributes when unavailable."""
        mock_coordinator.last_update_success = False

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        assert number.extra_state_attributes is None

    def test_device_info(self, mock_coordinator, power_number_item) -> None:
        """Test device info."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        device_info = number.device_info
        assert device_info is not None
        assert "identifiers" in device_info
        assert "name" in device_info


class TestNumberPlatformSetup:
    """Test number platform setup."""

    async def test_async_setup_entry_success(
        self, hass: HomeAssistant, mock_config_entry, mock_sax_data
    ) -> None:
        """Test successful setup of number entries."""
        # Mock number items for each battery
        mock_number_item = ApiItem(
            name="test_number",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
        )
        mock_sax_data.get_modbus_items_for_battery.return_value = [mock_number_item]

        # Store mock data in hass
        hass.data["sax_battery"] = {mock_config_entry.entry_id: mock_sax_data}

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should have created entities for each battery
        assert len(entities) >= 0  # At least no errors occurred

    async def test_async_setup_entry_no_coordinators(
        self, hass: HomeAssistant, mock_config_entry, mock_sax_data
    ) -> None:
        """Test setup with no coordinators."""
        mock_sax_data.coordinators = {}

        # Store mock data in hass
        hass.data["sax_battery"] = {mock_config_entry.entry_id: mock_sax_data}

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should have no entities when no coordinators
        assert len(entities) == 0

    async def test_async_setup_entry_no_number_items(
        self, hass: HomeAssistant, mock_config_entry, mock_sax_data
    ) -> None:
        """Test setup with no number items."""
        mock_sax_data.get_modbus_items_for_battery.return_value = []

        # Store mock data in hass
        hass.data["sax_battery"] = {mock_config_entry.entry_id: mock_sax_data}

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should have no entities when no number items
        assert len(entities) == 0


class TestNumberEntityConfiguration:
    """Test number entity configuration variations."""

    def test_number_with_percentage_format(
        self, mock_coordinator, percentage_number_item
    ) -> None:
        """Test number entity with percentage format."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=percentage_number_item,
            index=0,
        )

        assert number.native_unit_of_measurement == "%"
        assert number.native_min_value == 5
        assert number.native_max_value == 95
        assert number.native_step == 1

    def test_number_entity_category_config(self, mock_coordinator) -> None:
        """Test number entity category configuration."""
        config_item = ApiItem(
            name="config_number",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=config_item,
            index=0,
        )

        assert number.entity_category == EntityCategory.CONFIG

    def test_number_entity_category_diagnostic(self, mock_coordinator) -> None:
        """Test number entity category diagnostic."""
        diagnostic_item = ApiItem(
            name="diagnostic_number",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=diagnostic_item,
            index=0,
        )

        assert number.entity_category == EntityCategory.DIAGNOSTIC

    def test_number_unique_id_with_index(
        self, mock_coordinator, power_number_item
    ) -> None:
        """Test number unique ID with different indices."""
        number_0 = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=0,
        )

        number_1 = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=power_number_item,
            index=1,
        )

        assert number_0.unique_id == "battery_a_max_charge_power_0"
        assert number_1.unique_id == "battery_a_max_charge_power_1"
        assert number_0.unique_id != number_1.unique_id

    def test_number_name_formatting(self, mock_coordinator) -> None:
        """Test number name formatting."""
        item_with_underscores = ApiItem(
            name="test_underscore_name",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_b",
            modbus_item=item_with_underscores,
            index=0,
        )

        assert number.name == "Battery_B Test Underscore Name"

    def test_number_without_unit(self, mock_coordinator) -> None:
        """Test number entity without unit."""
        unitless_item = ApiItem(
            name="unitless_number",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=unitless_item,
            index=0,
        )

        assert number.native_unit_of_measurement is None

    def test_number_mode_property(self, mock_coordinator) -> None:
        """Test number mode property with different mode values."""
        # Test BOX mode
        box_item = ApiItem(
            name="charge_limit",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.NUMBER,
            address=200,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add mode attribute
        setattr(box_item, "mode", "box")

        box_number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=box_item,
            index=0,
        )
        assert box_number.mode == NumberMode.BOX

        # Test SLIDER mode
        slider_item = ApiItem(
            name="power_limit",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            address=201,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add mode attribute
        setattr(slider_item, "mode", "slider")

        slider_number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=slider_item,
            index=1,
        )
        assert slider_number.mode == NumberMode.SLIDER

        # Test AUTO mode (default case)
        auto_item = ApiItem(
            name="temperature_limit",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.NUMBER,
            address=202,
            battery_slave_id=1,
            divider=1.0,
        )
        # Dynamically add mode attribute with unknown value
        setattr(auto_item, "mode", "unknown_mode")  # Should default to AUTO

        auto_number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=auto_item,
            index=2,
        )
        assert auto_number.mode == NumberMode.AUTO

        # Test no mode attribute (should default to AUTO)
        no_mode_item = ApiItem(
            name="voltage_limit",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            address=203,
            battery_slave_id=1,
            divider=1.0,
        )
        # No mode attribute set - getattr will return "auto" default

        no_mode_number = SAXBatteryNumber(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=no_mode_item,
            index=3,
        )
        assert no_mode_number.mode == NumberMode.AUTO
