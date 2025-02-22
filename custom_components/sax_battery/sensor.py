### sensor.py
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfPower, PERCENTAGE
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the SAX Battery sensors."""
    sax_battery_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for battery_id, battery in sax_battery_data.batteries.items():
        entities.extend([
            SAXBatterySOCSensor(battery, battery_id),
            SAXBatteryPowerSensor(battery, battery_id),
        ])
    
    async_add_entities(entities)

class SAXBatterySensor(SensorEntity):
    """Base class for SAX Battery sensors."""
    
    def __init__(self, battery, battery_id):
        self.battery = battery
        self._battery_id = battery_id
        self._attr_unique_id = f"{DOMAIN}_{battery_id}_{self.__class__.__name__}"
        
    @property
    def should_poll(self):
        return True
        
    async def async_update(self):
        await self.battery.async_update()

class SAXBatterySOCSensor(SAXBatterySensor):
    """SAX Battery State of Charge (SOC) sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        
    @property
    def name(self):
        return f"{self._battery_id.upper()} SOC"
        
    @property
    def native_value(self):
        return self.battery.data.get("sax_soc")

class SAXBatteryPowerSensor(SAXBatterySensor):
    """SAX Battery Power sensor."""
    
    def __init__(self, battery, battery_id):
        super().__init__(battery, battery_id)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        
    @property
    def name(self):
        return f"{self._battery_id.upper()} Power"
        
    @property
    def native_value(self):
        return self.battery.data.get("sax_power")