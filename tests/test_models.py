"""Test models for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.sax_battery.const import (
    SAX_CAPACITY,
    SAX_CHARGE_POWER,
    SAX_COMBINED_SOC,
    SAX_DISCHARGE_POWER,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MAX_SOC,
    SAX_MIN_SOC,
    SAX_POWER,
    SAX_SMARTMETER_CURRENT_L1,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SOC,
)
from custom_components.sax_battery.const_legacy import MODBUS_BATTERY_POWER_LIMIT_ITEMS
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.models import BatteryModel, SAXBatteryData
from custom_components.sax_battery.protocol_mode import ProtocolMode


class TestBatteryModel:
    """Test BatteryModel functionality."""

    def test_battery_model_initialization(self, battery_model_data_basic) -> None:
        """Test BatteryModel initialization."""
        battery = BatteryModel(**battery_model_data_basic)

        assert battery.device_id == "bess_a"
        assert battery.name == "SAX Battery A"
        assert battery.host == "192.168.1.100"
        assert battery.port == 502
        assert battery.is_master is True

    def test_battery_model_data_operations(self, battery_model_data_basic) -> None:
        """Test BatteryModel data operations."""
        battery = BatteryModel(
            device_id=battery_model_data_basic["device_id"],
            name=battery_model_data_basic["name"],
        )

        # Test setting and getting values
        battery.set_value("soc", 85.5)
        battery.set_value("power", 1500)

        assert battery.get_value("soc") == 85.5
        assert battery.get_value("power") == 1500
        assert battery.get_value("nonexistent") is None

    def test_battery_model_modbus_items_master(
        self, mock_config_entry_pilot_enabled
    ) -> None:
        """Test BatteryModel modbus items for master battery."""
        battery = BatteryModel(
            device_id="bess_a",
            name="SAX Battery A",
            is_master=True,
            config_data=mock_config_entry_pilot_enabled.data,
        )

        modbus_items = battery.get_modbus_items()

        # Master battery should have basic items
        assert len(modbus_items) > 0

        # Check for system items (adjusted expectation based on actual implementation)
        system_items = [
            item for item in modbus_items if item.device == DeviceConstants.BESS
        ]
        assert len(system_items) > 0

    def test_battery_model_modbus_items_slave(self, battery_model_data_slave) -> None:
        """Test BatteryModel modbus items for slave battery."""
        battery = BatteryModel(
            **battery_model_data_slave,
            config_data={"control_power": False, "limit_power": False},
        )

        modbus_items = battery.get_modbus_items()

        # Slave battery should have basic items only
        assert len(modbus_items) > 0

        # Should not include smart meter items for slave
        smart_meter_items = [
            item
            for item in modbus_items
            if item.device == DeviceConstants.BESS and "smartmeter" in item.name.lower()
        ]
        assert len(smart_meter_items) == 0

    def test_battery_model_sax_items_master(self, battery_model_data_basic) -> None:
        """Test BatteryModel SAX items for master battery."""
        # Ensure control_power is enabled to generate SAX items
        battery_model_data_basic["config_data"] = {
            "control_power": True,
            "limit_power": True,
        }
        battery = BatteryModel(**battery_model_data_basic)

        sax_items = battery.get_sax_items()

        # Master battery should have aggregated items when pilot is enabled
        assert len(sax_items) > 0

        # Check for calculated sensor items (more common than NUMBER items)
        calc_items = [
            item for item in sax_items if item.mtype == TypeConstants.SENSOR_CALC
        ]
        assert len(calc_items) > 0

    def test_battery_model_sax_items_slave(self, battery_model_data_slave) -> None:
        """Test BatteryModel SAX items for slave battery."""
        battery = BatteryModel(**battery_model_data_slave)

        sax_items = battery.get_sax_items()

        # Slave battery should have no SAX items
        assert len(sax_items) == 0


class TestSAXBatteryData:
    """Test SAXBatteryData functionality."""

    def test_sax_battery_data_initialization(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test SAXBatteryData initialization."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        assert len(sax_data.batteries) == 2
        assert "bess_a" in sax_data.batteries
        assert "bess_b" in sax_data.batteries
        assert sax_data.master_battery_id == "bess_a"

    def test_sax_battery_data_battery_configuration(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test battery configuration in SAXBatteryData."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        battery_a = sax_data.batteries["bess_a"]
        battery_b = sax_data.batteries["bess_b"]

        assert battery_a.is_master is True
        assert battery_b.is_master is False
        assert battery_a.host == "192.168.1.100"
        assert battery_b.host == "192.168.1.101"

    def test_sax_battery_data_get_modbus_items_for_battery(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test get_modbus_items_for_battery method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Master battery should have items
        master_items = sax_data.get_modbus_items_for_battery("bess_a")
        assert len(master_items) > 0

        # Slave battery should have items
        slave_items = sax_data.get_modbus_items_for_battery("bess_b")
        assert len(slave_items) > 0

        # Non-existent battery should return empty list
        nonexistent_items = sax_data.get_modbus_items_for_battery("bess_z")
        assert len(nonexistent_items) == 0

    def test_sax_battery_data_get_modbus_items_for_battery_sunspec_master(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """SunSpec mode should merge in SunSpec-backed items for the master battery."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)
        sax_data.coordinators = {
            "bess_a": MagicMock(protocol_mode=ProtocolMode.SUNSPEC)
        }

        master_items = sax_data.get_modbus_items_for_battery("bess_a")
        item_names = {item.name for item in master_items}

        assert SAX_SOC in item_names
        assert SAX_POWER in item_names
        assert SAX_CAPACITY in item_names

        item_by_name = {item.name: item for item in master_items}
        assert item_by_name[SAX_SMARTMETER_CURRENT_L1].address == 40057
        assert item_by_name[SAX_SMARTMETER_TOTAL_POWER].address == 40072
        assert item_by_name[SAX_CAPACITY].address == 40097
        assert item_by_name[SAX_CHARGE_POWER].address == 40098
        assert item_by_name[SAX_DISCHARGE_POWER].address == 40099
        assert item_by_name[SAX_MAX_SOC].address == 40100
        assert item_by_name[SAX_SOC].address == 40102

    def test_sax_battery_data_get_modbus_items_for_battery_string_sunspec_mode(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """String-based SunSpec mode should merge canonical SunSpec items."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)
        sax_data.coordinators = {"bess_a": MagicMock(protocol_mode="sunspec")}

        master_items = sax_data.get_modbus_items_for_battery("bess_a")
        item_names = {item.name for item in master_items}

        assert SAX_SOC in item_names
        assert SAX_POWER in item_names
        assert SAX_CAPACITY in item_names

    def test_sax_battery_data_get_modbus_items_for_battery_sunspec_slave(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """SunSpec mode should not add master-only extended items to slave batteries."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)
        sax_data.coordinators = {
            "bess_b": MagicMock(protocol_mode=ProtocolMode.SUNSPEC)
        }

        slave_items = sax_data.get_modbus_items_for_battery("bess_b")
        item_names = {item.name for item in slave_items}

        assert SAX_SOC in item_names
        assert SAX_POWER in item_names
        assert SAX_CAPACITY not in item_names

    def test_sax_battery_data_get_sax_items_for_battery(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test get_sax_items_for_battery method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Master battery should have SAX items
        master_sax_items = sax_data.get_sax_items_for_battery("bess_a")
        assert len(master_sax_items) > 0

        # Slave battery should have no SAX items
        slave_sax_items = sax_data.get_sax_items_for_battery("bess_b")
        assert len(slave_sax_items) == 0

        # Non-existent battery should return empty list
        nonexistent_sax_items = sax_data.get_sax_items_for_battery("bess_z")
        assert len(nonexistent_sax_items) == 0

    def test_sax_battery_data_get_device_info(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test get_device_info method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        device_info_a = sax_data.get_device_info("bess_a", device=DeviceConstants.BESS)
        assert device_info_a.get("identifiers") == {("sax_battery", "bess_a")}
        assert device_info_a.get("name") == "SAX BESS A"

        device_info_b = sax_data.get_device_info("bess_b", DeviceConstants.BESS)
        assert device_info_b.get("identifiers") == {("sax_battery", "bess_b")}
        assert device_info_b.get("name") == "SAX BESS B"

    def test_sax_battery_data_single_battery(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test SAXBatteryData with single battery configuration."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        assert len(sax_data.batteries) == 1
        assert "bess_a" in sax_data.batteries
        assert sax_data.master_battery_id == "bess_a"
        assert sax_data.batteries["bess_a"].is_master is True

    def test_sax_battery_data_with_pilot_enabled(
        self, mock_hass, mock_config_entry_pilot_enabled
    ) -> None:
        """Test SAXBatteryData with pilot features enabled."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_pilot_enabled)

        assert len(sax_data.batteries) == 1
        assert sax_data.master_battery_id == "bess_a"

        # Master battery should have pilot-related items
        master_sax_items = sax_data.get_sax_items_for_battery("bess_a")
        assert len(master_sax_items) > 0

        # Check for calculated sensor items (these are more common in SAX items)
        calc_sensors = [
            item for item in master_sax_items if item.mtype == TypeConstants.SENSOR_CALC
        ]
        assert len(calc_sensors) > 0

    def test_sax_battery_data_master_slave_separation(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test proper master/slave separation in SAXBatteryData."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Master battery items
        master_modbus_items = sax_data.get_modbus_items_for_battery("bess_a")
        master_sax_items = sax_data.get_sax_items_for_battery("bess_a")

        # Slave battery items
        slave_modbus_items = sax_data.get_modbus_items_for_battery("bess_b")
        slave_sax_items = sax_data.get_sax_items_for_battery("bess_b")

        # Master should have more items including system-wide items
        assert len(master_modbus_items) >= len(slave_modbus_items)

        # Master should have SAX items, slave should not
        assert len(master_sax_items) > 0
        assert len(slave_sax_items) == 0

    def test_sax_battery_data_device_info_consistency(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test device info consistency across batteries."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Test device info for both batteries
        device_info_a = sax_data.get_device_info("bess_a", device=DeviceConstants.BESS)
        device_info_b = sax_data.get_device_info("bess_b", device=DeviceConstants.BESS)

        # Both should have consistent structure
        for device_info in [device_info_a, device_info_b]:
            assert "identifiers" in device_info
            assert "name" in device_info
            assert "manufacturer" in device_info
            assert device_info["manufacturer"] == "SAX"

        # Should have unique identifiers
        assert device_info_a.get("identifiers") != device_info_b.get("identifiers")
        assert device_info_a.get("name") != device_info_b.get("name")

    def test_sax_battery_data_empty_battery_handling(self, mock_hass) -> None:
        """Test SAXBatteryData handling of empty battery configuration."""
        # Create config entry with no batteries
        entry = MagicMock()
        entry.data = {
            "battery_count": 0,
            "master_battery": "",
        }

        sax_data = SAXBatteryData(mock_hass, entry)

        assert len(sax_data.batteries) == 0
        assert sax_data.master_battery_id is None

        # Should handle requests for non-existent batteries gracefully
        assert len(sax_data.get_modbus_items_for_battery("any_battery")) == 0
        assert len(sax_data.get_sax_items_for_battery("any_battery")) == 0


class TestSAXBatteryDataGetUniqueId:
    """Test SAXBatteryData.get_unique_id_for_item method."""

    async def test_get_unique_id_wo_registers_cluster_device(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation for WO registers with cluster device.

        WO registers (SAX_MAX_DISCHARGE, SAX_MAX_CHARGE) use master battery for
        hardware communication but are assigned to cluster device (DeviceConstants.SYS).

        Security:
            OWASP A01: Validates proper unique ID generation for system-level entities
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Test SAX_MAX_DISCHARGE (WO register with SYS device)
        max_discharge_item = next(
            (
                item
                for item in MODBUS_BATTERY_POWER_LIMIT_ITEMS
                if item.name == SAX_MAX_DISCHARGE
            ),
            None,
        )
        assert max_discharge_item is not None
        assert max_discharge_item.device == DeviceConstants.SYS

        unique_id = sax_data.get_unique_id_for_item(
            max_discharge_item,
            battery_id="bess_a",  # Uses master battery for Modbus
        )

        # WO registers use cluster device name regardless of battery_id
        assert unique_id == "sax_bms_max_discharge"

    async def test_get_unique_id_wo_registers_all_items(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation for all WO register items.

        Security:
            OWASP A03: Validates consistent unique ID generation for all power limit items
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        expected_unique_ids = {
            SAX_MAX_DISCHARGE: "sax_bms_max_discharge",
            SAX_MAX_CHARGE: "sax_bms_max_charge",
        }

        for item in MODBUS_BATTERY_POWER_LIMIT_ITEMS:
            unique_id = sax_data.get_unique_id_for_item(
                item,
                battery_id="bess_a",
            )

            assert unique_id == expected_unique_ids[item.name], (
                f"Failed for {item.name}: expected {expected_unique_ids[item.name]}, "
                f"got {unique_id}"
            )

    async def test_get_unique_id_per_battery_sensor(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test unique ID generation for per-battery sensor (SAX_POWER).

        Per-battery sensors use battery-specific device (DeviceConstants.BESS).

        Security:
            OWASP A01: Validates proper unique ID generation for battery-specific entities
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Find SAX_POWER item in battery items
        current_power_item = None
        for item in sax_data.get_modbus_items_for_battery("bess_a"):
            if item.name == SAX_POWER:
                current_power_item = item
                break

        assert current_power_item is not None
        assert current_power_item.device == DeviceConstants.BESS

        # Test for bess_a
        unique_id_a = sax_data.get_unique_id_for_item(
            current_power_item,
            battery_id="bess_a",
        )
        assert unique_id_a == "sax_bess_a_power"

        # Test for bess_b
        unique_id_b = sax_data.get_unique_id_for_item(
            current_power_item,
            battery_id="bess_b",
        )
        assert unique_id_b == "sax_bess_b_power"

    async def test_get_unique_id_virtual_entity_cluster(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test unique ID generation for virtual entity (SAX_COMBINED_SOC).

        Virtual entities (SAXItem) have no hardware backing and use battery_id=None.

        Security:
            OWASP A01: Validates proper unique ID generation for cluster-wide entities
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Find SAX_COMBINED_SOC item in SAX items
        combined_soc_item = None
        for item in sax_data.get_sax_items_for_battery("bess_a"):
            if item.name == SAX_COMBINED_SOC:
                combined_soc_item = item
                break

        assert combined_soc_item is not None
        assert isinstance(combined_soc_item, SAXItem)
        assert combined_soc_item.device == DeviceConstants.SYS

        # Virtual entities use battery_id=None
        unique_id = sax_data.get_unique_id_for_item(
            combined_soc_item,
            battery_id=None,
        )

        assert unique_id == "sax_bms_combined_soc"

    async def test_get_unique_id_config_entity_cluster(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation for config entity (SAX_MIN_SOC).

        Config entities (SAXItem) are virtual and use battery_id=None.

        Security:
            OWASP A01: Validates proper unique ID generation for configuration entities
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Find SAX_MIN_SOC item in SAX items
        min_soc_item = None
        for item in sax_data.get_sax_items_for_battery("bess_a"):
            if item.name == SAX_MIN_SOC:
                min_soc_item = item
                break

        assert min_soc_item is not None
        assert isinstance(min_soc_item, SAXItem)
        assert min_soc_item.device == DeviceConstants.SYS

        # Config entities use battery_id=None
        unique_id = sax_data.get_unique_id_for_item(
            min_soc_item,
            battery_id=None,
        )

        assert unique_id == "sax_bms_min_soc"

    async def test_get_unique_id_empty_item_name(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation with empty item name.

        Security:
            OWASP A03: Validates input validation for empty item names
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Create mock item with empty name
        empty_item = MagicMock(spec=ModbusItem)
        empty_item.name = ""
        empty_item.device = DeviceConstants.BESS

        unique_id = sax_data.get_unique_id_for_item(
            empty_item,
            battery_id="bess_a",
        )

        assert unique_id is None

    async def test_get_unique_id_whitespace_item_name(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation with whitespace-only item name.

        Security:
            OWASP A03: Validates input validation for whitespace item names
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Create mock item with whitespace name
        whitespace_item = MagicMock(spec=ModbusItem)
        whitespace_item.name = "   "
        whitespace_item.device = DeviceConstants.BESS

        unique_id = sax_data.get_unique_id_for_item(
            whitespace_item,
            battery_id="bess_a",
        )

        assert unique_id is None

    async def test_get_unique_id_prefix_removal(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation removes 'sax_' prefix from item name.

        Security:
            OWASP A03: Validates proper name normalization
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Create mock item with 'sax_' prefix
        prefixed_item = MagicMock(spec=ModbusItem)
        prefixed_item.name = "sax_power"
        prefixed_item.device = DeviceConstants.BESS

        unique_id = sax_data.get_unique_id_for_item(
            prefixed_item,
            battery_id="bess_a",
        )

        # Should remove 'sax_' prefix and convert to lowercase
        assert unique_id == "sax_bess_a_power"

    async def test_get_unique_id_case_normalization(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation converts to lowercase.

        Security:
            OWASP A03: Validates case normalization for consistency
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Create mock item with mixed case
        mixed_case_item = MagicMock(spec=ModbusItem)
        mixed_case_item.name = "SAX_POWER"
        mixed_case_item.device = DeviceConstants.BESS

        unique_id = sax_data.get_unique_id_for_item(
            mixed_case_item,
            battery_id="bess_a",
        )

        # Should convert to lowercase
        assert unique_id == "sax_bess_a_sax_power"

    async def test_get_unique_id_multiple_batteries_consistency(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test unique ID generation consistency across multiple batteries.

        Security:
            OWASP A01: Validates unique IDs are properly scoped per battery
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Find a common item
        current_soc_item = None
        for item in sax_data.get_modbus_items_for_battery("bess_a"):
            if item.name == SAX_SOC:
                current_soc_item = item
                break

        assert current_soc_item is not None

        # Generate unique IDs for different batteries
        unique_ids = {
            "bess_a": sax_data.get_unique_id_for_item(
                current_soc_item,
                battery_id="bess_a",
            ),
            "bess_b": sax_data.get_unique_id_for_item(
                current_soc_item,
                battery_id="bess_b",
            ),
        }

        # Verify unique IDs are different per battery
        assert unique_ids["bess_a"] == "sax_bess_a_soc"
        assert unique_ids["bess_b"] == "sax_bess_b_soc"
        assert unique_ids["bess_a"] != unique_ids["bess_b"]

    async def test_get_unique_id_device_type_consistency(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation respects device type from item.

        Security:
            OWASP A05: Validates device type handling prevents misconfiguration
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Test BESS device (battery-specific)
        bess_item = MagicMock(spec=ModbusItem)
        bess_item.name = "sax_test_sensor"
        bess_item.device = DeviceConstants.BESS

        bess_unique_id = sax_data.get_unique_id_for_item(
            bess_item,
            battery_id="bess_a",
        )
        assert bess_unique_id == "sax_bess_a_test_sensor"

        # Test SYS device (cluster-wide)
        sys_item = MagicMock(spec=ModbusItem)
        sys_item.name = "sax_test_control"
        sys_item.device = DeviceConstants.SYS

        sys_unique_id = sax_data.get_unique_id_for_item(
            sys_item,
            battery_id="bess_a",
        )
        assert sys_unique_id == "sax_bms_test_control"

        # Test SM device (smart meter)
        sm_item = MagicMock(spec=ModbusItem)
        sm_item.name = "sax_test_meter"
        sm_item.device = DeviceConstants.SM

        sm_unique_id = sax_data.get_unique_id_for_item(
            sm_item,
            battery_id="bess_a",
        )
        assert sm_unique_id == "sax_sm_test_meter"

    async def test_get_unique_id_error_handling(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test unique ID generation error handling.

        Security:
            OWASP A05: Validates proper error handling prevents exceptions
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        # Test with None item name (should trigger exception)
        none_item = MagicMock(spec=ModbusItem)
        none_item.name = None
        none_item.device = DeviceConstants.BESS

        unique_id = sax_data.get_unique_id_for_item(
            none_item,
            battery_id="bess_a",
        )

        # Should return None on error, not raise exception
        assert unique_id is None

    async def test_get_unique_id_all_test_items(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test unique ID generation for all specified test items.

        Comprehensive test covering:
        - MODBUS_BATTERY_POWER_LIMIT_ITEMS (WO registers)
        - SAX_CURRENT_L1 (per-battery sensor)
        - SAX_COMBINED_SOC (virtual entity)
        - SAX_MIN_SOC (config entity)

        Security:
            OWASP A01: Validates proper unique ID generation across all entity types
        """
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        expected_results: dict[str, dict[str, str | None]] = {
            # Smartmeter sensor (SM device)
            SAX_SMARTMETER_TOTAL_POWER: {
                "battery_id": "bess_a",
                "unique_id": "sax_sm_total_power_sm",
            },
            # WO registers (cluster device)
            SAX_MAX_DISCHARGE: {
                "battery_id": "bess_a",
                "unique_id": "sax_bms_max_discharge",
            },
            SAX_MAX_CHARGE: {
                "battery_id": "bess_a",
                "unique_id": "sax_bms_max_charge",
            },
            # Virtual entity (cluster device, battery_id=None)
            SAX_COMBINED_SOC: {
                "battery_id": None,
                "unique_id": "sax_bms_combined_soc",
            },
            # Config entity (cluster device, battery_id=None)
            SAX_MIN_SOC: {"battery_id": None, "unique_id": "sax_bms_min_soc"},
        }

        for item_name, expected in expected_results.items():
            # Find item (can be ModbusItem or SAXItem)
            item: ModbusItem | SAXItem | None = None

            # Check WO registers
            if item_name in (SAX_MAX_DISCHARGE, SAX_MAX_CHARGE):
                item = next(
                    (
                        i
                        for i in MODBUS_BATTERY_POWER_LIMIT_ITEMS
                        if i.name == item_name
                    ),
                    None,
                )

            # Check modbus items
            battery_id = expected.get("battery_id")
            if item is None and battery_id is not None and isinstance(battery_id, str):
                for i in sax_data.get_modbus_items_for_battery(battery_id):
                    if i.name == item_name:
                        item = i
                        break

            # Check SAX items
            if item is None and battery_id is None:
                for i in sax_data.get_sax_items_for_battery("bess_a"):  # type: ignore[assignment]
                    if i.name == item_name:
                        item = i
                        break

            assert item is not None, f"Item {item_name} not found"

            # Generate unique ID
            unique_id = sax_data.get_unique_id_for_item(
                item,
                battery_id=battery_id if isinstance(battery_id, str) else None,
            )

            expected_unique_id = expected.get("unique_id")
            assert unique_id == expected_unique_id, (
                f"Failed for {item_name}: expected {expected_unique_id}, got {unique_id}"
            )
