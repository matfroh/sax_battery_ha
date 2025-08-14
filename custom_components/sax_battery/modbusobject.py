"""Modbus communication classes."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from pymodbus.client import ModbusTcpClient
from pymodbus.client.mixin import ModbusClientMixin  # For DATATYPE
from pymodbus.exceptions import ModbusException

from homeassistant.components.sensor import SensorDeviceClass

from .const import MANUAL_CONTROL_SWITCH, SOLAR_CHARGING_SWITCH
from .enums import TypeConstants

if TYPE_CHECKING:
    from .items import ModbusItem

_LOGGER = logging.getLogger(__name__)


class ModbusAPI:
    """Modbus API for SAX Battery communication."""

    def __init__(self, host: str, port: int, battery_id: str) -> None:
        """Initialize ModbusAPI.

        Args:
            host: Modbus host IP
            port: Modbus port
            battery_id: Battery identifier

        """
        self._host = host
        self._port = port
        self.battery_id = battery_id
        self._connected = False
        self._connect_pending = False
        self._failed_reconnect_counter = 0

        self._modbus_client = ModbusTcpClient(
            host=host,
            port=port,
            timeout=10,
            retries=1,
            name=f"SAX_BATTERY_{battery_id.upper()}",
        )

    async def connect(self, startup: bool = False) -> bool:
        """Open modbus connection."""
        if self._connect_pending:
            _LOGGER.warning("Connection to battery already pending")
            return bool(self._modbus_client.connected)

        try:
            self._connect_pending = True
            if self._failed_reconnect_counter >= 3 and not startup:
                _LOGGER.warning(
                    "Connection to battery failed %d times. Waiting 5 minutes",
                    self._failed_reconnect_counter,
                )
                await asyncio.sleep(300)

            def _connect() -> bool:
                result = self._modbus_client.connect()  # type: ignore[no-untyped-call]
                return bool(result)

            connected = await asyncio.get_event_loop().run_in_executor(None, _connect)

            if connected:
                self._failed_reconnect_counter = 0
                self._connect_pending = False
                _LOGGER.info(
                    "Successfully connected to battery %s at %s:%d",
                    self.battery_id,
                    self._host,
                    self._port,
                )
                return True

            self._failed_reconnect_counter += 1
            self._connect_pending = False
            self._close_connection()
            return False  # noqa: TRY300

        except ModbusException as exc:
            _LOGGER.warning("Connection to battery failed: %s", exc)
            self._failed_reconnect_counter += 1
            self._connect_pending = False
            self._close_connection()
            return False

    def close(self) -> bool:
        """Close modbus connection."""
        return self._close_connection()

    def _close_connection(self) -> bool:
        """Close connection with proper error handling."""
        try:

            def _close() -> Any:
                return self._modbus_client.close()  # type: ignore[no-untyped-call]

            _close()
            return True  # noqa: TRY300
        except ModbusException:
            _LOGGER.warning("Closing connection to battery failed")
            return False

    def get_device(self) -> ModbusTcpClient:
        """Return modbus client."""
        return self._modbus_client

    async def write_holding_register(
        self, address: int, value: int, slave: int = 1
    ) -> bool:
        """Write a single holding register."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                _LOGGER.error("Cannot write - not connected to modbus")
                return False

        try:

            def _write() -> bool:
                result = self._modbus_client.write_register(
                    address=address, value=value, device_id=slave
                )
                return not result.isError() if result else False

            return await asyncio.get_event_loop().run_in_executor(None, _write)

        except ModbusException as exc:
            _LOGGER.warning("Failed to write holding register %d: %s", address, exc)
            return False

    async def read_holding_registers(
        self,
        address: int,
        count: int = 1,
        slave: int = 1,
        data_type: ModbusClientMixin.DATATYPE = ModbusClientMixin.DATATYPE.INT16,
        modbus_item: ModbusItem | None = None,
    ) -> int | None:
        """Read and validate a single holding register value."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                _LOGGER.error("Cannot read - not connected to modbus")
                return None

        try:

            def _read() -> int | None:
                result = self._modbus_client.read_holding_registers(
                    address=address, count=count, device_id=slave
                )
                if result.isError():
                    _LOGGER.warning(
                        "Error reading holding registers at %d: %s", address, result
                    )
                    return None
                value = ModbusTcpClient.convert_from_registers(
                    result.registers, data_type=data_type
                )
                # Ensure value is int for validation
                if isinstance(value, list):
                    value_int = int(value[0]) if value else None
                elif isinstance(value, (int, float)):
                    value_int = int(value)
                elif isinstance(value, str):
                    try:
                        value_int = int(value)
                    except ValueError:
                        value_int = None
                # else:
                #    value_int = None # Statement is unreachable
                if modbus_item and value_int is not None:
                    return self.validate_value(modbus_item, value_int)
                return value_int

            return await asyncio.get_event_loop().run_in_executor(None, _read)

        except ModbusException as exc:
            _LOGGER.warning("Failed to read holding registers at %d: %s", address, exc)
            return None

    async def read_input_registers(
        self,
        address: int,
        count: int = 1,
        slave: int = 1,
        data_type: ModbusClientMixin.DATATYPE = ModbusClientMixin.DATATYPE.INT16,
        modbus_item: ModbusItem | None = None,
    ) -> int | None:
        """Read and validate a single input register value."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                _LOGGER.error("Cannot read - not connected to modbus")
                return None

        try:

            def _read() -> int | None:
                result = self._modbus_client.read_input_registers(
                    address=address, count=count, device_id=slave
                )
                if result.isError():
                    _LOGGER.warning(
                        "Error reading input registers at %d: %s", address, result
                    )
                    return None
                value = ModbusTcpClient.convert_from_registers(
                    result.registers, data_type=data_type
                )
                # Ensure value is int for validation
                if isinstance(value, list):
                    value_int = int(value[0]) if value else None
                elif isinstance(value, (int, float)):
                    value_int = int(value)
                elif isinstance(value, str):
                    try:
                        value_int = int(value)
                    except ValueError:
                        value_int = None
                # else:
                #    value_int = None # Statement is unreachable
                if modbus_item and value_int is not None:
                    return self.validate_value(modbus_item, value_int)
                return value_int

            return await asyncio.get_event_loop().run_in_executor(None, _read)

        except ModbusException as exc:
            _LOGGER.warning("Failed to read input registers at %d: %s", address, exc)
            return None

    @staticmethod
    def validate_value(item: ModbusItem, raw_value: int) -> int | None:
        """Validate and process raw modbus value."""
        if not item.entitydescription:
            return raw_value

        device_class = item.entitydescription.device_class
        if not device_class:
            return raw_value

        match device_class:
            case SensorDeviceClass.TEMPERATURE:
                return ModbusAPI._validate_temperature(raw_value)
            case SensorDeviceClass.BATTERY:
                return ModbusAPI._validate_percentage(raw_value)
            case (
                SensorDeviceClass.POWER
                | SensorDeviceClass.ENERGY
                | SensorDeviceClass.VOLTAGE
                | SensorDeviceClass.CURRENT
            ):
                return raw_value
            case _:
                return raw_value

    @staticmethod
    def _validate_temperature(val: int) -> int | None:
        """Validate temperature values."""
        match val:
            case -32768 | 32768:
                return None
            case -32767:
                return -999
            case _:
                if val > 32768:
                    val -= 65536
                return val

    @staticmethod
    def _validate_percentage(val: int) -> int | None:
        """Validate percentage values."""
        if val == 65535:
            return None
        return val


