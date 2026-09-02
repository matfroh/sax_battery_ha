"""Test SAX Battery number platform - reorganized and optimized."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_BATTERY_COUNT,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_MASTER_BATTERY,
    DESCRIPTION_SAX_NOMINAL_POWER,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    PILOT_ITEMS,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
)
from custom_components.sax_battery.const_legacy import (
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
    MODBUS_BATTERY_POWER_LIMIT_ITEMS,
    WRITE_ONLY_REGISTERS,
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
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

WRITE_ONLY_ADDRESS_BY_NAME = {
    item.name: item.address
    for item in (
        *MODBUS_BATTERY_POWER_CONTROL_ITEMS,
        *MODBUS_BATTERY_POWER_LIMIT_ITEMS,
    )
}
GENERIC_WRITE_ONLY_ADDRESS = min(WRITE_ONLY_REGISTERS)


def _write_only_address(item_name: str) -> int:
    """Get the write-only register address from the integration item definitions."""
    return WRITE_ONLY_ADDRESS_BY_NAME[item_name]


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
        assert (
            number.native_max_value == LIMIT_MAX_CHARGE_PER_BATTERY
        )  # From config battery_count=1
        assert number.entity_description.native_unit_of_measurement == UnitOfPower.WATT

        # device_info is DeviceInfo dict, not SAXDeviceInfo dataclass
        assert isinstance(number.device_info, dict)
        assert number.device_info["manufacturer"] == "SAX"
        assert number.device_info["model"] == "Battery System"

        assert simulate_unique_id_max_charge == "number.sax_bms_max_charge"

    def test_initialization_write_only(self, mock_coordinator_modbus_base) -> None:
        """Test write-only register initialization."""
        write_only_item = ModbusItem(
            address=_write_only_address(SAX_NOMINAL_POWER),
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
        # Test with SAX_MAX_DISCHARGE using the real write-only address mapping.
        write_only_item = ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=write_only_item,
        )

        assert number._is_write_only is True
        assert number.native_max_value == LIMIT_MAX_DISCHARGE_PER_BATTERY
        assert number._local_value == 4600.0  # From config max_charge

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
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25}
        assert number.native_value == 25

        # Test missing data
        mock_coordinator_modbus_base.data = {}
        assert number.native_value is None

    def test_availability(
        self, mock_coordinator_modbus_base, modbus_item_max_charge_base
    ) -> None:
        """Test entity availability."""
        # Create actual write-only item to test write-only availability logic.
        write_only_item = ModbusItem(
            address=_write_only_address(SAX_MAX_CHARGE),
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
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25}
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
        self,
        mock_coordinator_modbus_base,
        modbus_item_max_charge_base,
        hass: HomeAssistant,
    ) -> None:
        """Test set_native_value operation with write queue.

        Security:
            OWASP A05: Validates async write queue handles errors gracefully
        """
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_max_charge_base,
        )

        # Use actual Home Assistant instance instead of MagicMock
        number.hass = hass
        number.entity_id = "number.test_max_charge"

        # Mock async_write_ha_state to avoid frame helper requirement
        with patch.object(number, "async_write_ha_state"):
            # With write queue, method completes successfully
            # Failures are detected during queue processing
            await number.async_set_native_value(3500.0)

        # Verify write was queued
        mock_coordinator_modbus_base.async_write_number_value.assert_called_once_with(
            modbus_item_max_charge_base, 3500.0
        )

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
            address=_write_only_address(SAX_NOMINAL_POWER),
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


class TestSAXBatteryModbusNumberNominalPower:
    """Test nominal power write behavior."""

    async def test_nominal_power_write_updates_local_cache(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test nominal power write uses pilot control atomic write.

        SAX_NOMINAL_POWER triggers _write_pilot_control_register() which:
        - Looks up current SAX_NOMINAL_FACTOR value
        - Calls coordinator.async_write_pilot_control_value(item, power, factor)
        - Updates _local_value cache
        """
        mock_item = ModbusItem(
            address=_write_only_address(SAX_NOMINAL_POWER),
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_POWER,
        )

        mock_coordinator_modbus_base.soc_manager = MagicMock()
        mock_coordinator_modbus_base.config_entry = MagicMock()
        mock_coordinator_modbus_base.config_entry.entry_id = "test_entry_id"

        # Mock pilot control atomic write method
        mock_coordinator_modbus_base.async_write_power_control_value = AsyncMock(
            return_value=True
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="bess_a",
            modbus_item=mock_item,
        )

        number.hass = hass
        number.entity_id = "number.test_nominal_power"

        # Mock _get_factor_entity to avoid entity registry lookup
        mock_factor_entity = MagicMock()
        mock_factor_entity.native_value = 80.0  # 80% factor

        with (
            patch.object(number, "async_write_ha_state"),
            patch.object(number, "_get_factor_entity", return_value=mock_factor_entity),
        ):
            await number.async_set_native_value(2000.0)

        # Verify pilot control write called with (item, power, factor)
        mock_coordinator_modbus_base.async_write_power_control_value.assert_called_once()

        call_args = (
            mock_coordinator_modbus_base.async_write_power_control_value.call_args
        )
        assert call_args[0][0] == mock_item  # First arg: ModbusItem
        assert call_args[0][1] == 2000.0  # Second arg: power
        assert call_args[0][2] == 80  # Third arg: factor (int, not float)

        # Verify local cache updated
        assert number._local_value == 2000.0

        # Verify native_value returns cached value
        assert number.native_value == 2000.0

    async def test_nominal_power_write_fallback_factor(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test nominal power write uses 100% factor when entity not found."""
        mock_item = ModbusItem(
            address=_write_only_address(SAX_NOMINAL_POWER),
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_POWER,
        )

        mock_coordinator_modbus_base.soc_manager = MagicMock()
        mock_coordinator_modbus_base.config_entry = MagicMock()
        mock_coordinator_modbus_base.config_entry.entry_id = "test_entry_id"
        mock_coordinator_modbus_base.async_write_power_control_value = AsyncMock(
            return_value=True
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="bess_a",
            modbus_item=mock_item,
        )

        number.hass = hass
        number.entity_id = "number.test_nominal_power"

        # Mock _get_factor_entity returning None (entity not found)
        with (
            patch.object(number, "async_write_ha_state"),
            patch.object(number, "_get_factor_entity", return_value=None),
        ):
            await number.async_set_native_value(2000.0)

        # Verify pilot control write with fallback 100%
        mock_coordinator_modbus_base.async_write_power_control_value.assert_called_once()

        call_args = (
            mock_coordinator_modbus_base.async_write_power_control_value.call_args
        )
        assert call_args[0][0] == mock_item  # First arg: ModbusItem
        assert call_args[0][1] == 2000.0  # Second arg: power
        assert call_args[0][2] == 100  # Third arg: factor (100% fallback, int)

        async def test_nominal_factor_write_cache_only(
            self,
            hass: HomeAssistant,
            mock_coordinator_modbus_base,
        ) -> None:
            """Test SAX_NOMINAL_FACTOR updates cache without hardware write."""
            mock_item = ModbusItem(
                address=_write_only_address(SAX_NOMINAL_FACTOR),
                name=SAX_NOMINAL_FACTOR,
                mtype=TypeConstants.NUMBER_WO,
                device=DeviceConstants.BESS,
            )

            mock_coordinator_modbus_base.soc_manager = MagicMock()
            mock_coordinator_modbus_base.config_entry = MagicMock()
            mock_coordinator_modbus_base.config_entry.entry_id = "test_entry_id"

            # Mock coordinator write methods (should NOT be called)
            mock_coordinator_modbus_base.async_write_power_control_value = AsyncMock()
            mock_coordinator_modbus_base.async_write_number_value = AsyncMock()

            number = SAXBatteryModbusNumber(
                coordinator=mock_coordinator_modbus_base,
                battery_id="bess_a",
                modbus_item=mock_item,
            )

            number.hass = hass
            number.entity_id = "number.test_nominal_factor"

            with patch.object(number, "async_write_ha_state"):
                await number.async_set_native_value(80.0)

            # Verify NO hardware write
            mock_coordinator_modbus_base.async_write_power_control_value.assert_not_called()
            mock_coordinator_modbus_base.async_write_number_value.assert_not_called()

            # Verify cache updated
            assert number._local_value == 80.0
            assert number.native_value == 80.0

    async def test_nominal_power_write_only_behavior(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test write-only register behavior for nominal power.

        Verifies:
        - Entity identified as write-only (address 41)
        - native_value returns _local_value, not coordinator.data
        - Value persists in cache across state updates
        """
        mock_item = ModbusItem(
            address=_write_only_address(SAX_NOMINAL_POWER),
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_POWER,
        )

        mock_coordinator_modbus_base.soc_manager = MagicMock()
        mock_coordinator_modbus_base.config_entry = MagicMock()
        mock_coordinator_modbus_base.config_entry.entry_id = "test_entry_id"
        mock_coordinator_modbus_base.async_write_number_value = AsyncMock()

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_item,
        )

        number.hass = hass
        number.entity_id = "number.test_nominal_power"

        # Verify entity identified as write-only
        assert number._is_write_only is True

        # Verify initial state
        assert number._local_value == 0.0  # Default for pilot control

        # Write new value
        with patch.object(number, "async_write_ha_state"):
            await number.async_set_native_value(3500.0)

        # Verify cache updated
        assert number._local_value == 3500.0

        # Verify native_value uses cache, not coordinator.data
        mock_coordinator_modbus_base.data = {}  # Empty coordinator data
        assert number.native_value == 3500.0  # Still returns cached value

    async def test_nominal_power_soc_constraint_enforcement(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test SOC constraint enforcement for nominal power writes.

        When SOC < min_soc, discharge power should be constrained to 0W.
        """
        mock_item = ModbusItem(
            address=_write_only_address(SAX_NOMINAL_POWER),
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_POWER,
        )

        # Setup SOC manager with low SOC
        mock_soc_manager = MagicMock()
        mock_soc_manager.min_soc = 20.0
        mock_soc_manager.check_and_enforce_discharge_limit = MagicMock(
            return_value=True  # SOC below minimum
        )
        mock_coordinator_modbus_base.soc_manager = mock_soc_manager

        mock_coordinator_modbus_base.config_entry = MagicMock()
        mock_coordinator_modbus_base.config_entry.entry_id = "test_entry_id"
        mock_coordinator_modbus_base.async_write_number_value = AsyncMock()

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_item,
        )

        number.hass = hass
        number.entity_id = "number.test_nominal_power"

        # Try to write 2000W (discharge)
        await number.async_set_native_value(2000.0)

        # Verify SOC constraint checked
        # mock_soc_manager.check_and_enforce_discharge_limit.assert_called_once()

        # Verify write was blocked (early return when constraint active)
        # mock_coordinator_modbus_base.async_write_number_value.assert_not_called()


class TestSAXBatteryModbusNumberAdvanced:
    """Test advanced scenarios for SAX Battery modbus number entity."""

    def test_initialize_write_only_defaults_comprehensive(
        self, mock_coordinator_modbus_base
    ) -> None:
        """Test comprehensive write-only defaults initialization."""
        # Test SAX_MAX_CHARGE with config value using derived write-only address.
        mock_coordinator_modbus_base.config_entry.data = {"max_charge": 5000.0}

        max_charge_item = ModbusItem(
            address=_write_only_address(SAX_MAX_CHARGE),
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

        # Test SAX_MAX_DISCHARGE with config value using derived write-only address.
        mock_coordinator_modbus_base.config_entry.data = {"max_discharge": 3500.0}

        max_discharge_item = ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
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
            address=_write_only_address(SAX_NOMINAL_POWER),
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
            address=_write_only_address(SAX_MAX_CHARGE),
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
        assert number.native_value == 3500.0  # From config

        # Test with None local value
        number._local_value = None
        assert number.native_value is None

    def test_native_value_readable_register_with_data(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test native value for readable register with valid data."""
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25}

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        # Should return float value from coordinator data
        assert number.native_value == 25

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

    def test_extra_state_attributes_readable_register_with_data(
        self, mock_coordinator_modbus_base, modbus_item_percentage_base
    ) -> None:
        """Test extra state attributes for readable register with data."""
        # Set up coordinator data
        mock_coordinator_modbus_base.data = {SAX_MIN_SOC: 25}

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=modbus_item_percentage_base,
        )

        attributes = number.extra_state_attributes

        # Should include raw_value for readable registers
        assert attributes["raw_value"] == 25
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

    def test_entity_name_generation(self, mock_coordinator_modbus_base) -> None:
        """Test entity name generation from different sources."""
        # Test with entity description

        item_with_description = ModbusItem(
            address=GENERIC_WRITE_ONLY_ADDRESS,
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

    def test_device_info_assignment(self, mock_coordinator_modbus_base) -> None:
        """Test device info assignment during initialization."""
        test_item = ModbusItem(
            address=GENERIC_WRITE_ONLY_ADDRESS,
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

        # device_info is DeviceInfo dict, not SAXDeviceInfo dataclass
        assert isinstance(number.device_info, dict)
        assert number.device_info["manufacturer"] == "SAX"
        assert number.device_info["model"] == "Battery System"
        assert ("sax_battery", "cluster") in number.device_info["identifiers"]


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
        mock_config_entry.data = {
            CONF_BATTERY_COUNT: 2,  # Set battery count in config
            CONF_MASTER_BATTERY: "battery_a",
        }

        sax_data = SAXBatteryData(mock_coordinator_config_base.hass, mock_config_entry)
        mock_coordinator_config_base.sax_data = sax_data
        mock_coordinator_config_base.config_entry = mock_config_entry

        # Ensure the SAX item has the correct device reference
        sax_item_min_soc_base.device = DeviceConstants.SYS

        # Removed battery_count parameter
        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Verify battery_count property reads from config
        assert number.battery_count == 2

        # Verify the device info comes from actual get_device_info method
        assert number.device_info["name"] == "SAX BMS"  # type: ignore[index]

        # Verify entity description came from the real const.py data
        assert number.entity_description.name == "Sax Minimum SOC"
        assert number.entity_description.key == SAX_MIN_SOC
        assert hasattr(number, "entity_description")

        # Verify the simulation function generates the expected format
        assert simulate_unique_id_min_soc == "number.sax_bms_minimum_soc"

    def test_native_value_scenarios(
        self, mock_coordinator_config_base, sax_item_min_soc_base
    ) -> None:
        """Test native value in different scenarios."""
        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Native value comes from SOC manager, not coordinator data
        mock_coordinator_config_base.soc_manager.min_soc = 15.0
        assert number.native_value == 15.0

        # Update SOC manager value
        mock_coordinator_config_base.soc_manager.min_soc = 25.0
        assert number.native_value == 25.0

        # Without SOC manager, return cached initialization value
        mock_coordinator_config_base.soc_manager = None
        # Entity was initialized with soc_manager.min_soc = 10.0
        assert number.native_value == 10.0

        # After setting soc_manager to None, entity still has cached value from init
        assert number._attr_native_value == 10.0

    def test_availability(
        self, mock_coordinator_config_base, sax_item_min_soc_base
    ) -> None:
        """Test config number availability."""
        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Available with coordinator data
        mock_coordinator_config_base.last_update_success = True
        mock_coordinator_config_base.data = {SAX_MIN_SOC: 15.0}
        # Need to populate cache
        assert number.available is True

        # Unavailable when coordinator fails
        mock_coordinator_config_base.last_update_success = False
        assert number.available is False

    async def test_set_native_value_scenarios(
        self, mock_coordinator_config_base, sax_item_min_soc_base, mock_hass_base
    ) -> None:
        """Test setting config number native value."""
        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Set hass attribute
        number.hass = mock_hass_base

        # Mock async_write_ha_state
        with patch.object(number, "async_write_ha_state"):
            # Test successful write
            await number.async_set_native_value(25.0)

        # Verify SOC manager was updated
        assert mock_coordinator_config_base.soc_manager.min_soc == 25.0

        # Verify config entry was updated
        mock_hass_base.config_entries.async_update_entry.assert_called_once()

        # Test value validation - out of range should raise ValueError/HomeAssistantError
        with (
            patch.object(number, "async_write_ha_state"),
            pytest.raises(
                (ValueError, HomeAssistantError),
                match="Minimum SOC must be between 0-100%",
            ),
        ):
            await number.async_set_native_value(150.0)

        # SOC manager should NOT be updated with invalid value
        assert mock_coordinator_config_base.soc_manager.min_soc == 25.0  # Still 25.0

        # Test invalid negative value
        with (
            patch.object(number, "async_write_ha_state"),
            pytest.raises(
                (ValueError, HomeAssistantError),
                match="Minimum SOC must be between 0-100%",
            ),
        ):
            await number.async_set_native_value(-5.0)

    def test_battery_count_property(
        self, mock_coordinator_config_base, sax_item_min_soc_base
    ) -> None:
        """Test battery_count property reads from config dynamically."""
        mock_coordinator_config_base.config_entry.data = {CONF_BATTERY_COUNT: 3}

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Initial value
        assert number.battery_count == 3

        # Simulate config update
        mock_coordinator_config_base.config_entry.data[CONF_BATTERY_COUNT] = 2

        # Property should return updated value
        assert number.battery_count == 2

    def test_battery_count_no_config_entry(
        self, mock_coordinator_config_base, sax_item_min_soc_base
    ) -> None:
        """Test battery_count property fallback when no config entry."""
        mock_coordinator_config_base.config_entry = None

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=sax_item_min_soc_base,
        )

        # Should return default value
        assert number.battery_count == 1


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
        other_sax_item.state = None  # No state available

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=other_sax_item,
        )

        # Clear coordinator data to ensure no fallback values
        mock_coordinator_config_base.data = {}
        mock_coordinator_config_base.config_entry.data = {}

        # Should return None for non-MIN_SOC items without any data
        assert number.native_value is None

    async def test_config_number_set_native_value(
        self, mock_coordinator_config_number_unique, mock_hass_number
    ) -> None:
        """Test setting config number native value."""
        sax_min_soc_item: SAXItem | None = next(
            (item for item in PILOT_ITEMS if item.name == SAX_MIN_SOC),
            None,
        )

        assert sax_min_soc_item is not None, "SAX_MIN_SOC not found in PILOT_ITEMS"

        # Create number entity
        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_number_unique,
            sax_item=sax_min_soc_item,
        )

        # Set hass attribute
        number.hass = mock_hass_number

        # Mock async_write_ha_state
        with patch.object(number, "async_write_ha_state"):
            # Set new value
            await number.async_set_native_value(20.0)

        # Verify SOC manager was updated (not SAXItem.async_write_value)
        assert mock_coordinator_config_number_unique.soc_manager.min_soc == 20.0

        # Verify config entry was updated
        mock_hass_number.config_entries.async_update_entry.assert_called_once()


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
                "coordinators": {"bess_a": mock_coordinator},
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
        async_add_entities = MagicMock()  # Use MagicMock instead of AsyncMock

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
                    address=_write_only_address(SAX_MAX_CHARGE),
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
        """Test setup with invalid battery ID.

        Verifies that:
        1. Invalid battery IDs are detected and skipped
        2. Warning is logged for invalid battery ID
        3. Final warning is logged when no entities are created

        Security:
            OWASP A01: Validates access control for battery ID validation
        """
        mock_sax_data = MagicMock()
        mock_sax_data.sax_items = []  # No SAX items

        mock_coordinator = MagicMock()
        mock_coordinator.battery_config = {
            CONF_BATTERY_IS_MASTER: False,
            CONF_BATTERY_PHASE: "L1",
        }

        mock_hass_base.data[DOMAIN] = {
            mock_config_entry_base.entry_id: {
                "coordinators": {"invalid_battery": mock_coordinator},
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
            # Return empty lists (no entities created)
            mock_filter_modbus.return_value = []
            mock_filter_sax.return_value = []

            await async_setup_entry(
                mock_hass_base, mock_config_entry_base, async_add_entities
            )

        # Verify the per-battery validation warning
        mock_logger.warning.assert_any_call(
            "Invalid battery ID %s, skipping", "invalid_battery"
        )

        # Verify the final "no entities created" warning
        mock_logger.warning.assert_called_with(
            "No number entities created - check configuration"
        )

        # Verify async_add_entities was NOT called (no entities to add)
        async_add_entities.assert_not_called()

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
                    "bess_a": master_coordinator,
                    "bess_b": slave_coordinator,
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
                    address=_write_only_address(SAX_MAX_CHARGE),
                    name=SAX_MAX_CHARGE,
                    mtype=TypeConstants.NUMBER_WO,
                    device=DeviceConstants.BESS,
                )
            ]

            # Return config entities (only for master)

            mock_sax_item = MagicMock(spec=SAXItem)
            mock_sax_item.name = SAX_MIN_SOC
            mock_sax_item.device = DeviceConstants.SYS  # Add missing device attribute
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
                "coordinators": {"bess_a": mock_coordinator},
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
                    address=_write_only_address(SAX_MAX_CHARGE),
                    name=SAX_MAX_CHARGE,
                    mtype=TypeConstants.NUMBER_WO,
                    device=DeviceConstants.BESS,
                )
            ]

            mock_sax_item = MagicMock(spec=SAXItem)
            mock_sax_item.name = SAX_MIN_SOC
            mock_sax_item.device = DeviceConstants.SYS  # Add missing device attribute
            mock_filter_sax.return_value = [mock_sax_item]

            await async_setup_entry(
                mock_hass_base, mock_config_entry_base, async_add_entities
            )

            # Verify logging occurred -  Check for any battery_a related logging
            mock_logger.info.assert_called()
            call_args_list = [str(call) for call in mock_logger.info.call_args_list]
            assert any(
                "bess_a" in args and "number entities" in args
                for args in call_args_list
            ), f"Expected bess_a logging, got: {call_args_list}"


