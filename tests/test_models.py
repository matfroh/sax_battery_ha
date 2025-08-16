"""Test models for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.models import BatteryModel, SAXBatteryData


class TestBatteryModel:
    """Test BatteryModel functionality."""

    def test_battery_model_initialization(self) -> None:
        """Test BatteryModel initialization."""
        battery = BatteryModel(
            device_id="battery_a",
            name="SAX Battery A",
            slave_id=1,
            host="192.168.1.100",
            port=502,
            is_master=True,
        )

        assert battery.device_id == "battery_a"
        assert battery.name == "SAX Battery A"
        assert battery.slave_id == 1
        assert battery.host == "192.168.1.100"
        assert battery.port == 502
        assert battery.is_master is True

    def test_battery_model_device_info(self) -> None:
        """Test BatteryModel device info."""
        battery = BatteryModel(
            device_id="battery_a",
            name="SAX Battery A",
        )

        device_info = battery.get_device_info()

        assert device_info["identifiers"] == {("sax_battery", "battery_a")}
        assert device_info["name"] == "SAX Battery A"
        assert device_info["manufacturer"] == "SAX"

    def test_battery_model_data_operations(self) -> None:
        """Test BatteryModel data operations."""
        battery = BatteryModel(
            device_id="battery_a",
            name="SAX Battery A",
        )

        # Test setting and getting values
        battery.set_value("soc", 85.5)
        battery.set_value("power", 1500)

        assert battery.get_value("soc") == 85.5
        assert battery.get_value("power") == 1500
        assert battery.get_value("nonexistent") is None

        # Test update data
        battery.update_data({"voltage": 48.2, "current": 31.25})

        assert battery.get_value("voltage") == 48.2
        assert battery.get_value("current") == 31.25

    def test_battery_model_convenience_properties(self) -> None:
        """Test BatteryModel convenience properties."""
        battery = BatteryModel(
            device_id="battery_a",
            name="SAX Battery A",
        )

        # Test properties return None when no data
        assert battery.soc is None
        assert battery.power is None
        assert battery.voltage_l1 is None
        assert battery.current_l1 is None

        # Set some data
        battery.update_data(
            {
                "sax_soc": 75,
                "sax_power": 2000,
                "voltage_l1": 48.5,
                "current_l1": 41.2,
            }
        )

        assert battery.soc == 75.0
        assert battery.power == 2000.0
        assert battery.voltage_l1 == 48.5
        assert battery.current_l1 == 41.2

    def test_battery_model_modbus_items_master(self) -> None:
        """Test BatteryModel modbus items for master battery."""
        battery = BatteryModel(
            device_id="battery_a",
            name="SAX Battery A",
            is_master=True,
            config_data={"pilot_from_ha": True, "limit_power": True},
        )

        modbus_items = battery.get_modbus_items()

        # Master battery should have basic items
        assert len(modbus_items) > 0

        # Check for system items (adjusted expectation based on actual implementation)
        system_items = [
            item for item in modbus_items if item.device == DeviceConstants.SYS
        ]
        assert len(system_items) > 0

    def test_battery_model_modbus_items_slave(self) -> None:
        """Test BatteryModel modbus items for slave battery."""
        battery = BatteryModel(
            device_id="battery_b",
            name="SAX Battery B",
            is_master=False,
            config_data={"pilot_from_ha": False, "limit_power": False},
        )

        modbus_items = battery.get_modbus_items()

        # Slave battery should have basic items only
        assert len(modbus_items) > 0

        # Should not include smart meter items for slave
        smart_meter_items = [
            item
            for item in modbus_items
            if item.device == DeviceConstants.SYS and "smartmeter" in item.name.lower()
        ]
        assert len(smart_meter_items) == 0

    def test_battery_model_sax_items_master(self) -> None:
        """Test BatteryModel SAX items for master battery."""
        battery = BatteryModel(
            device_id="battery_a",
            name="SAX Battery A",
            is_master=True,
        )

        sax_items = battery.get_sax_items()

        # Master battery should have aggregated and pilot items
        assert len(sax_items) > 0

        # Check for pilot items
        pilot_items = [item for item in sax_items if item.mtype == TypeConstants.SWITCH]
        assert len(pilot_items) > 0

    def test_battery_model_sax_items_slave(self) -> None:
        """Test BatteryModel SAX items for slave battery."""
        battery = BatteryModel(
            device_id="battery_b",
            name="SAX Battery B",
            is_master=False,
        )

        sax_items = battery.get_sax_items()

        # Slave battery should have no SAX items
        assert len(sax_items) == 0


class TestSAXBatteryData:
    """Test SAXBatteryData functionality."""

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        """Create mock HomeAssistant instance."""
        return MagicMock()

    @pytest.fixture
    def mock_config_entry(self) -> MagicMock:
        """Create mock config entry."""
        entry = MagicMock()
        entry.data = {
            "battery_count": 2,
            "master_battery": "battery_a",
            "battery_a_host": "192.168.1.100",
            "battery_a_port": 502,
            "battery_b_host": "192.168.1.101",
            "battery_b_port": 502,
        }
        return entry

    def test_sax_battery_data_initialization(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test SAXBatteryData initialization."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

        assert len(sax_data.batteries) == 2
        assert "battery_a" in sax_data.batteries
        assert "battery_b" in sax_data.batteries
        assert sax_data.master_battery_id == "battery_a"

    def test_sax_battery_data_battery_configuration(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test battery configuration in SAXBatteryData."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

        battery_a = sax_data.batteries["battery_a"]
        battery_b = sax_data.batteries["battery_b"]

        assert battery_a.is_master is True
        assert battery_b.is_master is False
        assert battery_a.host == "192.168.1.100"
        assert battery_b.host == "192.168.1.101"

    def test_sax_battery_data_is_battery_connected(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test is_battery_connected method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

        assert sax_data.is_battery_connected("battery_a") is True
        assert sax_data.is_battery_connected("battery_b") is True
        assert sax_data.is_battery_connected("battery_c") is False

    def test_sax_battery_data_should_poll_smart_meter(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test should_poll_smart_meter method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

        assert sax_data.should_poll_smart_meter("battery_a") is True
        assert sax_data.should_poll_smart_meter("battery_b") is False
        assert sax_data.should_poll_smart_meter("battery_c") is False

    def test_sax_battery_data_get_modbus_items_for_battery(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test get_modbus_items_for_battery method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

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
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test get_sax_items_for_battery method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

        # Master battery should have SAX items
        master_sax_items = sax_data.get_sax_items_for_battery("battery_a")
        assert len(master_sax_items) > 0

        # Slave battery should have no SAX items
        slave_sax_items = sax_data.get_sax_items_for_battery("battery_b")
        assert len(slave_sax_items) == 0

        # Non-existent battery should return empty list
        nonexistent_sax_items = sax_data.get_sax_items_for_battery("battery_z")
        assert len(nonexistent_sax_items) == 0

    def test_sax_battery_data_get_smart_meter_items(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test get_smart_meter_items method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

        smart_meter_items = sax_data.get_smart_meter_items()
        assert len(smart_meter_items) > 0

        # Should include smart meter device items
        smart_meter_device_items = [
            item for item in smart_meter_items if item.device == DeviceConstants.SM
        ]
        assert len(smart_meter_device_items) > 0

    def test_sax_battery_data_get_device_info(
        self, mock_hass: MagicMock, mock_config_entry: MagicMock
    ) -> None:
        """Test get_device_info method."""
        sax_data = SAXBatteryData(mock_hass, mock_config_entry)

        device_info_a = sax_data.get_device_info("battery_a")
        assert device_info_a["identifiers"] == {("sax_battery", "battery_a")}
        assert device_info_a["name"] == "SAX Battery A"

        device_info_b = sax_data.get_device_info("battery_b")
        assert device_info_b["identifiers"] == {("sax_battery", "battery_b")}
        assert device_info_b["name"] == "SAX Battery B"

        # Non-existent battery should return fallback device info
        device_info_fallback = sax_data.get_device_info("battery_z")
        assert device_info_fallback["identifiers"] == {("sax_battery", "battery_z")}
        assert device_info_fallback["name"] == "SAX Battery battery_z"

    def test_sax_battery_data_single_battery(self, mock_hass: MagicMock) -> None:
        """Test SAXBatteryData with single battery configuration."""
        entry = MagicMock()
        entry.data = {
            "battery_count": 1,
            "master_battery": "battery_a",
            "battery_a_host": "192.168.1.100",
            "battery_a_port": 502,
        }

        sax_data = SAXBatteryData(mock_hass, entry)

        assert len(sax_data.batteries) == 1
        assert "battery_a" in sax_data.batteries
        assert sax_data.master_battery_id == "battery_a"
        assert sax_data.batteries["battery_a"].is_master is True
