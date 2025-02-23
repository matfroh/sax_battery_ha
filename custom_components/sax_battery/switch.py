"""Switch platform for SAX Battery integration."""
import logging
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, SAX_STATUS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the SAX Battery switches."""
    sax_battery_data = hass.data[DOMAIN][entry.entry_id]
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
        self._attr_name = f"Battery {battery.battery_id.upper()} On/Off"
        self._attr_has_entity_name = True
        self._registers = self.battery._data_manager.modbus_registers[battery.battery_id][SAX_STATUS]
        
    @property
    def is_on(self):
        """Return true if switch is on."""
        status = self.battery.data.get(SAX_STATUS)
        return status == self._registers["state_on"]
        
    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        try:
            client = self.battery._data_manager.modbus_clients[self.battery.battery_id]
            result = await self.battery.hass.async_add_executor_job(
                client.write_register,
                self._registers["address"],
                self._registers["command_on"],
                64  # slave
            )
            if not hasattr(result, 'isError') or not result.isError():
                # Update will handle state verification
                await self.async_update()
            else:
                _LOGGER.error(f"Error turning on battery {self.battery.battery_id}: {result}")
        except Exception as err:
            _LOGGER.error(f"Failed to turn on battery {self.battery.battery_id}: {err}")
            
    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        try:
            client = self.battery._data_manager.modbus_clients[self.battery.battery_id]
            result = await self.battery.hass.async_add_executor_job(
                client.write_register,
                self._registers["address"],
                self._registers["command_off"],
                64  # slave
            )
            if not hasattr(result, 'isError') or not result.isError():
                # Update will handle state verification
                await self.async_update()
            else:
                _LOGGER.error(f"Error turning off battery {self.battery.battery_id}: {result}")
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