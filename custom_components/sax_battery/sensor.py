"""Sensor platform for SAX Battery integration."""

from datetime import datetime
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

from .const import (
    CONF_MASTER_BATTERY,
    DOMAIN,
    SAX_AC_POWER_TOTAL,
    SAX_ACTIVE_POWER_L1,
    SAX_ACTIVE_POWER_L2,
    SAX_ACTIVE_POWER_L3,
    SAX_APPARENT_POWER,
    SAX_CAPACITY,
    SAX_COMBINED_SOC,
    SAX_CURRENT_L1,
    SAX_CURRENT_L2,
    SAX_CURRENT_L3,
    SAX_CYCLES,
    SAX_ENERGY_CONSUMED,
    SAX_ENERGY_PRODUCED,
    SAX_GRID_FREQUENCY,
    SAX_PHASE_CURRENTS_SUM,
    SAX_POWER,
    SAX_POWER_FACTOR,
    SAX_REACTIVE_POWER,
    SAX_SMARTMETER,
    SAX_SMARTMETER_CURRENT_L1,
    SAX_SMARTMETER_CURRENT_L2,
    SAX_SMARTMETER_CURRENT_L3,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SMARTMETER_VOLTAGE_L1,
    SAX_SMARTMETER_VOLTAGE_L2,
    SAX_SMARTMETER_VOLTAGE_L3,
    SAX_SOC,
    SAX_STATUS,
    SAX_STORAGE_STATUS,
    SAX_TEMP,
    SAX_VOLTAGE_L1,
    SAX_VOLTAGE_L2,
    SAX_VOLTAGE_L3,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SAX Battery sensors."""
    sax_battery_data = hass.data[DOMAIN][entry.entry_id]
    master_battery_id = entry.data.get(CONF_MASTER_BATTERY)

    entities: list[SensorEntity] = []

    # Add combined power sensor first
    entities.append(SAXBatteryCombinedPowerSensor(sax_battery_data))
    entities.append(SAXBatteryCombinedSOCSensor(sax_battery_data))

    # Add individual battery sensors
    for battery_id, battery in sax_battery_data.batteries.items():
        entities.extend(
            [
                SAXBatteryStatusSensor(battery, battery_id),
                SAXBatterySOCSensor(battery, battery_id),
                SAXBatteryPowerSensor(battery, battery_id),
                SAXBatterySmartmeterSensor(battery, battery_id),
                SAXBatteryCapacitySensor(battery, battery_id),
                SAXBatteryCyclesSensor(battery, battery_id),
                SAXBatteryTempSensor(battery, battery_id),
                SAXBatteryEnergyProducedSensor(battery, battery_id),
                SAXBatteryEnergyConsumedSensor(battery, battery_id),
                SAXBatteryPhaseCurrentsSumSensor(battery, battery_id),
                SAXBatteryCurrentL1Sensor(battery, battery_id),
                SAXBatteryCurrentL2Sensor(battery, battery_id),
                SAXBatteryCurrentL3Sensor(battery, battery_id),
                SAXBatteryVoltageL1Sensor(battery, battery_id),
                SAXBatteryVoltageL2Sensor(battery, battery_id),
                SAXBatteryVoltageL3Sensor(battery, battery_id),
                SAXBatteryACPowerTotalSensor(battery, battery_id),
                SAXBatteryGridFrequencySensor(battery, battery_id),
                SAXBatteryApparentPowerSensor(battery, battery_id),
                SAXBatteryReactivePowerSensor(battery, battery_id),
                SAXBatteryPowerFactorSensor(battery, battery_id),
                SAXBatteryStorageStatusSensor(battery, battery_id),
                SAXBatteryActivePowerL1Sensor(battery, battery_id),
                SAXBatteryActivePowerL2Sensor(battery, battery_id),
                SAXBatteryActivePowerL3Sensor(battery, battery_id),
                SAXBatterySmartmeterCurrentL1Sensor(battery, battery_id),
                SAXBatterySmartmeterCurrentL2Sensor(battery, battery_id),
                SAXBatterySmartmeterCurrentL3Sensor(battery, battery_id),
                SAXBatterySmartmeterVoltageL1Sensor(battery, battery_id),
                SAXBatterySmartmeterVoltageL2Sensor(battery, battery_id),
                SAXBatterySmartmeterVoltageL3Sensor(battery, battery_id),
                SAXBatterySmartmeterTotalPowerSensor(battery, battery_id),
            ]
        )

        # Add cumulative energy sensors only for the master battery
        if battery_id == master_battery_id:
            entities.extend(
                [
                    SAXBatteryCumulativeEnergyProducedSensor(battery, battery_id),
                    SAXBatteryCumulativeEnergyConsumedSensor(battery, battery_id),
                ]
            )

    async_add_entities(entities)


class SAXBatterySensor(SensorEntity):
    """Base class for SAX Battery sensors."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the SAX Battery sensor."""
        self.battery = battery
        self._battery_id = battery_id
        self._attr_unique_id = (
            f"{DOMAIN}_{self._battery_id}_{self.__class__.__name__.lower()}"
        )

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.battery._data_manager.device_id)},  # noqa: SLF001
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    def convertToSignedValue(self,value,scale):
        """Some values are not returned in a properly signed form by the battery. Negative values appear as very high positive numbers"""
        max_value = 65536 * scale # for int16 values (2^16 = 65536)
        if (value > max_value / 2):
            return value - max_value # value is actually negative
        return value # value is positive, return it unchanged

    async def async_update(self) -> None:
        """Update the sensor."""
        await self.battery.async_update()


