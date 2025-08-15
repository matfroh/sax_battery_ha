"""Modbus communication classes."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import MANUAL_CONTROL_SWITCH, SOLAR_CHARGING_SWITCH
from .enums import TypeConstants

if TYPE_CHECKING:
    from .items import ModbusItem

_LOGGER = logging.getLogger(__name__)


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

    async def async_read_value(self) -> int | float | None:
        """Read value from modbus register."""
        if self._modbus_item.is_invalid:
            return None

        try:
            result = await self._modbus_api.read_holding_registers(
                count=1, modbus_item=self._modbus_item
            )
            # Ensure we return a proper numeric type
            if isinstance(result, (int, float)):
                return result
            return None  # noqa: TRY300
        except ModbusException:
            _LOGGER.exception("Failed to read value for %s", self._modbus_item.name)
            return None

    async def async_write_value(self, value: float) -> bool:
        """Write value to modbus register."""
        try:
            match self._modbus_item.mtype:
                case (
                    TypeConstants.SENSOR
                    | TypeConstants.NUMBER_RO
                    | TypeConstants.SENSOR_CALC
                ):
                    _LOGGER.warning(
                        "Attempted to write to read-only item %s",
                        self._modbus_item.name,
                    )
                    return False
                case _:
                    return await self._modbus_api.write_holding_register(
                        value=value, modbus_item=self._modbus_item
                    )
        except ModbusException:
            _LOGGER.exception("Failed to write value for %s", self._modbus_item.name)
            return False

    def get_switch_on_value(self) -> int:
        """Get the value to write for switch on state."""
        return 3 if self._is_pilot_switch() else 2

    def get_switch_off_value(self) -> int:
        """Get the value to write for switch off state."""
        return 4 if self._is_pilot_switch() else 1

    def _is_pilot_switch(self) -> bool:
        """Check if this is a pilot switch."""
        return self._modbus_item.name in [MANUAL_CONTROL_SWITCH, SOLAR_CHARGING_SWITCH]

    @property
    def modbus_item(self) -> ModbusItem:
        """Get the modbus item."""
        return self._modbus_item


class ModbusAPI:
    """Modbus API for SAX Battery communication."""

    def __init__(self, host: str, port: int, battery_id: str) -> None:
        """Initialize ModbusAPI."""
        self._host = host
        self._port = port
        self._battery_id = battery_id
        self._modbus_client: ModbusTcpClient | None = None
        self._connect_pending = False
        self._failed_reconnect_counter = 0

    async def connect(self, startup: bool = False) -> bool:
        """Connect to the modbus device."""
        if self._connect_pending:
            return False

        self._connect_pending = True

        try:
            self._modbus_client = ModbusTcpClient(host=self._host, port=self._port)
            if await asyncio.get_event_loop().run_in_executor(
                None, self._modbus_client.connect
            ):
                if self._modbus_client.connected:
                    self._failed_reconnect_counter = 0
                    _LOGGER.debug("Connected to modbus device %s", self._battery_id)
                    return True

            # Connection failed
            self._failed_reconnect_counter += 1
            self._close_connection()
            return False  # noqa: TRY300

        except ModbusException as exc:
            _LOGGER.error("ModbusException during connect: %s", exc)
            self._failed_reconnect_counter += 1
            self._close_connection()
            return False
        finally:
            self._connect_pending = False

    def close(self) -> bool:
        """Close the modbus connection."""
        try:
            return self._close_connection()
        except ModbusException as exc:
            _LOGGER.error("ModbusException during close: %s", exc)
            return False

    def _close_connection(self) -> bool:
        """Close the modbus connection."""
        if self._modbus_client is not None:
            self._modbus_client.close()  # type: ignore[no-untyped-call]
            self._modbus_client = None
        return True

    def get_device(self) -> ModbusTcpClient:
        """Get the modbus device."""
        if self._modbus_client is None:
            msg = "Modbus client not connected"
            raise ModbusException(msg)  # type: ignore[no-untyped-call]
        return self._modbus_client

    async def write_holding_register(
        self, value: float, modbus_item: ModbusItem | None = None
    ) -> bool:
        """Write to holding register."""
        if self._modbus_client is None or not self._modbus_client.connected:
            return False

        def _write() -> bool:
            try:
                # Apply factor and offset
                if modbus_item:
                    raw_value = int((value - modbus_item.offset) * modbus_item.factor)
                    address = modbus_item.address
                    device_id = modbus_item.battery_slave_id
                else:
                    raw_value = int(value)
                    address = 0
                    device_id = 1

                # Type guard to ensure _modbus_client is not None
                if self._modbus_client is None:
                    return False

                result = self._modbus_client.write_register(
                    address=address, value=raw_value, device_id=device_id
                )
                return not result.isError()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Write error: %s", exc)
                return False

        return await asyncio.get_event_loop().run_in_executor(None, _write)

    async def read_holding_registers(
        self,
        count: int,
        modbus_item: ModbusItem,
    ) -> int | float | None:
        """Read holding registers asynchronously."""

        def _read() -> int | float | None:
            """Sync internal read function."""

            try:
                _LOGGER.debug(
                    "Reading holding registers - Address: %s, Count: %s, Slave: %s",
                    modbus_item.address,
                    count,
                    modbus_item.battery_slave_id,
                )

                # Type guard to ensure _modbus_client is not None
                if self._modbus_client is None:
                    return None

                result = self._modbus_client.read_holding_registers(
                    address=modbus_item.address,
                    count=count,
                    device_id=modbus_item.battery_slave_id,
                )
                if result.isError():
                    _LOGGER.warning(
                        "Failed to read holding registers - Address: %s, Count: %s, Slave: %s",
                        modbus_item.address,
                        count,
                        modbus_item.battery_slave_id,
                    )
                    return None

                if not result.registers:
                    return None

                if hasattr(modbus_item, "data_type") and modbus_item.data_type:
                    converted_data = self._modbus_client.convert_from_registers(
                        result.registers, modbus_item.data_type
                    )
                    # Handle different return types from convert_from_registers
                    if isinstance(converted_data, (list, tuple)) and converted_data:
                        first_value = converted_data[0]
                        if isinstance(first_value, (int, float)):
                            # Apply factor and offset from ModbusItem
                            return first_value * modbus_item.factor + modbus_item.offset
                    elif isinstance(converted_data, (int, float)):
                        # Apply factor and offset from ModbusItem
                        return converted_data * modbus_item.factor + modbus_item.offset
                    return None

                # Fallback to raw register value
                raw_value = result.registers[0]
                if isinstance(raw_value, (int, float)):
                    # Apply factor and offset from ModbusItem
                    return raw_value * modbus_item.factor + modbus_item.offset

            except ModbusException as exc:
                _LOGGER.warning(
                    "ModbusException reading holding registers - Address: %s, Count: %s, Slave: %s: %s",
                    modbus_item.address,
                    count,
                    modbus_item.battery_slave_id,
                    exc,
                )
                return None
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error(
                    "Unexpected error reading holding registers - Address: %s, Count: %s, Slave: %s: %s",
                    modbus_item.address,
                    count,
                    modbus_item.battery_slave_id,
                    exc,
                )
                return None

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _read)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "Error in executor for reading holding registers - Address: %s, Count: %s, Slave: %s: %s",
                modbus_item.address,
                count,
                modbus_item.battery_slave_id,
                exc,
            )
            return None
