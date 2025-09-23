"""Test models for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.models import BatteryModel, SAXBatteryData


class TestBatteryModel:
    """Test BatteryModel functionality."""

    def test_battery_model_initialization(self, battery_model_data_basic) -> None:
        """Test BatteryModel initialization."""
        battery = BatteryModel(**battery_model_data_basic)

        assert battery.device_id == "battery_a"
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
            device_id="battery_a",
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
            config_data={"pilot_from_ha": False, "limit_power": False},
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
        # Ensure pilot_from_ha is enabled to generate SAX items
        battery_model_data_basic["config_data"] = {
            "pilot_from_ha": True,
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
        assert "battery_a" in sax_data.batteries
        assert "battery_b" in sax_data.batteries
        assert sax_data.master_battery_id == "battery_a"

    def test_sax_battery_data_battery_configuration(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test battery configuration in SAXBatteryData."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        battery_a = sax_data.batteries["battery_a"]
        battery_b = sax_data.batteries["battery_b"]

        assert battery_a.is_master is True
        assert battery_b.is_master is False
        assert battery_a.host == "192.168.1.100"
        assert battery_b.host == "192.168.1.101"

    def test_sax_battery_data_should_poll_smart_meter(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test should_poll_smart_meter method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        assert sax_data.should_poll_smart_meter("battery_a") is True
        assert sax_data.should_poll_smart_meter("battery_b") is False
        assert sax_data.should_poll_smart_meter("battery_c") is False

    def test_sax_battery_data_get_modbus_items_for_battery(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test get_modbus_items_for_battery method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Master battery should have items
        master_items = sax_data.get_modbus_items_for_battery("battery_a")
        assert len(master_items) > 0

        # Slave battery should have items
        slave_items = sax_data.get_modbus_items_for_battery("battery_b")
        assert len(slave_items) > 0

        # Non-existent battery should return empty list
        nonexistent_items = sax_data.get_modbus_items_for_battery("battery_z")
        assert len(nonexistent_items) == 0

    def test_sax_battery_data_get_sax_items_for_battery(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test get_sax_items_for_battery method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Master battery should have SAX items
        master_sax_items = sax_data.get_sax_items_for_battery("battery_a")
        assert len(master_sax_items) > 0

        # Slave battery should have no SAX items
        slave_sax_items = sax_data.get_sax_items_for_battery("battery_b")
        assert len(slave_sax_items) == 0

        # Non-existent battery should return empty list
        nonexistent_sax_items = sax_data.get_sax_items_for_battery("battery_z")
        assert len(nonexistent_sax_items) == 0

    def test_sax_battery_data_get_device_info(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test get_device_info method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        device_info_a = sax_data.get_device_info(
            "battery_a", device=DeviceConstants.BESS
        )
        assert device_info_a["identifiers"] == {("sax_battery", "battery_a")}
        assert device_info_a["name"] == "SAX Battery A"

        device_info_b = sax_data.get_device_info("battery_b", DeviceConstants.BESS)
        assert device_info_b["identifiers"] == {("sax_battery", "battery_b")}
        assert device_info_b["name"] == "SAX Battery B"

    def test_sax_battery_data_single_battery(
        self, mock_hass, mock_config_entry_single_battery
    ) -> None:
        """Test SAXBatteryData with single battery configuration."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_single_battery)

        assert len(sax_data.batteries) == 1
        assert "battery_a" in sax_data.batteries
        assert sax_data.master_battery_id == "battery_a"
        assert sax_data.batteries["battery_a"].is_master is True

    def test_sax_battery_data_with_pilot_enabled(
        self, mock_hass, mock_config_entry_pilot_enabled
    ) -> None:
        """Test SAXBatteryData with pilot features enabled."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_pilot_enabled)

        assert len(sax_data.batteries) == 1
        assert sax_data.master_battery_id == "battery_a"

        # Master battery should have pilot-related items
        master_sax_items = sax_data.get_sax_items_for_battery("battery_a")
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
        master_modbus_items = sax_data.get_modbus_items_for_battery("battery_a")
        master_sax_items = sax_data.get_sax_items_for_battery("battery_a")

        # Slave battery items
        slave_modbus_items = sax_data.get_modbus_items_for_battery("battery_b")
        slave_sax_items = sax_data.get_sax_items_for_battery("battery_b")

        # Master should have more items including system-wide items
        assert len(master_modbus_items) >= len(slave_modbus_items)

        # Master should have SAX items, slave should not
        assert len(master_sax_items) > 0
        assert len(slave_sax_items) == 0

        # Master should be able to poll smart meter
        assert sax_data.should_poll_smart_meter("battery_a") is True
        assert sax_data.should_poll_smart_meter("battery_b") is False

    def test_sax_battery_data_device_info_consistency(
        self, mock_hass, mock_config_entry_dual_battery
    ) -> None:
        """Test device info consistency across batteries."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry_dual_battery)

        # Test device info for both batteries
        device_info_a = sax_data.get_device_info(
            "battery_a", device=DeviceConstants.BESS
        )
        device_info_b = sax_data.get_device_info(
            "battery_b", device=DeviceConstants.BESS
        )

        # Both should have consistent structure
        for device_info in [device_info_a, device_info_b]:
            assert "identifiers" in device_info
            assert "name" in device_info
            assert "manufacturer" in device_info
            assert device_info["manufacturer"] == "SAX"

        # Should have unique identifiers
        assert device_info_a["identifiers"] != device_info_b["identifiers"]
        assert device_info_a["name"] != device_info_b["name"]

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
        assert sax_data.should_poll_smart_meter("any_battery") is False
        assert len(sax_data.get_modbus_items_for_battery("any_battery")) == 0
        assert len(sax_data.get_sax_items_for_battery("any_battery")) == 0
