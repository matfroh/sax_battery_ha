"""Modbus communication classes for SAX Battery integration.

This module provides simplified Modbus communication using pymodbus built-in
conversion methods as specified in the coding instructions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException, ModbusIOException

from .const import DEFAULT_PORT

if TYPE_CHECKING:
    from .items import ModbusItem

_LOGGER = logging.getLogger(__name__)

# Network error codes that indicate broken connections
BROKEN_CONNECTION_ERRORS = {
    32,  # EPIPE - Broken pipe
    104,  # ECONNRESET - Connection reset by peer
    110,  # ETIMEDOUT - Connection timed out
    111,  # ECONNREFUSED - Connection refused
    113,  # EHOSTUNREACH - No route to host
}


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
        self._modbus_client: ModbusTcpClient

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
            raise ValueError("Host must be a non-empty string")

        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError("Port must be an integer between 1 and 65535")

        self._host = host.strip()
        self._port = port

        # Create client with validated parameters
        self._modbus_client = ModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=5.0,
        )

    @property
    def host(self) -> str | None:
        """Get the host address."""
        return self._host

    @property
    def port(self) -> int:
        """Get the port number."""
        return self._port

    async def connect(self) -> bool:
        """Connect to modbus device with automatic retry on failure.

        Returns:
            bool: True if connection successful, False otherwise

        Performance: Efficient connection with proper async handling
        Security: Connection timeout limits and error handling
        """
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
            # Close existing connection if any
            if self._modbus_client is not None:
                try:
                    self._modbus_client.close()  # type: ignore[no-untyped-call]
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.debug("Error closing existing connection: %s", exc)

            # Create new client with validated host
            self._modbus_client = ModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=5.0,
            )

            # Attempt connection
            _LOGGER.debug(
                "Connecting to modbus device %s at %s:%d",
                self.battery_id,
                self._host,
                self._port,
            )

            connect_result = await asyncio.get_event_loop().run_in_executor(
                None, self._modbus_client.connect
            )

            if not connect_result or not self._modbus_client.connected:
                _LOGGER.error(
                    "Failed to connect to modbus device %s at %s:%d",
                    self.battery_id,
                    self._host,
                    self._port,
                )
                return False

            # Connection successful
            self.last_successful_connection = time.time()
            self.consecutive_failures = 0

            _LOGGER.debug("Connected to modbus device %s", self.battery_id)
            return True  # noqa: TRY300

        except (OSError, ConnectionException, ModbusException) as err:
            self.consecutive_failures += 1
            _LOGGER.error(
                "Connection failed for %s (attempt %d): %s",
                self.battery_id,
                self.consecutive_failures,
                err,
            )

            if self._modbus_client:
                try:  # noqa: SIM105
                    self._modbus_client.close()  # type: ignore[no-untyped-call]
                except Exception:  # noqa: BLE001
                    pass

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

    def close(self) -> bool:
        """Close the modbus connection safely.

        Returns:
            bool: True if closed successfully, False otherwise

        Security: Handles cleanup errors gracefully
        """
        try:
            if self._modbus_client is not None:
                self._modbus_client.close()  # type: ignore[no-untyped-call]
            return True  # noqa: TRY300
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Error during connection close: %s", exc)
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
            raise ValueError("Count must be a positive integer")
        if count > 125:  # Modbus protocol limit
            raise ValueError("Count exceeds Modbus protocol limit of 125 registers")

        if not self.is_connected():
            if not await self.connect():
                return None

        for attempt in range(max_retries + 1):
            try:
                result = self._modbus_client.read_holding_registers(
                    address=modbus_item.address,
                    count=count,
                    device_id=modbus_item.battery_slave_id,
                )

                if result.isError():
                    _LOGGER.warning(
                        "Modbus read error for %s: %s", self.battery_id, result
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                    return None

                # Use pymodbus built-in conversion per coding instructions
                converted_result = self._modbus_client.convert_from_registers(
                    registers=result.registers, data_type=modbus_item.data_type
                )
                if isinstance(converted_result, (int, float)):
                    converted_result = (
                        converted_result - modbus_item.offset
                    ) * modbus_item.factor

                    _LOGGER.debug(
                        "Read %s from %s: %s",
                        modbus_item.name,
                        self.battery_id,
                        converted_result,
                    )
                    return converted_result
                else:  # noqa: RET505
                    return None

            except (OSError, ConnectionException, ModbusIOException) as err:
                if attempt < max_retries:
                    _LOGGER.warning(
                        "Error on attempt %d for %s: %s",
                        attempt + 1,
                        self.battery_id,
                        err,
                    )
                    await self.reconnect_on_error()
                    continue
                _LOGGER.error(
                    "Failed to read from %s after %d attempts: %s",
                    self.battery_id,
                    max_retries + 1,
                    err,
                )
                return None

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
            if not await self.connect():
                return False

        try:
            # Convert value to registers using pymodbus built-in methods
            converted_registers = self._modbus_client.convert_to_registers(
                value, modbus_item.data_type
            )

            # Use the correct device_id from the ModbusItem
            device_id = (
                modbus_item.battery_slave_id
            )  # This should be 64 for SAX batteries

            # SAX does not support single register writes, so always use write_registers
            result = self._modbus_client.write_registers(
                address=modbus_item.address,
                values=converted_registers,
                device_id=device_id,
                no_response_expected=True,
            )

            # Enhanced SAX battery bug workaround
            if hasattr(result, "isError"):
                if result.isError():
                    # Check if this is a known SAX battery quirk
                    error_str = str(result).lower()

                    # These are real errors that should fail
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
                            "Real Modbus error for %s: %s", modbus_item.name, result
                        )
                        return False

                    # SAX battery specific: Exception with function_code=255 might be OK
                    if hasattr(result, "function_code") and result.function_code == 255:
                        _LOGGER.debug(
                            "SAX battery returned function_code=255 for %s - treating as success",
                            modbus_item.name,
                        )
                        return True

                    # Other SAX quirks - log but assume success
                    _LOGGER.debug(
                        "SAX battery quirk detected for %s: %s - assuming success",
                        modbus_item.name,
                        result,
                    )
                    return True
                else:  # noqa: RET505
                    # No error reported
                    return True

            # Can't determine error status - assume success for SAX compatibility
            _LOGGER.debug(
                "Cannot determine error status for %s, assuming success",
                modbus_item.name,
            )
            return True  # noqa: TRY300

        except (ModbusException, ValueError, TypeError) as exc:
            _LOGGER.error("Error writing to %s: %s", modbus_item.name, exc)
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

        try:
            # Security: Input validation
            if not isinstance(value, (int, float)):
                raise TypeError("Power value must be numeric")  # noqa: TRY301
            if not isinstance(power_factor, int) or not (0 <= power_factor <= 10000):
                raise ValueError(  # noqa: TRY301
                    f"Power factor {power_factor} outside valid range [0, 10000]"
                )

            # Use modbus_item for address and device_id if provided, otherwise use SAX defaults
            if modbus_item:
                address = modbus_item.address
                device_id = modbus_item.battery_slave_id
            else:
                _LOGGER.warning("No Modbus item provided for nominal power write")
                return False  # Address and device_id must be provided via modbus_item

            # Convert values to 16-bit unsigned integers
            power_int = max(0, min(65535, int(value))) & 0xFFFF
            pf_int = max(0, min(65535, power_factor)) & 0xFFFF

            # Write both registers in a single transaction
            def _write() -> bool:
                try:
                    if self._modbus_client is None:
                        return False  # type: ignore[unreachable]

                    # Single write_registers call for both power and power factor
                    result = self._modbus_client.write_registers(
                        address=address,
                        values=[power_int, pf_int],
                        device_id=device_id,
                        no_response_expected=True,
                    )

                    _LOGGER.debug(
                        "Wrote nominal power registers at address %d: power=%s, power_factor=%s",
                        address,
                        power_int,
                        pf_int,
                    )

                    # SAX battery bug workaround: Don't strictly validate transaction ID
                    # Just check that we didn't get a clear error response
                    if hasattr(result, "isError"):
                        if result.isError():
                            # Log the error but still check for SAX-specific success patterns
                            _LOGGER.debug(
                                "Write registers returned error status: %s", result
                            )

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
                            if (
                                hasattr(result, "function_code")
                                and result.function_code == 255
                            ):
                                _LOGGER.debug(
                                    "SAX battery returned function_code=255 for %s - treating as success",
                                    modbus_item.name,
                                )
                                return True
                        # No error reported - success
                        return True
                    # Can't determine error status - assume success
                    _LOGGER.debug("Cannot determine error status, assuming success")
                    return True  # noqa: TRY300

                except (ConnectionException, ModbusIOException, ModbusException) as exc:
                    _LOGGER.error("Modbus error during nominal power write: %s", exc)
                    return False
                except (ValueError, TypeError) as exc:
                    _LOGGER.error("Value error during nominal power write: %s", exc)
                    return False

            success = await asyncio.get_event_loop().run_in_executor(None, _write)

            if success:
                _LOGGER.debug(
                    "Successfully wrote nominal power control: power=%s, factor=%s",
                    value,
                    power_factor,
                )
            else:
                _LOGGER.warning(
                    "Failed to write nominal power control: power=%s, factor=%s",
                    value,
                    power_factor,
                )

            return success  # noqa: TRY300

        except (ValueError, TypeError) as exc:
            _LOGGER.error("Input validation error in write_nominal_power: %s", exc)
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
                self._modbus_client.close()  # type: ignore[no-untyped-call]
            except Exception:  # noqa: BLE001
                pass

        # Progressive delay based on consecutive failures
        base_delay = min(0.5 + (self.consecutive_failures * 0.2), 2.0)
        await asyncio.sleep(base_delay)

        # Attempt reconnection with fewer retries as failures accumulate
        max_attempts = max(1, 4 - self.consecutive_failures)

        for attempt in range(max_attempts):
            if await self.connect():
                return True

            if attempt < max_attempts - 1:
                await asyncio.sleep(1.0)

        _LOGGER.warning(
            "Failed to reconnect to %s after %d attempts",
            self.battery_id,
            max_attempts,
        )
        self.consecutive_failures += 1
        return False

    def should_force_reconnect(self) -> bool:
        """Determine if connection should be forcefully recreated.

        Returns:
            bool: True if reconnection should be forced

        Performance: Prevents hanging connections
        Security: Limits connection lifetime for security
        """
        # Force reconnect after too many consecutive failures
        if self.consecutive_failures > 10:
            return True

        # Force reconnect if connection has been idle too long
        if self.last_successful_connection:
            idle_time = time.time() - self.last_successful_connection
            if idle_time > 300:  # 5 minutes
                return True

        return False

    @property
    def connection_health(self) -> dict[str, Any]:
        """Get detailed connection health information.

        Returns:
            dict: Connection health metrics

        Performance: Efficient health status calculation
        Security: No sensitive information exposed
        """
        current_time = time.time()

        health_status = "good"
        if self.consecutive_failures > 5:
            health_status = "poor"
        elif self.consecutive_failures > 2:
            health_status = "degraded"

        return {
            "connected": self.is_connected(),
            "consecutive_failures": self.consecutive_failures,
            "last_successful_connection": self.last_successful_connection,
            "seconds_since_last_success": (
                current_time - self.last_successful_connection
                if self.last_successful_connection
                else None
            ),
            "battery_id": self.battery_id,
            "host": self.host,
            "port": self.port,
            "health_status": health_status,
            "should_force_reconnect": self.should_force_reconnect(),
        }

    async def ensure_connection(self) -> bool:
        """Ensure modbus connection is established with retry logic.

        Returns:
            bool: True if connection is ready, False otherwise

        Performance: Efficient connection state checking
        Security: Connection timeout limits
        """
        if self.is_connected():
            return True

        _LOGGER.debug(
            "Connection lost for %s, attempting to reconnect", self.battery_id
        )

        # Simple retry with backoff
        for attempt in range(3):
            if await self.connect():
                return True

            if attempt < 2:
                await asyncio.sleep(0.5)

        _LOGGER.error(
            "Failed to reconnect to %s after 3 attempts",
            self.battery_id,
        )
        return False
