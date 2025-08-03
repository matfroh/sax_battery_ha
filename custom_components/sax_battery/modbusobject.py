"""Modbus communication classes."""

from __future__ import annotations

import asyncio
import logging

from pymodbus import ModbusException
from pymodbus.client import AsyncModbusTcpClient

from homeassistant.components.sensor import SensorDeviceClass

from .const import MANUAL_CONTROL_SWITCH, SOLAR_CHARGING_SWITCH
from .enums import TypeConstants
from .items import ApiItem

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

        self._modbus_client = AsyncModbusTcpClient(
            host=host, port=port, name=f"SAX_BATTERY_{battery_id.upper()}", retries=1
        )

    async def connect(self, startup: bool = False) -> bool:
        """Open modbus connection."""
        if self._connect_pending:
            _LOGGER.warning("Connection to battery already pending")
            return self._modbus_client.connected

        try:
            self._connect_pending = True
            if self._failed_reconnect_counter >= 3 and not startup:
                _LOGGER.warning(
                    "Connection to battery failed %d times. Waiting 5 minutes",
                    self._failed_reconnect_counter,
                )
                await asyncio.sleep(300)

            await self._modbus_client.connect()
            if self._modbus_client.connected:
                self._failed_reconnect_counter = 0
                self._connect_pending = False
                return True

            self._failed_reconnect_counter += 1
            self._connect_pending = False
            self._modbus_client.close()
            return False  # noqa: TRY300

        except ModbusException:
            _LOGGER.warning("Connection to battery failed")
            self._failed_reconnect_counter += 1
            self._connect_pending = False
            self._modbus_client.close()
            return False

    def close(self) -> bool:
        """Close modbus connection."""
        try:
            self._modbus_client.close()
            return True  # noqa: TRY300
        except ModbusException:
            _LOGGER.warning("Closing connection to battery failed")
            return False

    def get_device(self) -> AsyncModbusTcpClient:
        """Return modbus client."""
        return self._modbus_client

    async def write_holding_register(
        self, address: int, value: int, slave: int = 1
    ) -> bool:
        """Write a single holding register."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                return False

        try:
            result = await self._modbus_client.write_register(
                address=address, value=value, slave=slave
            )
            return not result.isError() if result else False
        except ModbusException as exc:
            _LOGGER.warning("Failed to write holding register %d: %s", address, exc)
            return False

    async def read_holding_registers(
        self, address: int, count: int = 1, slave: int = 1
    ) -> list[int] | None:
        """Read multiple holding registers."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                return None

        try:
            result = await self._modbus_client.read_holding_registers(
                address=address, count=count, slave=slave
            )
            if result.isError():
                _LOGGER.warning(
                    "Error reading holding registers at %d: %s", address, result
                )
                return None
            return result.registers  # noqa: TRY300
        except ModbusException as exc:
            _LOGGER.warning("Failed to read holding registers at %d: %s", address, exc)
            return None

    async def read_input_registers(
        self, address: int, count: int = 1, slave: int = 1
    ) -> list[int] | None:
        """Read multiple input registers."""
        if not self._modbus_client.connected:
            await self.connect()
            if not self._modbus_client.connected:
                return None

        try:
            result = await self._modbus_client.read_input_registers(
                address=address, count=count, slave=slave
            )
            if result.isError():
                _LOGGER.warning(
                    "Error reading input registers at %d: %s", address, result
                )
                return None
            return result.registers  # noqa: TRY300
        except ModbusException as exc:
            _LOGGER.warning("Failed to read input registers at %d: %s", address, exc)
            return None


class ModbusItemValidator:
    """Validates modbus values based on device class and format."""

    @staticmethod
    def validate_value(item: ApiItem, raw_value: int) -> int | None:
        """Validate and process raw modbus value."""
        if not item.entitydescription:
            return raw_value

        device_class = item.entitydescription.device_class
        if not device_class:
            return raw_value

        match device_class:
            case SensorDeviceClass.TEMPERATURE:
                return ModbusItemValidator._validate_temperature(raw_value)
            case SensorDeviceClass.BATTERY:
                return ModbusItemValidator._validate_percentage(raw_value)
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
                # No sensor or invalid reading
                return None
            case -32767:
                # Sensor broken
                return -999
            case _:
                # Handle signed values
                if val > 32768:
                    val = val - 65536
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
        modbus_item: ApiItem,
    ) -> None:
        """Initialize ModbusObject.

        Args:
            modbus_api: The modbus API instance
            modbus_item: The modbus item definition

        """
        self._modbus_api = modbus_api
        self._modbus_item = modbus_item
        self._validator = ModbusItemValidator()

    async def async_read_value(self) -> int | None:
        """Read value from modbus register."""
        if self._modbus_item.is_invalid:
            return None

        try:
            match self._modbus_item.mtype:
                case TypeConstants.SENSOR | TypeConstants.SENSOR_CALC:
                    raw_values = await self._modbus_api.read_input_registers(
                        self._modbus_item.address,
                        slave=self._modbus_item.battery_slave_id,
                    )
                case (
                    TypeConstants.SELECT
                    | TypeConstants.NUMBER
                    | TypeConstants.NUMBER_RO
                ):
                    raw_values = await self._modbus_api.read_holding_registers(
                        self._modbus_item.address,
                        slave=self._modbus_item.battery_slave_id,
                    )
                case _:
                    _LOGGER.warning(
                        "Unsupported modbus item type %s for %s",
                        self._modbus_item.mtype,
                        self._modbus_item.name,
                    )
                    return None

            if not raw_values:
                return None

            validated_value = self._validator.validate_value(
                self._modbus_item, raw_values[0]
            )

            # Update item state
            if validated_value is None:
                self._modbus_item.is_invalid = True
            else:
                self._modbus_item.is_invalid = False

            return validated_value  # noqa: TRY300

        except ModbusException as exc:
            _LOGGER.warning(
                "ModbusException: Reading %s failed: %s",
                self._modbus_item.name,
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
                    success = await self._modbus_api.write_holding_register(
                        self._modbus_item.address,
                        self._prepare_write_value(value),
                        slave=self._modbus_item.battery_slave_id,
                    )
                    return success  # noqa: RET504
        except ModbusException as exc:
            _LOGGER.warning(
                "ModbusException: Writing %d to %s failed: %s",
                value,
                self._modbus_item.name,
                exc,
            )
            return False

    def _prepare_write_value(self, value: int) -> int:
        """Prepare value for writing to modbus."""
        # Handle signed values for temperature
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
                if status_item.text.lower() in ["connected", "on", "enabled"]:
                    return status_item.number
        return 1

    def get_switch_off_value(self) -> int:
        """Get the modbus value for switch OFF state."""
        if self._is_pilot_switch():
            return 0

        if self._modbus_item.resultlist:
            for status_item in self._modbus_item.resultlist:
                if status_item.text.lower() in ["off", "disconnected", "disabled"]:
                    return status_item.number
        return 0

    def _is_pilot_switch(self) -> bool:
        """Check if this is a pilot switch."""
        return self._modbus_item.name in [SOLAR_CHARGING_SWITCH, MANUAL_CONTROL_SWITCH]

    @property
    def item(self) -> ApiItem:
        """Get the modbus item."""
        return self._modbus_item
