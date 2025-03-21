"""Integration for SAX Battery."""

import asyncio
import logging

from pymodbus.client import ModbusTcpClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_DEVICE_ID,
    CONF_MANUAL_CONTROL,
    CONF_PILOT_FROM_HA,
    DOMAIN,
    SAX_AC_POWER_TOTAL,
    SAX_ACTIVE_POWER_L1,
    SAX_ACTIVE_POWER_L2,
    SAX_ACTIVE_POWER_L3,
    SAX_APPARENT_POWER,
    SAX_CAPACITY,
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

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


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
        if hasattr(sax_battery_data, "pilot"):
            await sax_battery_data.pilot.async_stop()

        # Close all Modbus connections
        for client in sax_battery_data.modbus_clients.values():
            client.close()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class SAXBatteryData:
    """Manages SAX Battery Modbus communication and data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the SAX Battery data manager."""
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

        _LOGGER.debug(
            "Initializing %s batteries. Master: %s", battery_count, master_battery_id
        )

        for i in range(1, battery_count + 1):
            battery_id = f"battery_{chr(96 + i)}"
            host = self.entry.data.get(f"{battery_id}_host")
            port = self.entry.data.get(f"{battery_id}_port")

            _LOGGER.debug("Setting up battery %s at %s:%s", battery_id, host, port)

            try:
                # Initialize Modbus TCP client
                client = ModbusTcpClient(host=host, port=port, timeout=10)
                if not client.connect():
                    raise ConnectionError(f"Could not connect to {host}:{port}")

                self.modbus_clients[battery_id] = client
                _LOGGER.info("Successfully connected to battery at %s:%s", host, port)

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
                        "command_off": 1,
                    },
                    SAX_SOC: {
                        "address": 46,
                        "count": 1,
                        "data_type": "int",
                        "slave": 64,
                        "scan_interval": 60,
                    },
                    SAX_POWER: {
                        "address": 47,
                        "count": 1,
                        "data_type": "int",
                        "offset": -16384,
                        "slave": 64,
                        "scan_interval": 15,
                    },
                    SAX_SMARTMETER: {
                        "address": 48,
                        "count": 1,
                        "data_type": "int",
                        "offset": -16384,
                        "slave": 64,
                        "scan_interval": 60,
                        "enabled": False,
                    },
                    SAX_CAPACITY: {
                        "address": 40115,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,
                        "slave": 40,
                        "scan_interval": 3600,
                    },
                    SAX_CYCLES: {
                        "address": 40116,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 3600,
                    },
                    SAX_TEMP: {
                        "address": 40117,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 120,
                    },
                    SAX_ENERGY_PRODUCED: {
                        "address": 40096,
                        "count": 1,
                        "data_type": "uint16",
                        "slave": 40,
                        "scan_interval": 3600,
                    },
                    SAX_ENERGY_CONSUMED: {
                        "address": 40097,
                        "count": 1,
                        "data_type": "uint16",
                        "slave": 40,
                        "scan_interval": 3600,
                    },
                    SAX_PHASE_CURRENTS_SUM: {
                        "address": 40073,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.01,  # Based on scaling factor -2
                        "slave": 40,
                        "scan_interval": 60,
                        #                        "enabled": False  # Disabled by default
                    },
                    SAX_CURRENT_L1: {
                        "address": 40074,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.01,  # Based on scaling factor -2
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_CURRENT_L2: {
                        "address": 40075,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.01,
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_CURRENT_L3: {
                        "address": 40076,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.01,
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_VOLTAGE_L1: {
                        "address": 40081,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.1,  # Based on scaling factor -1
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_VOLTAGE_L2: {
                        "address": 40082,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.1,
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_VOLTAGE_L3: {
                        "address": 40083,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.1,
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_AC_POWER_TOTAL: {
                        "address": 40085,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,  # Based on scaling factor 1
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_GRID_FREQUENCY: {
                        "address": 40087,
                        "count": 1,
                        "data_type": "uint16",
                        "scale": 0.1,  # Based on scaling factor -1
                        "slave": 40,
                        "scan_interval": 60,
                        #                        "enabled": False
                    },
                    SAX_APPARENT_POWER: {
                        "address": 40089,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,  # Based on scaling factor 1
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_REACTIVE_POWER: {
                        "address": 40091,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,  # Based on scaling factor 1
                        "slave": 40,
                        "scan_interval": 60,
                        #                        "enabled": False
                    },
                    SAX_POWER_FACTOR: {
                        "address": 40093,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 0.1,  # Based on scaling factor -1
                        "slave": 40,
                        "scan_interval": 60,
                        #                      "enabled": False
                    },
                    # Slave-ID 40: Smartmeter values
                    SAX_STORAGE_STATUS: {
                        "address": 40099,
                        "count": 1,
                        "data_type": "uint16",
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False,
                        "states": {1: "OFF", 2: "ON", 3: "Connected", 4: "Standby"},
                    },
                    SAX_SMARTMETER_CURRENT_L1: {
                        "address": 40100,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 0.01,  # Factor -2
                        "slave": 40,
                        "scan_interval": 60,
                        #                        "enabled": False
                    },
                    SAX_SMARTMETER_CURRENT_L2: {
                        "address": 40101,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 0.01,
                        "slave": 40,
                        "scan_interval": 60,
                        #                        "enabled": False
                    },
                    SAX_SMARTMETER_CURRENT_L3: {
                        "address": 40102,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 0.01,
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_ACTIVE_POWER_L1: {
                        "address": 40103,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,  # Based on scaling factor 1
                        "slave": 40,
                        "scan_interval": 60,
                        #                        "enabled": False
                    },
                    SAX_ACTIVE_POWER_L2: {
                        "address": 40104,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_ACTIVE_POWER_L3: {
                        "address": 40105,
                        "count": 1,
                        "data_type": "int16",
                        "scale": 10,
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_SMARTMETER_VOLTAGE_L1: {
                        "address": 40107,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 60,
                        #                        "enabled": False
                    },
                    SAX_SMARTMETER_VOLTAGE_L2: {
                        "address": 40108,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                    SAX_SMARTMETER_VOLTAGE_L3: {
                        "address": 40109,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 60,
                        #                      "enabled": False
                    },
                    SAX_SMARTMETER_TOTAL_POWER: {
                        "address": 40110,
                        "count": 1,
                        "data_type": "int16",
                        "slave": 40,
                        "scan_interval": 60,
                        #                       "enabled": False
                    },
                }

                # Initialize last update times for this battery's registers
                self.last_updates[battery_id] = {
                    register: 0 for register in self.modbus_registers[battery_id]
                }

                self.batteries[battery_id] = SAXBattery(self.hass, self, battery_id)
                await self.batteries[battery_id].async_init()

            except Exception as err:
                _LOGGER.error(
                    "Failed to connect to %s at %s:%s: %s", battery_id, host, port, err
                )
                raise ConfigEntryNotReady from err

        # Designate Master Battery
        if master_battery_id in self.batteries:
            self.master_battery = self.batteries[master_battery_id]
            _LOGGER.debug("Master battery set to %s", master_battery_id)
        else:
            _LOGGER.error(
                "Master battery %s not found in configured batteries", master_battery_id
            )
            raise ConfigEntryNotReady(f"Master battery {master_battery_id} not found")


###
class SAXBattery:
    """Represents a single SAX Battery."""

    def __init__(self, hass, data, battery_id) -> None:
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
                    slave=register_info["slave"],  # Use register-specific slave ID
                )
            )

            if hasattr(result, "registers"):
                return (
                    result.registers[0] + register_info.get("offset", 0)
                ) * register_info.get("scale", 1)
            _LOGGER.error(
                "Modbus error reading address %s: %s",
                register_info["address"],
                result,
            )
            return None  # noqa: TRY300
        except Exception as err:
            _LOGGER.error(
                "Failed to read register %s: %s", register_info["address"], err
            )
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
                    _LOGGER.error("Error updating register %s: %s", register_name, err)

        except Exception as err:
            _LOGGER.error("Error updating battery %s: %s", self.battery_id, err)
            return False

        return True