class ModbusObject:
    """Wrapper for modbus items with validation and communication."""

    def __init__(
        self,
        modbus_api: ModbusAPI,
        modbus_item: ModbusItem,
    ) -> None:
        """Initialize ModbusObject.

        Args:
            modbus_api: The modbus API instance
            modbus_item: The modbus item definition

        """
        self._modbus_api = modbus_api
        self._modbus_item = modbus_item

    async def async_read_value(self) -> int | None:
        """Read value from modbus register."""
        if self._modbus_item.is_invalid:
            return None

        try:
            if not self._modbus_api.get_device().connected:
                connected = await self._modbus_api.connect()
                if not connected:
                    _LOGGER.debug(
                        "Failed to connect for reading %s", self._modbus_item.name
                    )
                    return None

            value = await self._modbus_api.read_holding_registers(
                self._modbus_item.address,
                count=1,
                slave=self._modbus_item.battery_slave_id,
                data_type=self._modbus_item.data_type,
                modbus_item=self._modbus_item,
            )

            if value is None:
                _LOGGER.debug("No data received for %s", self._modbus_item.name)
                self._modbus_item.is_invalid = True
                return None

            self._modbus_item.state = value
            self._modbus_item.is_invalid = False
            return value  # noqa: TRY300

        except ModbusException as exc:
            _LOGGER.warning(
                "Error reading %s at address %d: %s",
                self._modbus_item.name,
                self._modbus_item.address,
                exc,
            )
            return None

    async def async_write_value(self, value: int) -> bool:
        """Write value to modbus register."""
        try:
            match self._modbus_item.mtype:
                case (
                    TypeConstants.SENSOR
                    | TypeConstants.NUMBER_RO
                    | TypeConstants.SENSOR_CALC
                ):
                    _LOGGER.warning(
                        "Attempted to write to read-only register %s",
                        self._modbus_item.name,
                    )
                    return False
                case _:
                    return await self._modbus_api.write_holding_register(
                        self._modbus_item.address,
                        self._prepare_write_value(value),
                        slave=self._modbus_item.battery_slave_id,
                    )
        except ModbusException as exc:
            _LOGGER.warning(
                "Error writing %d to %s: %s",
                value,
                self._modbus_item.name,
                exc,
            )
            return False

    def _prepare_write_value(self, value: int) -> int:
        """Prepare value for writing to modbus."""
        if (
            self._modbus_item.entitydescription
            and self._modbus_item.entitydescription.device_class
            == SensorDeviceClass.TEMPERATURE
            and value < 0
        ):
            return value + 65536
        return value

    def get_switch_on_value(self) -> int:
        """Get the modbus value for switch ON state."""
        if self._is_pilot_switch():
            return 1

        if self._modbus_item.resultlist:
            for status_item in self._modbus_item.resultlist:
                if status_item.text.lower() in ("on", "connected"):
                    return status_item.number
        return 1

    def get_switch_off_value(self) -> int:
        """Get the modbus value for switch OFF state."""
        if self._is_pilot_switch():
            return 0

        if self._modbus_item.resultlist:
            for status_item in self._modbus_item.resultlist:
                if status_item.text.lower() in ("off", "standby"):
                    return status_item.number
        return 0

    def _is_pilot_switch(self) -> bool:
        """Check if this is a pilot switch."""
        return self._modbus_item.name in [SOLAR_CHARGING_SWITCH, MANUAL_CONTROL_SWITCH]

    @property
    def item(self) -> ModbusItem:
        """Get the modbus item."""
        return self._modbus_item
