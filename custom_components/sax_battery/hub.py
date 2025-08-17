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

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize the hub."""
        self._hass = hass
        self._host = host
        self._port = port
        self._client: AsyncModbusTcpClient | None = None
        self._connected = False
        self._lock = asyncio.Lock()
        self.battery = SAXBattery(self)

    @property
    def host(self) -> str:
        """Return the host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the port."""
        return self._port

    @property
    def client(self):
        """Return the modbus client."""
        return self._client

    async def connect(self) -> bool:
        """Connect to the inverter."""
        async with self._lock:
            try:
                _LOGGER.info(
                    "Attempting to connect to SAX Battery at %s:%s",
                    self._host,
                    self._port,
                )

                if self._client is None:
                    _LOGGER.debug("Creating new AsyncModbusTcpClient")
                    # Use parameters that worked in original version - try different compatibility settings
                    self._client = AsyncModbusTcpClient(
                        host=self._host,
                        port=self._port,
                        timeout=30,  # Increased timeout like original
                        retries=3,  # Explicit retry count
                        # Try with explicit framer (some devices are picky)
                        # framer=ModbusSocketFramer,
                    )

                if not self._client.connected:
                    _LOGGER.debug("Client not connected, attempting connection...")

                    # Add network diagnostics
                    _LOGGER.info(
                        "Testing network connectivity to %s:%s", self._host, self._port
                    )
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(5)
                        result = sock.connect_ex((self._host, self._port))
                        sock.close()
                        if result == 0:
                            _LOGGER.info(
                                "TCP connection to %s:%s successful",
                                self._host,
                                self._port,
                            )
                        else:
                            _LOGGER.error(
                                "TCP connection to %s:%s failed (error %s)",
                                self._host,
                                self._port,
                                result,
                            )
                    except OSError as e:
                        _LOGGER.error("Network test failed: %s", e)

                    result = await self._client.connect()
                    _LOGGER.debug("Modbus connection result: %s", result)

                    if not result:
                        _LOGGER.error(
                            "Failed to connect to %s:%s - connection result was False",
                            self._host,
                            self._port,
                        )
                        return False

                self._connected = True
                _LOGGER.info(
                    "Successfully connected to SAX Battery at %s:%s",
                    self._host,
                    self._port,
                )

            except (ConnectionException, OSError, TimeoutError) as e:
                _LOGGER.error(
                    "Connection error to %s:%s: %s", self._host, self._port, e
                )
                self._connected = False
                return False
            except (ModbusIOException,) as e:
                _LOGGER.error(
                    "Modbus connection error to %s:%s: %s", self._host, self._port, e
                )
                self._connected = False
                return False
            else:
                return True

    async def disconnect(self) -> None:
        """Disconnect from the inverter."""
        async with self._lock:
            if self._client:
                self._client.close()
                self._client = None
            self._connected = False

    async def modbus_read_holding_registers(
        self, address: int, count: int, slave: int = 1
    ) -> list[int]:
        """Read holding registers with pymodbus 3.9.2 compatibility."""
        _LOGGER.debug(
            "Reading %d registers from address %d (slave %d)", count, address, slave
        )

        # Try to reconnect if not connected
        if not self._connected or not self._client:
            _LOGGER.warning(
                "Not connected (connected=%s, client=%s), attempting to reconnect",
                self._connected,
                self._client is not None,
            )
            if not await self.connect():
                raise HubConnectionError("Failed to connect to device")

        try:
            # Use the same pattern as the working original code
            result = await self._client.read_holding_registers(
                address=address,
                count=count,
                slave=slave,
            )

            _LOGGER.debug("Read result: %s", result)

            if result.isError():
                _LOGGER.error("Modbus error response: %s", result)
                # Don't disconnect on single read errors - might be temporary
                raise HubException(f"Modbus error: {result}")

        except (ConnectionException, ModbusIOException) as e:
            _LOGGER.error("Modbus communication error: %s", e)
            # Only disconnect after multiple failures or specific connection issues
            if "No response received" in str(e) or "Connection" in str(e):
                _LOGGER.warning(
                    "Connection issue detected, will try to reconnect on next read"
                )
                self._connected = False
            raise HubConnectionError(f"Modbus communication error: {e}") from e
        else:
            _LOGGER.debug("Successfully read registers: %s", result.registers)
            return result.registers

    async def read_data(self) -> dict[str, Any]:
        """Read data from all batteries."""
        if not self._connected:
            if not await self.connect():
                raise HubConnectionError("Unable to connect to device")

        try:
            data = {}
            battery_data = await self.battery.read_data()
            if battery_data:
                # For single battery setup, add both direct keys and battery_a prefixed keys
                data.update(battery_data)

                # Add battery-specific prefixed keys for multi-battery compatibility
                for key, value in battery_data.items():
                    data[f"battery_a_{key}"] = value

                _LOGGER.debug("Successfully read data with %d keys", len(data))
        except (HubException, ConnectionException, ModbusIOException) as e:
            _LOGGER.error("Error reading data: %s", e)
            raise
        else:
            return data


class SAXBattery:
    """SAX Battery representation."""

    def __init__(self, hub: SAXBatteryHub) -> None:
        """Initialize the battery."""
        self._hub = hub
        self._register_map = self._get_register_map()
        self.battery_id = "battery_a"  # Default battery ID
        self._data_manager = None  # Will be set by coordinator

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
    """Create and initialize the hub."""
    _LOGGER.debug("Creating hub with config: %s", list(config.keys()))

    # Find the first battery configuration
    host = None
    port = None

    # Look for battery_a_host, battery_b_host, etc.
    for key, value in config.items():
        if key.endswith("_host"):
            host = value
            # Find corresponding port
            port_key = key.replace("_host", "_port")
            port = config.get(port_key, 502)
            _LOGGER.debug(
                "Found battery config: %s=%s, %s=%s", key, host, port_key, port
            )
            break

    if host is None:
        # Fallback to direct host/port if available
        host = config.get("host") or config.get(CONF_HOST)
        port = config.get("port") or config.get(CONF_PORT, 502)
        _LOGGER.debug("Using fallback config: host=%s, port=%s", host, port)

    if host is None:
        _LOGGER.error(
            "No host configuration found in config keys: %s", list(config.keys())
        )
        raise HubInitFailed("No host configuration found")

    # Ensure port is an integer
    if isinstance(port, str):
        port = int(port)
    elif port is None:
        port = 502

    _LOGGER.info("Initializing SAX Battery Hub with %s:%s", host, port)
    hub = SAXBatteryHub(hass, host, port)

    # Test connection
    try:
        if not await hub.connect():
            msg = f"Could not connect to SAX Battery at {host}:{port}"
            _LOGGER.error(msg)
            raise HubInitFailed(msg)

        # Test reading some data - but don't fail if it doesn't work immediately
        _LOGGER.debug("Testing data read from hub...")

        # First, let's try some basic diagnostic reads
        _LOGGER.info("Running basic Modbus diagnostics...")
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
                        address=test_config["addr"], count=1, slave=test_config["slave"]
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

        _LOGGER.info("Successfully connected to SAX Battery at %s:%s", host, port)

    except HubException:
        await hub.disconnect()
        raise
    except (ConnectionException, ModbusIOException, OSError, TimeoutError) as e:
        _LOGGER.error("Hub initialization failed: %s", e)
        await hub.disconnect()
        raise HubInitFailed(f"Hub initialization failed: {e}") from e

    return hub
