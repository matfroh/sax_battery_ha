"""Sensor platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MASTER_BATTERY,
    DEFAULT_DEVICE_INFO,
    DOMAIN,
    MODBUS_BATTERY_ITEMS,
    SAX_POWER,
    SAX_SOC,
    SENSOR_TYPES,
    TypeConstants,
)
from .models import SAXBatteryData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SAX Battery sensors."""
    sax_data: SAXBatteryData = hass.data[DOMAIN][entry.entry_id]
    master_battery_id = entry.data.get(CONF_MASTER_BATTERY)

    entities: list[SensorEntity] = []

    # Add combined sensors
    entities.append(SAXBatteryCombinedPowerSensor(sax_data))
    entities.append(SAXBatteryCombinedSOCSensor(sax_data))

    # Add individual battery sensors based on SENSOR_TYPES and MODBUS_BATTERY_ITEMS
    for battery_id in sax_data.batteries:
        # Create sensors for each sensor type that's also in MODBUS_BATTERY_ITEMS
        sensor_entities = [
            SAXBatteryGenericSensor(
                sax_data, battery_id, item.name, SENSOR_TYPES[item.name]
            )
            for item in MODBUS_BATTERY_ITEMS
            if item.name in SENSOR_TYPES and item.type == TypeConstants.SENSOR
        ]
        entities.extend(sensor_entities)

        # Add cumulative energy sensors only for the master battery
        if battery_id == master_battery_id:
            entities.extend(
                [
                    SAXBatteryCumulativeEnergyProducedSensor(sax_data, battery_id),
                    SAXBatteryCumulativeEnergyConsumedSensor(sax_data, battery_id),
                ]
            )

    async_add_entities(entities)


class SAXBatterySensorBase(CoordinatorEntity, SensorEntity):
    """Base class for SAX Battery sensors."""

    def __init__(self, sax_data: SAXBatteryData, battery_id: str) -> None:
        """Initialize the SAX Battery sensor."""
        coordinator = sax_data.coordinator
        if coordinator is None:
            raise ValueError("Coordinator is required but not available")
        super().__init__(coordinator)
        self._sax_data = sax_data
        self._battery_id = battery_id
        self._battery = sax_data.batteries.get(battery_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._sax_data.device_id or "unknown")},
            name=DEFAULT_DEVICE_INFO.name,
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )


class SAXBatteryGenericSensor(SAXBatterySensorBase):
    """Generic SAX Battery sensor based on entity description."""

    def __init__(
        self,
        sax_data: SAXBatteryData,
        battery_id: str,
        sensor_key: str,
        entity_description: Any,
    ) -> None:
        """Initialize the generic sensor."""
        super().__init__(sax_data, battery_id)
        self.entity_description = entity_description
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{DOMAIN}_{self._battery_id}_{sensor_key}"
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} {entity_description.name.replace('SAX Battery ', '')}"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._battery:
            return self._battery.data.get(self._sensor_key)
        return None


class SAXBatteryCombinedPowerSensor(SAXBatterySensorBase):
    """SAX Battery Combined Power sensor."""

    def __init__(self, sax_data: SAXBatteryData) -> None:
        """Initialize the sensor."""
        super().__init__(sax_data, "combined")
        self._attr_name = "SAX Battery Combined Power"
        self._attr_unique_id = f"{DOMAIN}_combined_power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if not self._sax_data.batteries:
            return None

        total_power = 0
        for battery in self._sax_data.batteries.values():
            power = battery.data.get(SAX_POWER)
            if power is not None:
                total_power += power
        return total_power


class SAXBatteryCombinedSOCSensor(SAXBatterySensorBase):
    """SAX Battery Combined SOC sensor."""

    def __init__(self, sax_data: SAXBatteryData) -> None:
        """Initialize the sensor."""
        super().__init__(sax_data, "combined")
        self._attr_name = "SAX Battery Combined SOC"
        self._attr_unique_id = f"{DOMAIN}_combined_soc"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if not self._sax_data.batteries:
            return None

        total_soc = 0
        battery_count = 0
        for battery in self._sax_data.batteries.values():
            soc = battery.data.get(SAX_SOC)
            if soc is not None:
                total_soc += soc
                battery_count += 1

        if battery_count == 0:
            return None

        return total_soc / battery_count


class SAXBatteryCumulativeEnergyProducedSensor(SAXBatterySensorBase):
    """SAX Battery Cumulative Energy Produced sensor."""

    def __init__(self, sax_data: SAXBatteryData, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(sax_data, battery_id)
        self._attr_name = f"SAX Battery {battery_id.replace('_', ' ').title()} Cumulative Energy Produced"
        self._attr_unique_id = f"{DOMAIN}_{battery_id}_cumulative_energy_produced"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._cumulative_energy_produced = 0

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if not self._battery:
            return None

        energy_produced = self._battery.data.get("sax_energy_produced")
        if energy_produced is not None:
            self._cumulative_energy_produced += energy_produced
        return self._cumulative_energy_produced


class SAXBatteryCumulativeEnergyConsumedSensor(SAXBatterySensorBase):
    """SAX Battery Cumulative Energy Consumed sensor."""

    def __init__(self, sax_data: SAXBatteryData, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(sax_data, battery_id)
        self._attr_name = f"SAX Battery {battery_id.replace('_', ' ').title()} Cumulative Energy Consumed"
        self._attr_unique_id = f"{DOMAIN}_{battery_id}_cumulative_energy_consumed"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._cumulative_energy_consumed = 0

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if not self._battery:
            return None

        energy_consumed = self._battery.data.get("sax_energy_consumed")
        if energy_consumed is not None:
            self._cumulative_energy_consumed += energy_consumed
        return self._cumulative_energy_consumed