class SAXBatteryStatusSensor(SAXBatterySensor):
    """SAX Battery Status sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Status"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_STATUS)


class SAXBatterySOCSensor(SAXBatterySensor):
    """SAX Battery State of Charge (SOC) sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} SOC"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SOC)


class SAXBatteryPowerSensor(SAXBatterySensor):
    """SAX Battery Power sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Power"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_POWER)


class SAXBatterySmartmeterSensor(SAXBatterySensor):
    """SAX Battery Smartmeter sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Smartmeter"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER)


class SAXBatteryCapacitySensor(SAXBatterySensor):
    """SAX Battery Capacity sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Capacity"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_CAPACITY)


class SAXBatteryCyclesSensor(SAXBatterySensor):
    """SAX Battery Cycles sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Cycles"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_CYCLES)


class SAXBatteryTempSensor(SAXBatterySensor):
    """SAX Battery Temperature sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Temperature"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_TEMP)


class SAXBatteryEnergyProducedSensor(SAXBatterySensor):
    """SAX Battery Energy Produced sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Energy Produced"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_ENERGY_PRODUCED)


class SAXBatteryEnergyConsumedSensor(SAXBatterySensor):
    """SAX Battery Energy Consumed sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Energy Consumed"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_ENERGY_CONSUMED)


class SAXBatteryCumulativeEnergyProducedSensor(SAXBatterySensor):
    """SAX Battery Cumulative Energy Produced sensor from master battery."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = "Sax Battery Cumulative Energy going into the battery"
        self._attr_unique_id = f"{DOMAIN}_cumulative_energy_produced"
        self._last_update_time: datetime | None = None
        self._cumulative_value = 0

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._cumulative_value

    async def async_update(self) -> None:
        """Update the sensor."""
        await super().async_update()

        # Get current time
        current_time = datetime.now()

        # Only update the cumulative value once per hour
        if (
            self._last_update_time is None
            or (current_time - self._last_update_time).total_seconds() >= 3600
        ):  # 3600 seconds = 1 hour
            # Get the current energy produced value
            current_value = self.battery.data.get(SAX_ENERGY_PRODUCED, 0)

            if current_value is not None:
                # Update the cumulative value
                self._cumulative_value += current_value

                # Update the last update time
                self._last_update_time = current_time


