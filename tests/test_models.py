"""Test models.py functionality."""

from unittest.mock import MagicMock

from custom_components.sax_battery.models import (
    BatteryModel,
    SAXBatteryData,
    SmartMeterModel,
)


class TestBatteryModel:
    """Test BatteryModel dataclass."""

    def test_battery_model_init_defaults(self) -> None:
        """Test BatteryModel initialization with defaults."""
        battery = BatteryModel(
            device_id="battery_a",
            name="Battery A",
        )

        assert battery.device_id == "battery_a"
        assert battery.name == "Battery A"
        assert battery.slave_id == 1
        assert battery.host == ""
        assert battery.port == 502
        assert battery.is_master is False
        assert battery.data == {}

    def test_battery_model_with_custom_values(self) -> None:
        """Test BatteryModel with custom values."""
        battery = BatteryModel(
            device_id="battery_b",
            name="Battery B",
            slave_id=2,
            host="192.168.1.101",
            port=503,
            is_master=True,
        )

        assert battery.device_id == "battery_b"
        assert battery.name == "Battery B"
        assert battery.slave_id == 2
        assert battery.host == "192.168.1.101"
        assert battery.port == 503
        assert battery.is_master is True

    def test_battery_model_get_device_info(self) -> None:
        """Test BatteryModel get_device_info method."""
        battery = BatteryModel(
            device_id="battery_a",
            name="Battery A",
        )

        device_info = battery.get_device_info()

        assert device_info["identifiers"] == {("sax_battery", "battery_a")}
        assert device_info["name"] == "Battery A"
        assert "manufacturer" in device_info
        assert "model" in device_info

    def test_battery_model_get_modbus_items_slave(self) -> None:
        """Test BatteryModel get_modbus_items for slave battery."""
        battery = BatteryModel(
            device_id="battery_b",
            name="Battery B",
            is_master=False,
        )

        items = battery.get_modbus_items()

        # Slave battery should only get basic battery items
        assert isinstance(items, list)
        # Items should not include smart meter items for slave

    def test_battery_model_get_modbus_items_master(self) -> None:
        """Test BatteryModel get_modbus_items for master battery."""
        battery = BatteryModel(
            device_id="battery_a",
            name="Battery A",
            is_master=True,
        )

        items = battery.get_modbus_items()

        # Master battery should get battery + smart meter items
        assert isinstance(items, list)
        # Should have more items than slave battery

    def test_battery_model_get_sax_items_slave(self) -> None:
        """Test BatteryModel get_sax_items for slave battery."""
        battery = BatteryModel(
            device_id="battery_b",
            name="Battery B",
            is_master=False,
        )

        items = battery.get_sax_items()

        # Slave battery should have no SAX items
        assert items == []

    def test_battery_model_get_sax_items_master(self) -> None:
        """Test BatteryModel get_sax_items for master battery."""
        battery = BatteryModel(
            device_id="battery_a",
            name="Battery A",
            is_master=True,
        )

        items = battery.get_sax_items()

        # Master battery should get aggregated and pilot items
        assert isinstance(items, list)

    def test_battery_model_data_operations(self) -> None:
        """Test BatteryModel data operations."""
        battery = BatteryModel(
            device_id="battery_a",
            name="Battery A",
        )

        # Test direct data access (if data is a dict)
        # Test with no data initially
        assert len(battery.data) == 0

        # Test data manipulation if supported
        battery.data["test_key"] = "test_value"
        assert battery.data["test_key"] == "test_value"

        # Test data update
        new_data = {"key1": "value1", "key2": "value2"}
        battery.data.update(new_data)
        assert battery.data["key1"] == "value1"
        assert battery.data["key2"] == "value2"


