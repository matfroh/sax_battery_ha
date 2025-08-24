"""Integration for SAX Battery."""

import logging
from typing import Any

from pymodbus.client import ModbusTcpClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_DEVICE_ID,
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


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the SAX Battery integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAX Battery from a config entry."""
    try:
        # Create SAX Battery data instance
        sax_battery_data = SAXBatteryData(hass, entry)
        await sax_battery_data.async_init()
    except (ConnectionError, TimeoutError, ValueError) as err:
        _LOGGER.error("Failed to initialize SAX Battery: %s", err)
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sax_battery_data

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up pilot service if enabled
    if entry.data.get(CONF_PILOT_FROM_HA, False):
        # Import here to avoid circular import issues
        from .pilot import async_setup_pilot  # noqa: PLC0415

        await async_setup_pilot(hass, entry.entry_id)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
        self.master_battery: SAXBattery | None = None
        self.batteries: dict[str, SAXBattery] = {}
        self.modbus_clients: dict[str, ModbusTcpClient] = {}
        self.power_sensor_entity_id = entry.data.get("power_sensor_entity_id")
        self.pf_sensor_entity_id = entry.data.get("pf_sensor_entity_id")
        self.modbus_registers: dict[str, dict[str, Any]] = {}
        self.last_updates: dict[
            str, dict[str, float]
        ] = {}  # Initialize empty dictionary for last updates

    async def async_init(self) -> None:
        """Initialize Modbus connections and battery data."""
        battery_count = self.entry.data.get("battery_count", 1)
        master_battery_id = self.entry.data.get("master_battery")

        _LOGGER.debug(
            "Initializing %s batteries. Master: %s", battery_count, master_battery_id
        )

        for i in range(1, int(battery_count) + 1):
            battery_id = f"battery_{chr(96 + i)}"
            host = self.entry.data.get(f"{battery_id}_host")
            port = self.entry.data.get(f"{battery_id}_port")

            _LOGGER.debug("Setting up battery %s at %s:%s", battery_id, host, port)

            try:
                # Initialize Modbus TCP client
                host = str(self.entry.data.get(f"{battery_id}_host", ""))
                port = int(self.entry.data.get(f"{battery_id}_port", 502))

                client = ModbusTcpClient(host=host, port=port, timeout=10)
                if not client.connect():  # type: ignore[no-untyped-call]
                    msg = f"Could not connect to {host}:{port}"
                    raise ConfigEntryNotReady(msg)  # noqa: TRY301

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
                self.last_updates[battery_id] = dict.fromkeys(
                    self.modbus_registers[battery_id], 0
                )

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

    def __init__(
        self, hass: HomeAssistant, data: SAXBatteryData, battery_id: str
    ) -> None:
        """Initialize the battery."""
        self.hass = hass
        self.data: dict[str, Any] = {}  # Will store the latest readings
        self._data_manager = data
        self.battery_id = battery_id
        self._last_updates = data.last_updates[battery_id]

    async def async_init(self) -> None:
        """Initialize battery readings."""
        await self.async_update()

    async def read_modbus_register(
        self, client: ModbusTcpClient, register_info: dict[str, Any]
    ) -> float | None:
        """Read a Modbus register with proper error handling."""
        try:

            def _read_register() -> float | None:
                result = client.read_holding_registers(
                    address=register_info["address"],
                    count=register_info["count"],
                    slave=register_info["slave"],  # Use register-specific slave ID
                )
                if hasattr(result, "registers"):
                    return float(
                        (result.registers[0] + register_info.get("offset", 0))
                        * register_info.get("scale", 1)
                    )
                _LOGGER.error(
                    "Modbus error reading address %s: %s",
                    register_info["address"],
                    result,
                )
                return None

            return await self.hass.async_add_executor_job(_read_register)
        except (ConnectionError, TimeoutError, ValueError) as err:
            _LOGGER.error(
                "Failed to read register %s: %s", register_info["address"], err
            )
        return None

    async def async_update(self) -> bool:
        """Update the battery data."""
        try:
            client = self._data_manager.modbus_clients[self.battery_id]
            registers = self._data_manager.modbus_registers[self.battery_id]
            current_time = self.hass.loop.time()  # Get current time

            # Handle standard requests for non-slave 40
            for register_name, register_info in registers.items():
                if register_info["slave"] != 40:
                    # Check if enough time has passed since last update
                    time_since_update = current_time - self._last_updates[register_name]
                    if time_since_update < register_info["scan_interval"]:
                        continue

                    try:
                        result = await self.read_modbus_register(client, register_info)
                        if result is not None:
                            self.data[register_name] = result
                            self._last_updates[register_name] = current_time
                    except (ConnectionError, TimeoutError) as err:
                        _LOGGER.error(
                            "Error updating register %s: %s", register_name, err
                        )

            # Filter registers for slave ID 40 and find the range
            slave_id = 40
            slave_registers = {
                reg_name: reg_info
                for reg_name, reg_info in registers.items()
                if reg_info["slave"] == slave_id
            }

            if not slave_registers:
                return True  # Nothing to update for this slave

            # Check if any slave 40 registers need updating based on scan_interval
            needs_update = False
            for reg_name, reg_info in slave_registers.items():
                time_since_update = current_time - self._last_updates[reg_name]
                if time_since_update >= reg_info["scan_interval"]:
                    needs_update = True
                    break

            if not needs_update:
                return True  # No slave 40 registers need updating yet

            # Calculate the range of addresses to read
            start_address = min(
                reg_info["address"] for reg_info in slave_registers.values()
            )
            end_address = max(
                reg_info["address"] + reg_info.get("count", 1) - 1
                for reg_info in slave_registers.values()
            )
            register_count = end_address - start_address + 1

            _LOGGER.debug(
                "Batch reading registers %s to %s (slave %s, count: %s)",
                start_address,
                end_address,
                slave_id,
                register_count,
            )

            # Perform a bulk read
            try:

                def _bulk_read() -> Any:
                    return client.read_holding_registers(
                        address=start_address,
                        count=register_count,
                        slave=slave_id,
                    )

                result = await self.hass.async_add_executor_job(_bulk_read)

                if not hasattr(result, "registers"):
                    _LOGGER.error(
                        "Modbus error reading range %s-%s: %s",
                        start_address,
                        end_address,
                        result,
                    )
                    return False

                # At this point, result has registers attribute
                # Parse the bulk response
                for reg_name, reg_info in slave_registers.items():
                    reg_offset = reg_info["address"] - start_address
                    if 0 <= reg_offset < len(result.registers):  # type: ignore[union-attr]
                        raw_value = result.registers[reg_offset]  # type: ignore[union-attr]
                        value = (raw_value + reg_info.get("offset", 0)) * reg_info.get(
                            "scale", 1
                        )
                        self.data[reg_name] = value
                        # Update the timestamp for this register
                        self._last_updates[reg_name] = current_time
                    else:
                        _LOGGER.warning(
                            "Register %s (address %s) offset %s is out of range for result length %s",
                            reg_name,
                            reg_info["address"],
                            reg_offset,
                            len(result.registers),  # type: ignore[union-attr]
                        )

            except (ConnectionError, TimeoutError, ValueError) as err:
                _LOGGER.error(
                    "Failed to read bulk registers for slave %s: %s", slave_id, err
                )
                return False

        except TimeoutError as err:
            _LOGGER.error("Error updating battery %s: %s", self.battery_id, err)
            return False

        return True