class SAXBatteryCumulativeEnergyConsumedSensor(SAXBatterySensor):
    """SAX Battery Cumulative Energy Consumed sensor from master battery."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = "Sax Battery Cumulative Energy coming out of the battery"
        self._attr_unique_id = f"{DOMAIN}_cumulative_energy_consumed"
        self._last_update_time: datetime | None = None
        self._cumulative_value = 0

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._cumulative_value

    async def async_update(self) -> None:
        """Update the sensor."""
        await super().async_update()

        # Get current time
        current_time = datetime.now()

        # Only update the cumulative value once per hour
        if (
            self._last_update_time is None
            or (current_time - self._last_update_time).total_seconds() >= 3600
        ):  # 3600 seconds = 1 hour
            # Get the current energy consumed value
            current_value = self.battery.data.get(SAX_ENERGY_CONSUMED, 0)

            if current_value is not None:
                # Update the cumulative value
                self._cumulative_value += current_value

                # Update the last update time
                self._last_update_time = current_time


class SAXBatteryCombinedPowerSensor(SensorEntity):
    """Combined power sensor for all SAX Batteries."""

    def __init__(self, sax_battery_data: Any) -> None:
        """Initialize the sensor."""
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_combined_power"
        self._attr_name = "Sax Battery Combined Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

        # Add device info to group with other sensors
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    async def async_update(self) -> None:
        """Update the sensor."""
        # Update all batteries first
        for battery in self._data_manager.batteries.values():
            await battery.async_update()

        # Calculate combined power
        total_power = 0
        for battery in self._data_manager.batteries.values():
            power = battery.data.get(SAX_POWER, 0)
            if power is not None:
                total_power += power

        self._attr_native_value = total_power


class SAXBatteryCombinedSOCSensor(SensorEntity):
    """Combined State of Charge (SOC) sensor for all SAX Batteries."""

    def __init__(self, sax_battery_data: Any) -> None:
        """Initialize the sensor."""
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_combined_soc"
        self._attr_name = "Sax Battery Combined SOC"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

        # Add device info to group with other sensors
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    async def async_update(self) -> None:
        """Update the sensor."""
        # Update all batteries first
        for battery in self._data_manager.batteries.values():
            await battery.async_update()

        # Calculate average SOC
        total_soc = 0
        valid_batteries = 0

        for battery in self._data_manager.batteries.values():
            soc = battery.data.get(SAX_SOC)
            if soc is not None:
                total_soc += soc
                valid_batteries += 1

        # Only update if we have valid SOC data
        if valid_batteries > 0:
            combined_soc = round(total_soc / valid_batteries, 1)
            self._attr_native_value = combined_soc

            # Store the combined SOC in the data manager
            if not hasattr(self._data_manager, "combined_data"):
                self._data_manager.combined_data = {}
            self._data_manager.combined_data[SAX_COMBINED_SOC] = combined_soc
        else:
            self._attr_native_value = None
            if hasattr(self._data_manager, "combined_data"):
                self._data_manager.combined_data[SAX_COMBINED_SOC] = None


class SAXBatteryPhaseCurrentsSumSensor(SAXBatterySensor):
    """SAX Battery Sum of Phase Currents sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Phase Currents Sum"
        )

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_PHASE_CURRENTS_SUM)


class SAXBatteryCurrentL1Sensor(SAXBatterySensor):
    """SAX Battery Current L1 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Current L1"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_CURRENT_L1)


class SAXBatteryCurrentL2Sensor(SAXBatterySensor):
    """SAX Battery Current L2 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Current L2"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_CURRENT_L2)


class SAXBatteryCurrentL3Sensor(SAXBatterySensor):
    """SAX Battery Current L3 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Current L3"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_CURRENT_L3)


class SAXBatteryVoltageL1Sensor(SAXBatterySensor):
    """SAX Battery Voltage L1 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Voltage L1"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_VOLTAGE_L1)


class SAXBatteryVoltageL2Sensor(SAXBatterySensor):
    """SAX Battery Voltage L2 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Voltage L2"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_VOLTAGE_L2)


class SAXBatteryVoltageL3Sensor(SAXBatterySensor):
    """SAX Battery Voltage L3 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Voltage L3"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_VOLTAGE_L3)