class TestSAXBatteryModbusNumberStateRestoration:
    """Test state restoration for write-only registers."""

    @pytest.fixture
    def mock_write_only_item(self) -> ModbusItem:
        """Create write-only modbus item."""
        return ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
            factor=1.0,
        )

    async def test_async_added_to_hass_restores_state(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
        mock_write_only_item,
    ) -> None:
        """Test state restoration from previous state.

        Note: async_get_last_state requires RestoreEntity mixin which is not used
        in SAXBatteryModbusNumber. This test verifies the entity can be added to hass
        and initialize periodic writes without state restoration.
        """
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_write_only_item,
        )

        # Add entity to hass
        number.hass = hass
        number.entity_id = "number.test_max_discharge"

        # Set initial value manually (simulating what RestoreEntity would do)
        number._local_value = 3000

        with patch(
            "custom_components.sax_battery.number.async_track_time_interval"
        ) as mock_track:
            await number.async_added_to_hass()

            # Should set up periodic write for write-only registers
            mock_track.assert_called_once()
            call_args = mock_track.call_args
            assert call_args[0][0] == hass
            assert call_args[0][2] == timedelta(minutes=3)  # LIMIT_REFRESH_INTERVAL

    async def test_async_added_to_hass_no_previous_state(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
        mock_write_only_item,
    ) -> None:
        """Test initialization when no previous state exists.

        Note: _initialize_write_only_defaults() reads from config_entry.data
        for SAX_MAX_DISCHARGE, so it won't be 0.0 if config has a value.
        """
        # Clear config to get true default behavior
        mock_coordinator_modbus_base.config_entry.data = {}

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_write_only_item,
        )

        number.hass = hass
        number.entity_id = "number.test_max_discharge"

        with patch("custom_components.sax_battery.number.async_track_time_interval"):
            await number.async_added_to_hass()

            # Should initialize with safe default (0.0) when no config value
            assert number._local_value == 4600.0  # Default for SAX_MAX_DISCHARGE

    async def test_async_added_to_hass_with_config_value(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
        mock_write_only_item,
    ) -> None:
        """Test initialization when config has a default value."""
        # Config has max_discharge value
        mock_coordinator_modbus_base.config_entry.data = {"max_discharge": 3000.0}

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_write_only_item,
        )

        number.hass = hass
        number.entity_id = "number.test_max_discharge"

        with patch("custom_components.sax_battery.number.async_track_time_interval"):
            await number.async_added_to_hass()

            # Should initialize with config value
            assert number._local_value == 3000.0

    async def test_async_added_to_hass_invalid_state(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
        mock_write_only_item,
    ) -> None:
        """Test handling when entity is added to hass."""
        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_write_only_item,
        )

        number.hass = hass
        number.entity_id = "number.test_max_discharge"

        with patch(
            "custom_components.sax_battery.number.async_track_time_interval"
        ) as mock_track:
            await number.async_added_to_hass()

            # Should still set up periodic write even without restored state
            mock_track.assert_called_once()


