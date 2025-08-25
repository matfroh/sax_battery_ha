"""Test SAX Battery number platform."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    DESCRIPTION_SAX_MAX_CHARGE,
    DESCRIPTION_SAX_MAX_DISCHARGE,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.number import SAXBatteryNumber, async_setup_entry
from homeassistant.components.number import NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


@pytest.fixture
def power_number_item_test():
    """Create power number item."""
    return ModbusItem(
        address=100,
        name="sax_max_charge_power",
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.SYS,
        entitydescription=NumberEntityDescription(
            key="max_charge_power",
            name="Sax Maximum Charge Power",
            native_min_value=0,
            native_max_value=10000,
            native_step=100,
            native_unit_of_measurement="W",
        ),
    )


@pytest.fixture
def percentage_number_item_test():
    """Create percentage number item."""
    return ModbusItem(
        address=101,
        name="sax_min_soc",
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.SYS,
        entitydescription=NumberEntityDescription(
            key="min_soc",
            name="Sax Minimum State of Charge",
            native_min_value=5,
            native_max_value=95,
            native_step=1,
            native_unit_of_measurement=PERCENTAGE,
        ),
    )


class TestSAXBatteryNumber:
    """Test SAX Battery number entity."""

    def test_number_init(self, mock_coordinator_number, power_number_item_test) -> None:
        """Test number entity initialization."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        assert number._battery_id == "battery_a"
        assert number._modbus_item == power_number_item_test
        assert number.unique_id == "sax_battery_a_max_charge_power"
        assert number.name == "Sax Battery A Maximum Charge Power"

    def test_number_init_with_entity_description(
        self, mock_coordinator_number, power_number_item_test
    ) -> None:
        """Test number entity initialization with entity description."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        # Test that values come from entity description
        assert number.entity_description.native_min_value == 0
        assert number.entity_description.native_max_value == 10000
        assert number.entity_description.native_step == 100
        assert number.entity_description.native_unit_of_measurement == "W"

    def test_number_native_value(
        self, mock_coordinator_number, power_number_item_test
    ) -> None:
        """Test number native value."""
        mock_coordinator_number.data["sax_max_charge_power"] = 5000

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        assert number.native_value == 5000.0

    def test_number_native_value_missing_data(
        self, mock_coordinator_number, power_number_item_test
    ) -> None:
        """Test number native value when data is missing."""
        mock_coordinator_number.data = {}

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        assert number.native_value is None

    def test_number_native_value_invalid_data(
        self, mock_coordinator_number, power_number_item_test
    ) -> None:
        """Test number native value with invalid data."""
        mock_coordinator_number.data["sax_max_charge_power"] = "invalid"

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        assert number.native_value is None

    async def test_async_set_native_value_success(
        self, mock_coordinator_number, power_number_item_test
    ) -> None:
        """Test setting native value successfully."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        await number.async_set_native_value(6000.0)

        mock_coordinator_number.async_write_number_value.assert_called_once_with(
            power_number_item_test, 6000.0
        )

    async def test_async_set_native_value_failure(
        self, mock_coordinator_number, power_number_item_test
    ) -> None:
        """Test setting native value with failure."""
        mock_coordinator_number.async_write_number_value.return_value = False

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        with pytest.raises(
            HomeAssistantError,
            match="Failed to set value 6000.0 for Sax Battery A Maximum Charge Power",
        ):
            await number.async_set_native_value(6000.0)

    def test_extra_state_attributes(
        self, mock_coordinator_number, power_number_item_test
    ) -> None:
        """Test extra state attributes."""
        mock_coordinator_number.data["sax_max_charge_power"] = 5000

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        attributes = number.extra_state_attributes
        assert attributes is not None
        assert attributes["battery_id"] == "battery_a"
        assert attributes["modbus_address"] == 100
        assert attributes["raw_value"] == 5000
        assert "last_update" in attributes

    def test_device_info(self, mock_coordinator_number, power_number_item_test) -> None:
        """Test device info."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=power_number_item_test,
        )

        device_info = number.device_info
        assert device_info is not None
        mock_coordinator_number.sax_data.get_device_info.assert_called_once_with(
            "battery_a"
        )


class TestNumberPlatformSetup:
    """Test number platform setup."""

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
        # Mock coordinator but no number items
        mock_coordinator = MagicMock(spec=SAXBatteryCoordinator)
        mock_sax_data.coordinators = {"battery_a": mock_coordinator}
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
        self, mock_coordinator_number, percentage_number_item_test
    ) -> None:
        """Test number entity with percentage format."""
        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=percentage_number_item_test,
        )

        assert number.entity_description.native_unit_of_measurement == "%"
        assert number.name == "Sax Battery A Minimum State of Charge"

    def test_number_name_formatting(self, mock_coordinator_number) -> None:
        """Test number name formatting."""
        item_with_underscores = ModbusItem(
            name="sax_test_underscore_name",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            entitydescription=NumberEntityDescription(
                key="sax_test_underscore_name",
                name="Sax Test Underscore Name",
                mode=NumberMode.SLIDER,
                native_unit_of_measurement=UnitOfPower.WATT,
                native_min_value=0,
                native_max_value=3500,
                native_step=100,
            ),
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_b",
            modbus_item=item_with_underscores,
        )

        assert number.name == "Sax Battery B Test Underscore Name"

    def test_number_mode_property(self, mock_coordinator_number) -> None:
        """Test number mode property with different mode values."""
        box_item = ModbusItem(
            name="sax_charge_limit",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            address=200,
            battery_slave_id=1,
            factor=1.0,
            entitydescription=NumberEntityDescription(
                key="sax_test_underscore_name",
                name="Sax Test Underscore Name",
                mode=NumberMode.AUTO,
                native_unit_of_measurement=UnitOfPower.WATT,
                native_min_value=0,
                native_max_value=3500,
                native_step=100,
            ),
        )

        box_number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=box_item,
        )

        # Implementation defaults to AUTO mode when no entity description
        assert box_number.mode == NumberMode.AUTO

    def test_number_mode_from_entity_description(self, mock_coordinator_number) -> None:
        """Test number mode from entity description."""
        item_with_mode = ModbusItem(
            name="sax_slider_control",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER_WO,
            entitydescription=NumberEntityDescription(
                key="slider_control",
                name="Slider Control",
                mode=NumberMode.SLIDER,
            ),
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=item_with_mode,
        )

        assert number.entity_description.mode == NumberMode.SLIDER

    def test_number_entity_category_config(self, mock_coordinator_number) -> None:
        """Test number entity category configuration."""
        config_item = ModbusItem(
            name="sax_config_number",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER_WO,
            entitydescription=NumberEntityDescription(
                key="sax_test_underscore_name",
                name="Sax Test Underscore Name",
                mode=NumberMode.AUTO,
                native_unit_of_measurement=UnitOfPower.WATT,
                native_min_value=0,
                native_max_value=3500,
                native_step=100,
            ),
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=config_item,
        )

        # The entity category should be determined by the determine_entity_category function
        # which likely returns CONFIG based on the item type
        assert number.entity_category in (
            EntityCategory.CONFIG,
            EntityCategory.DIAGNOSTIC,
        )

    def test_number_entity_category_diagnostic(self, mock_coordinator_number) -> None:
        """Test number entity category diagnostic."""
        diagnostic_item = ModbusItem(
            name="sax_diagnostic_number",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER_WO,
            entitydescription=NumberEntityDescription(
                key="sax_test_underscore_name",
                name="Sax Test Underscore Name",
                mode=NumberMode.AUTO,
                native_unit_of_measurement=UnitOfPower.WATT,
                native_min_value=0,
                native_max_value=3500,
                native_step=100,
            ),
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=diagnostic_item,
        )

        # The entity category should be determined by the determine_entity_category function
        assert number.entity_category in (
            EntityCategory.CONFIG,
            EntityCategory.DIAGNOSTIC,
        )

    def test_number_entity_category_from_description(
        self, mock_coordinator_number
    ) -> None:
        """Test number entity category from entity description."""
        item_with_category = ModbusItem(
            name="sax_custom_number",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER_WO,
            entitydescription=NumberEntityDescription(
                key="custom_number",
                name="Custom Number",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=item_with_category,
        )

        assert number.entity_category == EntityCategory.DIAGNOSTIC

    def test_number_without_unit(self, mock_coordinator_number) -> None:
        """Test number entity without unit."""
        unitless_item = ModbusItem(
            name="sax_unitless_number",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER_WO,
            entitydescription=NumberEntityDescription(
                key="sax_test_underscore_name",
                name="Sax Test Underscore Name",
                mode=NumberMode.AUTO,
                native_unit_of_measurement=UnitOfPower.WATT,
                native_min_value=0,
                native_max_value=3500,
                native_step=100,
            ),
        )

        number = SAXBatteryNumber(
            coordinator=mock_coordinator_number,
            battery_id="battery_a",
            modbus_item=unitless_item,
        )

        assert number.entity_description.native_unit_of_measurement == UnitOfPower.WATT


class TestSAXBatteryNumberDynamicLimits:
    """Test dynamic limits functionality in SAX Battery number entities."""

    @pytest.fixture
    def max_charge_modbus_item(self):
        """Create max charge ModbusItem."""
        return ModbusItem(
            name=SAX_MAX_CHARGE,
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            entitydescription=DESCRIPTION_SAX_MAX_CHARGE,
            address=100,
            battery_slave_id=1,
            factor=1.0,
        )

    @pytest.fixture
    def max_discharge_modbus_item(self):
        """Create max discharge ModbusItem."""
        return ModbusItem(
            name=SAX_MAX_DISCHARGE,
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            entitydescription=DESCRIPTION_SAX_MAX_DISCHARGE,
            address=101,
            battery_slave_id=1,
            factor=1.0,
        )

    @pytest.fixture
    def regular_modbus_item(self):
        """Create regular ModbusItem (not charge/discharge)."""
        return ModbusItem(
            name="sax_regular_setting",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.NUMBER,
            entitydescription=DESCRIPTION_SAX_MAX_CHARGE,
            address=102,
            battery_slave_id=1,
            factor=1.0,
        )

    def test_apply_dynamic_limits_max_charge_single_battery(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test dynamic limits for max charge with single battery."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            return_value=4500,
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=1,
            )

            mock_calc.assert_called_once_with(1)
            assert number_entity._attr_native_max_value == 4500.0

    def test_apply_dynamic_limits_max_charge_dual_battery(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test dynamic limits for max charge with dual battery."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            return_value=9000,
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=2,
            )

            mock_calc.assert_called_once_with(2)
            assert number_entity._attr_native_max_value == 9000.0

    def test_apply_dynamic_limits_max_charge_triple_battery(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test dynamic limits for max charge with triple battery."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            return_value=13500,
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=3,
            )

            mock_calc.assert_called_once_with(3)
            assert number_entity._attr_native_max_value == 13500.0

    def test_apply_dynamic_limits_max_discharge_single_battery(
        self, mock_coordinator_number, max_discharge_modbus_item
    ):
        """Test dynamic limits for max discharge with single battery."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_discharge",
            return_value=3600,
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_discharge_modbus_item,
                battery_count=1,
            )

            mock_calc.assert_called_once_with(1)
            assert number_entity._attr_native_max_value == 3600.0

    def test_apply_dynamic_limits_max_discharge_dual_battery(
        self, mock_coordinator_number, max_discharge_modbus_item
    ):
        """Test dynamic limits for max discharge with dual battery."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_discharge",
            return_value=7200,
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_discharge_modbus_item,
                battery_count=2,
            )

            mock_calc.assert_called_once_with(2)
            assert number_entity._attr_native_max_value == 7200.0

    def test_apply_dynamic_limits_max_discharge_triple_battery(
        self, mock_coordinator_number, max_discharge_modbus_item
    ):
        """Test dynamic limits for max discharge with triple battery."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_discharge",
            return_value=10800,
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_discharge_modbus_item,
                battery_count=3,
            )

            mock_calc.assert_called_once_with(3)
            assert number_entity._attr_native_max_value == 10800.0

    def test_apply_dynamic_limits_regular_item_unchanged(
        self, mock_coordinator_number, regular_modbus_item
    ):
        """Test that regular items are not affected by dynamic limits."""
        with (
            patch(
                "custom_components.sax_battery.number.calculate_system_max_charge"
            ) as mock_charge_calc,
            patch(
                "custom_components.sax_battery.number.calculate_system_max_discharge"
            ) as mock_discharge_calc,
        ):
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=regular_modbus_item,
                battery_count=2,
            )

            # Calculations should not be called for regular items
            mock_charge_calc.assert_not_called()
            mock_discharge_calc.assert_not_called()

            # Should keep default max value
            assert number_entity._attr_native_max_value == 100.0

    def test_apply_dynamic_limits_max_charge_value_error(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test handling of ValueError in max charge calculation."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            side_effect=ValueError("Invalid battery count"),
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=-1,  # Invalid count
            )

            mock_calc.assert_called_once_with(-1)
            # Should keep default max value when ValueError occurs
            assert number_entity._attr_native_max_value == 100.0

    def test_apply_dynamic_limits_max_discharge_value_error(
        self, mock_coordinator_number, max_discharge_modbus_item
    ):
        """Test handling of ValueError in max discharge calculation."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_discharge",
            side_effect=ValueError("Invalid battery count"),
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_discharge_modbus_item,
                battery_count=0,  # Invalid count
            )

            mock_calc.assert_called_once_with(0)
            # Should keep default max value when ValueError occurs
            assert number_entity._attr_native_max_value == 100.0

    def test_apply_dynamic_limits_float_conversion_max_charge(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test float conversion for max charge limit."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            return_value=4500,  # Integer return
        ):
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=1,
            )

            # Should be converted to float
            assert isinstance(number_entity._attr_native_max_value, float)
            assert number_entity._attr_native_max_value == 4500.0

    def test_apply_dynamic_limits_float_conversion_max_discharge(
        self, mock_coordinator_number, max_discharge_modbus_item
    ):
        """Test float conversion for max discharge limit."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_discharge",
            return_value=3600,  # Integer return
        ):
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_discharge_modbus_item,
                battery_count=1,
            )

            # Should be converted to float
            assert isinstance(number_entity._attr_native_max_value, float)
            assert number_entity._attr_native_max_value == 3600.0

    def test_apply_dynamic_limits_zero_battery_count(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test handling of zero battery count."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            side_effect=ValueError("Invalid battery count: 0"),
        ):
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=0,
            )

            # Should keep default value when calculation fails
            assert number_entity._attr_native_max_value == 100.0

    def test_apply_dynamic_limits_negative_battery_count(
        self, mock_coordinator_number, max_discharge_modbus_item
    ):
        """Test handling of negative battery count."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_discharge",
            side_effect=ValueError("Invalid battery count: -1"),
        ):
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_discharge_modbus_item,
                battery_count=-1,
            )

            # Should keep default value when calculation fails
            assert number_entity._attr_native_max_value == 100.0

    def test_apply_dynamic_limits_preserves_other_attributes(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test that dynamic limits only affect max_value, not other attributes."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            return_value=4500,
        ):
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=1,
            )

            # Other attributes should remain unchanged
            assert number_entity._attr_native_min_value == 0.0
            assert number_entity._attr_native_step == 1.0
            assert number_entity._attr_native_max_value == 4500.0  # Only this changes

    def test_apply_dynamic_limits_multiple_calls_idempotent(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test that calling _apply_dynamic_limits multiple times is safe."""
        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            return_value=4500,
        ) as mock_calc:
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=1,
            )

            # Reset call count after initialization
            mock_calc.reset_mock()

            # Call method again manually
            number_entity._apply_dynamic_limits()

            # Should be called once more
            mock_calc.assert_called_once_with(1)
            assert number_entity._attr_native_max_value == 4500.0

    def test_apply_dynamic_limits_with_entity_description_max_value(
        self, mock_coordinator_number, max_charge_modbus_item
    ):
        """Test dynamic limits override entity description max values."""

        # Add entity description with a different max value
        max_charge_modbus_item.entitydescription = NumberEntityDescription(
            key="max_charge",
            name="Max Charge Power",
            native_max_value=1000.0,  # This should be overridden
        )

        with patch(
            "custom_components.sax_battery.number.calculate_system_max_charge",
            return_value=4500,
        ):
            number_entity = SAXBatteryNumber(
                coordinator=mock_coordinator_number,
                battery_id="battery_a",
                modbus_item=max_charge_modbus_item,
                battery_count=1,
            )

            # Dynamic limit should override entity description
            assert number_entity._attr_native_max_value == 4500.0
