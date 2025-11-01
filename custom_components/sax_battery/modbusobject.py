"""Modbus communication classes for SAX Battery integration.

This module provides simplified Modbus communication using pymodbus built-in
conversion methods with proper connection lifecycle management for pymodbus 3.11.2.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
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

    Pymodbus 3.11.2 Connection Management:
        - Proper connection lifecycle with context managers
        - Transaction-level locking to prevent stacking
        - Explicit connection cleanup after operations
        - Progressive backoff on failures
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

        # Connection health tracking
        self.consecutive_failures = 0
        self.last_successful_connection: float | None = None

        # CRITICAL: Single lock for ALL modbus operations
        self._operation_lock = asyncio.Lock()

        # Connection state tracking
        self._connection_validated = False

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

        # Create client with validated parameters and shorter timeout
        self._modbus_client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=3.0,  # Shorter timeout to detect issues faster
            retries=0,  # We handle retries ourselves
            reconnect_delay=0,  # No automatic reconnection
        )

        self._connection_validated = False

    @property
    def host(self) -> str | None:
        """Get the Modbus server hostname or IP address."""
        return self._host

    @property
    def port(self) -> int:
        """Get the Modbus server port number."""
        return self._port

    @asynccontextmanager
    async def _managed_connection(self):  # type:ignore[no-untyped-def]
        """Context manager for safe connection lifecycle.

        Ensures connection is established before operations and properly
        cleaned up afterwards to prevent transaction stacking.
        """
        connection_acquired = False
        try:
            # Ensure we have a connection
            if not self.is_connected():
                if not await self._connect_internal():
                    raise ConnectionException("Failed to establish connection")  # type: ignore[no-untyped-call]

            connection_acquired = True
            yield self._modbus_client

        finally:
            if connection_acquired:
                # CRITICAL: Longer pause to ensure transaction completes
                # This prevents the "extra data:" warnings
                await asyncio.sleep(0.1)  # Increased from 0.05

    async def connect(self) -> bool:
        """Connect to modbus device with automatic retry on failure.

        Returns:
            bool: True if connection successful, False otherwise
        """
        async with self._operation_lock:
            return await self._connect_internal()

    async def _connect_internal(self) -> bool:
        """Internal connection method with proper error handling."""
        if not self._host:
            _LOGGER.error("No host configured for %s", self.battery_id)
            return False

        try:
            # Close any existing connection first
            if self._modbus_client and self._modbus_client.connected:
                try:
                    await self._modbus_client.close()  # type:ignore[func-returns-value]
                    await asyncio.sleep(0.2)  # Increased wait time for full cleanup
                except Exception as e:  # noqa: BLE001
                    _LOGGER.debug("Error closing existing connection: %s", e)

            # Ensure old client is fully released
            self._modbus_client = None
            await asyncio.sleep(0.1)  # Brief pause before creating new client

            # Create fresh client instance for clean connection
            self._modbus_client = AsyncModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=3.0,
                retries=0,
                reconnect_delay=0,
            )

            connect_result = await self._modbus_client.connect()
            if connect_result:
                # Wait for connection to stabilize
                await asyncio.sleep(0.1)

                self.consecutive_failures = 0
                self._connection_validated = True
                _LOGGER.debug(
                    "Connected to %s at %s:%s", self.battery_id, self._host, self._port
                )
                return True
            else:  # noqa: RET505
                self.consecutive_failures += 1
                self._connection_validated = False
                _LOGGER.warning(
                    "Failed to connect to %s at %s:%s",
                    self.battery_id,
                    self._host,
                    self._port,
                )
                return False

        except (OSError, ConnectionException, ModbusException) as err:
            self.consecutive_failures += 1
            self._connection_validated = False
            _LOGGER.error("Connection error for %s: %s", self.battery_id, err)
            return False

    def is_connected(self) -> bool:
        """Check if modbus client is connected and validated."""
        return (
            self._modbus_client is not None
            and hasattr(self._modbus_client, "connected")
            and self._modbus_client.connected
            and self._connection_validated
        )

    async def close(self) -> bool:
        """Close the modbus connection safely."""
        async with self._operation_lock:
            try:
                if self._modbus_client is not None:
                    await self._modbus_client.close()  # type: ignore[func-returns-value]
                    await asyncio.sleep(0.1)  # Ensure cleanup
                self._connection_validated = False
                return True  # noqa: TRY300
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error(
                    "Error closing connection for %s: %s", self.battery_id, exc
                )
                return False

    async def read_holding_registers(
        self, count: int, modbus_item: ModbusItem, max_retries: int = 2
    ) -> int | float | None:
        """Read holding registers using pymodbus built-in conversion.

        Args:
            count: Number of registers to read
            modbus_item: ModbusItem containing read parameters
            max_retries: Maximum retry attempts (reduced from 3)

        Returns:
            Converted register value or None if failed
        """
        # Security: Input validation
        if not isinstance(count, int) or count <= 0:
            _LOGGER.error("Invalid count parameter: %s", count)
            return None
        if count > 125:
            _LOGGER.error("Count too large: %s (max 125)", count)
            return None

        # CRITICAL: Use operation lock for all modbus operations
        async with self._operation_lock:
            for attempt in range(max_retries + 1):
                try:
                    async with self._managed_connection() as client:
                        result = await client.read_holding_registers(  # pyright: ignore [reportOptionalMemberAccess]
                            address=modbus_item.address,
                            count=count,
                            device_id=modbus_item.battery_device_id,
                        )

                        if result.isError():
                            if attempt < max_retries:
                                await asyncio.sleep(0.2 * (attempt + 1))
                                # Force reconnection on error
                                self._connection_validated = False
                                continue
                            return None

                        if not result.registers:
                            _LOGGER.warning(
                                "Empty registers response for %s", self.battery_id
                            )
                            return None

                        # Use pymodbus built-in conversion
                        converted_result = client.convert_from_registers(  # pyright: ignore [reportOptionalMemberAccess]
                            result.registers, modbus_item.data_type
                        )

                        if isinstance(converted_result, (int, float)):
                            # Apply transformations
                            if (
                                hasattr(modbus_item, "factor")
                                and modbus_item.factor != 1.0
                            ):
                                converted_result *= modbus_item.factor
                            if (
                                hasattr(modbus_item, "offset")
                                and modbus_item.offset != 0
                            ):
                                converted_result -= modbus_item.offset

                            self.consecutive_failures = 0
                            return converted_result  # type:ignore[no-any-return]
                        return None

                except (ConnectionException, ModbusIOException, ModbusException) as exc:
                    _LOGGER.debug(
                        "Read error for %s (attempt %d/%d): %s",
                        self.battery_id,
                        attempt + 1,
                        max_retries + 1,
                        exc,
                    )
                    if attempt < max_retries:
                        self._connection_validated = False
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    return None

                except (OSError, TimeoutError) as exc:
                    _LOGGER.debug(
                        "Network error for %s (attempt %d/%d): %s",
                        self.battery_id,
                        attempt + 1,
                        max_retries + 1,
                        exc,
                    )
                    if attempt < max_retries:
                        self._connection_validated = False
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    return None

            return None

    async def write_registers(self, value: float, modbus_item: ModbusItem) -> bool:
        """Write value using pymodbus built-in conversion.

        Args:
            value: Numeric value to write
            modbus_item: ModbusItem containing write parameters

        Returns:
            bool: True if write successful, False otherwise
        """
        # CRITICAL: Use operation lock for all modbus operations
        async with self._operation_lock:
            try:
                async with self._managed_connection() as client:
                    # Convert value to registers
                    converted_registers: list[int] = client.convert_to_registers(  # pyright: ignore [reportOptionalMemberAccess]
                        value, modbus_item.data_type
                    )

                    _LOGGER.debug(
                        "Writing to %s at address %d: value=%s, registers=%s",
                        modbus_item.name,
                        modbus_item.address,
                        value,
                        converted_registers,
                    )

                    result = await client.write_registers(  # pyright: ignore [reportOptionalMemberAccess]
                        address=modbus_item.address,
                        values=converted_registers,
                        device_id=modbus_item.battery_device_id,
                        no_response_expected=True,
                    )

                    # Handle SAX battery quirks
                    # SAX batteries often return transaction ID errors but operations succeed
                    if hasattr(result, "isError"):
                        if result.isError():
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
                                return False

                            # Check for SAX function code 255 (assumed success)
                            if (
                                hasattr(result, "function_code")
                                and result.function_code == 255
                            ):
                                _LOGGER.debug(
                                    "SAX function code 255 - assuming success"
                                )
                                self.consecutive_failures = 0
                                return True

                            # For other errors (likely transaction ID mismatch), log but assume success
                            _LOGGER.debug(
                                "SAX quirk - write error reported but likely succeeded: %s",
                                result,
                            )
                            self.consecutive_failures = 0
                            return True

                    self.consecutive_failures = 0
                    return True

            except (ConnectionException, ModbusIOException, ModbusException) as exc:
                _LOGGER.error("Write error for %s: %s", self.battery_id, exc)
                return False
            except (OSError, TimeoutError) as exc:
                _LOGGER.error("Network error writing to %s: %s", self.battery_id, exc)
                return False
            except (ValueError, TypeError) as exc:
                _LOGGER.error("Value conversion error: %s", exc)
                return False

    async def write_nominal_power(
        self, value: float, power_factor: int, modbus_item: ModbusItem | None = None
    ) -> bool:
        """Write nominal power value with retry logic.

        Args:
            value: The nominal power value to write
            power_factor: Power factor as scaled integer
            modbus_item: Modbus item for context

        Returns:
            bool: True if write was successful
        """
        if not modbus_item:
            _LOGGER.warning("No Modbus item provided for nominal power write")
            return False

        max_retries = 2  # Reduced from 3

        # CRITICAL: Use operation lock for all modbus operations
        async with self._operation_lock:
            for retry_count in range(max_retries + 1):
                try:
                    async with self._managed_connection() as client:
                        # Validate and convert power values
                        power_int_signed = int(value)
                        power_int_signed = max(-32768, min(32767, power_int_signed))
                        power_int = power_int_signed & 0xFFFF
                        pf_int = max(0, min(65535, power_factor)) & 0xFFFF

                        # Atomic write
                        result = await client.write_registers(  # pyright: ignore [reportOptionalMemberAccess]
                            address=modbus_item.address,
                            values=[power_int, pf_int],
                            device_id=modbus_item.battery_device_id,
                            no_response_expected=True,
                        )

                        # SAX battery quirk handling
                        if hasattr(result, "isError") and result.isError():
                            error_str = str(result).lower()
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
                                if retry_count < max_retries:
                                    self._connection_validated = False
                                    await asyncio.sleep(0.5 * (retry_count + 1))
                                    continue
                                return False

                            # SAX function code 255 handling
                            if (
                                hasattr(result, "function_code")
                                and result.function_code == 255
                            ):
                                _LOGGER.debug(
                                    "SAX function_code=255 - treating as success"
                                )

                        # Success
                        self.consecutive_failures = 0
                        self.last_successful_connection = (
                            asyncio.get_event_loop().time()
                        )
                        return True

                except (
                    ConnectionException,
                    ModbusIOException,
                    OSError,
                    TimeoutError,
                ) as exc:
                    _LOGGER.warning(
                        "Network error writing nominal power (attempt %d/%d): %s",
                        retry_count + 1,
                        max_retries + 1,
                        exc,
                    )
                    if retry_count < max_retries:
                        self._connection_validated = False
                        await asyncio.sleep(0.5 * (retry_count + 1))
                        continue
                    return False

                except ModbusException as exc:
                    _LOGGER.error("Modbus exception writing nominal power: %s", exc)
                    if retry_count < max_retries:
                        self._connection_validated = False
                        await asyncio.sleep(0.5 * (retry_count + 1))
                        continue
                    return False

                except (ValueError, TypeError) as exc:
                    _LOGGER.error("Value error writing nominal power: %s", exc)
                    return False

            return False

    def should_force_reconnect(self) -> bool:
        """Check if connection should be forced to reconnect."""
        return self.consecutive_failures >= 3

    @property
    def connected(self) -> bool:
        """Property alias for is_connected for compatibility."""
        return self.is_connected()

    async def ensure_connection(self) -> bool:
        """Ensure connection is established."""
        if self.is_connected():
            return True
        return await self.connect()
