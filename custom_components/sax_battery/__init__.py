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
    CONF_DEVICE_ID,
    SAX_STATUS,
    SAX_SOC,
    SAX_POWER,
    SAX_SMARTMETER,
    SAX_CAPACITY,
    SAX_CYCLES,
    SAX_TEMP,
    SAX_ENERGY_PRODUCED,
    SAX_ENERGY_CONSUMED,
    CONF_PILOT_FROM_HA,
    CONF_MANUAL_CONTROL
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]

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

    
    # Set up pilot service if enabled
    if entry.data.get(CONF_PILOT_FROM_HA, False):
        from .pilot import async_setup_pilot
        await async_setup_pilot(hass, entry.entry_id)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Stop pilot service if running
        sax_battery_data = hass.data[DOMAIN][entry.entry_id]
        if hasattr(sax_battery_data, 'pilot'):
            await sax_battery_data.pilot.async_stop()
        
        # Close all Modbus connections
        for client in sax_battery_data.modbus_clients.values():
            client.close()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


class SAXBatteryData:
    """Manages SAX Battery Modbus communication and data."""
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.device_id = entry.data.get(CONF_DEVICE_ID)  
        self.master_battery = None
        self.batteries = {}
        self.modbus_clients = {}
        self.power_sensor_entity_id = entry.data.get("power_sensor_entity_id")
        self.pf_sensor_entity_id = entry.data.get("pf_sensor_entity_id")
        self.modbus_registers = {}
        self.last_updates = {}  # Initialize empty dictionary for last updates
        
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
                
                # Initialize the registers configuration
                self.modbus_registers[battery_id] = {
                    SAX_STATUS: {
                        "address": 45,
                        "count": 1,
                        "data_type": "int",
                        "slave": 64,
                        "scan_interval": 60,
                        "state_on": 3,
                        "state_off": 1,
                        "command_on": 2,
                        "command_off": 1
                    },
                    SAX_SOC: {
                        "address": 46,
                        "count": 1,
                        "data_type": "int",
                        "slave": 64,
                        "scan_interval": 60
                    },
                    SAX_POWER: {
                        "address": 47,
                        "count": 1,
                        "data_type": "int",
                        "offset": -16384,
                        "slave": 64,
                        "scan_interval": 15
                    },
                    SAX_SMARTMETER: {
                        "address": 48,
                        "count": 1,
                        "data_type": "int",
                        "offset": -16384,
                        "slave": 64,
                        "scan_interval": 60
                    },
                    SAX_CAPACITY: {
                        "address": 40115,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,
                        "slave": 40,
                        "scan_interval": 3600
                    },
                    SAX_CYCLES: {
                        "address": 40116,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 3600
                    },
                    SAX_TEMP: {
                        "address": 40117,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 120
                    },
                    SAX_ENERGY_PRODUCED: {
                        "address": 40096,
                        "count": 1,
                        "data_type": "uint16",
                        "slave": 40,
                        "scan_interval": 3600
                    },
                    SAX_ENERGY_CONSUMED: {
                        "address": 40097,
                        "count": 1,
                        "data_type": "uint16",
                        "slave": 40,
                        "scan_interval": 3600
                    }
                }
                
                # Initialize last update times for this battery's registers
                self.last_updates[battery_id] = {
                    register: 0 for register in self.modbus_registers[battery_id]
                }
                
                self.batteries[battery_id] = SAXBattery(self.hass, self, battery_id)
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

###
class SAXBattery:
    """Represents a single SAX Battery."""
    def __init__(self, hass, data, battery_id):
        """Initialize the battery."""
        self.hass = hass
        self.data = {}  # Will store the latest readings
        self._data_manager = data
        self.battery_id = battery_id
        self._last_updates = data.last_updates[battery_id]

    async def async_init(self):
        """Initialize battery readings."""
        await self.async_update()

    async def read_modbus_register(self, client, register_info):
        """Read a Modbus register with proper error handling."""
        try:
            result = await self.hass.async_add_executor_job(
                lambda: client.read_holding_registers(
                    address=register_info["address"],
                    count=register_info["count"],
                    slave=register_info["slave"]  # Use register-specific slave ID
                )
            )
        
            if hasattr(result, 'registers'):
                value = result.registers[0]
                # Apply offset and scale if present
                value = (value + register_info.get("offset", 0)) * register_info.get("scale", 1)
                return value
            else:
                _LOGGER.error(f"Modbus error reading address {register_info['address']}: {result}")
                return None
        except Exception as err:
            _LOGGER.error(f"Failed to read register {register_info['address']}: {err}")
            return None

    async def async_update(self):
        """Update the battery data."""
        try:
            client = self._data_manager.modbus_clients[self.battery_id]
            registers = self._data_manager.modbus_registers[self.battery_id]
            current_time = self.hass.loop.time()  # Get current time
            
            for register_name, register_info in registers.items():
                # Check if enough time has passed since last update
                time_since_update = current_time - self._last_updates[register_name]
                if time_since_update < register_info["scan_interval"]:
                    continue
                
                try:
                    result = await self.read_modbus_register(client, register_info)
                    if result is not None:
                        self.data[register_name] = result
                        self._last_updates[register_name] = current_time
                except Exception as err:
                    _LOGGER.error(f"Error updating register {register_name}: {err}")
                    
        except Exception as err:
            _LOGGER.error(f"Error updating battery {self.battery_id}: {err}")
            return False
            
        return True
