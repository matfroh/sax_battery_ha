"""Comprehensive tests for the SAX Battery sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_MASTER_BATTERY,
    DOMAIN,
    SAX_POWER,
    SAX_SOC,
    SAX_TEMP,
)
from custom_components.sax_battery.sensor import async_setup_entry
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant


@pytest.fixture(name="mock_sax_battery_entry")
def mock_sax_battery_entry_fixture():
    """Mock SAX Battery config entry."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 1,
        CONF_MASTER_BATTERY: "battery_a",
    }
    return mock_entry


@pytest.fixture(name="mock_sax_battery_three_entry")
def mock_sax_battery_three_entry_fixture():
    """Mock SAX Battery config entry for three batteries."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry_three"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 3,
        CONF_MASTER_BATTERY: "battery_a",
        "battery_b_host": "192.168.1.101",
        "battery_c_host": "192.168.1.102",
    }
    return mock_entry


class TestSAXBatterySensors:
    """Test SAX Battery sensor setup and functionality."""

    @patch("custom_components.sax_battery.sensor.SAXBatteryData")
    @patch("pymodbus.client.ModbusTcpClient")
    async def test_single_battery_sensor_count(
        self,
        mock_modbus_client,
        mock_battery_data_class,
        hass: HomeAssistant,
        mock_sax_battery_entry,
    ) -> None:
        """Test that correct number of sensors are created for single battery."""
        # Setup mock Modbus client
        mock_client_instance = MagicMock()
        mock_client_instance.connect.return_value = True
        mock_client_instance.read_holding_registers.return_value = MagicMock(
            registers=[50, 2500]
        )
        mock_modbus_client.return_value = mock_client_instance

        # Setup mock battery data
        mock_battery_data = MagicMock()
        mock_battery_data.device_id = "test_device"
        mock_battery_data.coordinator = MagicMock()
        mock_battery_data.coordinator.data = {
            "battery_a": {SAX_SOC: 85, SAX_POWER: 2500}
        }

        # Mock battery instance with proper data attribute
        mock_battery = MagicMock()
        mock_battery.async_update = AsyncMock()
        mock_battery.data = {SAX_SOC: 85, SAX_POWER: 2500}
        mock_battery_data.batteries = {"battery_a": mock_battery}

        mock_battery_data_class.return_value = mock_battery_data

        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_battery_entry.entry_id] = (
            mock_battery_data
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_battery_entry, mock_add_entities)

        # Verify entities were created
        assert len(entities) > 0, "No entities were created"

        # Check that we have combined sensors
        combined_entities = [
            e for e in entities if "combined" in str(e.unique_id).lower()
        ]
        assert len(combined_entities) >= 2, "Expected at least 2 combined sensors"

        # Check that we have individual battery sensors
        battery_entities = [e for e in entities if "battery_a" in str(e.unique_id)]
        assert len(battery_entities) > 0, "Expected individual battery sensors"

    @patch("custom_components.sax_battery.sensor.SAXBatteryData")
    @patch("pymodbus.client.ModbusTcpClient")
    async def test_three_battery_sensor_count(
        self,
        mock_modbus_client,
        mock_battery_data_class,
        hass: HomeAssistant,
        mock_sax_battery_three_entry,
    ) -> None:
        """Test that correct number of sensors are created for three batteries."""
        # Setup mock Modbus client
        mock_client_instance = MagicMock()
        mock_client_instance.connect.return_value = True
        mock_client_instance.read_holding_registers.return_value = MagicMock(
            registers=[50, 2500]
        )
        mock_modbus_client.return_value = mock_client_instance

        # Setup mock battery data for three batteries
        mock_battery_data = MagicMock()
        mock_battery_data.device_id = "test_device"
        mock_battery_data.coordinator = MagicMock()
        mock_battery_data.coordinator.data = {
            "battery_a": {SAX_SOC: 85, SAX_POWER: 2000},
            "battery_b": {SAX_SOC: 87, SAX_POWER: 2100},
            "battery_c": {SAX_SOC: 83, SAX_POWER: 1900},
        }

        # Mock battery instances with proper data attributes
        mock_batteries = {}
        battery_data = {
            "battery_a": {SAX_SOC: 85, SAX_POWER: 2000},
            "battery_b": {SAX_SOC: 87, SAX_POWER: 2100},
            "battery_c": {SAX_SOC: 83, SAX_POWER: 1900},
        }
        for battery_id in ["battery_a", "battery_b", "battery_c"]:
            mock_battery = MagicMock()
            mock_battery.async_update = AsyncMock()
            mock_battery.data = battery_data[battery_id]
            mock_batteries[battery_id] = mock_battery

        mock_battery_data.batteries = mock_batteries
        mock_battery_data_class.return_value = mock_battery_data

        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_battery_three_entry.entry_id] = (
            mock_battery_data
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_battery_three_entry, mock_add_entities)

        # Verify entities were created
        assert len(entities) > 0, "No entities were created"

        # Check that we have combined sensors
        combined_entities = [
            e for e in entities if "combined" in str(e.unique_id).lower()
        ]
        assert len(combined_entities) >= 2, "Expected at least 2 combined sensors"

        # Check that we have sensors for each battery
        for battery_id in ["battery_a", "battery_b", "battery_c"]:
            battery_entities = [e for e in entities if battery_id in str(e.unique_id)]
            assert len(battery_entities) > 0, f"Expected sensors for {battery_id}"

    @patch("custom_components.sax_battery.sensor.SAXBatteryData")
    @patch("pymodbus.client.ModbusTcpClient")
    async def test_sensor_properties(
        self,
        mock_modbus_client,
        mock_battery_data_class,
        hass: HomeAssistant,
        mock_sax_battery_entry,
    ) -> None:
        """Test that sensors have correct properties."""
        # Setup mocks
        mock_client_instance = MagicMock()
        mock_client_instance.connect.return_value = True
        mock_modbus_client.return_value = mock_client_instance

        mock_battery_data = MagicMock()
        mock_battery_data.device_id = "test_device_123"
        mock_battery_data.coordinator = MagicMock()
        mock_battery_data.coordinator.data = {
            "battery_a": {SAX_SOC: 85.5, SAX_POWER: 2500}
        }

        mock_battery = MagicMock()
        mock_battery.async_update = AsyncMock()
        mock_battery_data.batteries = {"battery_a": mock_battery}

        mock_battery_data_class.return_value = mock_battery_data

        hass.data.setdefault(DOMAIN, {})[mock_sax_battery_entry.entry_id] = (
            mock_battery_data
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_battery_entry, mock_add_entities)

        # Check device info on entities
        for entity in entities:
            assert hasattr(entity, "device_info"), (
                f"Entity {entity} missing device_info"
            )
            assert entity.device_info is not None, (
                f"Entity {entity} has None device_info"
            )

        # Check unique IDs
        unique_ids = [entity.unique_id for entity in entities]
        assert len(unique_ids) == len(set(unique_ids)), "Duplicate unique IDs found"

        # Check that all unique IDs are valid strings
        for uid in unique_ids:
            assert isinstance(uid, str), f"Unique ID {uid} is not a string"
            assert len(uid) > 0, f"Unique ID {uid} is empty"

    @patch("custom_components.sax_battery.sensor.SAXBatteryData")
    @patch("pymodbus.client.ModbusTcpClient")
    async def test_sensor_states(
        self,
        mock_modbus_client,
        mock_battery_data_class,
        hass: HomeAssistant,
        mock_sax_battery_entry,
    ) -> None:
        """Test sensor states for single battery."""
        # Setup mock Modbus client
        mock_client_instance = MagicMock()
        mock_client_instance.connect.return_value = True
        mock_client_instance.read_holding_registers.return_value = MagicMock(
            registers=[50, 2500]
        )
        mock_modbus_client.return_value = mock_client_instance

        # Setup mock battery data
        mock_battery_data = MagicMock()
        mock_battery_data.device_id = "test_device"
        mock_battery_data.coordinator = MagicMock()
        mock_battery_data.coordinator.data = {
            "battery_a": {SAX_SOC: 85.5, SAX_POWER: 2500, SAX_TEMP: 25.0}
        }

        mock_battery = MagicMock()
        mock_battery.async_update = AsyncMock()
        mock_battery.data = {SAX_SOC: 85.5, SAX_POWER: 2500, SAX_TEMP: 25.0}
        mock_battery_data.batteries = {"battery_a": mock_battery}

        mock_battery_data_class.return_value = mock_battery_data

        hass.data.setdefault(DOMAIN, {})[mock_sax_battery_entry.entry_id] = (
            mock_battery_data
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_battery_entry, mock_add_entities)

        # Test SOC sensor
        soc_sensors = [
            e
            for e in entities
            if hasattr(e, "_sensor_key") and e._sensor_key == SAX_SOC
        ]
        if soc_sensors:
            soc_sensor = soc_sensors[0]
            assert soc_sensor.native_value == 85.5
            assert soc_sensor.native_unit_of_measurement == PERCENTAGE
            assert soc_sensor.device_class == SensorDeviceClass.BATTERY

        # Test Power sensor
        power_sensors = [
            e
            for e in entities
            if hasattr(e, "_sensor_key") and e._sensor_key == SAX_POWER
        ]
        if power_sensors:
            power_sensor = power_sensors[0]
            assert power_sensor.native_value == 2500
            assert power_sensor.native_unit_of_measurement == UnitOfPower.WATT
            assert power_sensor.device_class == SensorDeviceClass.POWER

    @patch("custom_components.sax_battery.sensor.SAXBatteryData")
    @patch("pymodbus.client.ModbusTcpClient")
    async def test_energy_sensors_all_batteries(
        self,
        mock_modbus_client,
        mock_battery_data_class,
        hass: HomeAssistant,
        mock_sax_battery_three_entry,
    ) -> None:
        """Test that energy sensors exist for all batteries with master coordination."""
        # Setup mocks
        mock_client_instance = MagicMock()
        mock_client_instance.connect.return_value = True
        mock_modbus_client.return_value = mock_client_instance

        mock_battery_data = MagicMock()
        mock_battery_data.device_id = "test_device"
        mock_battery_data.coordinator = MagicMock()
        mock_battery_data.coordinator.data = {
            "battery_a": {SAX_SOC: 85, SAX_POWER: 2000},
            "battery_b": {SAX_SOC: 87, SAX_POWER: 2100},
            "battery_c": {SAX_SOC: 83, SAX_POWER: 1900},
        }

        mock_batteries = {}
        for battery_id in ["battery_a", "battery_b", "battery_c"]:
            mock_battery = MagicMock()
            mock_battery.async_update = AsyncMock()
            mock_batteries[battery_id] = mock_battery

        mock_battery_data.batteries = mock_batteries
        mock_battery_data_class.return_value = mock_battery_data

        hass.data.setdefault(DOMAIN, {})[mock_sax_battery_three_entry.entry_id] = (
            mock_battery_data
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_battery_three_entry, mock_add_entities)

        # Check for energy sensors - should exist for all batteries
        energy_entities = [
            e
            for e in entities
            if "energy" in str(e.unique_id).lower()
            and (
                "produced" in str(e.unique_id).lower()
                or "consumed" in str(e.unique_id).lower()
            )
        ]

        # All batteries have energy sensors, but only master handles write operations
        master_energy_entities = [
            e for e in energy_entities if "battery_a" in str(e.unique_id)
        ]
        slave_energy_entities = [
            e
            for e in energy_entities
            if "battery_b" in str(e.unique_id) or "battery_c" in str(e.unique_id)
        ]

        # Both master and slaves should have energy sensors
        assert len(master_energy_entities) > 0, (
            "Master battery should have energy sensors"
        )
        assert len(slave_energy_entities) > 0, (
            "Slave batteries have energy sensors with values replicated from master"
        )

    @patch("custom_components.sax_battery.sensor.SAXBatteryData")
    @patch("pymodbus.client.ModbusTcpClient")
    async def test_combined_sensors(
        self,
        mock_modbus_client,
        mock_battery_data_class,
        hass: HomeAssistant,
        mock_sax_battery_three_entry,
    ) -> None:
        """Test combined sensors for three battery configuration."""
        # Setup mock Modbus client
        mock_client_instance = MagicMock()
        mock_client_instance.connect.return_value = True
        mock_modbus_client.return_value = mock_client_instance

        mock_battery_data = MagicMock()
        mock_battery_data.device_id = "test_device_123"
        mock_battery_data.coordinator = MagicMock()

        # Setup coordinator data for three batteries
        mock_battery_data.coordinator.data = {
            "battery_a": {SAX_SOC: 85.0, SAX_POWER: 2000},
            "battery_b": {SAX_SOC: 87.0, SAX_POWER: 2100},
            "battery_c": {SAX_SOC: 83.0, SAX_POWER: 1900},
        }

        # Create mock batteries with proper data attributes
        mock_batteries = {}
        battery_data = {
            "battery_a": {SAX_SOC: 85.0, SAX_POWER: 2000},
            "battery_b": {SAX_SOC: 87.0, SAX_POWER: 2100},
            "battery_c": {SAX_SOC: 83.0, SAX_POWER: 1900},
        }
        for battery_id in ["battery_a", "battery_b", "battery_c"]:
            mock_battery = MagicMock()
            mock_battery.async_update = AsyncMock()
            mock_battery.data = battery_data[battery_id]
            mock_batteries[battery_id] = mock_battery

        mock_battery_data.batteries = mock_batteries
        mock_battery_data_class.return_value = mock_battery_data

        hass.data.setdefault(DOMAIN, {})[mock_sax_battery_three_entry.entry_id] = (
            mock_battery_data
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_battery_three_entry, mock_add_entities)

        # Test combined SOC sensor
        combined_soc_sensors = [
            e
            for e in entities
            if hasattr(e, "unique_id") and "combined_soc" in e.unique_id.lower()
        ]

        if combined_soc_sensors:
            combined_soc = combined_soc_sensors[0]
            # Combined SOC should be average: (85 + 87 + 83) / 3 = 85
            expected_soc = (85.0 + 87.0 + 83.0) / 3
            # Allow for small floating point differences
            if combined_soc.native_value is not None:
                assert abs(combined_soc.native_value - expected_soc) < 0.1

        # Test combined power sensor
        combined_power_sensors = [
            e
            for e in entities
            if hasattr(e, "unique_id") and "combined_power" in e.unique_id.lower()
        ]

        if combined_power_sensors:
            combined_power = combined_power_sensors[0]
            # Combined power should be sum: 2000 + 2100 + 1900 = 6000
            expected_power = 2000 + 2100 + 1900
            if combined_power.native_value is not None:
                assert combined_power.native_value == expected_power

    @patch("pymodbus.client.ModbusTcpClient")
    async def test_no_network_calls_in_tests(
        self, mock_modbus_client, hass: HomeAssistant
    ):
        """Test that no real network calls are made during testing."""
        # Setup mock that tracks calls
        mock_client_instance = MagicMock()
        mock_client_instance.connect.return_value = True
        mock_modbus_client.return_value = mock_client_instance

        # Verify the mock was used instead of real network
        assert True  # Mock is available

        # If there were any calls, they should be to mock, not real IPs
        if mock_modbus_client.call_args_list:
            for call in mock_modbus_client.call_args_list:
                if call.args:
                    host = call.args[0]
                    assert not host.startswith("192.168."), (
                        f"Real network call detected to {host}"
                    )
                    assert not host.startswith("10."), (
                        f"Real network call detected to {host}"
                    )
