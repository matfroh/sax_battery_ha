"""Test SAX Battery number platform - reorganized and optimized."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    DOMAIN,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.models import SAXBatteryData
from custom_components.sax_battery.number import (
    SAXBatteryConfigNumber,
    SAXBatteryModbusNumber,
    async_setup_entry,
)
from homeassistant.components.number import NumberEntityDescription
from homeassistant.const import UnitOfPower
from homeassistant.exceptions import HomeAssistantError


class TestSAXBatteryModbusNumber:
    """Test SAX Battery modbus number entity - consolidated tests."""

    def test_initialization_modbus_item(
        self,
        mock_coordinator_modbus_base,
        modbus_item_max_charge_base,
        simulate_unique_id_max_charge,
    ) -> None:
        """Test basic number entity initialization."""

        mock_config_entry = MagicMock()
        mock_config_entry.data = {"battery_count": 1, "master_battery": "battery_a"}

        sax_data = SAXBatteryData(mock_coordinator_modbus_base.hass, mock_config_entry)
        mock_coordinator_modbus_base.sax_data = sax_data

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_max_charge_base,
        )

        assert number.name == "Max Charge"
        assert number._battery_id == "battery_a"
        assert number._modbus_item == modbus_item_max_charge_base
        assert number.entity_description.native_unit_of_measurement == UnitOfPower.WATT
        # Device info should come from actual get_device_info method
        assert number.device_info["name"] == "SAX Cluster"  # type: ignore[index]
        assert simulate_unique_id_max_charge == "number.sax_cluster_max_charge"

    def test_initialization_write_only(self, mock_coordinator_modbus_base) -> None:
        """Test write-only register initialization."""
        write_only_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        assert number._is_write_only is True
        # SAX_NOMINAL_POWER is a pilot control item, so it gets safe default 0.0
        assert number._local_value == 0.0  # Security: safe default for pilot control

    def test_initialization_write_only_max_charge(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test write-only register initialization for max charge."""
        # Test with SAX_MAX_CHARGE which should use config values
        # Fix: Use address from WRITE_ONLY_REGISTERS to make it actually write-only
        write_only_item = ModbusItem(
            address=41,  # Fixed: Use address that's actually in WRITE_ONLY_REGISTERS
            name=SAX_MAX_CHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        assert number._is_write_only is True
        assert number._local_value == 4000.0  # From config max_charge

    def test_native_value_scenarios(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test native value in different scenarios."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        # Test with data
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25.5}
        assert number.native_value == 25.5

        # Test missing data
        mock_coordinator_modbus_base.data = {}
        assert number.native_value is None

    def test_availability(
        self, mock_coordinator_modbus_base, modbus_item_max_charge_base
    ) -> None:
        """Test entity availability."""
        # Fix: Create actual write-only item to test write-only availability logic
        write_only_item = ModbusItem(
            address=41,  # This is in WRITE_ONLY_REGISTERS
            name=SAX_MAX_CHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        # Write-only registers are available when coordinator is successful
        mock_coordinator_modbus_base.last_update_success = True
        mock_coordinator_modbus_base.data = None  # Write-only doesn't need data
        assert number.available is True

        # Unavailable when coordinator fails
        mock_coordinator_modbus_base.last_update_success = False
        assert number.available is False

    def test_availability_readable_register(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test availability for readable register."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        # Readable registers need data presence
        mock_coordinator_modbus_base.last_update_success = True
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25.5}
        assert number.available is True

        # Unavailable when data is missing
        mock_coordinator_modbus_base.data = {}
        assert number.available is False

    async def test_set_native_value_success(
        self, mock_coordinator_modbus_base, modbus_item_max_charge_base
    ) -> None:
        """Test successful set_native_value operation."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_max_charge_base,
        )

        with patch.object(number, "async_write_ha_state"):
            await number.async_set_native_value(3000.0)

        mock_coordinator_modbus_base.async_write_number_value.assert_called_once_with(
            modbus_item_max_charge_base, 3000.0
        )

    async def test_set_native_value_failure(
        self, mock_coordinator_modbus_base, modbus_item_max_charge_base
    ) -> None:
        """Test set_native_value operation failure."""
        mock_coordinator_modbus_base.async_write_number_value.return_value = False

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_max_charge_base,
        )

        with pytest.raises(HomeAssistantError, match="Failed to write value"):
            await number.async_set_native_value(3000.0)

    def test_extra_state_attributes(
        self, mock_coordinator_modbus_base, modbus_item_max_charge_base
    ) -> None:
        """Test extra state attributes for different register types."""
        # Regular register
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_max_charge_base,
        )

        attributes = number.extra_state_attributes
        assert attributes["battery_id"] == "battery_a"
        assert attributes["entity_type"] == "modbus"
        assert "last_update" in attributes

        # Write-only register
        write_only_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        write_only_number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        wo_attributes = write_only_number.extra_state_attributes
        assert wo_attributes["is_write_only"] is True
        assert "local_value" in wo_attributes

    def test_write_only_defaults_security(self, mock_coordinator_modbus_base) -> None:
        """Test that pilot control items don't get dangerous defaults."""
        # Clear config to ensure no dangerous defaults
        mock_coordinator_modbus_base.config_entry.data = {}

        pilot_control_items = [
            (SAX_NOMINAL_POWER, 41),
            (SAX_NOMINAL_FACTOR, 42),
        ]

        for item_name, address in pilot_control_items:
            item = ModbusItem(
                address=address,
                name=item_name,
                mtype=TypeConstants.NUMBER_WO,
                device=DeviceConstants.BESS,
            )

            number = SAXBatteryModbusNumber(
                coordinator=mock_coordinator_modbus_base,
                battery_id="battery_a",
                modbus_item=item,
            )

            # Security: pilot control items should only get safe defaults (0.0)
            assert number._local_value == 0.0, f"Dangerous default for {item_name}"


class TestSAXBatteryModbusNumberAdvanced:
    """Test advanced scenarios for SAX Battery modbus number entity."""

    def test_initialize_write_only_defaults_comprehensive(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test comprehensive write-only defaults initialization."""
        # Test SAX_MAX_CHARGE with config value - fix: use correct address
        mock_coordinator_modbus_base.config_entry.data = {"max_charge": 5000.0}

        max_charge_item = ModbusItem(
            address=41,  # Fixed: Use address that's in WRITE_ONLY_REGISTERS
            name=SAX_MAX_CHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        max_charge_number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=max_charge_item,
        )

        assert max_charge_number._local_value == 5000.0

        # Test SAX_MAX_DISCHARGE with config value - fix: use correct address
        mock_coordinator_modbus_base.config_entry.data = {"max_discharge": 3500.0}

        max_discharge_item = ModbusItem(
            address=42,  # Fixed: Use address that's in WRITE_ONLY_REGISTERS
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        max_discharge_number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=max_discharge_item,
        )

        assert max_discharge_number._local_value == 3500.0

    def test_initialize_write_only_defaults_no_config_entry(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test initialization when no config entry exists."""
        # Remove config entry
        mock_coordinator_modbus_base.config_entry = None

        write_only_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        # Should not crash and local_value should remain None
        assert number._local_value is None

    def test_native_value_write_only_register(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test native value for write-only register."""
        write_only_item = ModbusItem(
            address=41,  # Fixed: Use address that's in WRITE_ONLY_REGISTERS
            name=SAX_MAX_CHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        # Should return local value for write-only registers
        assert number.native_value == 4000.0  # From config

        # Test with None local value
        number._local_value = None
        assert number.native_value is None

    def test_native_value_readable_register_with_data(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test native value for readable register with valid data."""
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25.5}

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        # Should return float value from coordinator data
        assert number.native_value == 25.5

    def test_native_value_readable_register_none_data(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test native value when coordinator data is None."""
        mock_coordinator_modbus_base.data = None

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        assert number.native_value is None

    async def test_set_native_value_pilot_control_success(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test successful pilot control set_native_value operation."""
        pilot_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=pilot_item,
        )

        # Mock pilot control write method
        with (
            patch.object(
                number, "_write_pilot_control_value_transactional", return_value=True
            ) as mock_pilot_write,
            patch.object(number, "async_write_ha_state"),
        ):
            await number.async_set_native_value(2500.0)

        mock_pilot_write.assert_called_once_with(2500.0)

    async def test_set_native_value_pilot_control_failure(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test failed pilot control set_native_value operation."""
        pilot_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=pilot_item,
        )

        # Mock pilot control write method to fail
        with (
            patch.object(
                number, "_write_pilot_control_value_transactional", return_value=False
            ),
            pytest.raises(HomeAssistantError, match="Failed to write value"),
        ):
            await number.async_set_native_value(2500.0)

    async def test_set_native_value_exception_handling(
        self, mock_coordinator_modbus_base, modbus_item_max_charge_base
    ) -> None:
        """Test exception handling in set_native_value."""
        mock_coordinator_modbus_base.async_write_number_value.side_effect = ValueError(
            "Test exception"
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_max_charge_base,
        )

        with pytest.raises(HomeAssistantError, match="Unexpected error setting"):
            await number.async_set_native_value(3000.0)

    def test_extra_state_attributes_readable_register_with_data(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test extra state attributes for readable register with data."""
        # Set up coordinator data
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25.5}

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        attributes = number.extra_state_attributes

        # Should include raw_value for readable registers
        assert attributes["raw_value"] == 25.5
        assert attributes["is_write_only"] is False
        assert "local_value" not in attributes  # Only for write-only

    def test_extra_state_attributes_no_coordinator_data(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test extra state attributes without coordinator data."""
        # Clear coordinator data
        mock_coordinator_modbus_base.data = None

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        attributes = number.extra_state_attributes
        assert attributes["raw_value"] is None
        assert attributes["entity_type"] == "modbus"

    async def test_async_added_to_hass_write_only_restoration(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test async_added_to_hass when restoration is needed."""
        write_only_item = ModbusItem(
            address=41,  # Fixed: Use address that's in WRITE_ONLY_REGISTERS
            name=SAX_MAX_CHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        # Clear local value to simulate need for restoration
        number._local_value = None

        await number.async_added_to_hass()

        # Value should be restored from config
        assert number._local_value == 4000.0

    async def test_async_added_to_hass_no_restoration_needed(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test async_added_to_hass when restoration is not needed."""
        write_only_item = ModbusItem(
            address=41,  # Fixed: Use correct address
            name=SAX_MAX_CHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        # Set a local value (simulating already initialized)
        number._local_value = 3000.0
        initial_value = number._local_value

        await number.async_added_to_hass()

        # Value should remain unchanged
        assert number._local_value == initial_value

    def test_find_pilot_control_pair_power_item(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test pilot control pair finding for power item."""
        power_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=power_item,
        )

        # Should find the power factor pair
        assert number._pilot_control_pair is not None
        assert number._pilot_control_pair.name == SAX_NOMINAL_FACTOR

    def test_find_pilot_control_pair_factor_item(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test pilot control pair finding for factor item."""
        factor_item = ModbusItem(
            address=42,
            name=SAX_NOMINAL_FACTOR,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=factor_item,
        )

        # Should find the power pair
        assert number._pilot_control_pair is not None
        assert number._pilot_control_pair.name == SAX_NOMINAL_POWER

    def test_find_pilot_control_pair_non_pilot_item(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test pilot control pair finding for non-pilot item."""
        regular_item = ModbusItem(
            address=41,  # Fixed: Use valid write-only address
            name=SAX_MAX_CHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=regular_item,
        )

        # Should not find a pair for non-pilot control item
        assert number._pilot_control_pair is None

    def test_entity_name_generation(self, mock_coordinator_modbus_base) -> None:
        """Test entity name generation from different sources."""
        # Test with entity description

        item_with_description = ModbusItem(
            address=41,  # Fixed: Use valid address
            name="sax_test_setting",
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
            entitydescription=NumberEntityDescription(
                key="test_setting",
                name="Sax Test Setting Name",
            ),
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=item_with_description,
        )

        # Should use entity description name without "Sax " prefix
        assert number.name == "Test Setting Name"

        # Test without entity description
        item_without_description = ModbusItem(
            address=42,  # Fixed: Use valid address
            name="sax_another_setting",
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number2 = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=item_without_description,
        )

        # Should generate clean name from item name
        assert number2.name == "Another Setting"

    def test_device_info_assignment(self, mock_coordinator_modbus_base) -> None:
        """Test device info assignment during initialization."""
        test_item = ModbusItem(
            address=41,  # Fixed: Use valid address
            name="sax_test_setting",
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_b",
            modbus_item=test_item,
        )

        # Verify device info was requested for the correct battery
        mock_coordinator_modbus_base.sax_data.get_device_info.assert_called_with(
            "battery_b", test_item.device
        )
        assert number.device_info == {"name": "Test Battery"}


class TestSAXBatteryConfigNumber:
    """Test SAX Battery config number entity - consolidated tests."""

    def test_initialization_sax_item(
        self,
        mock_coordinator_config_base,
        sax_item_min_soc_base,
        mock_device_info_cluster,
        simulate_unique_id_min_soc,
    ) -> None:
        """Test config number initialization with proper unique ID generation."""

        mock_config_entry = MagicMock()
        mock_config_entry.data = {"battery_count": 1, "master_battery": "battery_a"}

        sax_data = SAXBatteryData(mock_coordinator_config_base.hass, mock_config_entry)
        mock_coordinator_config_base.sax_data = sax_data

        # Ensure the SAX item has the correct device reference
        sax_item_min_soc_base.device = DeviceConstants.SYS

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Verify the device info comes from actual get_device_info method
        assert number.device_info["name"] == "SAX Cluster"  # type: ignore[index]

        # Verify entity description came from the real const.py data
        assert number.entity_description.name == "Sax Minimum SOC"
        assert number.entity_description.key == SAX_MIN_SOC
        assert hasattr(number, "entity_description")

        # Verify the simulation function generates the expected format
        assert simulate_unique_id_min_soc == "number.sax_cluster_minimum_soc"

    def test_native_value_scenarios(
        self, mock_coordinator_config_base, sax_item_min_soc_base
    ) -> None:
        """Test native value in different scenarios."""
        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # With data
        assert number.native_value == 15.0  # From config entry

        # Without config entry
        mock_coordinator_config_base.config_entry = None
        assert number.native_value is None

    def test_availability(
        self, mock_coordinator_config_base, sax_item_min_soc_base
    ) -> None:
        """Test config number availability."""
        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Available with data
        assert number.available is True

        # Unavailable without data
        mock_coordinator_config_base.data = None
        assert number.available is False

    async def test_set_native_value_scenarios(
        self, mock_coordinator_config_base, sax_item_min_soc_base, mock_hass_base
    ) -> None:
        """Test setting config number native value."""
        sax_item_min_soc_base.async_write_value = AsyncMock(return_value=True)

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Success case
        with (
            patch.object(number, "async_write_ha_state"),
            patch.object(number, "hass", mock_hass_base),
        ):
            await number.async_set_native_value(20.0)

        sax_item_min_soc_base.async_write_value.assert_called_once_with(20.0)

        # Failure case
        sax_item_min_soc_base.async_write_value.return_value = False

        with (
            patch.object(number, "async_write_ha_state"),
            patch.object(number, "hass", mock_hass_base),
            pytest.raises(HomeAssistantError, match="Failed to write"),
        ):
            await number.async_set_native_value(20.0)


@pytest.fixture
def mock_sax_item_min_soc_base():
    """Create a test SAX item for min SOC."""
    sax_item = MagicMock(spec=SAXItem)
    sax_item.name = SAX_MIN_SOC
    sax_item.device = DeviceConstants.SYS
    sax_item.entitydescription = NumberEntityDescription(
        key="min_soc",
        name="Minimum SOC",
    )
    sax_item.async_write_value = AsyncMock(return_value=True)
    return sax_item


class TestSAXBatteryConfigNumberAdvanced:
    """Test advanced scenarios for SAX Battery config number entity."""

    def test_config_number_device_info(
        self, mock_coordinator_config_base, mock_sax_item_min_soc_base
    ) -> None:
        """Test config number device info."""
        # Mock cluster device info
        mock_coordinator_config_base.sax_data.get_device_info.return_value = {
            "name": "SAX Battery Cluster"
        }

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=mock_sax_item_min_soc_base,
        )

        assert number.device_info == {"name": "SAX Battery Cluster"}
        mock_coordinator_config_base.sax_data.get_device_info.assert_called_with(
            "cluster", DeviceConstants.SYS
        )

    def test_config_number_native_value_non_min_soc(
        self, mock_coordinator_config_base
    ) -> None:
        """Test config number native value for non-MIN_SOC items."""
        # Create a different SAX item (not MIN_SOC)

        other_sax_item = MagicMock(spec=SAXItem)
        other_sax_item.name = "sax_other_setting"
        other_sax_item.entitydescription = None
        other_sax_item.device = DeviceConstants.SYS

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=other_sax_item,
        )

        # Should return None for non-MIN_SOC items
        assert number.native_value is None

    async def test_config_number_set_native_value_exception_handling(
        self, mock_coordinator_config_base, mock_sax_item_min_soc_base, mock_hass_base
    ) -> None:
        """Test config number set_native_value with exception handling."""

        # Mock write failure with generic exception
        mock_sax_item_min_soc_base.async_write_value = AsyncMock(
            side_effect=ValueError("Test error")
        )

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=mock_sax_item_min_soc_base,
        )

        with (
            patch.object(number, "async_write_ha_state"),
            patch.object(number, "hass", mock_hass_base),
            pytest.raises(HomeAssistantError, match="Unexpected error setting"),
        ):
            await number.async_set_native_value(25.0)


class TestSAXBatteryPilotControl:
    """Test pilot control functionality - consolidated tests."""

    def test_pilot_control_detection(
        self, mock_coordinator_pilot_control_base, modbus_item_pilot_power_base
    ):
        """Test pilot control item detection and pairing."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=modbus_item_pilot_power_base,
        )

        assert number._is_pilot_control_item is True
        assert number._pilot_control_pair is not None
        assert number._pilot_control_pair.name == SAX_NOMINAL_FACTOR
        assert number._transaction_key == "battery_a_pilot_control"

    def test_power_factor_validation(
        self, mock_coordinator_pilot_control_base, modbus_item_pilot_factor_base
    ):
        """Test power factor validation with different scales."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=modbus_item_pilot_factor_base,
        )

        # Valid values
        assert number._validate_power_factor_range(950) is True  # 1000 scale
        assert number._validate_power_factor_range(9500) is True  # 10000 scale
        assert number._validate_power_factor_range(0) is True
        assert number._validate_power_factor_range(1000) is True
        assert number._validate_power_factor_range(10000) is True

        # Invalid values
        assert number._validate_power_factor_range(-1) is False
        assert number._validate_power_factor_range(10001) is False

    async def test_transactional_write_scenarios(
        self, mock_coordinator_pilot_control_base, modbus_item_pilot_power_base
    ):
        """Test pilot control transactional writes."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=modbus_item_pilot_power_base,
        )

        # Atomic write with existing power factor
        mock_coordinator_pilot_control_base.data = {SAX_NOMINAL_FACTOR: 950}
        result = await number._write_pilot_control_value_transactional(3000.0)
        assert result is True
        mock_coordinator_pilot_control_base.async_write_pilot_control_value.assert_called_once()

        # Deferred transaction with missing power factor
        mock_coordinator_pilot_control_base.data = {}
        mock_coordinator_pilot_control_base.async_write_pilot_control_value.reset_mock()
        result = await number._write_pilot_control_value_transactional(3000.0)
        assert result is True  # Transaction staged
        mock_coordinator_pilot_control_base.async_write_pilot_control_value.assert_not_called()

        # Transaction should be staged
        assert (
            number._transaction_key in SAXBatteryModbusNumber._pilot_control_transaction
        )

    def test_transaction_cleanup(self, mock_coordinator_pilot_control_base):
        """Test transaction cleanup functionality."""
        current_time = time.time()

        # Create mixed transactions
        SAXBatteryModbusNumber._pilot_control_transaction = {
            "expired": {
                "timestamp": current_time - 10.0,
                "power": 1000,
                "power_factor": 950,
                "pending_writes": {"power"},
            },
            "valid": {
                "timestamp": current_time,
                "power": 2000,
                "power_factor": 900,
                "pending_writes": {"power_factor"},
            },
        }

        SAXBatteryModbusNumber._cleanup_expired_transactions(current_time)

        assert "expired" not in SAXBatteryModbusNumber._pilot_control_transaction
        assert "valid" in SAXBatteryModbusNumber._pilot_control_transaction

    def test_extra_state_attributes_pilot_control(
        self, mock_coordinator_pilot_control_base, modbus_item_pilot_power_base
    ):
        """Test extra state attributes for pilot control items."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=modbus_item_pilot_power_base,
        )

        attributes = number.extra_state_attributes
        assert attributes["is_pilot_control"] is True
        assert attributes["pilot_control_note"] == (
            "Pilot control register - atomic transaction with paired register"
        )
        assert attributes["transaction_pending"] is False  # No pending transactions


class TestSAXBatteryPilotControlAdvanced:
    """Test advanced pilot control scenarios."""

    def test_power_factor_validation_edge_cases(
        self, mock_coordinator_pilot_control_base
    ) -> None:
        """Test power factor validation edge cases."""
        factor_item = ModbusItem(
            address=42,
            name=SAX_NOMINAL_FACTOR,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=factor_item,
        )

        # Test exact boundary values
        assert number._validate_power_factor_range(0) is True  # Minimum valid
        assert number._validate_power_factor_range(1000) is True  # Max for 1000 scale
        assert number._validate_power_factor_range(10000) is True  # Max for 10000 scale

        # Test invalid values
        assert number._validate_power_factor_range(-0.1) is False  # Below minimum
        assert number._validate_power_factor_range(10001) is False  # Above maximum

    def test_power_factor_validation_exception_handling(
        self, mock_coordinator_pilot_control_base
    ) -> None:
        """Test power factor validation with conversion errors."""
        factor_item = ModbusItem(
            address=42,
            name=SAX_NOMINAL_FACTOR,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=factor_item,
        )

        # Fix: Test the actual validation method behavior with invalid input
        # The method should handle exceptions and return False
        result = number._validate_power_factor_range("invalid")  # type: ignore[arg-type]
        assert result is False  # Should handle the error gracefully

        # Test with None input
        result = number._validate_power_factor_range(None)  # type: ignore[arg-type]
        assert result is False

    async def test_get_current_pilot_control_value_from_coordinator(
        self, mock_coordinator_pilot_control_base
    ) -> None:
        """Test getting pilot control value from coordinator data."""
        power_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=power_item,
        )

        # Set up coordinator data
        mock_coordinator_pilot_control_base.data = {SAX_NOMINAL_POWER: 2500.0}

        result = await number._get_current_pilot_control_value(SAX_NOMINAL_POWER)
        assert result == 2500.0

    async def test_get_current_pilot_control_value_from_local_state(
        self, mock_coordinator_pilot_control_base
    ) -> None:
        """Test getting pilot control value from local state."""
        power_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=power_item,
        )

        # Set local value and clear coordinator data
        number._local_value = 2500.0
        mock_coordinator_pilot_control_base.data = {}

        result = await number._get_current_pilot_control_value(SAX_NOMINAL_POWER)
        assert result == 2500.0

    async def test_get_current_pilot_control_value_not_available(
        self, mock_coordinator_pilot_control_base
    ) -> None:
        """Test getting pilot control value when not available."""
        power_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=power_item,
        )

        # Clear all data sources
        mock_coordinator_pilot_control_base.data = {}
        number._local_value = None

        result = await number._get_current_pilot_control_value(SAX_NOMINAL_FACTOR)
        assert result is None

    async def test_pilot_control_transaction_staging_and_execution(
        self, mock_coordinator_pilot_control_base
    ) -> None:
        """Test comprehensive pilot control transaction staging and execution."""
        power_item = ModbusItem(
            address=41,
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        factor_item = ModbusItem(
            address=42,
            name=SAX_NOMINAL_FACTOR,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        power_number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=power_item,
        )

        factor_number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_pilot_control_base,
            battery_id="battery_a",
            modbus_item=factor_item,
        )

        # Stage power value first
        mock_coordinator_pilot_control_base.data = {}
        result1 = await power_number._write_pilot_control_value_transactional(3000.0)
        assert result1 is True  # Staged successfully

        # Should not execute atomic write yet
        mock_coordinator_pilot_control_base.async_write_pilot_control_value.assert_not_called()

        # Stage power factor value - should trigger atomic write
        result2 = await factor_number._write_pilot_control_value_transactional(950.0)
        assert result2 is True  # Executed successfully

        # Should have executed atomic write
        mock_coordinator_pilot_control_base.async_write_pilot_control_value.assert_called_once()

    def test_cleanup_expired_transactions_mixed_timestamps(
        self, mock_coordinator_pilot_control_base
    ) -> None:
        """Test cleanup of expired transactions with mixed timestamps."""
        current_time = time.time()

        # Set up transactions with different timestamps
        SAXBatteryModbusNumber._pilot_control_transaction = {
            "expired_1": {
                "timestamp": current_time - 10.0,  # Expired
                "power": 1000,
                "power_factor": 950,
                "pending_writes": {"power"},
            },
            "valid_1": {
                "timestamp": current_time - 0.5,  # Valid
                "power": 2000,
                "power_factor": 900,
                "pending_writes": {"power_factor"},
            },
            "expired_2": {
                "timestamp": current_time - 5.0,  # Expired
                "power": 1500,
                "power_factor": 850,
                "pending_writes": {"power", "power_factor"},
            },
        }

        # Call cleanup
        SAXBatteryModbusNumber._cleanup_expired_transactions(current_time)

        # Only valid_1 should remain
        assert "expired_1" not in SAXBatteryModbusNumber._pilot_control_transaction
        assert "expired_2" not in SAXBatteryModbusNumber._pilot_control_transaction
        assert "valid_1" in SAXBatteryModbusNumber._pilot_control_transaction


