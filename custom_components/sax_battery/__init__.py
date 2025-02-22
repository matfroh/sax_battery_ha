### __init__.py
import asyncio
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from pymodbus.client import ModbusTcpClient
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
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

async def async_setup(hass: HomeAssistant, config):
    """Set up the SAX Battery integration."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up SAX Battery from a config entry."""
    try:
        # Create SAX Battery data instance
        sax_battery_data = SAXBatteryData(hass, entry)
        await sax_battery_data.async_init()
    except Exception as err:
        _LOGGER.error("Failed to initialize SAX Battery: %s", err)
        raise ConfigEntryNotReady from err
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sax_battery_data

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Close all Modbus connections
        sax_battery_data = hass.data[DOMAIN][entry.entry_id]
        for client in sax_battery_data.modbus_clients.values():
            client.close()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

class SAXBatteryData:
    """Manages SAX Battery Modbus communication and data."""
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.master_battery = None
        self.batteries = {}
        self.modbus_clients = {}
        self.power_sensor_entity_id = entry.data.get("power_sensor_entity_id")
        self.pf_sensor_entity_id = entry.data.get("pf_sensor_entity_id")
        self.modbus_registers = {}
        
    async def async_init(self):
        """Initialize Modbus connections and battery data."""
        battery_count = self.entry.data.get("battery_count")
        master_battery_id = self.entry.data.get("master_battery")
        
        _LOGGER.debug(f"Initializing {battery_count} batteries. Master: {master_battery_id}")
        
        for i in range(1, battery_count + 1):
            battery_id = f"battery_{chr(96+i)}"
            host = self.entry.data.get(f"{battery_id}_host")
            port = self.entry.data.get(f"{battery_id}_port")
            
            _LOGGER.debug(f"Setting up battery {battery_id} at {host}:{port}")
            
            try:
                # Initialize Modbus TCP client
                client = ModbusTcpClient(
                    host=host,
                    port=port,
                    timeout=10
                )
                if not client.connect():  
                    raise ConnectionError(f"Could not connect to {host}:{port}")
    
                self.modbus_clients[battery_id] = client
                _LOGGER.info(f"Successfully connected to battery at {host}:{port}")
                

                
                self.batteries[battery_id] = SAXBattery(self.hass, self, battery_id)
            
            # Add registers for this battery
                self.modbus_registers[battery_id] = {
                    SAX_STATUS: {"address": 45, "count": 1, "data_type": "int"},
                    SAX_SOC: {"address": 46, "count": 1, "data_type": "int"},
                    SAX_POWER: {"address": 47, "count": 1, "data_type": "int", "offset": -16384},
                    SAX_SMARTMETER: {"address": 48, "count": 1, "data_type": "int", "offset": -16384},
                    SAX_CAPACITY: {"address": 40115, "count": 1, "data_type": "int16", "scale": 10},
                    SAX_CYCLES: {"address": 40116, "count": 1, "data_type": "int16"},
                    SAX_TEMP: {"address": 40117, "count": 1, "data_type": "int16"},
                    SAX_ENERGY_PRODUCED: {"address": 40096, "count": 1, "data_type": "uint16"},
                    SAX_ENERGY_CONSUMED: {"address": 40097, "count": 1, "data_type": "uint16"},
                }
            
                await self.batteries[battery_id].async_init()
            
            except Exception as err:
                _LOGGER.error(f"Failed to connect to {battery_id} at {host}:{port}: {err}")
                raise ConfigEntryNotReady from err        
                    
        # Designate Master Battery
        if master_battery_id in self.batteries:
            self.master_battery = self.batteries[master_battery_id]
            _LOGGER.debug(f"Master battery set to {master_battery_id}")
        else:
            _LOGGER.error(f"Master battery {master_battery_id} not found in configured batteries")
            raise ConfigEntryNotReady(f"Master battery {master_battery_id} not found")

class SAXBattery:
    """Represents a single SAX Battery."""
    def __init__(self, hass, data, battery_id):
        self.hass = hass
        self.data = {}  # Will store the latest readings
        self._data_manager = data
        self.battery_id = battery_id

    async def async_init(self):
        """Initialize the battery."""
        # Initial data fetch
        await self.async_update()

    async def async_update(self):
        """Update the battery data."""
        try:
            client = self._data_manager.modbus_clients[self.battery_id]
            registers = self._data_manager.modbus_registers[self.battery_id]
            
            for register_name, register_info in registers.items():
                result = await self.read_modbus_register(
                    client,
                    register_info["address"],
                    register_info["count"],
                    register_info.get("offset", 0),
                    register_info.get("scale", 1)
                )
                self.data[register_name] = result
                
        except Exception as err:
            _LOGGER.error(f"Error updating battery {self.battery_id}: {err}")
            return False
            
        return True

    async def read_modbus_register(self, client, address, count, offset=0, scale=1):
        """Read a Modbus register with proper error handling."""
        try:
            result = await self.hass.async_add_executor_job(
            	client.read_holding_registers,
                address,
                count,
                64
            )
            if not hasattr(result, 'isError') or not result.isError():
                value = result.registers[0]
                return (value + offset) * scale
            else:
                _LOGGER.error(f"Modbus error reading address {address}: {result}")
                return None
        except Exception as err:
            _LOGGER.error(f"Failed to read register {address}: {err}")
            return None