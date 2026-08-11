"""Modbus communication classes for SAX Battery integration.

This module provides simplified Modbus communication using pymodbus built-in
conversion methods as specified in the coding instructions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
import random
import time
from typing import TYPE_CHECKING

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException, ModbusIOException

from .const import DEFAULT_PORT

if TYPE_CHECKING:
    from .items import ModbusItem

_LOGGER = logging.getLogger(__name__)

# Connection management constants
MODBUS_RECONNECT_DELAY = 5.0  # Seconds between reconnection attempts
MODBUS_CONNECTION_TIMEOUT = 10.0  # Connection timeout
MAX_RECONNECTION_ATTEMPTS = 3  # Max attempts before giving up
MODBUS_TIMEOUT = 8.0  # Timeout for modbus operations in seconds
MODBUS_RETRIES = 0  # Number of retries for modbus operations


@dataclass
class OperationStatus:
    """Status of the last Modbus operation.

    Attributes:
        success: Whether operation succeeded
        error_type: Type of error if failed (modbus, network, timeout, None)
        error_message: Error description if failed
        timestamp: When operation completed
        register_address: Address accessed (for tracking)

    Security:
        OWASP A05: Minimal error exposure without sensitive data
    """

    success: bool
    error_type: str | None = None
    error_message: str | None = None
    timestamp: datetime | None = None
    register_address: int | None = None


class ModbusAPI:
    """Simplified Modbus communication handler with connection pooling.

    Connection Management:
        - Connection pooling: Single persistent connection per battery
        - Automatic reconnection with exponential backoff
        - Connection health tracking via consecutive_failures
        - Operation-level timeouts prevent hanging

    Performance:
        - Single operation lock prevents transaction stacking
        - Connection reuse eliminates setup overhead
        - Progressive backoff prevents network flooding

    Security (OWASP A05):
        - Limited retry attempts (max 3 per operation)
        - Progressive backoff prevents DoS
        - Connection validation before operations
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
        self._modbus_client: AsyncModbusTcpClient | None = None

        # Simple last-operation status (lightweight)
        self.last_operation_status = OperationStatus(success=True)

        # Connection health tracking
        self.consecutive_failures = 0
        self._last_reconnect_attempt: float = 0
        self._is_connecting: bool = False

        # Performance: Single lock for all operations
        self._operation_lock = asyncio.Lock()

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
            timeout=MODBUS_TIMEOUT,  # use decimals for milliseconds
            retries=MODBUS_RETRIES,
            reconnect_delay=MODBUS_RECONNECT_DELAY,
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
        """Establish Modbus connection with reconnection logic.

        Returns:
            True if connection successful, False otherwise

        Security:
            OWASP A05: Progressive backoff prevents DoS
        """
        # Prevent concurrent connection attempts
        if self._is_connecting:
            _LOGGER.debug("%s: Connection already in progress", self.battery_id)
            return False

        # Check if already connected
        if self.is_connected():
            return True

        # Rate limiting: Don't reconnect too frequently
        time_since_last_attempt = time.monotonic() - self._last_reconnect_attempt
        if time_since_last_attempt < MODBUS_RECONNECT_DELAY:
            remaining = MODBUS_RECONNECT_DELAY - time_since_last_attempt
            _LOGGER.debug(
                "%s: Skipping reconnect (cooldown: %.1fs remaining)",
                self.battery_id,
                remaining,
            )
            return False

        self._is_connecting = True
        self._last_reconnect_attempt = time.monotonic()

        try:
            # Type guard: Validate host is configured
            if not self._host:
                _LOGGER.error("%s: No host configured for connection", self.battery_id)
                return False

            # Close existing connection if any
            if self._modbus_client is not None:
                try:
                    self._modbus_client.close()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug(
                        "%s: Error closing old connection: %s",
                        self.battery_id,
                        err,
                    )
                finally:
                    self._modbus_client = None

            # Create new connection with timeout (host is now guaranteed to be str)
            self._modbus_client = AsyncModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=MODBUS_CONNECTION_TIMEOUT,
            )

            # Attempt connection
            connected = await asyncio.wait_for(
                self._modbus_client.connect(),
                timeout=MODBUS_CONNECTION_TIMEOUT,
            )

            if not connected:
                self._record_operation_failure(
                    "connection",
                    f"Failed to connect to {self._host}:{self._port}",
                )
                _LOGGER.warning(
                    "%s: Connection failed to %s:%s",
                    self.battery_id,
                    self._host,
                    self._port,
                )
                return False

            # Connection successful
            _LOGGER.info(
                "%s: Connected to %s:%s",
                self.battery_id,
                self._host,
                self._port,
            )
            self.consecutive_failures = 0
            return True  # noqa: TRY300

        except (TimeoutError, OSError) as err:
            self._record_operation_failure("connection", str(err))
            _LOGGER.warning(
                "%s: Connection error: %s",
                self.battery_id,
                err,
            )
            return False

        finally:
            self._is_connecting = False

    def _record_operation_success(self, register_address: int | None = None) -> None:
        """Record successful operation.

        Args:
            register_address: Address accessed (optional)
        """
        self.last_operation_status = OperationStatus(
            success=True,
            timestamp=datetime.now(),
            register_address=register_address,
        )
        # Reset failure counter on success
        self.consecutive_failures = 0

    def _record_operation_failure(
        self,
        error_type: str,
        error_message: str,
        register_address: int | None = None,
    ) -> None:
        """Record failed operation.

        Args:
            error_type: Type of error (modbus, network, timeout)
            error_message: Error description
            register_address: Address accessed (optional)
        """
        self.last_operation_status = OperationStatus(
            success=False,
            error_type=error_type,
            error_message=error_message,
            timestamp=datetime.now(),
            register_address=register_address,
        )
        self.consecutive_failures += 1

    def is_connected(self) -> bool:
        """Check if modbus client is connected.

        Returns:
            bool: True if connected, False otherwise
        """
        return self._modbus_client is not None and self._modbus_client.connected

    async def close(self) -> bool:
        """Close the modbus connection safely.

        Returns:
            bool: True if closed successfully, False otherwise

        Security:
            OWASP A05: Ensures proper resource cleanup
        """
        if self._modbus_client is None:
            return True  # Already closed

        try:
            # Check if actually connected before closing
            if (
                hasattr(self._modbus_client, "connected")
                and self._modbus_client.connected
            ):
                self._modbus_client.close()
            else:
                _LOGGER.debug(
                    "Modbus client for %s already disconnected",
                    self.battery_id,
                )
            return True  # noqa: TRY300
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "Error closing connection for %s: %s",
                self.battery_id,
                exc,
            )
            return False
        finally:
            # Always clean up the reference
            self._modbus_client = None

    async def read_register_block(
        self,
        address: int,
        count: int,
        device_id: int,
    ) -> list[int] | None:
        """Read a raw register block for startup protocol detection.

        Args:
            address: Internal Modbus register address
            count: Number of registers to read
            device_id: Modbus device/unit ID

        Returns:
            List of register values, or None on failure

        Security:
            OWASP A05: Input validation and bounded low-level probing
        """
        # Security: Validate probe request
        if address < 0 or address > 65535:
            _LOGGER.error("Invalid block read address: %s", address)
            return None

        if count <= 0 or count > 125:
            _LOGGER.error("Invalid block read count: %s", count)
            return None

        if device_id <= 0 or device_id > 255:
            _LOGGER.error("Invalid block read device_id: %s", device_id)
            return None

        if not self.is_connected() and not await self.connect():
            _LOGGER.debug(
                "Block read connect failed for %s",
                self.battery_id,
            )
            return None

        async with self._operation_lock:
            try:
                if not self._modbus_client:
                    return None

                result = await self._modbus_client.read_holding_registers(
                    address=address,
                    count=count,
                    device_id=device_id,
                )

                if result.isError() or not result.registers:
                    self._record_operation_failure(
                        "modbus",
                        f"raw block read error at {address} (device_id={device_id})",
                        register_address=address,
                    )
                    return None

                self._record_operation_success(address)
                return list(result.registers)

            except (ConnectionException, ModbusIOException) as exc:
                self._record_operation_failure(
                    "network",
                    str(exc),
                    register_address=address,
                )
                return None

            except ModbusException as exc:
                self._record_operation_failure(
                    "modbus",
                    str(exc),
                    register_address=address,
                )
                return None

            except (OSError, TimeoutError) as exc:
                error_type = "timeout" if isinstance(exc, TimeoutError) else "network"
                self._record_operation_failure(
                    error_type,
                    str(exc),
                    register_address=address,
                )
                return None

    def decode_register_block_value(
        self,
        registers: list[int],
        modbus_item: ModbusItem,
        scale_factor_value: int | None = None,
    ) -> int | float | None:
        """Decode a raw register slice using the item's datatype and scaling."""
        if not registers:
            return None

        if not self._modbus_client:
            _LOGGER.debug(
                "%s: Cannot decode registers for %s without an active modbus client",
                self.battery_id,
                modbus_item.name,
            )
            return None

        converted_result = self._modbus_client.convert_from_registers(
            registers,
            modbus_item.data_type,
        )

        if not isinstance(converted_result, (int, float)):
            return None

        if scale_factor_value is not None:
            converted_result *= 10**scale_factor_value
        elif modbus_item.factor != 1.0:
            converted_result *= modbus_item.factor

        if modbus_item.offset != 0:
            converted_result -= modbus_item.offset

        return converted_result

    async def read_holding_registers(
        self, count: int, modbus_item: ModbusItem
    ) -> int | float | None:
        """Read holding registers using pymodbus built-in conversion.

        Args:
            count: Number of registers to read
            modbus_item: ModbusItem containing read parameters

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

        # Check if we've exceeded reconnection attempts
        if self.consecutive_failures >= MAX_RECONNECTION_ATTEMPTS:
            _LOGGER.debug(
                "Skipping read for %s - max reconnection attempts exceeded",
                self.battery_id,
            )
            return None

        if not self.is_connected():
            _LOGGER.debug("Not connected to %s, attempting connection", self.battery_id)
            if not await self.connect():
                _LOGGER.warning("Failed to connect to %s", self.battery_id)
                return None

        # CRITICAL: Use operation lock to prevent concurrent writes
        async with self._operation_lock:
            try:
                if not self._modbus_client:
                    return None

                result = await self._modbus_client.read_holding_registers(
                    address=modbus_item.address,
                    count=count,
                    device_id=modbus_item.battery_device_id,
                )

                if result.isError():
                    _LOGGER.warning(
                        "Modbus read error for %s at address %d: %s",
                        self.battery_id,
                        modbus_item.address,
                        result,
                    )
                    self._record_operation_failure(
                        str(result), "modbus", modbus_item.address
                    )
                    self.consecutive_failures += 1
                    return None

                if not result.registers:
                    _LOGGER.warning("Empty registers response for %s", self.battery_id)
                    return None

                # Use pymodbus built-in conversion
                converted_result = (
                    self._modbus_client.convert_from_registers(
                        result.registers, modbus_item.data_type
                    )
                    if self._modbus_client
                    else None
                )

                if isinstance(converted_result, (int, float)):
                    # Apply factor and offset transformations
                    if hasattr(modbus_item, "factor") and modbus_item.factor != 1.0:
                        converted_result *= modbus_item.factor

                    if hasattr(modbus_item, "offset") and modbus_item.offset != 0:
                        converted_result -= modbus_item.offset

                    # Reset failure counter on successful read
                    self._record_operation_success(modbus_item.address)
                    self.consecutive_failures = 0
                    return converted_result

                return None  # noqa: TRY300

            except (ConnectionException, ModbusIOException) as exc:
                # ModbusIOException includes "No response" errors -> network
                # ConnectionException is true connection failure -> network
                self._record_operation_failure(
                    "network",
                    f"Connection error reading from {self.battery_id} at address {modbus_item.address}: {exc}",
                    register_address=modbus_item.address,
                )
                self.consecutive_failures += 1
                _LOGGER.error(
                    "Connection error reading from %s at address %s: %s",
                    self.battery_id,
                    modbus_item.address,
                    exc,
                )
                return None
            except ModbusException as exc:
                self._record_operation_failure(
                    "modbus",
                    f"Modbus error reading from {self.battery_id} at address {modbus_item.address}: {exc}",
                    register_address=modbus_item.address,
                )
                self.consecutive_failures += 1
                _LOGGER.error(
                    "Modbus error reading from %s at address %s: %s",
                    self.battery_id,
                    modbus_item.address,
                    exc,
                )

                return None
            except (OSError, TimeoutError) as exc:
                error_type = "timeout" if isinstance(exc, TimeoutError) else "network"
                self._record_operation_failure(
                    error_type,
                    f"Network error reading from {self.battery_id} at address {modbus_item.address}: {exc}",
                    register_address=modbus_item.address,
                )
                self.consecutive_failures += 1
                _LOGGER.error(
                    "Network error reading from %s at address %s: %s",
                    self.battery_id,
                    modbus_item.address,
                    exc,
                )
                return None

    async def write_registers(self, value: int, modbus_item: ModbusItem) -> bool:
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
        # Attempt reconnection if not connected
        if not self.is_connected():  # checks for None client too
            _LOGGER.warning("Not connected to %s", self.battery_id)
            if not await self._attempt_reconnection(modbus_item):
                return False

        # CRITICAL: Use operation lock to prevent concurrent writes
        async with self._operation_lock:
            try:
                if not self._modbus_client:
                    return False

                if self.should_force_reconnect():
                    _LOGGER.info("Forced reconnection requested")
                    await self._attempt_reconnection(modbus_item)

                # Convert value to registers using pymodbus built-in method
                converted_registers: list[int] = (
                    self._modbus_client.convert_to_registers(  # pyright: ignore [union-attr]
                        value, modbus_item.data_type
                    )
                )
                _LOGGER.debug(
                    "Writing to %s at address %d: value=%s, registers=%s",
                    modbus_item.name,
                    modbus_item.address,
                    value,
                    converted_registers,
                )
                # SAX does not support single register writes, so always use write_registers
                result = await self._modbus_client.write_registers(  # pyright: ignore [union-attr]
                    address=modbus_item.address,
                    values=converted_registers,
                    device_id=modbus_item.battery_device_id,
                    no_response_expected=True,
                )

                # Handle SAX battery quirks - some results don't have isError method
                if hasattr(result, "isError"):
                    if result.isError():
                        # Check for SAX-specific function code 255 (assumed success)
                        if (
                            hasattr(result, "function_code")
                            and result.function_code == 255
                        ):
                            _LOGGER.debug(
                                "SAX function code 255 - assuming success for %s",
                                self.battery_id,
                            )
                            # Reset failure counter on successful write
                            self._record_operation_success(modbus_item.address)
                            self.consecutive_failures = 0
                            return True
                        else:  # noqa: RET505
                            error_str = str(result).lower()
                            # Check for real errors (not transaction ID mismatches)
                            real_errors = [
                                "connection",
                                "timeout",
                                "refused",
                                "unreachable",
                                "illegal function",
                                "illegal data address",
                                "illegal data value",
                            ]

                            # If it's a real error, fail
                            if any(
                                real_error in error_str for real_error in real_errors
                            ):
                                _LOGGER.warning(
                                    "Real write error for %s: %s",
                                    self.battery_id,
                                    result,
                                )
                                self._record_operation_failure(
                                    str(result), "modbus", modbus_item.address
                                )
                                self.consecutive_failures += 1
                                return False
                        #  On error log details and fail (return False)
                        _LOGGER.warning(
                            "Write error for %s, %s at address %d: value=%s, registers=%s",
                            self.battery_id,
                            modbus_item.name,
                            modbus_item.address,
                            value,
                            converted_registers,
                        )
                        self._record_operation_failure(
                            str(result), "modbus", modbus_item.address
                        )
                        self.consecutive_failures += 1
                        return False

                    # Reset failure counter on successful write
                    self._record_operation_success(modbus_item.address)
                    self.consecutive_failures = 0
                    return True
                else:  # noqa: RET505
                    # No isError method - assume success (SAX workaround)
                    _LOGGER.debug(
                        "No isError method - assuming success for %s", self.battery_id
                    )
                    # Reset failure counter on assumed success
                    self._record_operation_success(modbus_item.address)
                    self.consecutive_failures = 0
                    return True

            except (ConnectionException, ModbusIOException) as exc:
                self.consecutive_failures += 1
                self._record_operation_failure(str(exc), "connect", modbus_item.address)
                _LOGGER.error(
                    "Connection error writing to %s: %s", self.battery_id, exc
                )
                return False

            except ModbusException as exc:
                self.consecutive_failures += 1
                self._record_operation_failure(str(exc), "modbus", modbus_item.address)
                _LOGGER.error(
                    "Modbus exception writing to %s: %s", self.battery_id, exc
                )
                return False

            except (OSError, TimeoutError) as exc:
                self.consecutive_failures += 1
                self._record_operation_failure(str(exc), "timeout", modbus_item.address)
                _LOGGER.error("Network error writing to %s: %s", self.battery_id, exc)
                return False

            except (ValueError, TypeError) as exc:
                _LOGGER.error("Value conversion error for %s: %s", self.battery_id, exc)
                return False

    async def write_nominal_power(
        self, value: int, power_factor: int, modbus_item: ModbusItem | None = None
    ) -> bool:
        """Write nominal power value to SAX Battery.

        Handles SAX battery quirks:
        - Transaction ID bug: Battery returns wrong transaction ID
        - Write-only registers: Cannot read back to verify
        - Atomic write: Power and power factor must be written together

        Args:
            value: The nominal power value to write (can be negative for charging)
            power_factor: Power factor as scaled integer (e.g., 9500 for 0.95)
            modbus_item: Optional modbus item for context (address and device_id)

        Returns:
            bool: True if write was successful, False otherwise

        Security:
            OWASP A05: Validates connection state and input ranges
            OWASP A03: Input validation prevents injection

        Performance:
            Single write operation without retries (pymodbus handles retries internally)
            Operation lock prevents concurrent writes
        """
        if not modbus_item:
            _LOGGER.warning("No Modbus item provided for nominal power write")
            return False

        # Validate connection state
        if not self.is_connected():
            _LOGGER.warning(
                "Not connected to %s, attempting reconnection", self.battery_id
            )
            if not await self._attempt_reconnection(modbus_item):
                return False

        # CRITICAL: Use operation lock to prevent concurrent writes
        async with self._operation_lock:
            try:
                # Validate and convert power values
                # Security (OWASP A03): Input validation
                power_int_signed = int(value)
                power_int_signed = max(-32768, min(32767, power_int_signed))
                power_int = power_int_signed & 0xFFFF  # Convert to unsigned 16-bit

                pf_int = max(0, min(65535, power_factor)) & 0xFFFF

                if not self._modbus_client:
                    _LOGGER.error("Modbus client is None after connection check")
                    return False

                _LOGGER.debug(
                    "Writing nominal_power=%dW, power_factor=%d to %s at address %d",
                    power_int_signed,
                    pf_int,
                    self.battery_id,
                    modbus_item.address,
                )

                # Atomic write of both registers
                # Performance: Single write operation, pymodbus handles retries
                result = await self._modbus_client.write_registers(
                    address=modbus_item.address,
                    values=[power_int, pf_int],
                    device_id=modbus_item.battery_device_id,
                    no_response_expected=True,  # SAX Battery quirk: wrong transaction ID
                )

                # SAX battery quirk: Wrong transaction ID in response
                # Check for real errors only (connection, timeout, illegal function)
                if hasattr(result, "isError") and result.isError():
                    error_str = str(result).lower()

                    # Real errors that require attention
                    real_errors = [
                        "connection",
                        "timeout",
                        "refused",
                        "unreachable",
                        "illegal function",
                        "illegal data address",
                        "illegal data value",
                    ]

                    if any(real_error in error_str for real_error in real_errors):
                        _LOGGER.error(
                            "Write error for %s: %s (treating as failure)",
                            self.battery_id,
                            result,
                        )
                        self._record_operation_failure(
                            str(result), "modbus", modbus_item.address
                        )
                        self.consecutive_failures += 1
                        return False

                    # Transaction ID mismatch: Expected behavior, ignore
                    _LOGGER.debug(
                        "Ignoring expected transaction ID mismatch for %s: %s",
                        self.battery_id,
                        result,
                    )

                # Success - reset failure counter
                self.consecutive_failures = 0
                _LOGGER.debug(
                    "Successfully wrote nominal_power=%dW to %s",
                    power_int_signed,
                    self.battery_id,
                )
                self._record_operation_success(modbus_item.address)
                return True  # noqa: TRY300

            except (ConnectionException, ModbusIOException) as exc:
                _LOGGER.error(
                    "Connection error writing nominal power to %s: %s",
                    self.battery_id,
                    exc,
                )
                self._record_operation_failure(str(exc), "connect", modbus_item.address)
                self.consecutive_failures += 1
                # Trigger reconnection on next operation
                await self._force_disconnect()
                return False

            except (OSError, TimeoutError) as exc:
                _LOGGER.error(
                    "Network error writing nominal power to %s: %s",
                    self.battery_id,
                    exc,
                )
                self._record_operation_failure(str(exc), "timeout", modbus_item.address)
                self.consecutive_failures += 1
                # Trigger reconnection on next operation
                await self._force_disconnect()
                return False

            except ModbusException as exc:
                _LOGGER.error(
                    "Modbus exception writing nominal power to %s: %s",
                    self.battery_id,
                    exc,
                )
                self._record_operation_failure(str(exc), "modbus", modbus_item.address)
                self.consecutive_failures += 1
                return False

            except (ValueError, TypeError) as exc:
                # Security (OWASP A03): Log validation errors
                _LOGGER.error(
                    "Value conversion error for %s: %s",
                    self.battery_id,
                    exc,
                )
                return False

    async def _attempt_reconnection(self, modbus_item: ModbusItem) -> bool:
        """Attempt to reconnect after connection failure.

        This method provides automatic reconnection with exponential backoff
        to handle SAX battery reboots and network issues gracefully.

        Returns:
            True if reconnection successful, False otherwise

        Security:
            OWASP A05: Limited retry attempts prevent resource exhaustion

        Performance:
            Exponential backoff prevents connection storms and gives device time to recover
        """
        # Prevent infinite reconnection attempts
        if self.consecutive_failures >= MAX_RECONNECTION_ATTEMPTS:
            _LOGGER.error(
                "Max reconnection attempts (%d) reached for %s, backing off until next update cycle",
                MAX_RECONNECTION_ATTEMPTS,
                self.battery_id,
            )
            return False

        # Calculate delay BEFORE incrementing counter to get correct attempt number
        # Attempt 1: consecutive_failures=0 -> 2^1=2s
        # Attempt 2: consecutive_failures=1 -> 2^2=4s
        # Attempt 3: consecutive_failures=2 -> 2^3=8s
        base_delay = 2 ** (self.consecutive_failures + 1)
        jitter = round(random.uniform(0, 0.3 * base_delay), 2)
        delay = round(min(base_delay + jitter, 15.0), 2)

        # Now increment for tracking
        self.consecutive_failures += 1

        _LOGGER.info(
            "Connection lost for %s, attempting reconnection (attempt %d/%d)",
            self.battery_id,
            self.consecutive_failures,
            MAX_RECONNECTION_ATTEMPTS,
        )

        # Force close the broken connection with proper cleanup
        await self._force_disconnect()

        _LOGGER.info(
            "Waiting %.2fs before reconnection attempt for %s (prevents connection storms)",
            delay,
            self.battery_id,
        )
        await asyncio.sleep(delay)

        # Attempt reconnection with validation
        try:
            if await self.connect():
                # Verify connection with a test read
                if await self._verify_connection(modbus_item):
                    self.consecutive_failures = 0
                    _LOGGER.info(
                        "Reconnection successful for %s after %.2fs backoff",
                        self.battery_id,
                        delay,
                    )
                    return True

                _LOGGER.warning(
                    "Reconnection established but verification failed for %s",
                    self.battery_id,
                )
                await self._force_disconnect()
                return False

            _LOGGER.warning(
                "Reconnection attempt %d/%d failed for %s",
                self.consecutive_failures,
                MAX_RECONNECTION_ATTEMPTS,
                self.battery_id,
            )
            return False  # noqa: TRY300

        except (OSError, TimeoutError, ConnectionException) as exc:
            _LOGGER.error(
                "Reconnection error for %s (attempt %d/%d): %s",
                self.battery_id,
                self.consecutive_failures,
                MAX_RECONNECTION_ATTEMPTS,
                exc,
            )
            return False

    async def _force_disconnect(self) -> None:
        """Force close connection with proper cleanup.

        Security:
            OWASP A05: Ensures resources are properly released

        Performance:
            Prevents socket leak and allows clean reconnection
        """
        if self._modbus_client:
            try:
                # Close connection gracefully
                self._modbus_client.close()

                # Wait for socket cleanup (OS needs time to release resources)
                await asyncio.sleep(0.2)

            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Error during forced disconnect for %s: %s",
                    self.battery_id,
                    exc,
                )
            finally:
                # Clear client reference to prevent use-after-close
                self._modbus_client = None
                _LOGGER.debug("Cleared modbus client reference for %s", self.battery_id)

    async def _verify_connection(self, modbus_item: ModbusItem) -> bool:
        """Verify connection with a lightweight test read.

        Args:
            modbus_item: ModbusItem to use for connection verification

        Returns:
            True if connection is valid, False otherwise

        Security:
            OWASP A05: Validates connection state before operations

        Performance:
            Single register read minimizes verification overhead
        """
        if not self._modbus_client or not self._modbus_client.connected:
            _LOGGER.debug("Connection verification failed: client not connected")
            return False

        # CRITICAL: Use operation lock to prevent concurrent writes
        async with self._operation_lock:
            try:
                # Try to read register as lightweight test
                response = await self._modbus_client.read_holding_registers(
                    address=modbus_item.address,
                    count=1,
                    device_id=modbus_item.battery_device_id,
                )

                if response.isError():
                    _LOGGER.debug(
                        "Connection verification failed for %s: %s",
                        self.battery_id,
                        response,
                    )
                    return False

                _LOGGER.debug(
                    "Connection verification successful for %s", self.battery_id
                )
                return True  # noqa: TRY300

            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Connection verification exception for %s: %s",
                    self.battery_id,
                    exc,
                )
                return False

    def get_diagnostics(self) -> dict[str, object]:
        """Return diagnostic information for troubleshooting.

        Returns:
            Dictionary with connection state and operation metrics

        Security:
            OWASP A05: Does not expose host IP (caller must redact)

        Performance:
            Lightweight attribute access, no I/O
        """
        diagnostics: dict[str, object] = {
            "connected": self.is_connected(),
            "port": self._port,
            "battery_id": self.battery_id,
            "consecutive_failures": self.consecutive_failures,
        }

        # Last operation status
        status = self.last_operation_status
        diagnostics["last_operation"] = {
            "success": status.success,
            "error_type": status.error_type,
            "error_message": status.error_message,
            "timestamp": (status.timestamp.isoformat() if status.timestamp else None),
            "register_address": status.register_address,
        }

        return diagnostics

    def should_force_reconnect(self) -> bool:
        """Check if forced reconnection is needed.

        Returns:
            True if reconnection should be forced, False otherwise

        Performance:
            Checks connection health metrics
        """
        return not self.is_connected()

    @property
    def connected(self) -> bool:
        """Property alias for is_connected for compatibility."""
        return self.is_connected()
