"""SAX Battery Modbus Hub for pymodbus 3.9.2 compatibility."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusIOException

_LOGGER = logging.getLogger(__name__)

# Improved timeout constants
MODBUS_TIMEOUT = 5.0  # Reduced from 30 to 5 seconds
MODBUS_RETRIES = 1  # Reduced from 3 to 1 retry
READ_TIMEOUT = 3.0  # Individual register read timeout


class HubException(HomeAssistantError):
    """Base exception for hub errors."""


class HubConnectionError(HubException):
    """Connection error."""


class HubInitFailed(HubException):
    """Init failed error."""


class SAXBatteryHub:
    """Main hub for SAX Battery communication."""

    def __init__(
        self, hass: HomeAssistant, battery_configs: list[dict[str, Any]]
    ) -> None:
        """Initialize the hub with multiple battery configurations."""
        self._hass = hass
        self._battery_configs = battery_configs
        self._clients: dict[str, AsyncModbusTcpClient | None] = {}
        self._connected: dict[str, bool] = {}
        self._lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()  # Separate lock for write operations
        self._reading = False  # Prevent concurrent reads
        self.batteries: dict[str, SAXBattery] = {}

        # Initialize batteries based on configuration
        for config in battery_configs:
            battery_id = config["battery_id"]
            battery = SAXBattery(self, battery_id, config["host"], config["port"])
            self.batteries[battery_id] = battery
            self._clients[battery_id] = None
            self._connected[battery_id] = False

    @property
    def host(self) -> str:
        """Return the first battery host for backward compatibility."""
        if self.batteries:
            first_battery = next(iter(self.batteries.values()))
            return first_battery.host
        return ""

    @property
    def port(self) -> int:
        """Return the first battery port for backward compatibility."""
        if self.batteries:
            first_battery = next(iter(self.batteries.values()))
            return first_battery.port
        return 502

    @property
    def client(self) -> AsyncModbusTcpClient | None:
        """Return the first battery client for backward compatibility."""
        if self.batteries:
            first_battery = next(iter(self.batteries.values()))
            return self._clients.get(first_battery.battery_id)
        return None

    async def connect(self) -> bool:
        """Connect to all battery inverters."""
        async with self._lock:
            all_connected = True

            for battery_id, battery in self.batteries.items():
                try:
                    _LOGGER.debug(
                        "Attempting to connect to SAX Battery %s at %s:%s",
                        battery_id,
                        battery.host,
                        battery.port,
                    )

                    if self._clients[battery_id] is None:
                        _LOGGER.debug(
                            "Creating new AsyncModbusTcpClient for %s", battery_id
                        )
                        self._clients[battery_id] = AsyncModbusTcpClient(
                            host=battery.host,
                            port=battery.port,
                            timeout=MODBUS_TIMEOUT,  # Reduced timeout
                            retries=MODBUS_RETRIES,  # Reduced retries
                        )

                    client = self._clients[battery_id]
                    if client and not client.connected:
                        _LOGGER.debug(
                            "Client for %s not connected, attempting connection...",
                            battery_id,
                        )

                        # Quick network test with timeout
                        try:
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(2)  # Quick test
                            result = sock.connect_ex((battery.host, battery.port))
                            sock.close()
                            if result != 0:
                                _LOGGER.error(
                                    "TCP connection to %s:%s failed (error %s)",
                                    battery.host,
                                    battery.port,
                                    result,
                                )
                                all_connected = False
                                continue
                        except OSError as e:
                            _LOGGER.error(
                                "Network test failed for %s: %s", battery_id, e
                            )
                            all_connected = False
                            continue

                        # Add timeout to connection attempt
                        result = await asyncio.wait_for(
                            client.connect(), timeout=MODBUS_TIMEOUT
                        )

                        if not result:
                            _LOGGER.error(
                                "Failed to connect to %s at %s:%s",
                                battery_id,
                                battery.host,
                                battery.port,
                            )
                            all_connected = False
                            continue

                    self._connected[battery_id] = True
                    _LOGGER.debug(
                        "Successfully connected to SAX Battery %s", battery_id
                    )

                except asyncio.TimeoutError:
                    _LOGGER.error(
                        "Connection timeout to %s at %s:%s",
                        battery_id,
                        battery.host,
                        battery.port,
                    )
                    self._connected[battery_id] = False
                    all_connected = False
                except (ConnectionException, OSError) as e:
                    _LOGGER.error("Connection error to %s: %s", battery_id, e)
                    self._connected[battery_id] = False
                    all_connected = False

            return all_connected

    async def disconnect(self) -> None:
        """Disconnect from all battery inverters."""
        async with self._lock:
            for battery_id, client in self._clients.items():
                if client:
                    client.close()
                    self._clients[battery_id] = None
                self._connected[battery_id] = False

    async def modbus_write_registers(
        self, battery_id: str, address: int, values: list[int], slave: int = 64
    ) -> bool:
        """Write to Modbus registers with proper locking."""
        async with self._write_lock:
            try:
                # Add delay to avoid conflicts with reads
                await asyncio.sleep(0.5)

                client = self._clients.get(battery_id)
                if not client:
                    _LOGGER.error("No Modbus client found for battery %s", battery_id)
                    return False

                # Ensure connection
                if not client.connected:
                    await client.connect()
                    await asyncio.sleep(0.1)

                _LOGGER.debug(
                    "Writing %d values to battery %s, address %d, slave %d: %s",
                    len(values),
                    battery_id,
                    address,
                    slave,
                    values,
                )

                result = await asyncio.wait_for(
                    client.write_registers(address, values, slave=slave),
                    timeout=10.0,
                )

                if result.isError():
                    _LOGGER.error(
                        "Modbus write error for battery %s: %s", battery_id, result
                    )
                    return False

                _LOGGER.debug(
                    "Successfully wrote to battery %s, address %d", battery_id, address
                )
                return True

            except asyncio.TimeoutError:
                _LOGGER.error(
                    "Write timeout to battery %s (address %d)", battery_id, address
                )
                return False
            except (ConnectionException, ModbusIOException) as e:
                _LOGGER.error("Modbus write error for battery %s: %s", battery_id, e)
                return False
            except Exception as e:
                _LOGGER.error(
                    "Unexpected error writing to battery %s: %s", battery_id, e
                )
                return False

    async def modbus_read_holding_registers(
        self, address: int, count: int, slave: int = 1, battery_id: str | None = None
    ) -> list[int]:
        """Read holding registers with timeout protection."""
        if battery_id is None:
            battery_id = list(self.batteries.keys())[0] if self.batteries else ""

        _LOGGER.debug(
            "Reading %d registers from address %d (slave %d) for battery %s",
            count,
            address,
            slave,
            battery_id,
        )

        client = self._clients.get(battery_id)
        is_connected = self._connected.get(battery_id, False)

        # Quick reconnect attempt if needed
        if not is_connected or not client or not client.connected:
            _LOGGER.debug(
                "Battery %s not connected, attempting quick reconnect", battery_id
            )
            # Don't call full connect() here - just reconnect this specific client
            client = self._clients.get(battery_id)
            if client:
                try:
                    result = await asyncio.wait_for(
                        client.connect(), timeout=MODBUS_TIMEOUT
                    )
                    if result:
                        self._connected[battery_id] = True
                    else:
                        raise HubConnectionError(
                            f"Quick reconnect failed for battery {battery_id}"
                        )
                except asyncio.TimeoutError:
                    raise HubConnectionError(
                        f"Reconnect timeout for battery {battery_id}"
                    )
            else:
                raise HubConnectionError(
                    f"No client available for battery {battery_id}"
                )

        try:
            # Add timeout to individual register reads
            result = await asyncio.wait_for(
                client.read_holding_registers(
                    address=address,
                    count=count,
                    slave=slave,
                ),
                timeout=READ_TIMEOUT,  # 3 second timeout per read
            )

            if result.isError():
                _LOGGER.error(
                    "Modbus error response for battery %s: %s", battery_id, result
                )
                raise HubException(f"Modbus error for battery {battery_id}: {result}")

            _LOGGER.debug(
                "Successfully read %d registers from battery %s",
                len(result.registers),
                battery_id,
            )
            return result.registers

        except asyncio.TimeoutError:
            _LOGGER.error(
                "Register read timeout for battery %s (address %d, took >%ds)",
                battery_id,
                address,
                READ_TIMEOUT,
            )
            self._connected[battery_id] = False  # Mark as disconnected
            raise HubConnectionError(
                f"Read timeout for battery {battery_id} at address {address}"
            )
        except (ConnectionException, ModbusIOException) as e:
            _LOGGER.error(
                "Modbus communication error for battery %s: %s", battery_id, e
            )
            if "No response received" in str(e) or "Connection" in str(e):
                self._connected[battery_id] = False
            raise HubConnectionError(
                f"Modbus communication error for battery {battery_id}: {e}"
            ) from e

    async def read_data(self) -> dict[str, Any]:
        """Read data from all batteries with improved concurrency and timeout protection."""
        # Prevent concurrent reads
        if self._reading:
            _LOGGER.debug("Read already in progress, skipping duplicate request")
            return {}

        self._reading = True
        try:
            _LOGGER.debug("Starting coordinated data read from all batteries")

            # Add overall timeout to prevent coordinator getting stuck
            return await asyncio.wait_for(
                self._read_data_internal(),
                timeout=30.0,  # Overall timeout for all batteries
            )

        except asyncio.TimeoutError:
            _LOGGER.error("Overall data read timeout (>30s), aborting")
            # Reset connection states to force reconnect
            for battery_id in self.batteries:
                self._connected[battery_id] = False
            return {}
        finally:
            self._reading = False

    async def _read_data_internal(self) -> dict[str, Any]:
        """Internal data reading logic."""
        # Quick connect check
        if not await self.connect():
            _LOGGER.warning("Failed to connect to batteries, returning empty data")
            return {}

        data = {}

        # Read from all batteries concurrently instead of sequentially
        battery_tasks = []
        for battery_id, battery in self.batteries.items():
            task = asyncio.create_task(
                self._read_battery_data_safe(battery_id, battery)
            )
            battery_tasks.append((battery_id, task))

        # Wait for all battery reads with timeout
        for battery_id, task in battery_tasks:
            try:
                battery_data = await asyncio.wait_for(task, timeout=15.0)
                if battery_data:
                    # Add battery-specific keys
                    for key, value in battery_data.items():
                        data[f"{battery_id}_{key}"] = value

                    # First battery also gets direct keys (backward compatibility)
                    if battery_id == list(self.batteries.keys())[0]:
                        data.update(battery_data)

                    _LOGGER.debug(
                        "Successfully read %d keys from %s",
                        len(battery_data),
                        battery_id,
                    )
            except asyncio.TimeoutError:
                _LOGGER.error(
                    "Battery %s read timeout (>15s), marking as disconnected",
                    battery_id,
                )
                self._connected[battery_id] = False
            except Exception as e:
                _LOGGER.error("Error reading from %s: %s", battery_id, e)

        _LOGGER.debug(
            "Completed data read with %d total keys from %d batteries",
            len(data),
            len(self.batteries),
        )
        return data

    async def _read_battery_data_safe(
        self, battery_id: str, battery: "SAXBattery"
    ) -> dict[str, float | int | None]:
        """Safely read data from a single battery with error handling."""
        try:
            return await battery.read_data()
        except Exception as e:
            _LOGGER.error("Error reading data from %s: %s", battery_id, e)
            return {}


class SAXBattery:
    """SAX Battery representation."""

    def __init__(
        self, hub: SAXBatteryHub, battery_id: str, host: str, port: int
    ) -> None:
        """Initialize the battery."""
        self._hub = hub
        self.battery_id = battery_id
        self.host = host
        self.port = port
        self._register_map = self._get_register_map()
        self._data_manager: Any = None  # Will be set by coordinator

    def _get_register_map(self) -> dict[str, dict[str, Any]]:
        """Get the complete register map for SAX Battery from original working version."""
        # Include ALL registers from the original_init.py file
        return {
            # Slave 64 registers (basic battery data)
            "status": {
                "address": 45,
                "count": 1,
                "scale": 1,
                "unit": None,
                "name": "Status",
                "slave": 64,
            },
            "soc": {
                "address": 46,
                "count": 1,
                "scale": 1,
                "unit": "%",
                "name": "State of Charge",
                "slave": 64,
            },
            "power": {
                "address": 47,
                "count": 1,
                "scale": 1,
                "unit": "W",
                "name": "Power",
                "signed": True,
                "offset": -16384,
                "slave": 64,
            },
            "smartmeter": {
                "address": 48,
                "count": 1,
                "scale": 1,
                "unit": None,
                "name": "Smart Meter",
                "signed": True,
                "offset": -16384,
                "slave": 64,
            },
            # Slave 40 registers (detailed battery info)
            "capacity": {
                "address": 40115,
                "count": 1,
                "scale": 10,
                "unit": "Wh",
                "name": "Capacity",
                "slave": 40,
            },
            "cycles": {
                "address": 40116,
                "count": 1,
                "scale": 1,
                "unit": "cycles",
                "name": "Cycles",
                "slave": 40,
            },
            "temp": {
                "address": 40117,
                "count": 1,
                "scale": 1,
                "unit": "°C",
                "name": "Temperature",
                "slave": 40,
            },
            "energy_produced": {
                "address": 40096,
                "count": 1,
                "scale": 1,
                "unit": "kWh",
                "name": "Energy Produced",
                "slave": 40,
            },
            "energy_consumed": {
                "address": 40097,
                "count": 1,
                "scale": 1,
                "unit": "kWh",
                "name": "Energy Consumed",
                "slave": 40,
            },
            "phase_currents_sum": {
                "address": 40073,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Phase Currents Sum",
                "slave": 40,
            },
            "current_l1": {
                "address": 40074,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Current L1",
                "slave": 40,
            },
            "current_l2": {
                "address": 40075,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Current L2",
                "slave": 40,
            },
            "current_l3": {
                "address": 40076,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Current L3",
                "slave": 40,
            },
            "voltage_l1": {
                "address": 40081,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Voltage L1",
                "slave": 40,
            },
            "voltage_l2": {
                "address": 40082,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Voltage L2",
                "slave": 40,
            },
            "voltage_l3": {
                "address": 40083,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Voltage L3",
                "slave": 40,
            },
            "ac_power_total": {
                "address": 40085,
                "count": 1,
                "scale": 10,
                "unit": "W",
                "name": "AC Power Total",
                "signed": True,
                "slave": 40,
            },
            "grid_frequency": {
                "address": 40087,
                "count": 1,
                "scale": 0.1,
                "unit": "Hz",
                "name": "Grid Frequency",
                "slave": 40,
            },
            "apparent_power": {
                "address": 40089,
                "count": 1,
                "scale": 10,
                "unit": "VA",
                "name": "Apparent Power",
                "signed": True,
                "slave": 40,
            },
            "reactive_power": {
                "address": 40091,
                "count": 1,
                "scale": 10,
                "unit": "VAR",
                "name": "Reactive Power",
                "signed": True,
                "slave": 40,
            },
            "power_factor": {
                "address": 40093,
                "count": 1,
                "scale": 0.1,
                "unit": None,
                "name": "Power Factor",
                "signed": True,
                "slave": 40,
            },
            "storage_status": {
                "address": 40099,
                "count": 1,
                "scale": 1,
                "unit": None,
                "name": "Storage Status",
                "slave": 40,
            },
            # Smart meter readings (slave 40)
            "smartmeter_current_l1": {
                "address": 40100,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Smart Meter Current L1",
                "signed": True,
                "slave": 40,
            },
            "smartmeter_current_l2": {
                "address": 40101,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Smart Meter Current L2",
                "signed": True,
                "slave": 40,
            },
            "smartmeter_current_l3": {
                "address": 40102,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Smart Meter Current L3",
                "signed": True,
                "slave": 40,
            },
            "active_power_l1": {
                "address": 40103,
                "count": 1,
                "scale": 10,
                "unit": "W",
                "name": "Active Power L1",
                "signed": True,
                "slave": 40,
            },
            "active_power_l2": {
                "address": 40104,
                "count": 1,
                "scale": 10,
                "unit": "W",
                "name": "Active Power L2",
                "signed": True,
                "slave": 40,
            },
            "active_power_l3": {
                "address": 40105,
                "count": 1,
                "scale": 10,
                "unit": "W",
                "name": "Active Power L3",
                "signed": True,
                "slave": 40,
            },
            "smartmeter_voltage_l1": {
                "address": 40107,
                "count": 1,
                "scale": 1,
                "unit": "V",
                "name": "Smart Meter Voltage L1",
                "slave": 40,
            },
            "smartmeter_voltage_l2": {
                "address": 40108,
                "count": 1,
                "scale": 1,
                "unit": "V",
                "name": "Smart Meter Voltage L2",
                "slave": 40,
            },
            "smartmeter_voltage_l3": {
                "address": 40109,
                "count": 1,
                "scale": 1,
                "unit": "V",
                "name": "Smart Meter Voltage L3",
                "slave": 40,
            },
            "smartmeter_total_power": {
                "address": 40110,
                "count": 1,
                "scale": 1,
                "unit": "W",
                "name": "Smart Meter Total Power",
                "signed": True,
                "slave": 40,
            },
        }

    def _convert_value(
        self, raw_value: int | list[int], config: dict[str, Any]
    ) -> float | int:
        """Convert raw modbus value to proper value."""
        if isinstance(raw_value, list):
            if len(raw_value) == 2:
                # 32-bit value (high word, low word)
                value = (raw_value[0] << 16) + raw_value[1]
            else:
                value = raw_value[0]
        else:
            value = raw_value

        # Apply offset first (used in original code for some registers)
        offset = config.get("offset", 0)
        if offset != 0:
            value += offset

        # Handle signed values
        if config.get("signed", False):
            if isinstance(raw_value, list) and len(raw_value) == 2:
                # 32-bit signed
                if value >= 2**31:
                    value -= 2**32
            elif value >= 2**15:
                # 16-bit signed
                value -= 2**16

        # Apply scale
        scale = config.get("scale", 1)
        if scale != 1:
            return float(value * scale)

        return float(value)

    async def read_data(self) -> dict[str, float | int | None]:
        """Read battery data."""
        _LOGGER.debug("Starting to read battery data...")
        _LOGGER.debug(
            "Will read %d registers: %s",
            len(self._register_map),
            list(self._register_map.keys()),
        )
        data: dict[str, float | int | None] = {}

        for key, config in self._register_map.items():
            slave_id = config.get("slave", 1)  # Get slave ID from config
            _LOGGER.debug(
                "Reading register for %s: address=%d, count=%d, slave=%d",
                key,
                config["address"],
                config["count"],
                slave_id,
            )
            try:
                raw_registers = await self._hub.modbus_read_holding_registers(
                    address=config["address"],
                    count=config["count"],
                    slave=slave_id,
                    battery_id=self.battery_id,  # Pass battery_id to specify which client to use
                )

                if raw_registers is not None:
                    _LOGGER.debug(
                        "Successfully read %d registers for %s: %s",
                        len(raw_registers),
                        key,
                        raw_registers,
                    )
                    if config["count"] == 1:
                        value = self._convert_value(raw_registers[0], config)
                    else:
                        value = self._convert_value(raw_registers, config)

                    data[key] = value
                    _LOGGER.debug(
                        "Converted value for %s: %s %s",
                        key,
                        value,
                        config.get("unit", ""),
                    )
                else:
                    _LOGGER.warning(
                        "No data received for %s (address %d)", key, config["address"]
                    )

            except (HubException, ConnectionException, ModbusIOException) as e:
                _LOGGER.error(
                    "Error reading %s (address %d): %s", key, config["address"], e
                )
                data[key] = None

        _LOGGER.debug("Finished reading battery data, got %d values", len(data))
        return data


async def create_hub(hass: HomeAssistant, config: dict[str, Any]) -> SAXBatteryHub:
    """Create and initialize the hub with multi-battery support."""
    _LOGGER.debug("Creating hub with config: %s", list(config.keys()))

    # Collect battery configurations (battery_a_host, battery_b_host, etc.)
    battery_configs = []

    # Look for battery_a_host, battery_b_host, battery_c_host
    for battery_letter in ["a", "b", "c"]:
        host_key = f"battery_{battery_letter}_host"
        port_key = f"battery_{battery_letter}_port"

        if host_key in config:
            host = config[host_key]
            port = config.get(port_key, 502)

            # Ensure port is an integer
            if isinstance(port, str):
                port = int(port)
            elif port is None:
                port = 502

            battery_id = f"battery_{battery_letter}"
            battery_configs.append(
                {
                    "battery_id": battery_id,
                    "host": host,
                    "port": port,
                }
            )
            _LOGGER.debug(
                "Found battery config: %s=%s, %s=%s", host_key, host, port_key, port
            )

    if not battery_configs:
        # Fallback to direct host/port for single battery setup (backward compatibility)
        host = config.get("host") or config.get(CONF_HOST)
        port = config.get("port") or config.get(CONF_PORT, 502)

        if host is None:
            _LOGGER.error(
                "No battery configuration found in config keys: %s", list(config.keys())
            )
            raise HubInitFailed("No battery configuration found")

        # Ensure port is an integer
        if isinstance(port, str):
            port = int(port)
        elif port is None:
            port = 502

        # Add single battery config
        battery_configs.append(
            {
                "battery_id": "battery_a",  # Default to battery_a for single setup
                "host": host,
                "port": port,
            }
        )
        _LOGGER.debug(
            "Using fallback single battery config: host=%s, port=%s", host, port
        )

    _LOGGER.info("Initializing SAX Battery Hub with %d batteries", len(battery_configs))
    for config_item in battery_configs:
        _LOGGER.info(
            "Battery %s: %s:%s",
            config_item["battery_id"],
            config_item["host"],
            config_item["port"],
        )

    hub = SAXBatteryHub(hass, battery_configs)

    # Test connection to all batteries
    try:
        if not await hub.connect():
            msg = "Could not connect to any SAX Battery"
            _LOGGER.error(msg)
            raise HubInitFailed(msg)

        # Test reading some data from first battery - but don't fail if it doesn't work immediately
        _LOGGER.debug("Testing data read from hub...")
        first_battery_id = list(hub.batteries.keys())[0] if hub.batteries else None

        if first_battery_id:
            # First, let's try some basic diagnostic reads on the first battery
            _LOGGER.info("Running basic Modbus diagnostics on %s...", first_battery_id)
            try:
                # Try reading the basic status/SOC registers that should work
                test_configs = [
                    {"addr": 45, "slave": 64, "desc": "Status"},
                    {"addr": 46, "slave": 64, "desc": "SOC"},
                    {"addr": 47, "slave": 64, "desc": "Power"},
                    {"addr": 40115, "slave": 40, "desc": "Capacity"},
                    {"addr": 40117, "slave": 40, "desc": "Temperature"},
                ]

                for test_config in test_configs:
                    try:
                        _LOGGER.debug(
                            "Testing register %d (slave %d) for %s",
                            test_config["addr"],
                            test_config["slave"],
                            test_config["desc"],
                        )
                        result = await hub.modbus_read_holding_registers(
                            address=int(test_config["addr"]),
                            count=1,
                            slave=int(test_config["slave"]),
                            battery_id=first_battery_id,
                        )
                        _LOGGER.info(
                            "SUCCESS: %s register at address %d (slave %d) with value: %s",
                            test_config["desc"],
                            test_config["addr"],
                            test_config["slave"],
                            result,
                        )
                        break
                    except (HubException, ConnectionException, ModbusIOException) as e:
                        _LOGGER.debug(
                            "Register %d (slave %d) failed: %s",
                            test_config["addr"],
                            test_config["slave"],
                            e,
                        )

            except (
                HubException,
                ConnectionException,
                ModbusIOException,
                OSError,
            ) as diag_err:
                _LOGGER.error("Diagnostic tests failed: %s", diag_err)

        try:
            test_data = await hub.read_data()
            _LOGGER.debug("Test data read result: %s", test_data)
            # Don't fail if no data initially - the coordinator will retry
            if test_data:
                _LOGGER.info("Successfully read initial data from SAX Battery")
            else:
                _LOGGER.warning(
                    "No initial data read, but connection appears stable - will retry via coordinator"
                )
        except (HubException, ConnectionException, ModbusIOException) as read_err:
            _LOGGER.warning(
                "Initial data read failed: %s - will retry via coordinator", read_err
            )
            # Don't fail the setup - let the coordinator handle retries

        _LOGGER.info(
            "Successfully connected to SAX Battery hub with %d batteries",
            len(battery_configs),
        )

    except HubException:
        await hub.disconnect()
        raise
    except (ConnectionException, ModbusIOException, OSError, TimeoutError) as e:
        _LOGGER.error("Hub initialization failed: %s", e)
        await hub.disconnect()
        raise HubInitFailed(f"Hub initialization failed: {e}") from e

    return hub
