"""Switch platform for SAX Battery integration."""
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN, SAX_STATUS

async def async_setup_entry(hass, entry_id, async_add_entities):
    """Set up the SAX Battery switches."""
    sax_battery_data = hass.data[DOMAIN][entry_id]
    entities = []
    
    for battery in sax_battery_data.batteries.values():
        entities.append(SAXBatteryOnOffSwitch(battery))
    
    async_add_entities(entities)

class SAXBatteryOnOffSwitch(SwitchEntity):
    """SAX Battery On/Off switch."""
    
    def __init__(self, battery):
        """Initialize the switch."""
        self.battery = battery
        self._attr_unique_id = f"{DOMAIN}_{battery.battery_id}_switch"
        self._attr_name = f"{battery.battery_id.upper()} On/Off"
        
    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.battery.data.get(SAX_STATUS) == 1
        
    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        try:
            client = self.battery._data_manager.modbus_clients[self.battery.battery_id]
            result = client.write_register(address=45, value=1, slave=64)
            if not result.isError():
                self.battery.data[SAX_STATUS] = 1
                self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error(f"Failed to turn on battery {self.battery.battery_id}: {err}")
            
    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        try:
            client = self.battery._data_manager.modbus_clients[self.battery.battery_id]
            result = client.write_register(address=45, value=0, slave=64)
            if not result.isError():
                self.battery.data[SAX_STATUS] = 0
                self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error(f"Failed to turn off battery {self.battery.battery_id}: {err}")
            
    @property
    def available(self):
        """Return True if entity is available."""
        return SAX_STATUS in self.battery.data
        
    @property
    def should_poll(self):
        """Return True if entity has to be polled for state."""
        return True
        
    async def async_update(self):
        """Update the switch state."""
        await self.battery.async_update()