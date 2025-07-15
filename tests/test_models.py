"""Test models.py functionality."""

from unittest.mock import MagicMock

from custom_components.sax_battery.models import (
    BatteryDevice,
    BatteryRole,
    CommunicationInterface,
    SAXBatteryData,
    SAXBatterySystem,
    SmartMeterData,
)


class TestBatteryRole:
    """Test BatteryRole enum."""

    def test_battery_role_values(self) -> None:
        """Test battery role enum values."""
        assert BatteryRole.MASTER.value == "master"
        assert BatteryRole.SLAVE.value == "slave"


class TestCommunicationInterface:
    """Test CommunicationInterface enum."""

    def test_communication_interface_values(self) -> None:
        """Test communication interface enum values."""
        assert CommunicationInterface.MODBUS_TCP.value == "modbus_tcp"
        assert CommunicationInterface.MODBUS_RTU.value == "modbus_rtu"


class TestSmartMeterData:
    """Test SmartMeterData dataclass."""

    def test_smart_meter_data_init_defaults(self) -> None:
        """Test SmartMeterData initialization with defaults."""
        data = SmartMeterData()

        # Total grid measurements
        assert data.total_power is None
        assert data.grid_frequency is None

        # Phase-specific measurements
        assert data.voltage_l1 is None
        assert data.voltage_l2 is None
        assert data.voltage_l3 is None

        assert data.current_l1 is None
        assert data.current_l2 is None
        assert data.current_l3 is None

        assert data.active_power_l1 is None
        assert data.active_power_l2 is None
        assert data.active_power_l3 is None

        # Grid connection status
        assert data.import_power is None
        assert data.export_power is None
        assert data.last_update is not None  # Should have a default time

    def test_smart_meter_data_with_values(self) -> None:
        """Test SmartMeterData with specific values."""
        data = SmartMeterData(
            total_power=1500.0,
            grid_frequency=50.0,
            voltage_l1=230.0,
            voltage_l2=231.0,
            voltage_l3=229.0,
            import_power=100.0,
            export_power=0.0,
            last_update=1234567890.0,
        )

        assert data.total_power == 1500.0
        assert data.grid_frequency == 50.0
        assert data.voltage_l1 == 230.0
        assert data.voltage_l2 == 231.0
        assert data.voltage_l3 == 229.0
        assert data.import_power == 100.0
        assert data.export_power == 0.0
        assert data.last_update == 1234567890.0


class TestBatteryDevice:
    """Test BatteryDevice dataclass."""

    def test_battery_device_init_defaults(self) -> None:
        """Test BatteryDevice initialization with defaults."""
        device = BatteryDevice(
            battery_id="battery_a",
            host="192.168.1.100",
        )

        assert device.battery_id == "battery_a"
        assert device.host == "192.168.1.100"
        assert device.port == 502
        assert device.slave_id == 64
        assert device.role == "slave"
        assert device.phase == "L1"
        assert device.data == {}
        assert device.last_update is not None

    def test_battery_device_with_custom_values(self) -> None:
        """Test BatteryDevice with custom values."""
        device = BatteryDevice(
            battery_id="battery_b",
            host="192.168.1.101",
            port=503,
            slave_id=65,
            role="master",
            phase="L2",
        )

        assert device.battery_id == "battery_b"
        assert device.host == "192.168.1.101"
        assert device.port == 503
        assert device.slave_id == 65
        assert device.role == "master"
        assert device.phase == "L2"

    def test_battery_device_is_master(self) -> None:
        """Test BatteryDevice is_master property."""
        master_device = BatteryDevice(
            battery_id="battery_a",
            host="192.168.1.100",
            role="master",
        )
        slave_device = BatteryDevice(
            battery_id="battery_b",
            host="192.168.1.101",
            role="slave",
        )

        assert master_device.is_master is True
        assert slave_device.is_master is False


