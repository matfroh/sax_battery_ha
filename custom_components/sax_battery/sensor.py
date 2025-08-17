"""Sensor platform for SAX Battery integration."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SAX Battery sensors."""
    coordinator: SAXBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    # Create sensors for all data keys from the coordinator
    if coordinator.data:
        entities.extend(SAXBatterySensor(coordinator, key) for key in coordinator.data)

    async_add_entities(entities)


class SAXBatterySensor(CoordinatorEntity, SensorEntity):
    """SAX Battery sensor using coordinator."""

    def __init__(self, coordinator: SAXBatteryCoordinator, data_key: str) -> None:
        """Initialize the SAX Battery sensor."""
        super().__init__(coordinator)
        self._data_key = data_key
        self._attr_unique_id = f"{DOMAIN}_{data_key}"
        self._attr_name = self._get_sensor_name(data_key)
        self._attr_device_class, self._attr_native_unit_of_measurement = self._get_device_class_and_unit(data_key)
        self._attr_state_class = self._get_state_class(data_key)

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "sax_battery_system")},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    def _get_sensor_name(self, key: str) -> str:
        """Get human-readable sensor name."""
        name_mapping = {
            "soc": "State of Charge",
            "status": "Status",
            "power": "Power",
            "smartmeter": "Smart Meter",
            "capacity": "Capacity",
            "cycles": "Cycles",
            "temp": "Temperature",
            "energy_produced": "Energy Produced",
            "energy_consumed": "Energy Consumed",
            "voltage_l1": "Voltage L1",
            "voltage_l2": "Voltage L2",
            "voltage_l3": "Voltage L3",
            "current_l1": "Current L1",
            "current_l2": "Current L2",
            "current_l3": "Current L3",
            "grid_frequency": "Grid Frequency",
            "active_power_l1": "Active Power L1",
            "active_power_l2": "Active Power L2",
            "active_power_l3": "Active Power L3",
            "apparent_power": "Apparent Power",
            "reactive_power": "Reactive Power",
            "power_factor": "Power Factor",
            "phase_currents_sum": "Phase Currents Sum",
            "ac_power_total": "AC Power Total",
            "storage_status": "Storage Status",
            "smartmeter_voltage_l1": "Smart Meter Voltage L1",
            "smartmeter_voltage_l2": "Smart Meter Voltage L2",
            "smartmeter_voltage_l3": "Smart Meter Voltage L3",
            "smartmeter_current_l1": "Smart Meter Current L1",
            "smartmeter_current_l2": "Smart Meter Current L2",
            "smartmeter_current_l3": "Smart Meter Current L3",
            "smartmeter_total_power": "Smart Meter Total Power",
        }
        return name_mapping.get(key, key.replace("_", " ").title())

    def _get_device_class_and_unit(self, key: str) -> tuple[SensorDeviceClass | None, str | None]:
        """Get device class and unit for sensor."""
        mapping = {
            "soc": (SensorDeviceClass.BATTERY, PERCENTAGE),
            "power": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "capacity": (SensorDeviceClass.ENERGY, UnitOfEnergy.WATT_HOUR),
            "temp": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
            "energy_produced": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR),
            "energy_consumed": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR),
            "voltage_l1": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "voltage_l2": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "voltage_l3": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "current_l1": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "current_l2": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "current_l3": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "grid_frequency": (SensorDeviceClass.FREQUENCY, UnitOfFrequency.HERTZ),
            "active_power_l1": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "active_power_l2": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "active_power_l3": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "apparent_power": (SensorDeviceClass.APPARENT_POWER, "VA"),
            "reactive_power": (SensorDeviceClass.REACTIVE_POWER, "VAR"),
            "phase_currents_sum": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "ac_power_total": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "smartmeter_voltage_l1": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "smartmeter_voltage_l2": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "smartmeter_voltage_l3": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "smartmeter_current_l1": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "smartmeter_current_l2": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "smartmeter_current_l3": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "smartmeter_total_power": (SensorDeviceClass.POWER, UnitOfPower.WATT),
        }
        return mapping.get(key, (None, None))

    def _get_state_class(self, key: str) -> SensorStateClass | None:
        """Get state class for sensor."""
        if key in ["energy_produced", "energy_consumed", "cycles"]:
            return SensorStateClass.TOTAL_INCREASING
        if key in ["soc", "power", "temp", "voltage_l1", "voltage_l2", "voltage_l3",
                   "current_l1", "current_l2", "current_l3", "grid_frequency",
                   "active_power_l1", "active_power_l2", "active_power_l3",
                   "apparent_power", "reactive_power", "phase_currents_sum",
                   "ac_power_total", "smartmeter_voltage_l1", "smartmeter_voltage_l2",
                   "smartmeter_voltage_l3", "smartmeter_current_l1", "smartmeter_current_l2",
                   "smartmeter_current_l3", "smartmeter_total_power", "capacity"]:
            return SensorStateClass.MEASUREMENT
        return None

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._data_key in (self.coordinator.data or {})
