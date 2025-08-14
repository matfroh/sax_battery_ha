"""Modbus communication classes."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

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

    async def async_read_value(self) -> int | None:
        """Read value from modbus register."""
        if self._modbus_item.is_invalid:
            return None

        try:
            if not self._modbus_api.get_device().connected:
                connected = await self._modbus_api.connect()
                if not connected:
                    return None

            value = await self._modbus_api.read_holding_registers(
                count=1,
                slave=self._modbus_item.battery_slave_id,
                modbus_item=self._modbus_item,
            )

            if value is None:
                _LOGGER.debug("No data received for %s", self._modbus_item.name)
                self._modbus_item.is_invalid = True
                return None

            # Convert to int for consistent return type
            int_value = int(value)
            self._modbus_item.state = int_value
            self._modbus_item.is_invalid = False
            return int_value  # noqa: TRY300

        except ModbusException as exc:
            _LOGGER.warning(
                "Error reading %s at address %d: %s",
                self._modbus_item.name,
                self._modbus_item.address,
                exc,
            )
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
                        "Attempted to write to read-only register %s",
                        self._modbus_item.name,
                    )
                    return False
                case _:
                    return await self._modbus_api.write_holding_register(
                        value=value,
                        slave=self._modbus_item.battery_slave_id,
                        modbus_item=self._modbus_item,
                    )
        except ModbusException as exc:
            _LOGGER.warning(
                "Error writing %s to %s: %s",
                value,
                self._modbus_item.name,
                exc,
            )
            return False

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
        self, value: float, slave: int = 1, modbus_item: ModbusItem | None = None
    ) -> bool:
        """Write a single holding register."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                _LOGGER.error("Cannot write - not connected to modbus")
                return False

        if modbus_item is None:
            _LOGGER.error("No modbus item provided for write operation")
            return False

        try:
            # Apply factor to convert physical value to register value
            register_value = (
                value / modbus_item.factor if modbus_item.factor != 0 else value
            )

            # Convert to registers using pymodbus helper
            reg_values = self._modbus_client.convert_to_registers(
                register_value, modbus_item.data_type
            )

            def _write() -> bool:
                result = self._modbus_client.write_register(
                    address=modbus_item.address,
                    value=reg_values[0] if reg_values else int(register_value),
                    device_id=slave,
                )
                return not result.isError() if result else False

            return await asyncio.get_event_loop().run_in_executor(None, _write)

        except (ModbusException, ValueError, ZeroDivisionError) as exc:
            _LOGGER.warning(
                "Failed to write holding register %d: %s",
                modbus_item.address if modbus_item else 0,
                exc,
            )
            return False

    async def read_holding_registers(
        self,
        count: int = 1,
        slave: int = 1,
        modbus_item: ModbusItem | None = None,
    ) -> int | float | None:
        """Read and validate a single holding register value."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                _LOGGER.error("Cannot read - not connected to modbus")
                return None

        if modbus_item is None:
            _LOGGER.error("No modbus item provided")
            return None

        try:

            def _read() -> float | None:
                result = self._modbus_client.read_holding_registers(
                    address=modbus_item.address, count=count, device_id=slave
                )
                if result.isError():
                    return None

                if not result.registers:
                    return None

                # Convert from registers using pymodbus helper
                raw_value = self._modbus_client.convert_from_registers(
                    result.registers, modbus_item.data_type
                )

                # Handle different return types from convert_from_registers
                try:
                    if isinstance(raw_value, (list, tuple)):
                        # For lists, use the first element
                        numeric_value = float(raw_value[0]) if raw_value else 0.0
                    elif isinstance(raw_value, (int, float, str)):
                        numeric_value = float(raw_value)

                    # Apply factor and offset from ModbusItem
                    return numeric_value * modbus_item.factor + modbus_item.offset

                except (ValueError, TypeError, IndexError) as exc:
                    _LOGGER.warning(
                        "Failed to convert raw value %s to float: %s", raw_value, exc
                    )
                    return None

            return await asyncio.get_event_loop().run_in_executor(None, _read)

        except (ModbusException, ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Failed to read holding registers at %d: %s",
                modbus_item.address if modbus_item else 0,
                exc,
            )
            return None