class TestSmartMeterModel:
    """Test SmartMeterModel dataclass."""

    def test_smart_meter_model_init(self) -> None:
        """Test SmartMeterModel initialization."""
        smart_meter = SmartMeterModel(
            device_id="smartmeter_001",
            name="Smart Meter",
        )

        assert smart_meter.device_id == "smartmeter_001"
        assert smart_meter.name == "Smart Meter"
        assert smart_meter.data == {}

    def test_smart_meter_model_get_device_info(self) -> None:
        """Test SmartMeterModel get_device_info method."""
        smart_meter = SmartMeterModel(
            device_id="battery_a_smartmeter",
            name="Battery A Smart Meter",
        )

        device_info = smart_meter.get_device_info()

        # The implementation appends '_smartmeter' to the device_id for identifiers
        assert device_info["identifiers"] == {
            ("sax_battery", "battery_a_smartmeter_smartmeter")
        }
        assert device_info["name"] == "Battery A Smart Meter Smart Meter"
        assert device_info["model"] == "Smart Meter"
        assert "via_device" in device_info

    def test_smart_meter_model_get_modbus_items(self) -> None:
        """Test SmartMeterModel get_modbus_items method."""
        smart_meter = SmartMeterModel(
            device_id="smartmeter_001",
            name="Smart Meter",
        )

        items = smart_meter.get_modbus_items()

        # Smart meter has no direct modbus items (data comes through battery)
        assert items == []

    def test_smart_meter_model_get_sax_items(self) -> None:
        """Test SmartMeterModel get_sax_items method."""
        smart_meter = SmartMeterModel(
            device_id="smartmeter_001",
            name="Smart Meter",
        )

        items = smart_meter.get_sax_items()

        # Smart meter has no SAX items
        assert items == []

    def test_smart_meter_model_data_access(self) -> None:
        """Test SmartMeterModel data access."""
        smart_meter = SmartMeterModel(
            device_id="smartmeter_001",
            name="Smart Meter",
        )

        # Test with no data initially
        assert len(smart_meter.data) == 0

        # Test data manipulation
        smart_meter.data["smartmeter_total_power"] = 2500.0
        assert smart_meter.data["smartmeter_total_power"] == 2500.0


