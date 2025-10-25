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

        # Attempt reconnection if not connected
        if not self.is_connected():
            _LOGGER.warning("Not connected to %s", self.battery_id)
            if not await self._attempt_reconnection():
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
                        "Modbus read error for %s at address %d (attempt %d/%d): %s",
                        self.battery_id,
                        modbus_item.address,
                        attempt + 1,
                        max_retries + 1,
                        result,
                    )

                    # On error, attempt reconnection for next retry
                    if attempt < max_retries:
                        if await self._attempt_reconnection():
                            # Wait briefly before retry
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

                    # Reset failure counter on successful read
                    self.consecutive_failures = 0
                    return converted_result
                else:  # noqa: RET505
                    return None

            except (ConnectionException, ModbusIOException) as exc:
                _LOGGER.error(
                    "Connection error reading from %s at address %d (attempt %d/%d): %s",
                    self.battery_id,
                    modbus_item.address,
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )

                #  Attempt reconnection on connection errors
                if attempt < max_retries:
                    if await self._attempt_reconnection():
                        await asyncio.sleep(0.1)
                        continue

                return None

            except ModbusException as exc:
                _LOGGER.error(
                    "Modbus exception reading from %s at address %d: %s",
                    self.battery_id,
                    modbus_item.address,
                    exc,
                )

                #  Attempt reconnection on Modbus exceptions
                if attempt < max_retries:
                    if await self._attempt_reconnection():
                        await asyncio.sleep(0.1)
                        continue

                return None

            except (OSError, TimeoutError) as exc:
                _LOGGER.error(
                    "Network error reading from %s at address %d: %s",
                    self.battery_id,
                    modbus_item.address,
                    exc,
                )

                #  Attempt reconnection on network errors
                if attempt < max_retries:
                    if await self._attempt_reconnection():
                        await asyncio.sleep(0.1)
                        continue

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
        # Attempt reconnection if not connected
        if not self.is_connected():
            _LOGGER.warning("Not connected to %s", self.battery_id)
            if not await self._attempt_reconnection():
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
                        # Reset failure counter on successful write
                        self.consecutive_failures = 0
                        return True

                    #  On error, attempt reconnection and retry once
                    _LOGGER.warning(
                        "Write error for %s, attempting reconnection", self.battery_id
                    )
                    if await self._attempt_reconnection():
                        # Retry write once after reconnection
                        _LOGGER.debug("Retrying write after reconnection")
                        return await self.write_registers(value, modbus_item)

                    return False

                # Reset failure counter on successful write
                self.consecutive_failures = 0
                return True
            else:  # noqa: RET505
                # No isError method - assume success (SAX workaround)
                _LOGGER.debug(
                    "No isError method - assuming success for %s", self.battery_id
                )
                # Reset failure counter on assumed success
                self.consecutive_failures = 0
                return True

        except (ConnectionException, ModbusIOException) as exc:
            _LOGGER.error("Connection error writing to %s: %s", self.battery_id, exc)

            # Attempt reconnection and retry once
            if await self._attempt_reconnection():
                _LOGGER.debug("Retrying write after reconnection")
                return await self.write_registers(value, modbus_item)

            return False

        except ModbusException as exc:
            _LOGGER.error("Modbus exception writing to %s: %s", self.battery_id, exc)

            # Attempt reconnection and retry once
            if await self._attempt_reconnection():
                _LOGGER.debug("Retrying write after reconnection")
                return await self.write_registers(value, modbus_item)

            return False

        except (OSError, TimeoutError) as exc:
            _LOGGER.error("Network error writing to %s: %s", self.battery_id, exc)

            # Attempt reconnection and retry once
            if await self._attempt_reconnection():
                _LOGGER.debug("Retrying write after reconnection")
                return await self.write_registers(value, modbus_item)

            return False

        except (ValueError, TypeError) as exc:
            _LOGGER.error("Value conversion error for %s: %s", self.battery_id, exc)
            return False

    async def write_nominal_power(
        self, value: float, power_factor: int, modbus_item: ModbusItem | None = None
    ) -> bool:
        """Write nominal power value with retry logic using loop-based backoff.

        Handles SAX battery transaction ID bug by using write_registers with both values
        in a single transaction and not strictly validating the response.

        Args:
            value: The nominal power value to write (can be negative for charging)
            power_factor: Power factor as scaled integer (e.g., 9500 for 0.95)
            modbus_item: Optional modbus item for context (address and device_id)

        Returns:
            bool: True if write was successful, False otherwise

        Security:
            OWASP A05: Validates proper retry limits and connection state

        Performance:
            Uses exponential backoff to avoid overwhelming network/device
        """
        if not modbus_item:
            _LOGGER.warning("No Modbus item provided for nominal power write")
            return False

        max_retries = 3
        retry_count = 0

        while retry_count <= max_retries:
            # Check for forced reconnection from coordinator (preserves existing functionality)
            if self.should_force_reconnect():
                _LOGGER.info("Forced reconnection requested by coordinator")
                await self._attempt_reconnection()

            # Ensure connection (non-recursive)
            if not await self.ensure_connection():
                retry_count += 1
                if retry_count > max_retries:
                    _LOGGER.error("Max reconnection attempts reached")
                    return False

                # Exponential backoff: 2s, 4s, 8s
                delay = min(2**retry_count, 10)
                _LOGGER.warning(
                    "Connection failed, retrying in %ds (attempt %d/%d)",
                    delay,
                    retry_count,
                    max_retries,
                )
                await asyncio.sleep(delay)
                continue

            try:
                # Validate and convert power values
                power_int_signed = int(value)
                power_int_signed = max(-32768, min(32767, power_int_signed))
                power_int = power_int_signed & 0xFFFF
                pf_int = max(0, min(65535, power_factor)) & 0xFFFF

                # Atomic write
                result = await self._modbus_client.write_registers(
                    address=modbus_item.address,
                    values=[power_int, pf_int],
                    device_id=modbus_item.battery_device_id,
                    no_response_expected=True,
                )

                # SAX battery bug workaround (preserve existing logic)
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
                        _LOGGER.warning("Real Modbus error detected: %s", result)
                        retry_count += 1
                        if retry_count > max_retries:
                            return False

                        delay = min(2**retry_count, 10)
                        await asyncio.sleep(delay)
                        continue  # Loop retry instead of recursion

                    # SAX battery quirk handling
                    if hasattr(result, "function_code") and result.function_code == 255:
                        _LOGGER.debug(
                            "SAX battery function_code=255 - treating as success"
                        )

                # Success path
                self.consecutive_failures = 0
                self.last_successful_connection = asyncio.get_event_loop().time()
                return True  # noqa: TRY300

            except (
                ConnectionException,
                ModbusIOException,
                OSError,
                TimeoutError,
            ) as exc:
                _LOGGER.warning(
                    "Network error writing nominal power: %s (attempt %d/%d)",
                    exc,
                    retry_count,
                    max_retries,
                )
                retry_count += 1
                if retry_count > max_retries:
                    _LOGGER.error("Max write attempts reached after network errors")
                    return False

                # Exponential backoff before retry
                delay = min(2**retry_count, 10)
                await asyncio.sleep(delay)
                continue  # Loop retry

            except ModbusException as exc:
                _LOGGER.error("Modbus exception writing nominal power: %s", exc)
                retry_count += 1
                if retry_count > max_retries:
                    return False

                delay = min(2**retry_count, 10)
                await asyncio.sleep(delay)
                continue  # Loop retry

            except (ValueError, TypeError) as exc:
                _LOGGER.error("Value error writing nominal power: %s", exc)
                return False  # No retry for validation errors

        # Exhausted retries
        return False

    async def _attempt_reconnection(self) -> bool:
        """Attempt to reconnect after connection failure.

        This method provides automatic reconnection with progressive backoff
        to handle SAX battery reboots and network issues gracefully.

        Returns:
            True if reconnection successful, False otherwise

        Security:
            OWASP A05: Limited retry attempts prevent resource exhaustion

        Performance:
            Progressive backoff based on consecutive failures
        """
        # Prevent infinite reconnection attempts
        if self.consecutive_failures >= 3:
            _LOGGER.error(
                "Max reconnection attempts (3) reached for %s, giving up until next update cycle",
                self.battery_id,
            )
            return False

        self.consecutive_failures += 1

        _LOGGER.info(
            "Connection lost for %s, attempting reconnection (attempt %d/3)",
            self.battery_id,
            self.consecutive_failures,
        )

        # Close the broken connection
        if self._modbus_client:
            try:
                await self._modbus_client.close()  # type: ignore[func-returns-value]
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Error closing connection: %s", exc)

        # Progressive backoff: 2s, 4s, 8s (max 10s)
        delay = min(self.consecutive_failures * 2.0, 10.0)
        _LOGGER.debug("Waiting %ds before reconnection attempt", delay)
        await asyncio.sleep(delay)

        # Actually check if reconnection succeeded
        try:
            if await self.connect():
                self.consecutive_failures = 0  # Reset on success
                self.last_successful_connection = asyncio.get_event_loop().time()
                _LOGGER.info("Reconnection successful for %s", self.battery_id)
                return True

            _LOGGER.warning(
                "Reconnection attempt %d/3 failed", self.consecutive_failures
            )
            return False  # noqa: TRY300

        except (OSError, TimeoutError, ConnectionException) as exc:
            _LOGGER.error("Reconnection error: %s", exc)
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