class TestAsyncSetupEntry:
    """Test async_setup_entry function - essential scenarios only."""

    @pytest.fixture
    def setup_data(self, mock_hass_base, mock_config_entry_base):
        """Create setup data for entry tests."""
        mock_sax_data = MagicMock()
        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.get_sax_items_for_battery.return_value = []

        mock_coordinator = MagicMock()
        mock_coordinator.hass = mock_hass_base
        mock_coordinator.battery_config = {"is_master": True, "phase": "L1"}
        mock_coordinator.sax_data = mock_sax_data

        mock_hass_base.data[DOMAIN] = {
            mock_config_entry_base.entry_id: {
                "coordinators": {"battery_a": mock_coordinator},
                "sax_data": mock_sax_data,
            }
        }

        return {
            "hass": mock_hass_base,
            "config_entry": mock_config_entry_base,
            "coordinator": mock_coordinator,
            "sax_data": mock_sax_data,
        }

    async def test_setup_basic_scenarios(self, setup_data):
        """Test basic setup scenarios."""
        async_add_entities = MagicMock()  # Fixed: Use MagicMock instead of AsyncMock

        with (
            patch(
                "custom_components.sax_battery.number.filter_items_by_type"
            ) as mock_filter_modbus,
            patch(
                "custom_components.sax_battery.number.filter_sax_items_by_type"
            ) as mock_filter_sax,
        ):
            # No entities case
            mock_filter_modbus.return_value = []
            mock_filter_sax.return_value = []

            await async_setup_entry(
                setup_data["hass"], setup_data["config_entry"], async_add_entities
            )

            async_add_entities.assert_not_called()

            # With entities case
            mock_filter_modbus.return_value = [
                ModbusItem(
                    address=41,  # Fixed: Use valid address
                    name=SAX_MAX_CHARGE,
                    mtype=TypeConstants.NUMBER_WO,
                    device=DeviceConstants.BESS,
                )
            ]

            await async_setup_entry(
                setup_data["hass"], setup_data["config_entry"], async_add_entities
            )

            async_add_entities.assert_called_once()
            entities = async_add_entities.call_args[0][0]
            assert len(entities) == 1
            assert isinstance(entities[0], SAXBatteryModbusNumber)

    async def test_setup_invalid_battery_id(
        self, mock_hass_base, mock_config_entry_base
    ):
        """Test setup with invalid battery ID."""
        mock_sax_data = MagicMock()
        mock_coordinator = MagicMock()

        mock_hass_base.data[DOMAIN] = {
            mock_config_entry_base.entry_id: {
                "coordinators": {"invalid_battery": mock_coordinator},
                "sax_data": mock_sax_data,
            }
        }

        async_add_entities = MagicMock()  # Fixed: Use MagicMock instead of AsyncMock

        with patch("custom_components.sax_battery.number._LOGGER") as mock_logger:
            await async_setup_entry(
                mock_hass_base, mock_config_entry_base, async_add_entities
            )

        mock_logger.warning.assert_called_with(
            "Invalid battery ID %s, skipping", "invalid_battery"
        )

    async def test_setup_with_master_and_slave_batteries(
        self, mock_hass_base, mock_config_entry_base
    ):
        """Test setup with both master and slave batteries."""
        mock_sax_data = MagicMock()
        mock_sax_data.device = DeviceConstants.BESS
        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.get_sax_items_for_battery.return_value = []

        # Create master and slave coordinators
        master_coordinator = MagicMock()
        master_coordinator.hass = mock_hass_base
        master_coordinator.battery_config = {"is_master": True, "phase": "L1"}
        master_coordinator.sax_data = mock_sax_data

        slave_coordinator = MagicMock()
        slave_coordinator.hass = mock_hass_base
        slave_coordinator.battery_config = {"is_master": False, "phase": "L2"}
        slave_coordinator.sax_data = mock_sax_data

        mock_hass_base.data[DOMAIN] = {
            mock_config_entry_base.entry_id: {
                "coordinators": {
                    "battery_a": master_coordinator,
                    "battery_b": slave_coordinator,
                },
                "sax_data": mock_sax_data,
            }
        }

        async_add_entities = MagicMock()

        with (
            patch(
                "custom_components.sax_battery.number.filter_items_by_type"
            ) as mock_filter_modbus,
            patch(
                "custom_components.sax_battery.number.filter_sax_items_by_type"
            ) as mock_filter_sax,
        ):
            # Return entities for both batteries
            mock_filter_modbus.return_value = [
                ModbusItem(
                    address=41,  # Fixed: Use valid address
                    name=SAX_MAX_CHARGE,
                    mtype=TypeConstants.NUMBER_WO,
                    device=DeviceConstants.BESS,
                )
            ]

            # Return config entities (only for master)

            mock_sax_item = MagicMock(spec=SAXItem)
            mock_sax_item.name = SAX_MIN_SOC
            mock_sax_item.device = (
                DeviceConstants.SYS
            )  # Fix: Add missing device attribute
            mock_filter_sax.return_value = [mock_sax_item]

            await async_setup_entry(
                mock_hass_base, mock_config_entry_base, async_add_entities
            )

            # Verify entities were created for both batteries
            async_add_entities.assert_called()
            call_args = async_add_entities.call_args[0][0]
            assert len(call_args) >= 3  # At least 3 entities (2 modbus + 1 config)

        async def test_setup_no_master_coordinator(
            self, mock_hass_base, mock_config_entry_base
        ):
            """Test setup without master coordinator."""
            mock_sax_data = MagicMock()
            mock_sax_data.get_modbus_items_for_battery.return_value = []

            # Create only slave coordinator
            slave_coordinator = MagicMock()
            slave_coordinator.hass = mock_hass_base
            slave_coordinator.battery_config = {"is_master": False, "phase": "L2"}
            slave_coordinator.sax_data = mock_sax_data

            mock_hass_base.data[DOMAIN] = {
                mock_config_entry_base.entry_id: {
                    "coordinators": {"battery_b": slave_coordinator},
                    "sax_data": mock_sax_data,
                }
            }

            async_add_entities = MagicMock()

            with patch(
                "custom_components.sax_battery.number.filter_items_by_type"
            ) as mock_filter_modbus:
                mock_filter_modbus.return_value = []

                await async_setup_entry(
                    mock_hass_base, mock_config_entry_base, async_add_entities
                )

            # Should not create any entities (no modbus entities and no master for config)
            async_add_entities.assert_not_called()

    async def test_setup_logging_verification(
        self, mock_hass_base, mock_config_entry_base
    ):
        """Test that proper logging occurs during setup."""
        mock_sax_data = MagicMock()
        mock_sax_data.device = DeviceConstants.SYS
        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.get_sax_items_for_battery.return_value = []

        mock_coordinator = MagicMock()
        mock_coordinator.hass = mock_hass_base
        mock_coordinator.battery_config = {"is_master": True, "phase": "L1"}
        mock_coordinator.sax_data = mock_sax_data

        mock_hass_base.data[DOMAIN] = {
            mock_config_entry_base.entry_id: {
                "coordinators": {"battery_a": mock_coordinator},
                "sax_data": mock_sax_data,
            }
        }

        async_add_entities = MagicMock()

        with (
            patch("custom_components.sax_battery.number._LOGGER") as mock_logger,
            patch(
                "custom_components.sax_battery.number.filter_items_by_type"
            ) as mock_filter_modbus,
            patch(
                "custom_components.sax_battery.number.filter_sax_items_by_type"
            ) as mock_filter_sax,
        ):
            mock_filter_modbus.return_value = [
                ModbusItem(
                    address=41,  # Fixed: Use valid address
                    name=SAX_MAX_CHARGE,
                    mtype=TypeConstants.NUMBER_WO,
                    device=DeviceConstants.BESS,
                )
            ]

            mock_sax_item = MagicMock(spec=SAXItem)
            mock_sax_item.name = SAX_MIN_SOC
            mock_sax_item.device = (
                DeviceConstants.SYS
            )  # Fix: Add missing device attribute
            mock_filter_sax.return_value = [mock_sax_item]

            await async_setup_entry(
                mock_hass_base, mock_config_entry_base, async_add_entities
            )

            # Verify logging occurred - fix: Check for any battery_a related logging
            mock_logger.info.assert_called()
            call_args_list = [str(call) for call in mock_logger.info.call_args_list]
            assert any(
                "battery_a" in args and "number entities" in args
                for args in call_args_list
            ), f"Expected battery_a logging, got: {call_args_list}"