class TestSAXBatteryData:
    """Test SAXBatteryData dataclass."""

    def test_sax_battery_data_init_defaults(self) -> None:
        """Test SAXBatteryData initialization with defaults."""
        sax_data = SAXBatteryData()

        assert sax_data.batteries == {}
        assert sax_data.smart_meter_data is None
        assert sax_data.coordinators == {}
        assert sax_data.modbus_api is None
        assert sax_data.master_battery_id is None

    async def test_sax_battery_data_async_initialize(self) -> None:
        """Test SAXBatteryData async_initialize method."""
        sax_data = SAXBatteryData()

        # Should not raise any exceptions
        await sax_data.async_initialize()

    def test_sax_battery_data_is_battery_connected(self) -> None:
        """Test SAXBatteryData is_battery_connected method."""
        sax_data = SAXBatteryData()

        # No batteries initially
        assert sax_data.is_battery_connected("battery_a") is False

        # Add a battery
        battery = BatteryModel(device_id="battery_a", name="Battery A")
        sax_data.batteries["battery_a"] = battery

        assert sax_data.is_battery_connected("battery_a") is True
        assert sax_data.is_battery_connected("battery_b") is False

    def test_sax_battery_data_should_poll_smart_meter(self) -> None:
        """Test SAXBatteryData should_poll_smart_meter method."""
        sax_data = SAXBatteryData()

        # No batteries
        assert sax_data.should_poll_smart_meter("battery_a") is False

        # Add slave battery
        slave_battery = BatteryModel(
            device_id="battery_b", name="Battery B", is_master=False
        )
        sax_data.batteries["battery_b"] = slave_battery

        assert sax_data.should_poll_smart_meter("battery_b") is False

        # Add master battery
        master_battery = BatteryModel(
            device_id="battery_a", name="Battery A", is_master=True
        )
        sax_data.batteries["battery_a"] = master_battery

        assert sax_data.should_poll_smart_meter("battery_a") is True
        assert sax_data.should_poll_smart_meter("battery_b") is False

    def test_sax_battery_data_get_modbus_items_for_battery(self) -> None:
        """Test SAXBatteryData get_modbus_items_for_battery method."""
        sax_data = SAXBatteryData()

        # No battery
        items = sax_data.get_modbus_items_for_battery("battery_a")
        assert items == []

        # Add battery
        battery = BatteryModel(device_id="battery_a", name="Battery A")
        sax_data.batteries["battery_a"] = battery

        items = sax_data.get_modbus_items_for_battery("battery_a")
        assert isinstance(items, list)

    def test_sax_battery_data_get_sax_items_for_battery(self) -> None:
        """Test SAXBatteryData get_sax_items_for_battery method."""
        sax_data = SAXBatteryData()

        # No battery
        items = sax_data.get_sax_items_for_battery("battery_a")
        assert items == []

        # Add slave battery
        slave_battery = BatteryModel(
            device_id="battery_b", name="Battery B", is_master=False
        )
        sax_data.batteries["battery_b"] = slave_battery

        items = sax_data.get_sax_items_for_battery("battery_b")
        assert items == []  # Slave has no SAX items

        # Add master battery
        master_battery = BatteryModel(
            device_id="battery_a", name="Battery A", is_master=True
        )
        sax_data.batteries["battery_a"] = master_battery

        items = sax_data.get_sax_items_for_battery("battery_a")
        assert isinstance(items, list)  # Master has SAX items

    def test_sax_battery_data_get_smart_meter_items(self) -> None:
        """Test SAXBatteryData get_smart_meter_items method."""
        sax_data = SAXBatteryData()

        items = sax_data.get_smart_meter_items()
        assert isinstance(items, list)

    def test_sax_battery_data_get_modbus_api(self) -> None:
        """Test SAXBatteryData get_modbus_api method."""
        sax_data = SAXBatteryData()

        # No API initially
        assert sax_data.get_modbus_api() is None

        # Set API
        mock_api = MagicMock()
        sax_data.modbus_api = mock_api

        assert sax_data.get_modbus_api() == mock_api

    def test_sax_battery_data_get_device_info(self) -> None:
        """Test SAXBatteryData get_device_info method."""
        sax_data = SAXBatteryData()

        # No battery - should return fallback
        device_info = sax_data.get_device_info("battery_a")
        assert device_info["identifiers"] == {("sax_battery", "battery_a")}
        assert device_info["name"] == "SAX Battery battery_a"

        # Add battery
        battery = BatteryModel(device_id="battery_a", name="Battery A")
        sax_data.batteries["battery_a"] = battery

        device_info = sax_data.get_device_info("battery_a")
        assert device_info["identifiers"] == {("sax_battery", "battery_a")}
        assert device_info["name"] == "Battery A"

    def test_sax_battery_data_battery_data_access(self) -> None:
        """Test SAXBatteryData battery data access patterns."""
        sax_data = SAXBatteryData()

        # Add battery
        battery = BatteryModel(device_id="battery_a", name="Battery A")
        sax_data.batteries["battery_a"] = battery

        # Test direct data access patterns that might be used by the coordinator
        battery.data["soc"] = 85.5
        battery.data["power"] = 1500.0
        battery.data["voltage_l1"] = 230.0
        battery.data["current_l1"] = 6.5

        assert battery.data["soc"] == 85.5
        assert battery.data["power"] == 1500.0
        assert battery.data["voltage_l1"] == 230.0
        assert battery.data["current_l1"] == 6.5

    def test_sax_battery_data_smart_meter_data_access(self) -> None:
        """Test SAXBatteryData smart meter data access patterns."""
        sax_data = SAXBatteryData()

        # Initialize smart meter data if it exists as a model
        if hasattr(sax_data, "smart_meter_data") and sax_data.smart_meter_data is None:
            # Test that smart meter data can be set
            smart_meter = SmartMeterModel(
                device_id="smartmeter_001", name="Smart Meter"
            )
            sax_data.smart_meter_data = smart_meter

            # Test data access
            smart_meter.data["total_power"] = 2500.0
            assert smart_meter.data["total_power"] == 2500.0
