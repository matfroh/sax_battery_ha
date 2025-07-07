"""Test models.py functionality."""

from unittest.mock import MagicMock

from custom_components.sax_battery.models import (
    BatteryConfig,
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
        assert data.last_update is None

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


class TestBatteryConfig:
    """Test BatteryConfig dataclass."""

    def test_battery_config_init_defaults(self) -> None:
        """Test BatteryConfig initialization with defaults."""
        config = BatteryConfig(
            battery_id="battery_a",
            role=BatteryRole.MASTER,
            tcp_host="192.168.1.100",
        )

        assert config.battery_id == "battery_a"
        assert config.role == BatteryRole.MASTER
        assert config.tcp_host == "192.168.1.100"
        assert config.tcp_port == 502
        assert config.tcp_slave_id == 64
        assert config.rtu_slave_id == 40
        assert config.max_charge_power is None
        assert config.max_discharge_power is None

    def test_battery_config_with_custom_values(self) -> None:
        """Test BatteryConfig with custom values."""
        config = BatteryConfig(
            battery_id="battery_b",
            role=BatteryRole.SLAVE,
            tcp_host="192.168.1.101",
            tcp_port=503,
            tcp_slave_id=65,
            rtu_slave_id=41,
            max_charge_power=4500,
            max_discharge_power=3600,
        )

        assert config.battery_id == "battery_b"
        assert config.role == BatteryRole.SLAVE
        assert config.tcp_host == "192.168.1.101"
        assert config.tcp_port == 503
        assert config.tcp_slave_id == 65
        assert config.rtu_slave_id == 41
        assert config.max_charge_power == 4500
        assert config.max_discharge_power == 3600


class TestSAXBatterySystem:
    """Test SAXBatterySystem dataclass."""

    def test_sax_battery_system_init_defaults(self) -> None:
        """Test SAXBatterySystem initialization with defaults."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert system.entry == mock_entry
        assert system.coordinator is None
        assert system.device_id is None
        assert system.master_battery_id is None
        assert system.battery_configs == {}
        assert system.modbus_api is None
        assert isinstance(system.smart_meter_data, SmartMeterData)
        assert system.batteries == {}
        assert system.pilot is None
        assert system.system_power_limits == {}
        assert system.phase_balancing_enabled is True

    def test_get_master_battery_no_master(self) -> None:
        """Test get_master_battery when no master is set."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert system.get_master_battery() is None

    def test_get_master_battery_with_master(self) -> None:
        """Test get_master_battery when master is set."""
        mock_entry = MagicMock()
        mock_battery = MagicMock()

        system = SAXBatterySystem(entry=mock_entry)
        system.master_battery_id = "battery_a"
        system.batteries = {"battery_a": mock_battery, "battery_b": MagicMock()}

        assert system.get_master_battery() == mock_battery

    def test_get_slave_batteries_empty(self) -> None:
        """Test get_slave_batteries when no batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert system.get_slave_batteries() == []

    def test_get_slave_batteries_with_master_and_slaves(self) -> None:
        """Test get_slave_batteries with master and slave batteries."""
        mock_entry = MagicMock()
        mock_master = MagicMock()
        mock_slave1 = MagicMock()
        mock_slave2 = MagicMock()

        system = SAXBatterySystem(entry=mock_entry)
        system.master_battery_id = "battery_a"
        system.batteries = {
            "battery_a": mock_master,
            "battery_b": mock_slave1,
            "battery_c": mock_slave2,
        }

        slaves = system.get_slave_batteries()
        assert len(slaves) == 2
        assert mock_slave1 in slaves
        assert mock_slave2 in slaves
        assert mock_master not in slaves

    def test_should_poll_smart_meter_master(self) -> None:
        """Test should_poll_smart_meter for master battery."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)
        system.master_battery_id = "battery_a"

        assert system.should_poll_smart_meter("battery_a") is True
        assert system.should_poll_smart_meter("battery_b") is False

    def test_should_poll_smart_meter_no_master(self) -> None:
        """Test should_poll_smart_meter when no master is set."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert system.should_poll_smart_meter("battery_a") is False

    def test_get_polling_interval_for_battery_realtime(self) -> None:
        """Test get_polling_interval_for_battery for realtime data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert (
            system.get_polling_interval_for_battery("battery_a", "battery_realtime")
            == 10
        )

    def test_get_polling_interval_for_battery_static(self) -> None:
        """Test get_polling_interval_for_battery for static data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert (
            system.get_polling_interval_for_battery("battery_a", "battery_static")
            == 300
        )

    def test_get_polling_interval_for_battery_smartmeter_basic_master(self) -> None:
        """Test get_polling_interval_for_battery for smart meter basic data on master."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)
        system.master_battery_id = "battery_a"

        assert (
            system.get_polling_interval_for_battery("battery_a", "smartmeter_basic")
            == 10
        )
        assert (
            system.get_polling_interval_for_battery("battery_b", "smartmeter_basic")
            == 0
        )

    def test_get_polling_interval_for_battery_smartmeter_phase_master(self) -> None:
        """Test get_polling_interval_for_battery for smart meter phase data on master."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)
        system.master_battery_id = "battery_a"

        assert (
            system.get_polling_interval_for_battery("battery_a", "smartmeter_phase")
            == 60
        )
        assert (
            system.get_polling_interval_for_battery("battery_b", "smartmeter_phase")
            == 0
        )

    def test_get_polling_interval_for_battery_default(self) -> None:
        """Test get_polling_interval_for_battery with unknown data type."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert system.get_polling_interval_for_battery("battery_a", "unknown") == 10

    def test_get_modbus_items_for_battery(self) -> None:
        """Test get_modbus_items_for_battery method."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)
        system.master_battery_id = "battery_a"

        # Should return empty list for now (placeholder implementation)
        assert system.get_modbus_items_for_battery("battery_a") == []
        assert system.get_modbus_items_for_battery("battery_b") == []

    def test_get_total_system_power_no_batteries(self) -> None:
        """Test get_total_system_power with no batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert system.get_total_system_power() == 0.0

    def test_get_total_system_power_with_batteries(self) -> None:
        """Test get_total_system_power with batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        # Create mock batteries with power data
        mock_battery1 = MagicMock()
        mock_battery1.data = {"sax_power": 1500}

        mock_battery2 = MagicMock()
        mock_battery2.data = {"sax_power": 2000}

        mock_battery3 = MagicMock()
        mock_battery3.data = {"sax_power": None}  # Should be ignored

        mock_battery4 = MagicMock()
        mock_battery4.data = {}  # No power data, should be ignored

        system.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
            "battery_c": mock_battery3,
            "battery_d": mock_battery4,
        }

        assert system.get_total_system_power() == 3500.0

    def test_get_total_system_power_invalid_data(self) -> None:
        """Test get_total_system_power with invalid power data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        # Create mock battery with invalid power data
        mock_battery = MagicMock()
        mock_battery.data = {"sax_power": "invalid"}

        system.batteries = {"battery_a": mock_battery}

        assert system.get_total_system_power() == 0.0

    def test_get_average_soc_no_batteries(self) -> None:
        """Test get_average_soc with no batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        assert system.get_average_soc() is None

    def test_get_average_soc_with_batteries(self) -> None:
        """Test get_average_soc with batteries."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        # Create mock batteries with SOC data
        mock_battery1 = MagicMock()
        mock_battery1.data = {"sax_soc": 80}

        mock_battery2 = MagicMock()
        mock_battery2.data = {"sax_soc": 75}

        mock_battery3 = MagicMock()
        mock_battery3.data = {"sax_soc": 85}

        system.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
            "battery_c": mock_battery3,
        }

        assert system.get_average_soc() == 80.0

    def test_get_average_soc_with_invalid_data(self) -> None:
        """Test get_average_soc with invalid SOC data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        # Create mock batteries with mixed valid/invalid SOC data
        mock_battery1 = MagicMock()
        mock_battery1.data = {"sax_soc": 80}

        mock_battery2 = MagicMock()
        mock_battery2.data = {"sax_soc": None}  # Should be ignored

        mock_battery3 = MagicMock()
        mock_battery3.data = {"sax_soc": "invalid"}  # Should be ignored

        mock_battery4 = MagicMock()
        mock_battery4.data = {}  # No SOC data, should be ignored

        system.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
            "battery_c": mock_battery3,
            "battery_d": mock_battery4,
        }

        assert system.get_average_soc() == 80.0

    def test_get_average_soc_no_valid_data(self) -> None:
        """Test get_average_soc with no valid SOC data."""
        mock_entry = MagicMock()
        system = SAXBatterySystem(entry=mock_entry)

        # Create mock batteries with no valid SOC data
        mock_battery1 = MagicMock()
        mock_battery1.data = {"sax_soc": None}

        mock_battery2 = MagicMock()
        mock_battery2.data = {}

        system.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
        }

        assert system.get_average_soc() is None


class TestSAXBatteryDataAlias:
    """Test SAXBatteryData alias compatibility."""

    def test_sax_battery_data_alias(self) -> None:
        """Test that SAXBatteryData is an alias for SAXBatterySystem."""
        mock_entry = MagicMock()
        data = SAXBatteryData(entry=mock_entry)

        assert isinstance(data, SAXBatterySystem)
        assert data.entry == mock_entry
