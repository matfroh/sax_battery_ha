"""SAX Battery Modbus Hub for pymodbus 3.9.2 compatibility."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusIOException
from pymodbus.pdu import ExceptionResponse

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

    async def connect(self) -> bool:
        """Connect to the inverter."""
        async with self._lock:
            try:
                if self._client is None:
                    self._client = AsyncModbusTcpClient(
                        host=self._host,
                        port=self._port,
                        timeout=10,
                    )

                if not self._client.connected:
                    result = await self._client.connect()
                    if not result:
                        _LOGGER.error("Failed to connect to %s:%s", self._host, self._port)
                        return False

                self._connected = True
                _LOGGER.debug("Connected to %s:%s", self._host, self._port)

            except (ConnectionException, OSError, TimeoutError) as e:
                _LOGGER.error("Connection error to %s:%s: %s", self._host, self._port, e)
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
        if not self._connected or not self._client:
            raise HubConnectionError("Not connected to device")

        try:
            # Use slave parameter for backward compatibility
            result = await self._client.read_holding_registers(
                address=address,
                count=count,
                slave=slave,
            )

            if result.isError():
                if isinstance(result, ExceptionResponse):
                    raise HubException(f"Modbus exception: {result}")
                raise HubException(f"Modbus error: {result}")
                
        except (ConnectionException, ModbusIOException) as e:
            _LOGGER.error("Modbus communication error: %s", e)
            self._connected = False
            raise HubConnectionError(f"Modbus communication error: {e}") from e
        except Exception as e:
            _LOGGER.error("Unexpected error reading registers: %s", e)
            raise HubException(f"Unexpected error: {e}") from e
        else:
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
                data.update(battery_data)
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

    def _get_register_map(self) -> dict[str, dict[str, Any]]:
        """Get the register map for SAX Battery."""
        # This is the register configuration from the original code
        return {
            "soc": {
                "address": 13030,
                "count": 1,
                "scale": 0.1,
                "unit": "%",
                "name": "State of Charge",
            },
            "status": {
                "address": 13006,
                "count": 1,
                "scale": 1,
                "unit": None,
                "name": "Status",
            },
            "power": {
                "address": 13021,
                "count": 2,
                "scale": 1,
                "unit": "W",
                "name": "Power",
                "signed": True,
            },
            "smartmeter": {
                "address": 13034,
                "count": 1,
                "scale": 1,
                "unit": None,
                "name": "Smart Meter",
            },
            "capacity": {
                "address": 13025,
                "count": 2,
                "scale": 0.1,
                "unit": "Wh",
                "name": "Capacity",
            },
            "cycles": {
                "address": 13027,
                "count": 2,
                "scale": 1,
                "unit": "cycles",
                "name": "Cycles",
            },
            "temp": {
                "address": 13005,
                "count": 1,
                "scale": 0.1,
                "unit": "°C",
                "name": "Temperature",
            },
            "energy_produced": {
                "address": 13001,
                "count": 2,
                "scale": 0.1,
                "unit": "kWh",
                "name": "Energy Produced",
            },
            "energy_consumed": {
                "address": 13003,
                "count": 2,
                "scale": 0.1,
                "unit": "kWh",
                "name": "Energy Consumed",
            },
            "voltage_l1": {
                "address": 13011,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Voltage L1",
            },
            "voltage_l2": {
                "address": 13012,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Voltage L2",
            },
            "voltage_l3": {
                "address": 13013,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Voltage L3",
            },
            "current_l1": {
                "address": 13014,
                "count": 1,
                "scale": 0.1,
                "unit": "A",
                "name": "Current L1",
                "signed": True,
            },
            "current_l2": {
                "address": 13015,
                "count": 1,
                "scale": 0.1,
                "unit": "A",
                "name": "Current L2",
                "signed": True,
            },
            "current_l3": {
                "address": 13016,
                "count": 1,
                "scale": 0.1,
                "unit": "A",
                "name": "Current L3",
                "signed": True,
            },
            "grid_frequency": {
                "address": 13017,
                "count": 1,
                "scale": 0.01,
                "unit": "Hz",
                "name": "Grid Frequency",
            },
            "active_power_l1": {
                "address": 13018,
                "count": 1,
                "scale": 1,
                "unit": "W",
                "name": "Active Power L1",
                "signed": True,
            },
            "active_power_l2": {
                "address": 13019,
                "count": 1,
                "scale": 1,
                "unit": "W",
                "name": "Active Power L2",
                "signed": True,
            },
            "active_power_l3": {
                "address": 13020,
                "count": 1,
                "scale": 1,
                "unit": "W",
                "name": "Active Power L3",
                "signed": True,
            },
            "apparent_power": {
                "address": 13031,
                "count": 1,
                "scale": 1,
                "unit": "VA",
                "name": "Apparent Power",
            },
            "reactive_power": {
                "address": 13032,
                "count": 1,
                "scale": 1,
                "unit": "VAR",
                "name": "Reactive Power",
                "signed": True,
            },
            "power_factor": {
                "address": 13033,
                "count": 1,
                "scale": 0.001,
                "unit": None,
                "name": "Power Factor",
                "signed": True,
            },
            "phase_currents_sum": {
                "address": 13029,
                "count": 1,
                "scale": 0.1,
                "unit": "A",
                "name": "Phase Currents Sum",
                "signed": True,
            },
            "ac_power_total": {
                "address": 13023,
                "count": 1,
                "scale": 1,
                "unit": "W",
                "name": "AC Power Total",
                "signed": True,
            },
            "storage_status": {
                "address": 13007,
                "count": 1,
                "scale": 1,
                "unit": None,
                "name": "Storage Status",
            },
            "smartmeter_voltage_l1": {
                "address": 13035,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Smart Meter Voltage L1",
            },
            "smartmeter_voltage_l2": {
                "address": 13036,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Smart Meter Voltage L2",
            },
            "smartmeter_voltage_l3": {
                "address": 13037,
                "count": 1,
                "scale": 0.1,
                "unit": "V",
                "name": "Smart Meter Voltage L3",
            },
            "smartmeter_current_l1": {
                "address": 13038,
                "count": 1,
                "scale": 0.1,
                "unit": "A",
                "name": "Smart Meter Current L1",
                "signed": True,
            },
            "smartmeter_current_l2": {
                "address": 13039,
                "count": 1,
                "scale": 0.1,
                "unit": "A",
                "name": "Smart Meter Current L2",
                "signed": True,
            },
            "smartmeter_current_l3": {
                "address": 13040,
                "count": 1,
                "scale": 0.1,
                "unit": "A",
                "name": "Smart Meter Current L3",
                "signed": True,
            },
            "smartmeter_total_power": {
                "address": 13041,
                "count": 2,
                "scale": 1,
                "unit": "W",
                "name": "Smart Meter Total Power",
                "signed": True,
            },
        }

    def _convert_value(self, raw_value: int | list[int], config: dict[str, Any]) -> float | int:
        """Convert raw modbus value to proper value."""
        if isinstance(raw_value, list):
            if len(raw_value) == 2:
                # 32-bit value (high word, low word)
                value = (raw_value[0] << 16) + raw_value[1]
            else:
                value = raw_value[0]
        else:
            value = raw_value

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
        data: dict[str, float | int | None] = {}

        for key, config in self._register_map.items():
            try:
                raw_registers = await self._hub.modbus_read_holding_registers(
                    address=config["address"],
                    count=config["count"],
                    slave=1,
                )

                if raw_registers is not None:
                    if config["count"] == 1:
                        value = self._convert_value(raw_registers[0], config)
                    else:
                        value = self._convert_value(raw_registers, config)

                    data[key] = value
                    _LOGGER.debug("Read %s: %s %s", key, value, config.get("unit", ""))

            except (HubException, ConnectionException, ModbusIOException) as e:
                _LOGGER.error("Error reading %s: %s", key, e)
                data[key] = None

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
            _LOGGER.debug("Found battery config: %s=%s, %s=%s", key, host, port_key, port)
            break
    
    if host is None:
        # Fallback to direct host/port if available
        host = config.get("host") or config.get(CONF_HOST)
        port = config.get("port") or config.get(CONF_PORT, 502)
        _LOGGER.debug("Using fallback config: host=%s, port=%s", host, port)
    
    if host is None:
        _LOGGER.error("No host configuration found in config keys: %s", list(config.keys()))
        raise HubInitFailed("No host configuration found")

    _LOGGER.info("Initializing SAX Battery Hub with %s:%s", host, port)
    hub = SAXBatteryHub(hass, host, port)

    # Test connection
    try:
        if not await hub.connect():
            msg = f"Could not connect to SAX Battery at {host}:{port}"
            _LOGGER.error(msg)
            raise HubInitFailed(msg)

        # Test reading some data
        test_data = await hub.read_data()
        if not test_data:
            msg = f"Could not read data from SAX Battery at {host}:{port}"
            _LOGGER.error(msg)
            raise HubInitFailed(msg)

        _LOGGER.info("Successfully connected to SAX Battery at %s:%s", host, port)

    except HubException:
        await hub.disconnect()
        raise
    except Exception as e:
        _LOGGER.error("Hub initialization failed: %s", e)
        await hub.disconnect()
        raise HubInitFailed(f"Hub initialization failed: {e}") from e

    return hub
