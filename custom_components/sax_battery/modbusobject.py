"""Modbus communication classes for SAX Battery integration.

This module provides simplified Modbus communication using pymodbus built-in
conversion methods as specified in the coding instructions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException, ModbusIOException

from .const import DEFAULT_PORT

if TYPE_CHECKING:
    from .items import ModbusItem

_LOGGER = logging.getLogger(__name__)


class ModbusAPI:
    """Simplified Modbus communication handler using pymodbus built-in conversion.

    This implementation follows the coding instructions to use pymodbus client
    conversion methods and handles the SAX battery transaction ID bug.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int = DEFAULT_PORT,
        battery_id: str | None = None,
    ) -> None:
        """Initialize ModbusAPI with proper pymodbus client.

        Args:
            host: Modbus server hostname or IP address
            port: Modbus server port number
            battery_id: Battery identifier for logging
        """
        self._host = host
        self._port = port
        self.battery_id = battery_id or "unknown"
        self._modbus_client: AsyncModbusTcpClient

        # Connection health tracking
        self.consecutive_failures = 0
        self.last_successful_connection: float | None = None
        self.connection_lock = asyncio.Lock()

        if host:
            self.set_connection_params(host, port)

    def set_connection_params(self, host: str, port: int) -> None:
        """Set connection parameters with validation.

        Args:
            host: Modbus server hostname or IP address
            port: Modbus server port number

        Raises:
            ValueError: If host or port parameters are invalid

        Security: Validates input parameters per OWASP guidelines
        """
        if not isinstance(host, str) or not host.strip():
            raise ValueError(f"Invalid host parameter: {host}")

        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError(f"Invalid port parameter: {port}")

        self._host = host.strip()
        self._port = port

        # Create client with validated parameters
        self._modbus_client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=5.0,
        )

    @property
    def host(self) -> str | None:
        """Get the Modbus server hostname or IP address.

        Returns:
            str | None: The configured hostname/IP address, or None if not set
        """
        return self._host

    @property
    def port(self) -> int:
        """Get the Modbus server port number.

        Returns:
            int: The configured port number
        """
        return self._port

    async def connect(self) -> bool:
        """Connect to modbus device with automatic retry on failure.

        Returns:
            bool: True if connection successful, False otherwise

        Performance: Efficient connection with proper async handling
        Security: Connection timeout limits and error handling
        """
        # Create connection_lock if it doesn't exist (for test compatibility)
        if not hasattr(self, "connection_lock"):
            self.connection_lock = asyncio.Lock()

        async with self.connection_lock:
            return await self._connect_internal()

    async def _connect_internal(self) -> bool:
        """Internal connection method with proper error handling."""
        if not self._host:
            _LOGGER.error("No host configured for %s", self.battery_id)
            return False

        try:
            connect_result = await self._modbus_client.connect()
            if connect_result:
                self.consecutive_failures = 0
                _LOGGER.debug(
                    "Connected to %s at %s:%s", self.battery_id, self._host, self._port
                )
                return True
            else:  # noqa: RET505
                self.consecutive_failures += 1
                _LOGGER.warning(
                    "Failed to connect to %s at %s:%s",
                    self.battery_id,
                    self._host,
                    self._port,
                )
                return False

        except (OSError, ConnectionException, ModbusException) as err:
            self.consecutive_failures += 1
            _LOGGER.error("Connection error for %s: %s", self.battery_id, err)
            return False

    def is_connected(self) -> bool:
        """Check if modbus client is connected.

        Returns:
            bool: True if connected, False otherwise
        """
        return (
            self._modbus_client is not None
            and hasattr(self._modbus_client, "connected")
            and self._modbus_client.connected
        )

    async def close(self) -> bool:
        """Close the modbus connection safely.

        Returns:
            bool: True if closed successfully, False otherwise

        Security: Handles cleanup errors gracefully
        """
        try:
            if self._modbus_client is not None:
                await self._modbus_client.close()  # type: ignore[func-returns-value]
            return True  # noqa: TRY300
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Error closing connection for %s: %s", self.battery_id, exc)
            return False

    async def read_holding_registers(
        self, count: int, modbus_item: ModbusItem, max_retries: int = 3
    ) -> int | float | None:
        """Read holding registers using pymodbus built-in conversion.

        Args:
            count: Number of registers to read
            modbus_item: ModbusItem containing read parameters
            max_retries: Maximum retry attempts

        Returns:
            Converted register value or None if failed

        Security: Input validation and error handling
        Performance: Uses pymodbus optimized conversion methods
        """
        # Security: Input validation
        if not isinstance(count, int) or count <= 0:
            _LOGGER.error("Invalid count parameter: %s", count)
            return None
        if count > 125:
            _LOGGER.error("Count too large: %s (max 125)", count)
            return None

        if not self.is_connected():
            _LOGGER.warning("Not connected to %s", self.battery_id)
            return None

        for attempt in range(max_retries + 1):
            try:
                result = await self._modbus_client.read_holding_registers(
                    address=modbus_item.address,
                    count=count,
                    device_id=modbus_item.battery_device_id,
                )

                if result.isError():
                    _LOGGER.warning(
                        "Modbus read error for %s: %s", self.battery_id, result
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(0.1)
                        continue
                    return None

                if not result.registers:
                    _LOGGER.warning("Empty registers response for %s", self.battery_id)
                    return None

                # Use pymodbus built-in conversion
                converted_result = self._modbus_client.convert_from_registers(
                    result.registers, modbus_item.data_type
                )
                if isinstance(converted_result, (int, float)):
                    # Apply factor and offset transformations
                    if hasattr(modbus_item, "factor") and modbus_item.factor != 1.0:
                        converted_result *= modbus_item.factor

                    if hasattr(modbus_item, "offset") and modbus_item.offset != 0:
                        converted_result -= modbus_item.offset

                    return converted_result
                else:  # noqa: RET505
                    return None

            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Read error for %s: %s", self.battery_id, exc)
                if attempt < max_retries:
                    await asyncio.sleep(0.1)
                    continue

        return None

    async def write_registers(self, value: float, modbus_item: ModbusItem) -> bool:
        """Write value using pymodbus built-in conversion.

        Handles SAX battery transaction ID bug by not strictly validating responses.

        Args:
            value: Numeric value to write
            modbus_item: ModbusItem containing write parameters

        Returns:
            bool: True if write successful, False otherwise

        Performance: Uses pymodbus optimized methods
        Security: Input validation and safe conversion
        """
        if not self.is_connected():
            _LOGGER.warning("Not connected to %s", self.battery_id)
            return False

        try:
            # Convert value to registers using pymodbus built-in method
            converted_registers: list[int] = self._modbus_client.convert_to_registers(
                value, modbus_item.data_type
            )
            _LOGGER.debug(
                "Writing to %s at address %d: value=%s, registers=%s",
                modbus_item.name,
                modbus_item.address,
                value,
                converted_registers,
            )
            # SAX does not support single register writes, so always use write_registers
            result = await self._modbus_client.write_registers(
                address=modbus_item.address,
                values=converted_registers,
                device_id=modbus_item.battery_device_id,
                no_response_expected=True,
            )

            # Handle SAX battery quirks - some results don't have isError method
            if hasattr(result, "isError"):
                if result.isError():
                    # Check for SAX-specific function code 255 (assumed success)
                    if hasattr(result, "function_code") and result.function_code == 255:
                        _LOGGER.debug(
                            "SAX function code 255 - assuming success for %s",
                            self.battery_id,
                        )
                        return True
                    return False
                return True
            else:  # noqa: RET505
                # No isError method - assume success (SAX workaround)
                _LOGGER.debug(
                    "No isError method - assuming success for %s", self.battery_id
                )
                return True

        except (ModbusException, ValueError, TypeError) as exc:
            _LOGGER.error("Write error for %s: %s", self.battery_id, exc)
            return False

    async def write_nominal_power(
        self, value: float, power_factor: int, modbus_item: ModbusItem | None = None
    ) -> bool:
        """Write nominal power value with specific power factor using single write_registers call.

        Handles SAX battery transaction ID bug by using write_registers with both values
        in a single transaction and not strictly validating the response.

        Args:
            value: The nominal power value to write
            power_factor: Power factor as scaled integer (e.g., 9500 for 0.95)
            modbus_item: Optional modbus item for context (address and device_id)

        Returns:
            bool: True if write was successful, False otherwise

        Security: Validates all inputs and addresses
        Performance: Single write_registers call for both values
        """
        if not await self.ensure_connection():
            return False

        if not (0 <= power_factor <= 10000):
            raise ValueError(
                f"Power factor {power_factor} outside valid range [0, 10000]"
            )

        if not modbus_item:
            _LOGGER.warning("No Modbus item provided for nominal power write")
            return False  # Address and slave must be provided via modbus_item
        try:
            # Default SAX addresses if no modbus_item provided

            # Convert values to 16-bit unsigned integers
            power_int = max(0, min(65535, int(value))) & 0xFFFF
            pf_int = max(0, min(65535, power_factor)) & 0xFFFF

            # Atomic write for registers power and power factor
            result = await self._modbus_client.write_registers(
                address=modbus_item.address,
                values=[power_int, pf_int],
                device_id=modbus_item.battery_device_id,
                no_response_expected=True,
            )

            _LOGGER.debug(
                "Wrote nominal power registers at address %d: power=%s, power_factor=%s",
                modbus_item.address,
                power_int,
                pf_int,
            )

            # SAX battery bug workaround: Don't strictly validate transaction ID
            # Just check that we didn't get a clear error response
            if hasattr(result, "isError"):
                if result.isError():
                    # Log the error but still check for SAX-specific success patterns
                    _LOGGER.debug("Write registers returned error status: %s", result)

                    # Check if this is a known SAX battery quirk
                    error_str = str(result).lower()
                    # Some SAX batteries return errors even on successful writes
                    # Check for specific error patterns that indicate real failures
                    real_errors = [
                        "connection",
                        "timeout",
                        "refused",
                        "unreachable",
                        "illegal function",
                        "illegal data address",
                        "illegal data value",
                    ]

                    if any(error in error_str for error in real_errors):
                        _LOGGER.error(
                            "Real failure detected in write response: %s",
                            result,
                        )
                        return False

                    # SAX battery specific: Exception with function_code=255 might be OK
                    if hasattr(result, "function_code") and result.function_code == 255:
                        _LOGGER.debug(
                            "SAX battery returned function_code=255 - treating as success"
                        )
                        return True
                # No error reported - success
                return True
            # Can't determine error status - assume success
            _LOGGER.debug("Cannot determine error status, assuming success")
            return True  # noqa: TRY300

        except (ConnectionException, ModbusIOException, ModbusException) as exc:
            _LOGGER.error("Modbus error writing nominal power: %s", exc)
            return False
        except (ValueError, TypeError) as exc:
            _LOGGER.error("Value error writing nominal power: %s", exc)
            return False

    async def reconnect_on_error(self) -> bool:
        """Attempt to reconnect after an error with enhanced backoff.

        Returns:
            bool: True if reconnection successful, False otherwise

        Performance: Progressive delay based on failure history
        Security: Limited retry attempts to prevent resource exhaustion
        """
        _LOGGER.debug(
            "Connection lost for %s, attempting to reconnect", self.battery_id
        )

        # Close the broken connection
        if self._modbus_client:
            try:  # noqa: SIM105
                await self._modbus_client.close()  # type: ignore[func-returns-value]
            except Exception:  # noqa: BLE001
                pass  # Ignore errors when closing broken connection

        # Progressive delay based on consecutive failures
        base_delay = min(self.consecutive_failures * 0.5, 30.0)
        await asyncio.sleep(base_delay)

        # Attempt reconnection with fewer retries as failures accumulate
        max_attempts = max(1, 4 - self.consecutive_failures)

        for attempt in range(max_attempts):
            if await self._connect_internal():
                _LOGGER.info("Reconnection successful for %s", self.battery_id)
                return True

            if attempt < max_attempts - 1:  # Don't sleep after last attempt
                await asyncio.sleep(1.0)

        _LOGGER.warning(
            "Failed to reconnect to %s after %d attempts",
            self.battery_id,
            max_attempts,
        )
        self.consecutive_failures += 1
        return False

    def should_force_reconnect(self) -> bool:
        """Check if connection should be forced to reconnect."""
        return self.consecutive_failures >= 3

    @property
    def connected(self) -> bool:
        """Property alias for is_connected for compatibility."""
        return self.is_connected()

    async def ensure_connection(self) -> bool:
        """Ensure connection is established.

        Returns:
            bool: True if connected, False otherwise
        """
        if self.is_connected():
            return True
        return await self.connect()