class SAXBatteryACPowerTotalSensor(SAXBatterySensor):
    """SAX Battery AC Power Total sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} AC Power Total"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""


class SAXBatteryGridFrequencySensor(SAXBatterySensor):
    """SAX Battery Grid Frequency sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.FREQUENCY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Grid Frequency"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_GRID_FREQUENCY)


class SAXBatteryApparentPowerSensor(SAXBatterySensor):
    """SAX Battery Apparent Power sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.APPARENT_POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "VA"  # Volt-Ampere
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Apparent Power"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_APPARENT_POWER)


class SAXBatteryReactivePowerSensor(SAXBatterySensor):
    """SAX Battery Reactive Power sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.REACTIVE_POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "var"  # Volt-Ampere Reactive
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Reactive Power"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        value= self.battery.data.get(SAX_REACTIVE_POWER)
        return self.convertToSignedValue(value, 10)


class SAXBatteryPowerFactorSensor(SAXBatterySensor):
    """SAX Battery Power Factor sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER_FACTOR
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Power Factor"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_POWER_FACTOR)


class SAXBatteryStorageStatusSensor(SAXBatterySensor):
    """SAX Battery Storage Status sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Storage Status"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        status_value = self.battery.data.get(SAX_STORAGE_STATUS)
        if status_value is None:
            return None

        # Map status value to text representation
        status_map = {1: "OFF", 2: "ON", 3: "Connected", 4: "Standby"}
        return status_map.get(status_value, f"Unknown ({status_value})")


class SAXBatterySmartmeterCurrentL1Sensor(SAXBatterySensor):
    """SAX Battery Current L1 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Smartmeter Current L1"
        )

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER_CURRENT_L1)


class SAXBatterySmartmeterCurrentL2Sensor(SAXBatterySensor):
    """SAX Battery Current L2 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Smartmeter Current L2"
        )

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER_CURRENT_L2)


class SAXBatterySmartmeterCurrentL3Sensor(SAXBatterySensor):
    """SAX Battery Current L3 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Smartmeter Current L3"
        )

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER_CURRENT_L3)


class SAXBatteryActivePowerL1Sensor(SAXBatterySensor):
    """SAX Battery Active Power L1 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Active Power L1"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        value = self.battery.data.get(SAX_ACTIVE_POWER_L1)
        return self.convertToSignedValue(value, 10)


class SAXBatteryActivePowerL2Sensor(SAXBatterySensor):
    """SAX Battery Active Power L2 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Active Power L2"

    #       self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        value = self.battery.data.get(SAX_ACTIVE_POWER_L2)
        return self.convertToSignedValue(value, 10)


class SAXBatteryActivePowerL3Sensor(SAXBatterySensor):
    """SAX Battery Active Power L3 sensor."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} Active Power L3"

    #        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        value = self.battery.data.get(SAX_ACTIVE_POWER_L3)
        return self.convertToSignedValue(value, 10)


class SAXBatterySmartmeterVoltageL1Sensor(SAXBatterySensor):
    """Smartmeter Voltage L1 sensor for the SAX Battery system."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Smartmeter Voltage L1"
        )
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER_VOLTAGE_L1)


class SAXBatterySmartmeterVoltageL2Sensor(SAXBatterySensor):
    """Smartmeter Voltage L2 sensor for the SAX Battery system."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Smartmeter Voltage L2"
        )
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER_VOLTAGE_L2)


class SAXBatterySmartmeterVoltageL3Sensor(SAXBatterySensor):
    """Smartmeter Voltage L3 sensor for the SAX Battery system."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Smartmeter Voltage L3"
        )
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER_VOLTAGE_L3)


class SAXBatterySmartmeterTotalPowerSensor(SAXBatterySensor):
    """Smartmeter Total Power for the SAX Battery system."""

    def __init__(self, battery: Any, battery_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(battery, battery_id)
        self._attr_name = (
            f"Sax {battery_id.replace('_', ' ').title()} Smartmeter Total Power"
        )
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_entity_registry_enabled_default = False  # Disabled by default

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self.battery.data.get(SAX_SMARTMETER_TOTAL_POWER)
