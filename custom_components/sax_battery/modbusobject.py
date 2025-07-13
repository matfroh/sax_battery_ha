"""Modbusobject.

A Modbus object that contains a Modbus item and communicates with the Modbus.
It contains a ModbusClient for setting and getting Modbus register values
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymodbus import ExceptionResponse, ModbusException
from pymodbus.client import AsyncModbusTcpClient

from homeassistant.components.sensor import SensorDeviceClass

from .const import TypeConstants
from .items import ModbusItem
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)


class ModbusAPI:
    """ModbusAPI class provides a connection to the modbus, which is used by the ModbusItems."""

    def __init__(self, config_entry: SAXBatteryData, battery_id: str) -> None:
        """Construct ModbusAPI.

        Args:
            config_entry: HASS config entry
            battery_id: Battery identifier (e.g., "battery_a", "battery_b", "battery_c")

        """
        # self._ip: str = config_entry.data[CONF.HOST]
        # self._port: int = config_entry.data[CONF.PORT]
        self._connected: bool = False
        self._connect_pending: bool = False
        self._failed_reconnect_counter: int = 0
        self.entry = config_entry.entry
        self.battery_id = battery_id

        _host_data = self.entry.data.get(f"{battery_id}_host")
        _port_data = self.entry.data.get(f"{battery_id}_port")
        _host = str(_host_data) if _host_data is not None else ""
        _port = int(_port_data) if _port_data is not None else 502

        self._modbus_client: AsyncModbusTcpClient = AsyncModbusTcpClient(
            host=_host, port=_port, name=f"SAX_BATTERY_{battery_id.upper()}", retries=1
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
                    "Connection to battery failed %s times. Waiting 15 minutes",
                    str(self._failed_reconnect_counter),
                )
                await asyncio.sleep(300)
            await self._modbus_client.connect()
            if self._modbus_client.connected:
                # _LOGGER.warning("Connection to battery succeeded")
                self._failed_reconnect_counter = 0
                self._connect_pending = False
                return self._modbus_client.connected
            self._failed_reconnect_counter += 1
            self._connect_pending = False
            self._modbus_client.close()
            return self._modbus_client.connected  # noqa: TRY300

        except ModbusException:
            _LOGGER.warning("Connection to battery failed")
            self._failed_reconnect_counter += 1
            self._connect_pending = False
            self._modbus_client.close()
            return self._modbus_client.connected

    def close(self) -> bool:
        """Close modbus connection."""
        try:
            self._modbus_client.close()
        except ModbusException:
            _LOGGER.warning("Closing connection to battery failed")
            return False
        _LOGGER.info("Connection to battery closed")
        return True

    def get_device(self) -> AsyncModbusTcpClient:
        """Return modbus connection."""
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
            return result.registers
        except ModbusException as exc:
            _LOGGER.warning("Failed to read holding registers at %d: %s", address, exc)
            return None


class ModbusObject(ModbusAPI):
    """ModbusObject.

    A Modbus object that contains a Modbus item and communicates with the Modbus.
    It contains a ModbusClient for setting and getting Modbus register values
    """

    def __init__(
        self,
        modbus_api: ModbusAPI,
        modbus_item: ModbusItem,
        no_connect_warn: bool = False,
    ) -> None:
        """Construct ModbusObject.

        Args:
            modbus_api: The modbus API
            modbus_item: definition of modbus item
            no_connect_warn: suppress connection warnings

        """
        self._modbus_item: ModbusItem = modbus_item
        self._modbus_client: AsyncModbusTcpClient = modbus_api.get_device()
        self._no_connect_warn: bool = no_connect_warn

    def check_valid_result(self, val: int) -> int | None:
        """Check if item is available and valid."""
        # Check if entitydescription exists and has device_class

        if not self._modbus_item.entitydescription:
            self._modbus_item.is_invalid = False
            return val

        device_class = self._modbus_item.entitydescription.device_class

        if not device_class:
            self._modbus_item.is_invalid = False
            return val

        match device_class:
            case SensorDeviceClass.TEMPERATURE:
                return self.check_temperature(val)
            case SensorDeviceClass.BATTERY:
                return self.check_percentage(val)
            case (
                SensorDeviceClass.POWER
                | SensorDeviceClass.ENERGY
                | SensorDeviceClass.VOLTAGE
                | SensorDeviceClass.CURRENT
            ):
                return self.check_status(val)
            case _:
                self._modbus_item.is_invalid = False
                return val

    def check_temperature(self, val: int) -> int | None:
        """Check availability of temperature item and translate return value to valid int.

        Args:
            val: The value from the modbus

        Returns:
            Processed temperature value or None if invalid

        """
        match val:
            case -32768:
                # No Sensor installed, remove it from the list
                self._modbus_item.is_invalid = True
                return None
            case 32768:
                # This seems to be zero, should be allowed
                self._modbus_item.is_invalid = True
                return None
            case -32767:
                # Sensor broken set return value to -99.9 to inform user
                self._modbus_item.is_invalid = False
                return -999
            case _:
                # Temperature Sensor seems to be Einerkomplement
                if val > 32768:
                    val = val - 65536
                self._modbus_item.is_invalid = False
                return val

    def check_percentage(self, val: int) -> int | None:
        """Check availability of percentage item and translate.

        return value to valid int
        :param val: The value from the modbus
        :type val: int
        """
        if val == 65535:
            self._modbus_item.is_invalid = True
            return None
        self._modbus_item.is_invalid = False
        return val

    def check_status(self, val: int) -> int:
        """Check general availability of item."""
        self._modbus_item.is_invalid = False
        return val

    def check_valid_response(self, val: int) -> int:
        """Check if item is valid to write."""
        match self._modbus_item.mformat:
            case SensorDeviceClass.TEMPERATURE:
                if val < 0:  # type: ignore[unreachable]
                    val = val + 65536
                return val
            case _:
                return val

    def validate_modbus_answer(self, mbr: Any) -> int | None:
        """Check if there's a valid answer from modbus and translate it to a valid int depending from type.

        :param mbr: The modbus response
        :type mbr: modbus response
        """
        val = None
        if mbr.isError():
            myexception_code: ExceptionResponse = mbr
            if myexception_code.exception_code == 2:
                self._modbus_item.is_invalid = True
            else:
                _LOGGER.warning(
                    "Received Modbus library error: %s in item: %s",
                    str(mbr),
                    str(self._modbus_item.name),
                )
            return None
        if isinstance(mbr, ExceptionResponse):
            _LOGGER.warning(
                "Received ModbusException: %s from library in item: %s",
                str(mbr),
                str(self._modbus_item.name),
            )
            # THIS IS NOT A PYTHON EXCEPTION, but a valid modbus message
            return None
        if len(mbr.registers) > 0:
            val = self.check_valid_result(mbr.registers[0])
        return val

    async def async_read_value(self, slave_id: int) -> int | None:
        """Read the value from the modbus register."""
        # if slave_id is None:
        #     _LOGGER.error(
        #         "slave_id cannot be None for reading %s", self._modbus_item.name
        #     )
        #     return None

        if not self._modbus_client.connected:
            if not self._no_connect_warn:
                _LOGGER.warning(
                    "Try to read value for %s without connection",
                    self._modbus_item.translation_key,
                )
            return None

        if self._modbus_item.is_invalid:
            return None

        try:
            match self._modbus_item.type:
                case TypeConstants.SENSOR | TypeConstants.SENSOR_CALC:
                    mbr = await self._modbus_client.read_input_registers(
                        self._modbus_item.address, slave=slave_id
                    )
                    return self.validate_modbus_answer(mbr)
                case (
                    TypeConstants.SELECT
                    | TypeConstants.NUMBER
                    | TypeConstants.NUMBER_RO
                ):
                    mbr = await self._modbus_client.read_holding_registers(
                        self._modbus_item.address, slave=slave_id
                    )
                    return self.validate_modbus_answer(mbr)
                case _:
                    _LOGGER.warning(
                        "Unsupported modbus item type %s for %s",
                        self._modbus_item.type,
                        self._modbus_item.name,
                    )
                    return None
        except ModbusException as exc:
            _LOGGER.warning(
                "ModbusException: Reading %s in item: %s failed",
                exc,
                self._modbus_item.name,
            )
            return None

    async def async_write_value(self, slave_id: int, value: int) -> bool:
        """Write the value to the modbus register.

        Args:
            slave_id: The Modbus slave ID
            value: The value to write to the modbus register

        Returns:
            True if write was successful, False otherwise
        """
        # if slave_id is None:
        #     _LOGGER.error(
        #         "slave_id cannot be None for writing to %s", self._modbus_item.name
        #     )
        #     return False

        if not self._modbus_client.connected:
            _LOGGER.warning(
                "Cannot write to %s - no connection", self._modbus_item.name
            )
            return False

        try:
            match self._modbus_item.type:
                case (
                    TypeConstants.SENSOR
                    | TypeConstants.NUMBER_RO
                    | TypeConstants.SENSOR_CALC
                ):
                    # Sensor entities are read-only
                    _LOGGER.warning(
                        "Attempted to write to read-only register %s",
                        self._modbus_item.name,
                    )
                    return False
                case _:
                    await self._modbus_client.write_register(
                        self._modbus_item.address,
                        self.check_valid_response(value),
                        slave=slave_id,
                    )
                    return True
        except ModbusException as exc:
            _LOGGER.warning(
                "ModbusException: Writing %s to %s (%s) failed: %s",
                str(value),
                str(self._modbus_item.name),
                str(self._modbus_item.address),
                exc,
            )
            return False

    async def async_write_switch_value(self, value: bool) -> bool:
        """Write switch value with proper conversion for this ModbusItem."""
        if not self._modbus_client.connected:
            _LOGGER.warning(
                "Cannot write switch value to %s - no connection",
                self._modbus_item.name,
            )
            return False

        # Convert boolean to appropriate Modbus value
        modbus_value = self._convert_switch_value(value)

        # Get slave ID from modbus item
        slave_id = getattr(self._modbus_item, "battery_slave_id", None)
        if slave_id is None:
            _LOGGER.error(
                "battery_slave_id not set for switch %s - cannot write value",
                self._modbus_item.name,
            )
            return False

        try:
            await self._modbus_client.write_register(
                address=self._modbus_item.address, value=modbus_value, slave=slave_id
            )
            _LOGGER.debug(
                "Successfully wrote switch value %s (modbus: %d) to %s",
                value,
                modbus_value,
                self._modbus_item.name,
            )
            return True
        except ModbusException as exc:
            _LOGGER.warning(
                "ModbusException: Writing switch value %s to %s (%s) failed: %s",
                str(value),
                str(self._modbus_item.name),
                str(self._modbus_item.address),
                exc,
            )
            return False

    async def async_write_number_value(self, value: float) -> bool:
        """Write numeric value with proper conversion for this ModbusItem.

        Args:
            value: The float value to write

        Returns:
            True if write was successful, False otherwise
        """
        if not self._modbus_client.connected:
            _LOGGER.warning(
                "Cannot write number value to %s - no connection",
                self._modbus_item.name,
            )
            return False

        # Get slave ID from modbus item
        slave_id = getattr(self._modbus_item, "battery_slave_id", None)
        if slave_id is None:
            _LOGGER.error(
                "battery_slave_id not set for number %s - cannot write value",
                self._modbus_item.name,
            )
            return False

        # Convert float to integer for Modbus
        try:
            # Apply scaling/conversion based on item properties
            divider = getattr(self._modbus_item, "divider", 1)
            modbus_value = int(value * divider) if divider != 1 else int(value)

            # Validate range if specified
            min_value = getattr(self._modbus_item, "min_value", None)
            max_value = getattr(self._modbus_item, "max_value", None)

            if min_value is not None and modbus_value < min_value:
                _LOGGER.warning(
                    "Value %d below minimum %d for %s",
                    modbus_value,
                    min_value,
                    self._modbus_item.name,
                )
                return False

            if max_value is not None and modbus_value > max_value:
                _LOGGER.warning(
                    "Value %d above maximum %d for %s",
                    modbus_value,
                    max_value,
                    self._modbus_item.name,
                )
                return False

            await self._modbus_client.write_register(
                address=self._modbus_item.address,
                value=self.check_valid_response(modbus_value),
                slave=slave_id,
            )
            _LOGGER.debug(
                "Successfully wrote number value %s (modbus: %d) to %s",
                value,
                modbus_value,
                self._modbus_item.name,
            )
            return True

        except (ValueError, TypeError) as exc:
            _LOGGER.error(
                "Invalid value conversion for %s: %s -> %s",
                self._modbus_item.name,
                value,
                exc,
            )
            return False
        except ModbusException as exc:
            _LOGGER.warning(
                "ModbusException: Writing number value %s to %s (%s) failed: %s",
                str(value),
                str(self._modbus_item.name),
                str(self._modbus_item.address),
                exc,
            )
            return False

    def _convert_switch_value(self, value: bool) -> int:
        """Convert boolean switch value to appropriate Modbus register value."""
        if value:
            # Check for pilot switches first
            if self._is_pilot_switch():
                return 1  # Pilot switches use 1 for "on"

            # Use on_value from ModbusItem if defined
            on_value = getattr(self._modbus_item, "on_value", None)
            if on_value is not None:
                return int(on_value)

            # Check resultlist for "on" state mapping
            resultlist = getattr(self._modbus_item, "resultlist", None)
            if resultlist:
                for status_item in resultlist:
                    if status_item.text.lower() in ["connected", "on", "enabled"]:
                        return int(status_item.number)

            return 1  # Default "on" value
        else:
            # Check for pilot switches first
            if self._is_pilot_switch():
                return 0  # Pilot switches use 0 for "off"

            # Use off_value from ModbusItem if defined
            off_value = getattr(self._modbus_item, "off_value", None)
            if off_value is not None:
                return int(off_value)

            # Check resultlist for "off" state mapping
            resultlist = getattr(self._modbus_item, "resultlist", None)
            if resultlist:
                for status_item in resultlist:
                    if status_item.text.lower() in ["off", "disconnected", "disabled"]:
                        return int(status_item.number)

            return 0  # Default "off" value

    def _is_pilot_switch(self) -> bool:
        """Check if this is a pilot switch."""
        from .const import SOLAR_CHARGING_SWITCH, MANUAL_CONTROL_SWITCH

        return self._modbus_item.name in [SOLAR_CHARGING_SWITCH, MANUAL_CONTROL_SWITCH]

    def get_switch_state(self) -> bool | None:
        """Get current switch state from coordinator data."""
        # This will be called by the switch entity to get current state
        # The actual value comes from the coordinator's data
        pass  # Implementation depends on how coordinator stores data

    def get_on_value(self) -> int:
        """Get the Modbus value that represents "on" state."""
        return self._convert_switch_value(True)

    def get_off_value(self) -> int:
        """Get the Modbus value that represents "off" state."""
        return self._convert_switch_value(False)
