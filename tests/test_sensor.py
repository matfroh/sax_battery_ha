"""Test SAX Battery sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sax_battery.const import (
    DESCRIPTION_SAX_SOC,
    DESCRIPTION_SAX_TEMP,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.sensor import SAXBatterySensor
from homeassistant.components.sensor import SensorEntityDescription


@pytest.fixture
def mock_coordinator():
    """Create mock coordinator."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.last_update_success = True
    coordinator.last_update_success_time = "2024-01-01T00:00:00+00:00"
    coordinator.data = {
        "sax_temperature": 25.5,
        "sax_soc": 80,
        "sax_power": 1500,
        "sax_charge_power": 0,
        "sax_discharge_power": 1500,
    }

    # Mock the sax_data attribute and its methods
    mock_sax_data = MagicMock()
    mock_sax_data.get_device_info.return_value = {
        "identifiers": {("sax_battery", "battery_a")},
        "name": "SAX Battery A",
        "manufacturer": "SAX",
        "model": "SAX Battery",
    }
    coordinator.sax_data = mock_sax_data
    return coordinator


@pytest.fixture
def temperature_item():
    """Create temperature sensor item."""
    return ModbusItem(
        address=100,
        name="sax_temperature",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
        entitydescription=DESCRIPTION_SAX_TEMP,
    )


@pytest.fixture
def percentage_item():
    """Create percentage sensor item."""
    return ModbusItem(
        address=101,
        name="sax_soc",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
        entitydescription=DESCRIPTION_SAX_SOC,
    )


class TestSAXBatterySensor:
    """Test SAX Battery sensor."""

    def test_sensor_init(self, mock_coordinator, temperature_item) -> None:
        """Test sensor initialization."""
        sensor = SAXBatterySensor(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=temperature_item,
            index=0,
        )

        assert sensor._battery_id == "battery_a"
        assert sensor._modbus_item == temperature_item
        assert sensor.unique_id == "battery_a_sax_temperature_0"
        assert sensor.name == "Sax Battery A Temperature"
        if isinstance(sensor._modbus_item.entitydescription, SensorEntityDescription):
            assert (
                sensor._modbus_item.entitydescription.native_unit_of_measurement == "°C"
            )

    def test_sensor_native_value(self, mock_coordinator, temperature_item) -> None:
        """Test sensor native value."""
        sensor = SAXBatterySensor(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=temperature_item,
            index=0,
        )

        assert sensor.native_value == 25.5

    def test_sensor_native_value_with_divider(
        self, mock_coordinator, percentage_item
    ) -> None:
        """Test sensor native value with divider."""
        percentage_item.divider = 10
        mock_coordinator.data["sax_soc"] = 800  # Raw value

        sensor = SAXBatterySensor(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=percentage_item,
            index=0,
        )

        assert sensor.native_value == 80.0  # 800 / 10
        if isinstance(sensor._modbus_item.entitydescription, SensorEntityDescription):
            assert (
                sensor._modbus_item.entitydescription.native_unit_of_measurement == "%"
            )

    def test_sensor_unavailable_when_coordinator_failed(
        self, mock_coordinator, temperature_item
    ) -> None:
        """Test sensor returns None when coordinator update failed."""
        mock_coordinator.last_update_success = False

        sensor = SAXBatterySensor(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=temperature_item,
            index=0,
        )

        assert sensor.native_value == 25.5

    def test_sensor_state_class_determination(self, mock_coordinator) -> None:
        """Test state class determination."""
        temperature_item = ModbusItem(
            name="sax_temperature",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
        )

        sensor = SAXBatterySensor(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=temperature_item,
            index=0,
        )

        assert (
            sensor.state_class is None
        )  # No state class when no description is provided

    def test_sensor_extra_state_attributes(
        self, mock_coordinator, temperature_item
    ) -> None:
        """Test sensor extra state attributes."""
        sensor = SAXBatterySensor(
            coordinator=mock_coordinator,
            battery_id="battery_a",
            modbus_item=temperature_item,
            index=0,
        )

        attributes = sensor.extra_state_attributes
        assert attributes is not None
        assert attributes["battery_id"] == "battery_a"
        assert attributes["modbus_address"] == 100
        assert "last_update" in attributes