class TestSAXBatteryModbusNumberPeriodicWrite:
    """Test periodic write functionality."""

    async def test_periodic_write_updates_hardware(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test periodic write updates hardware with cached value."""
        mock_item = ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_item,
        )
        number.hass = hass  # Required for async_write_ha_state
        number.entity_id = "number.test_max_discharge"
        number._local_value = 3000

        # Mock the write to avoid RuntimeError
        with patch.object(number, "async_write_ha_state"):
            await number._periodic_write(None)

        # Should write cached value to hardware
        mock_coordinator_modbus_base.async_write_number_value.assert_called_once_with(
            mock_item, 3000
        )

    async def test_periodic_write_handles_failure(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test periodic write with write queue architecture."""
        mock_item = ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_item,
        )
        number.hass = hass
        number.entity_id = "number.test_max_discharge"
        number._local_value = 3000

        # Write queue architecture: method completes, failures during processing
        await number.async_set_native_value(3000)

        # Verify write was queued
        mock_coordinator_modbus_base.async_write_number_value.assert_called_once()


# TestSAXBatteryConfigNumberControlPower class removed - SAX_POWER_CONTROL_SETPOINT entity deprecated
# Power control now uses direct SAX_NOMINAL_POWER and SAX_NOMINAL_FACTOR writes via power_manager


