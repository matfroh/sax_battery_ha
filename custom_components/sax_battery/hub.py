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
                    _LOGGER.info(
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
                            timeout=30,  # Increased timeout like original
                            retries=3,  # Explicit retry count
                        )

                    client = self._clients[battery_id]
                    if client and not client.connected:
                        _LOGGER.debug(
                            "Client for %s not connected, attempting connection...",
                            battery_id,
                        )

                        # Add network diagnostics
                        _LOGGER.info(
                            "Testing network connectivity to %s:%s",
                            battery.host,
                            battery.port,
                        )
                        try:
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(5)
                            result = sock.connect_ex((battery.host, battery.port))
                            sock.close()
                            if result == 0:
                                _LOGGER.info(
                                    "TCP connection to %s:%s successful",
                                    battery.host,
                                    battery.port,
                                )
                            else:
                                _LOGGER.error(
                                    "TCP connection to %s:%s failed (error %s)",
                                    battery.host,
                                    battery.port,
                                    result,
                                )
                        except OSError as e:
                            _LOGGER.error(
                                "Network test failed for %s: %s", battery_id, e
                            )

                        result = await client.connect()
                        _LOGGER.debug(
                            "Modbus connection result for %s: %s", battery_id, result
                        )

                        if not result:
                            _LOGGER.error(
                                "Failed to connect to %s at %s:%s - connection result was False",
                                battery_id,
                                battery.host,
                                battery.port,
                            )
                            all_connected = False
                            continue

                    self._connected[battery_id] = True
                    _LOGGER.info(
                        "Successfully connected to SAX Battery %s at %s:%s",
                        battery_id,
                        battery.host,
                        battery.port,
                    )

                except (ConnectionException, OSError, TimeoutError) as e:
                    _LOGGER.error(
                        "Connection error to %s at %s:%s: %s",
                        battery_id,
                        battery.host,
                        battery.port,
                        e,
                    )
                    self._connected[battery_id] = False
                    all_connected = False
                except (ModbusIOException,) as e:
                    _LOGGER.error(
                        "Modbus connection error to %s at %s:%s: %s",
                        battery_id,
                        battery.host,
                        battery.port,
                        e,
                    )
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

    async def modbus_read_holding_registers(
        self, address: int, count: int, slave: int = 1, battery_id: str | None = None
    ) -> list[int]:
        """Read holding registers with pymodbus 3.9.2 compatibility."""
        # Use first battery if no specific battery_id provided (backward compatibility)
        if battery_id is None:
            battery_id = list(self.batteries.keys())[0] if self.batteries else ""

        _LOGGER.debug(
            "Reading %d registers from address %d (slave %d) for battery %s",
            count,
            address,
            slave,
            battery_id,
        )

        # Get the specific client for this battery
        client = self._clients.get(battery_id)
        is_connected = self._connected.get(battery_id, False)

        # Try to reconnect if not connected
        if not is_connected or not client:
            _LOGGER.warning(
                "Battery %s not connected (connected=%s, client=%s), attempting to reconnect",
                battery_id,
                is_connected,
                client is not None,
            )
            if not await self.connect():
                raise HubConnectionError(f"Failed to connect to battery {battery_id}")

        # Get the client for this specific battery after potential reconnect
        client = self._clients.get(battery_id)
        if not client:
            raise HubConnectionError(f"No client available for battery {battery_id}")

        try:
            # Use the same pattern as the working original code
            result = await client.read_holding_registers(
                address=address,
                count=count,
                slave=slave,
            )

            _LOGGER.debug("Read result for battery %s: %s", battery_id, result)

            if result.isError():
                _LOGGER.error(
                    "Modbus error response for battery %s: %s", battery_id, result
                )
                # Don't disconnect on single read errors - might be temporary
                raise HubException(f"Modbus error for battery {battery_id}: {result}")

        except (ConnectionException, ModbusIOException) as e:
            _LOGGER.error(
                "Modbus communication error for battery %s: %s", battery_id, e
            )
            # Only disconnect after multiple failures or specific connection issues
            if "No response received" in str(e) or "Connection" in str(e):
                _LOGGER.warning(
                    "Connection issue detected for battery %s, will try to reconnect on next read",
                    battery_id,
                )
                self._connected[battery_id] = False
            raise HubConnectionError(
                f"Modbus communication error for battery {battery_id}: {e}"
            ) from e
        else:
            _LOGGER.debug("Successfully read registers: %s", result.registers)
            return result.registers

    async def read_data(self) -> dict[str, Any]:
        """Read data from all batteries."""
        # Connect to all batteries first
        if not await self.connect():
            raise HubConnectionError("Unable to connect to any device")

        try:
            data = {}

            # Read data from each configured battery
            for battery_id, battery in self.batteries.items():
                try:
                    battery_data = await battery.read_data()
                    if battery_data:
                        # Add both direct keys (for backward compatibility) and battery-specific keys
                        if (
                            battery_id == list(self.batteries.keys())[0]
                        ):  # First battery gets direct keys too
                            data.update(battery_data)

                        # Add battery-specific prefixed keys
                        for key, value in battery_data.items():
                            data[f"{battery_id}_{key}"] = value

                        _LOGGER.debug(
                            "Successfully read data from %s with %d keys",
                            battery_id,
                            len(battery_data),
                        )
                except (HubException, ConnectionException, ModbusIOException) as e:
                    _LOGGER.error("Error reading data from %s: %s", battery_id, e)
                    # Continue with other batteries even if one fails

            _LOGGER.debug(
                "Successfully read data from all batteries with %d total keys",
                len(data),
            )
        except Exception as e:
            _LOGGER.error("Error reading data from batteries: %s", e)
            raise
        else:
            return data


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
        """Get the register map for SAX Battery from original working version."""
        # Use the exact register configuration that was working with pymodbus 3.7.3
        return {
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
            "phase_currents_sum": {
                "address": 40073,
                "count": 1,
                "scale": 0.01,
                "unit": "A",
                "name": "Phase Currents Sum",
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