class TestSAXBatterySystem:
    """Test SAXBatterySystem dataclass."""

    def test_sax_battery_system_init_defaults(self) -> None:
        """Test SAXBatterySystem initialization with defaults."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        assert system.entry == mock_entry
        assert system.config_entry == mock_entry
        assert system.coordinator is None
        assert system.device_id == mock_entry.entry_id
        assert system.master_battery_id is None
        assert system.modbus_api is None
        assert isinstance(system.smart_meter_data, SmartMeterData)
        assert system.batteries == {}
        assert system.pilot is None
        assert system.system_power_limits == {}
        assert system.phase_balancing_enabled is True

    def test_get_master_battery_no_master(self) -> None:
        """Test get_master_battery when no master is set."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        assert system.get_master_battery() is None

    def test_get_master_battery_with_master(self) -> None:
        """Test get_master_battery when master is set."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add a master battery
        master_battery = system.add_battery(
            battery_id="battery_a", host="192.168.1.100", role="master"
        )

        assert system.get_master_battery() == master_battery

    def test_get_slave_batteries_empty(self) -> None:
        """Test get_slave_batteries when no batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        assert system.get_slave_batteries() == []

    def test_get_slave_batteries_with_master_and_slaves(self) -> None:
        """Test get_slave_batteries with master and slave batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add batteries
        master_battery = system.add_battery(
            battery_id="battery_a", host="192.168.1.100", role="master"
        )
        slave_battery_1 = system.add_battery(
            battery_id="battery_b", host="192.168.1.101", role="slave"
        )
        slave_battery_2 = system.add_battery(
            battery_id="battery_c", host="192.168.1.102", role="slave"
        )

        slaves = system.get_slave_batteries()
        assert len(slaves) == 2
        assert slave_battery_1 in slaves
        assert slave_battery_2 in slaves
        assert master_battery not in slaves

    def test_should_poll_smart_meter_master(self) -> None:
        """Test should_poll_smart_meter for master battery."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add master battery
        system.add_battery(battery_id="battery_a", host="192.168.1.100", role="master")

        assert system.should_poll_smart_meter("battery_a") is True

    def test_should_poll_smart_meter_no_master(self) -> None:
        """Test should_poll_smart_meter when no master is set."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        assert system.should_poll_smart_meter("battery_a") is False

    def test_get_polling_interval_for_battery_master(self) -> None:
        """Test get_polling_interval_for_battery for master battery."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add master battery
        system.add_battery(battery_id="battery_a", host="192.168.1.100", role="master")

        assert system.get_polling_interval_for_battery("battery_a") == 5

    def test_get_polling_interval_for_battery_slave(self) -> None:
        """Test get_polling_interval_for_battery for slave battery."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add slave battery
        system.add_battery(battery_id="battery_b", host="192.168.1.101", role="slave")

        assert system.get_polling_interval_for_battery("battery_b") == 10

    def test_get_polling_interval_for_battery_unknown(self) -> None:
        """Test get_polling_interval_for_battery for unknown battery."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        assert system.get_polling_interval_for_battery("unknown_battery") == 10

    def test_get_modbus_items_for_battery(self) -> None:
        """Test get_modbus_items_for_battery method."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        items = system.get_modbus_items_for_battery("battery_a")
        assert isinstance(items, list)

    def test_get_total_system_power_no_batteries(self) -> None:
        """Test get_total_system_power with no batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        assert system.get_total_system_power() == 0.0

    def test_get_total_system_power_with_batteries(self) -> None:
        """Test get_total_system_power with batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add batteries with power data
        battery_a = system.add_battery("battery_a", "192.168.1.100")
        battery_b = system.add_battery("battery_b", "192.168.1.101")

        battery_a.data["power"] = 1000.0
        battery_b.data["power"] = 1500.0

        assert system.get_total_system_power() == 2500.0

    def test_get_total_system_power_invalid_data(self) -> None:
        """Test get_total_system_power with invalid power data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add batteries with mixed data types
        battery_a = system.add_battery("battery_a", "192.168.1.100")
        battery_b = system.add_battery("battery_b", "192.168.1.101")
        battery_c = system.add_battery("battery_c", "192.168.1.102")

        battery_a.data["power"] = 1000.0  # Valid
        battery_b.data["power"] = "invalid"  # Invalid - string
        battery_c.data["power"] = None  # Invalid - None

        # Should only count valid power values
        assert system.get_total_system_power() == 1000.0

    def test_get_average_soc_no_batteries(self) -> None:
        """Test get_average_soc with no batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        assert system.get_average_soc() is None

    def test_get_average_soc_with_batteries(self) -> None:
        """Test get_average_soc with batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add batteries with SOC data
        battery_a = system.add_battery("battery_a", "192.168.1.100")
        battery_b = system.add_battery("battery_b", "192.168.1.101")
        battery_c = system.add_battery("battery_c", "192.168.1.102")

        battery_a.data["soc"] = 80.0
        battery_b.data["soc"] = 85.0
        battery_c.data["soc"] = 90.0

        assert system.get_average_soc() == 85.0

    def test_get_average_soc_with_invalid_data(self) -> None:
        """Test get_average_soc with invalid SOC data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add batteries with mixed data types
        battery_a = system.add_battery("battery_a", "192.168.1.100")
        battery_b = system.add_battery("battery_b", "192.168.1.101")
        battery_c = system.add_battery("battery_c", "192.168.1.102")

        battery_a.data["soc"] = 80.0  # Valid
        battery_b.data["soc"] = "invalid"  # Invalid - string
        battery_c.data["soc"] = None  # Invalid - None

        # Should only count valid SOC values
        assert system.get_average_soc() == 80.0

    def test_get_average_soc_no_valid_data(self) -> None:
        """Test get_average_soc with no valid SOC data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add batteries with invalid SOC data
        battery_a = system.add_battery("battery_a", "192.168.1.100")
        battery_b = system.add_battery("battery_b", "192.168.1.101")

        battery_a.data["soc"] = "invalid"
        battery_b.data["soc"] = None

        assert system.get_average_soc() is None

    def test_add_battery(self) -> None:
        """Test add_battery method."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        battery = system.add_battery(
            battery_id="battery_a",
            host="192.168.1.100",
            port=503,
            slave_id=65,
            role="master",
            phase="L2",
        )

        assert battery.battery_id == "battery_a"
        assert battery.host == "192.168.1.100"
        assert battery.port == 503
        assert battery.slave_id == 65
        assert battery.role == "master"
        assert battery.phase == "L2"
        assert system.batteries["battery_a"] == battery
        assert system.master_battery_id == "battery_a"

    def test_remove_battery(self) -> None:
        """Test remove_battery method."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add battery
        system.add_battery("battery_a", "192.168.1.100", role="master")
        assert "battery_a" in system.batteries
        assert system.master_battery_id == "battery_a"

        # Remove battery
        system.remove_battery("battery_a")
        assert "battery_a" not in system.batteries
        assert system.master_battery_id is None

    def test_get_batteries_by_phase(self) -> None:
        """Test get_batteries_by_phase method."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(config_entry=mock_entry)

        # Add batteries on different phases
        battery_l1 = system.add_battery("battery_a", "192.168.1.100", phase="L1")
        battery_l2 = system.add_battery("battery_b", "192.168.1.101", phase="L2")
        battery_l3 = system.add_battery("battery_c", "192.168.1.102", phase="L3")

        l1_batteries = system.get_batteries_by_phase("L1")
        l2_batteries = system.get_batteries_by_phase("L2")
        l3_batteries = system.get_batteries_by_phase("L3")

        assert len(l1_batteries) == 1
        assert battery_l1 in l1_batteries
        assert len(l2_batteries) == 1
        assert battery_l2 in l2_batteries
        assert len(l3_batteries) == 1
        assert battery_l3 in l3_batteries


class TestSAXBatteryDataAlias:
    """Test SAXBatteryData alias."""

    def test_sax_battery_data_alias(self) -> None:
        """Test that SAXBatteryData is an alias for SAXBatterySystem."""
        mock_entry = MagicMock()
        data = SAXBatteryData(config_entry=mock_entry)

        # Should be the same class
        assert isinstance(data, SAXBatterySystem)
        assert SAXBatteryData == SAXBatterySystem