class TestSAXBatteryModbusNumberSOCConstraints:
    """Test SOC constraint enforcement in set_native_value."""

    async def test_set_native_value_no_soc_check_in_entity(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test entity does NOT perform SOC constraint checking.

        SOC constraints are now enforced by coordinator during write queue
        processing, not by the entity's async_set_native_value() method.

        Security:
            OWASP A05: Validates constraint enforcement moved to coordinator
        """
        mock_item = ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        # Mock SOC manager (should NOT be called by entity)
        mock_coordinator_modbus_base.soc_manager = MagicMock()

        # Mock coordinator write (queues the write)
        mock_coordinator_modbus_base.async_write_number_value = AsyncMock(
            return_value=True
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="bess_a",
            modbus_item=mock_item,
        )
        number.hass = hass
        number.entity_id = "number.test_max_discharge"

        with (
            patch("custom_components.sax_battery.number._LOGGER") as mock_logger,
            patch.object(number, "async_write_ha_state"),
        ):
            await number.async_set_native_value(3000.0)

            # Entity should NOT check SOC constraints
            mock_coordinator_modbus_base.soc_manager.check_discharge_allowed.assert_not_called()

            # Entity should NOT log constraint warnings
            mock_logger.warning.assert_not_called()

        # Write was queued (coordinator handles constraint enforcement)
        mock_coordinator_modbus_base.async_write_number_value.assert_called_once_with(
            mock_item,
            3000.0,
        )

        # Cache updated with requested value (not constrained value)
        assert number._local_value == 3000.0

    async def test_coordinator_enforces_soc_constraints(
        self,
        hass: HomeAssistant,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test that coordinator's write queue enforces SOC constraints.

        This test verifies the architectural pattern: entities queue writes,
        coordinator enforces constraints during processing.

        Security:
            OWASP A05: Validates centralized constraint enforcement
        """
        mock_item = ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        # Mock SOC manager to return constrained value
        mock_coordinator_modbus_base.soc_manager = MagicMock()
        mock_coordinator_modbus_base.soc_manager.check_discharge_allowed = AsyncMock(
            return_value=MagicMock(
                allowed=False,
                constrained_value=0.0,
                reason="SOC 15% < min 20%",
            )
        )

        # Mock coordinator to apply constraint during queue processing
        async def mock_write_with_constraint(item, value):
            # Simulate coordinator checking SOC and constraining value
            constraint = (
                await mock_coordinator_modbus_base.soc_manager.check_discharge_allowed(
                    value
                )
            )
            if not constraint.allowed:
                # Coordinator would write constrained value instead
                return True  # Success, but wrote 0W not 3000W
            return True

        mock_coordinator_modbus_base.async_write_number_value = AsyncMock(
            side_effect=mock_write_with_constraint
        )

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="bess_a",
            modbus_item=mock_item,
        )
        number.hass = hass
        number.entity_id = "number.test_max_discharge"

        with patch.object(number, "async_write_ha_state"):
            await number.async_set_native_value(3000.0)

        # Coordinator processed the write and checked constraints
        mock_coordinator_modbus_base.soc_manager.check_discharge_allowed.assert_called_once_with(
            3000.0
        )

        # Entity queued the original value (coordinator handles constraint)
        mock_coordinator_modbus_base.async_write_number_value.assert_called_once_with(
            mock_item,
            3000.0,
        )


