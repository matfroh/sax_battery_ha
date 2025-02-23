"""Sensor platform for SAX Battery integration."""
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass
)
from homeassistant.const import (
    UnitOfPower,
    UnitOfEnergy,
    UnitOfTemperature,
    PERCENTAGE,
)
from .const import (
    DOMAIN,
    SAX_STATUS,
    SAX_SOC,
    SAX_POWER,
    SAX_SMARTMETER,
    SAX_CAPACITY,
    SAX_CYCLES,
    SAX_TEMP,
    SAX_ENERGY_PRODUCED,
    SAX_ENERGY_CONSUMED,
    SAX_COMBINED_POWER,
)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the SAX Battery sensors."""
    sax_battery_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []

    # Add combined power sensor first
    entities.append(SAXBatteryCombinedPowerSensor(sax_battery_data))
    
    # Add individual battery sensors
    for battery_id, battery in sax_battery_data.batteries.items():
        entities.extend([
            SAXBatteryStatusSensor(battery, battery_id),
            SAXBatterySOCSensor(battery, battery_id),
            SAXBatteryPowerSensor(battery, battery_id),
            SAXBatterySmartmeterSensor(battery, battery_id),
            SAXBatteryCapacitySensor(battery, battery_id),
            SAXBatteryCyclesSensor(battery, battery_id),
            SAXBatteryTempSensor(battery, battery_id),
            SAXBatteryEnergyProducedSensor(battery, battery_id),
            SAXBatteryEnergyConsumedSensor(battery, battery_id),
        ])
    
    async_add_entities(entities)

class SAXBatterySensor(SensorEntity):
    """Base class for SAX Battery sensors."""
    
    def __init__(self, battery, battery_id):
        """Initialize the sensor."""
        self.battery = battery
        self._battery_id = battery_id
        self._attr_unique_id = f"{DOMAIN}_{battery_id}_{self.__class__.__name__}"
        
        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.battery._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def should_poll(self):
        """Return True if entity has to be polled for state."""
        return True
        
    async def async_update(self):
        """Update the sensor."""
        await self.battery.async_update()

class SAXBatteryStatusSensor(SAXBatterySensor):
    """SAX Battery Status sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_name = f"Battery {battery_id.upper()} Status"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_STATUS)

class SAXBatterySOCSensor(SAXBatterySensor):
    """SAX Battery State of Charge (SOC) sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_name = f"Battery {battery_id.upper()} SOC"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_SOC)

class SAXBatteryPowerSensor(SAXBatterySensor):
    """SAX Battery Power sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Battery {battery_id.upper()} Power"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_POWER)

class SAXBatterySmartmeterSensor(SAXBatterySensor):
    """SAX Battery Smartmeter sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_name = f"Battery {battery_id.upper()} Smartmeter"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_SMARTMETER)

class SAXBatteryCapacitySensor(SAXBatterySensor):
    """SAX Battery Capacity sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = f"Battery {battery_id.upper()} Capacity"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_CAPACITY)

class SAXBatteryCyclesSensor(SAXBatterySensor):
    """SAX Battery Cycles sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_name = f"Battery {battery_id.upper()} Cycles"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_CYCLES)

class SAXBatteryTempSensor(SAXBatterySensor):
    """SAX Battery Temperature sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_name = f"Battery {battery_id.upper()} Temperature"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_TEMP)

class SAXBatteryEnergyProducedSensor(SAXBatterySensor):
    """SAX Battery Energy Produced sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = f"Battery {battery_id.upper()} Energy Produced"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_ENERGY_PRODUCED)

class SAXBatteryEnergyConsumedSensor(SAXBatterySensor):
    """SAX Battery Energy Consumed sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_name = f"Battery {battery_id.upper()} Energy Consumed"
        
    @property
    def native_value(self):
        return self.battery.data.get(SAX_ENERGY_CONSUMED)
        
class SAXBatteryCombinedPowerSensor(SensorEntity):
    """Combined power sensor for all SAX Batteries."""
    
    def __init__(self, sax_battery_data):
        """Initialize the sensor."""
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_combined_power"
        self._attr_name = "Battery Combined Power"
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
    def should_poll(self):
        """Return True if entity has to be polled for state."""
        return True

    async def async_update(self):
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