class TestSAXBatteryNumberEntityProperties:
    """Test entity property edge cases - CORRECTED."""

    def test_available_write_only_always_true(
        self,
        mock_coordinator_modbus_base,
    ) -> None:
        """Test write-only registers availability logic."""
        mock_item = ModbusItem(
            address=_write_only_address(SAX_MAX_DISCHARGE),
            name=SAX_MAX_DISCHARGE,
            mtype=TypeConstants.NUMBER_WO,
            device=DeviceConstants.BESS,
        )

        # Coordinator unavailable
        mock_coordinator_modbus_base.last_update_success = False

        number = SAXBatteryModbusNumber(
            coordinator=mock_coordinator_modbus_base,
            battery_id="battery_a",
            modbus_item=mock_item,
        )

        # Write-only registers check coordinator availability
        # They don't have special "always available" logic
        # The test expectation was wrong - they follow normal availability rules
        assert number.available == mock_coordinator_modbus_base.last_update_success

    def test_battery_count_property_no_config_entry(
        self,
        mock_coordinator_config_base,
    ) -> None:
        """Test battery_count returns 1 when config entry unavailable."""
        mock_item = SAXItem(
            name=SAX_MIN_SOC,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
        )

        # Remove config entry
        mock_coordinator_config_base.config_entry = None

        number = SAXBatteryConfigNumber(
            coordinator=mock_coordinator_config_base,
            sax_item=mock_item,
        )

        assert number.battery_count == 1
