"""SAX Battery data update coordinator."""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import Coroutine
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from pymodbus import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .circuit_breaker import (
    CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CircuitBreaker,
)
from .const import (
    CONF_BATTERY_IS_MASTER,
    CONF_LIMIT_POWER,
    CONF_MIN_SOC,
    DEFAULT_MIN_SOC,
    DOMAIN,
    SAX_COMBINED_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
    SAX_SOC,
    SAX_STATUS,
)
from .coordinator_statistics import CoordinatorStatistics
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem, SAXItem
from .modbusobject import ModbusAPI
from .models import SAXBatteryData
from .soc_manager import SOCManager

_LOGGER = logging.getLogger(__name__)

# Polling intervals (in seconds)
BATTERY_POLL_INTERVAL = 15  # master battery data polling (SOC, Power, Status)
BATTERY_POLL_SLAVE_INTERVAL = 30  # slave battery data polling (SOC, Power, Status)
SINGLE_ITEM_POLL_TIMEOUT = 10  # Per-item timeout to prevent cascade failures

# Performance monitoring constants
CYCLE_TIME_HISTORY_SIZE = 100  # Number of cycle times to keep for statistics
ERROR_HISTORY_SIZE = 1000  # Number of error events to keep for diagnostics
CYCLE_STATS_LOG_INTERVAL = 240  # Log cycle statistics every N updates (~1 hour)


class SAXBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """SAX Battery data update coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        battery_id: str,
        sax_data: SAXBatteryData,
        modbus_api: ModbusAPI,
        config_entry: ConfigEntry,
        battery_config: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{battery_id}",
            update_interval=timedelta(seconds=10),
            config_entry=config_entry,
        )

        self.battery_id = battery_id
        self.config_entry = config_entry
        self.sax_data = sax_data
        self.modbus_api = modbus_api
        self.battery_config = battery_config

        # Initialize timestamp for tracking last successful update
        self.last_update_success_time: datetime | None = None

        # Write queue for Modbus operations
        # Queue items: (ModbusItem, value, write_type)
        # write_type: "normal" | "nominal_power" | "batch"
        self._write_queue: asyncio.Queue[
            tuple[ModbusItem, int, str, dict[str, Any]]
        ] = asyncio.Queue()
        self._write_lock = asyncio.Lock()

        # Track pending writes for UI updates
        self._pending_writes: dict[str, int] = {}

        # Performance monitoring: Cycle time tracking
        # Store last N cycle times for statistics (FIFO)
        self._cycle_start_time: float | None = None
        self._last_cycle_duration: float | None = None
        self._total_updates: int = 0
        self._failed_updates: int = 0

        # Circuit breaker for Modbus communication protection
        # Security (OWASP A05): Prevents resource exhaustion
        self._circuit_breaker = CircuitBreaker(
            name=battery_id,
            failure_threshold=CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            cooldown_seconds=CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )

        # Statistics tracker (composition pattern — extracted from coordinator)
        self._statistics = CoordinatorStatistics(
            circuit_breaker=self._circuit_breaker,
            battery_id=self.battery_id,
            last_cycle_duration_fn=lambda: self._last_cycle_duration,
        )

        # Track nominal power atomic write state
        self._nominal_power_pending: dict[str, int] = {}  # {power: int, factor: int}

        # Set the modbus API reference for all items
        for item in self.sax_data.get_modbus_items_for_battery(battery_id):
            if hasattr(item, "modbus_api"):
                item.modbus_api = self.modbus_api

        if self.sax_data.batteries[self.battery_id].is_master:
            self.update_interval = timedelta(seconds=BATTERY_POLL_INTERVAL)
        else:
            self.update_interval = timedelta(seconds=BATTERY_POLL_SLAVE_INTERVAL)

        # Initialize SOC manager
        min_soc = self.config_entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        limit_power_enabled = self.config_entry.data.get(CONF_LIMIT_POWER, False)

        self.soc_manager = SOCManager(
            coordinator=self,
            min_soc=min_soc,
            enabled=limit_power_enabled,
        )

        _LOGGER.debug(
            "SOC manager initialized: min_soc=%s%%, enabled=%s",
            min_soc,
            limit_power_enabled,
        )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Return the circuit breaker instance for diagnostics."""
        return self._circuit_breaker

    @property
    def statistics(self) -> CoordinatorStatistics:
        """Return the statistics tracker for diagnostics."""
        return self._statistics

    @property
    def cycle_time_statistics(self) -> dict[str, Any]:
        """Get cycle time and error statistics (delegates to statistics tracker)."""
        return self._statistics.cycle_time_statistics

    @property
    def is_master(self) -> bool:
        """Check if this is the master battery coordinator."""
        return bool(self.battery_config.get(CONF_BATTERY_IS_MASTER, False))

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via Modbus with write queue processing.

        Performance:
            Processes write queue before reads to minimize Modbus roundtrips
        Security:
            OWASP A05: Single-threaded Modbus access prevents device resets
            Circuit breaker pattern prevents overwhelming unresponsive devices
        """
        # Security: Initialize with proper type annotation
        data: dict[str, Any] = {}

        # Start cycle time measurement
        self._cycle_start_time = time.monotonic()

        # Check circuit breaker state
        if not self._circuit_breaker.pre_update_check():
            cycle_duration = time.monotonic() - self._cycle_start_time
            self._circuit_breaker.record_cycle_time(cycle_duration)
            raise UpdateFailed(
                f"Circuit breaker open"
                f" (cooldown: {self._circuit_breaker.cooldown_remaining:.0f}s"
                f" remaining)"
            )

        try:
            # STEP 1: Process write queue first (before reads)
            await self._process_write_queue(data)

            # Get entity registry to check enabled state
            entity_registry = er.async_get(self.hass)

            # Performance: Filter items to only poll enabled entities
            enabled_items = await self._get_enabled_modbus_items(entity_registry)

            # remove items which were just written
            enabled_items = [item for item in enabled_items if item.name not in data]

            # Batch polls by device for efficiency
            device_batches = self._group_items_by_device(enabled_items)

            # Performance: Use extend pattern for collecting tasks
            polling_tasks: list[Coroutine[Any, Any, dict[str, Any]]] = []
            polling_tasks.extend(
                [
                    self._poll_device_batch(device, items)
                    for device, items in device_batches.items()
                ]
            )

            # Execute all polling tasks concurrently
            batch_results = await asyncio.gather(*polling_tasks, return_exceptions=True)

            # Process results and update data dictionary
            batch_failure_count = 0
            batch_total_count = len(device_batches)
            last_batch_error: Exception | None = None

            for device, result in zip(
                device_batches.keys(), batch_results, strict=True
            ):
                if isinstance(result, Exception):
                    batch_failure_count += 1
                    last_batch_error = result
                    _LOGGER.warning("Failed to poll device %s: %s", device, result)
                    continue

                # Security: Type check before dictionary update
                if isinstance(result, dict):
                    data.update(result)
                else:
                    _LOGGER.warning(
                        "Unexpected result type from device %s polling: %s",
                        device,
                        type(result),
                    )

            # Security (OWASP A05): If ALL batches failed, trigger
            # circuit breaker to protect against unresponsive devices
            if batch_total_count > 0 and batch_failure_count == batch_total_count:
                self._failed_updates += 1
                self._circuit_breaker.record_failure(
                    last_batch_error or OSError("All device batches failed")
                )

                if self._cycle_start_time:
                    cycle_duration = time.monotonic() - self._cycle_start_time
                    self._circuit_breaker.record_cycle_time(cycle_duration)

                raise UpdateFailed(  # noqa: TRY301
                    f"All {batch_total_count} device batches failed: {last_batch_error}"
                )

            # Update calculated values for enabled SAX items only
            await self._update_enabled_calculated_values(data, entity_registry)

            # Update smart meter data if this is the master battery
            if self.is_master:
                await self._update_smart_meter_data_registry_aware(
                    data, entity_registry
                )

            # Check SOC constraints after data update
            if self.soc_manager and self.is_master:
                combined_soc = data.get(SAX_COMBINED_SOC)
                if combined_soc is not None and combined_soc < self.soc_manager.min_soc:
                    _LOGGER.debug(
                        "SOC %.1f%% below minimum %.1f%% - triggering enforcement",
                        combined_soc,
                        self.soc_manager.min_soc,
                    )
                    self.hass.async_create_task(
                        self.soc_manager.check_and_enforce_discharge_limit()
                    )

            _LOGGER.debug(
                "Polled %d enabled entities, skipped %d disabled entities",
                len(enabled_items),
                len(self._get_all_modbus_items()) - len(enabled_items),
            )

            # Calculate cycle time
            cycle_duration = time.monotonic() - self._cycle_start_time
            self._circuit_breaker.record_cycle_time(cycle_duration)
            self._last_cycle_duration = cycle_duration
            self._total_updates += 1

            # Track BMS unavailability: SAX_STATUS absent despite successful poll
            # indicates a transient battery reset / modbus gap on that register
            if SAX_STATUS not in data:
                self._statistics.collect_bms_unavailability()

            # Invalidate statistics cache (lazy aggregation - Issue #43)
            self._statistics.mark_dirty()

            # Record success in circuit breaker
            self._circuit_breaker.record_success()

            # Log cycle time statistics periodically
            if self._total_updates % CYCLE_STATS_LOG_INTERVAL == 0:
                self._statistics.log_cycle_statistics()

            # Security: Update successful polling timestamp
            self.last_update_success_time = datetime.now()

            return data  # noqa: TRY300

        except UpdateFailed:
            # Re-raise UpdateFailed (from all-batches-failed or circuit
            # breaker check). Circuit breaker already handled above.
            raise

        except (ModbusException, OSError, builtins.TimeoutError) as err:
            self._failed_updates += 1
            self._circuit_breaker.record_failure(err)

            if self._cycle_start_time:
                cycle_duration = time.monotonic() - self._cycle_start_time
                self._circuit_breaker.record_cycle_time(cycle_duration)

            raise UpdateFailed(f"Modbus communication error: {err}") from err

        except Exception as err:
            # Unexpected errors don't trigger circuit breaker
            self._failed_updates += 1

            if self._cycle_start_time:
                cycle_duration = time.monotonic() - self._cycle_start_time
                self._circuit_breaker.record_cycle_time(cycle_duration)

            _LOGGER.exception(
                "Unexpected error during data update: %s",
                self.battery_id,
            )
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _process_write_queue(self, data: dict[str, Any]) -> None:
        """Process all pending writes in queue.

        Args:
            data: Dictionary to store written values

        Security:
            OWASP A05: Serialized write processing prevents device conflicts
        """
        async with self._write_lock:
            while not self._write_queue.empty():
                try:
                    item, value, write_type, metadata = await asyncio.wait_for(
                        self._write_queue.get(),
                        timeout=0.1,
                    )

                    success = False

                    # Handle atomic nominal power write
                    if write_type == "nominal_power":
                        factor = metadata.get("factor", 100)

                        success = await self.modbus_api.write_nominal_power(
                            value,
                            int(factor),
                            item,
                        )

                        if success:
                            _LOGGER.debug(
                                "Atomic write succeeded: power=%sW, factor=%s%%",
                                value,
                                factor,
                            )
                            # Update both cached values
                            data[SAX_NOMINAL_POWER] = value
                            data[SAX_NOMINAL_FACTOR] = factor
                            self._pending_writes.pop(SAX_NOMINAL_POWER, None)
                            self._pending_writes.pop(SAX_NOMINAL_FACTOR, None)
                        else:
                            _LOGGER.warning(
                                "Atomic write failed: power=%sW, factor=%s%%",
                                value,
                                factor,
                            )

                    # Handle normal write
                    else:
                        success = await self.modbus_api.write_registers(
                            value,
                            item,
                        )

                        if success:
                            _LOGGER.debug(
                                "Write succeeded: %s=%s",
                                item.name,
                                value,
                            )
                            data[item.name] = value
                            self._pending_writes.pop(item.name, None)
                        else:
                            _LOGGER.warning(
                                "Write failed: %s=%s",
                                item.name,
                                value,
                            )

                except builtins.TimeoutError:
                    break  # No more pending writes
                except Exception as err:  # noqa: BLE001
                    if item is not None:  # pyright: ignore[reportPossiblyUnboundVariable]
                        _LOGGER.error(
                            "Write queue error for %s: %s",
                            item.name if "item" in locals() else "unknown",  # pyright: ignore[reportPossiblyUnboundVariable]
                            err,
                        )

    def _get_all_modbus_items(self) -> list[ModbusItem]:
        """Get all ModbusItems for this battery for statistics."""
        return [
            item
            for item in self.sax_data.get_modbus_items_for_battery(self.battery_id)
            if isinstance(item, ModbusItem)
        ]

    def _group_items_by_device(
        self, items: list[ModbusItem]
    ) -> dict[DeviceConstants, list[ModbusItem]]:
        """Group ModbusItems by device for efficient batch polling.

        Args:
            items: List of ModbusItems to group

        Returns:
            dict: Items grouped by device type

        Performance: Single pass grouping with extend pattern
        """
        device_groups: dict[DeviceConstants, list[ModbusItem]] = {}

        for item in items:
            if item.device not in device_groups:
                device_groups[item.device] = []
            device_groups[item.device].append(item)

        return device_groups

    async def _poll_device_batch(
        self, device: DeviceConstants, items: list[ModbusItem]
    ) -> dict[str, Any]:
        """Poll a batch of items from the same device.

        Args:
            device: Device type (BESS, SM, etc.) t
            items: List of ModbusItem objects to poll

        Returns:
                Dictionary of item_name -> value

        Performance:
            Groups consecutive registers into batch reads
        """

        batch_data: dict[str, Any] = {}

        try:
            # Ensure connection before polling batch
            if not self.modbus_api.is_connected():
                _LOGGER.debug(
                    "%s: Not connected before polling device %s, attempting connection",
                    self.battery_id,
                    device.value,
                )
                if not await self.modbus_api.connect():
                    _LOGGER.warning(
                        "%s: Failed to connect for device %s polling",
                        self.battery_id,
                        device.value,
                    )
                    return batch_data

            _LOGGER.debug("Polling %d items from device %s", len(items), device.value)

            # Performance: Use list comprehension for concurrent polling
            polling_tasks = [self._poll_single_item(item) for item in items]
            results = await asyncio.gather(*polling_tasks, return_exceptions=True)

            # Collect results
            for item, result in zip(items, results, strict=True):
                # Check if read failed
                if not self.modbus_api.last_operation_status.success:
                    self._statistics.collect_modbus_error(
                        self.modbus_api.last_operation_status
                    )
                    _LOGGER.debug(
                        "%s: Failed to read %s (address %d): %s",
                        self.battery_id,
                        item.name,
                        item.address,
                        self.modbus_api.last_operation_status.error_message,
                    )
                    continue  # Skip this item
                if isinstance(result, Exception):
                    _LOGGER.debug("Failed to poll %s: %s", item.name, result)
                    batch_data[item.name] = None
                else:
                    batch_data[item.name] = result

            return batch_data  # noqa: TRY300

        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Error polling device batch %s: %s", device.value, exc)
            return batch_data

    async def _poll_single_item(self, item: ModbusItem) -> Any:
        """Poll a single ModbusItem.

        Args:
            item: ModbusItem to poll

        Returns:
            Any: Polled value or None on error

        Performance: Direct item polling with per-item timeout
        Security: Prevents single unresponsive register from blocking all polling
        """
        try:
            return await asyncio.wait_for(
                item.async_read_value(),
                timeout=SINGLE_ITEM_POLL_TIMEOUT,
            )
        except TimeoutError:
            _LOGGER.warning(
                "Timeout polling %s at address %s after %ss",
                item.name,
                item.address,
                SINGLE_ITEM_POLL_TIMEOUT,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "Error polling %s: %s",
                item.name,
                exc,
            )
            return None

    async def _update_enabled_calculated_values(
        self, data: dict[str, Any], entity_registry: Any
    ) -> None:
        """Update calculated SAX values for enabled entities only.

        Args:
            data: Dictionary to store calculated values
            entity_registry: Home Assistant entity registry

        Performance: Only calculates values for enabled SAX entities
        Security:
            OWASP A05: Input validation and safe registry access
            OWASP A03: Null safety to prevent attribute access errors
        """
        try:
            # Security: Validate coordinator data is available
            if self.data is None:
                _LOGGER.debug(  # type:ignore[unreachable]
                    "Coordinator data not yet available, skipping calculated values update"
                )
                return

            # Get SAX items for this battery
            all_sax_items = self.sax_data.get_sax_items_for_battery(self.battery_id)

            # Performance: Filter to only enabled SAX entities
            enabled_sax_items = []
            for sax_item in all_sax_items:
                if not isinstance(sax_item, SAXItem):
                    continue  # type: ignore[unreachable]

                # Check if SAX entity is enabled in registry
                unique_id = (
                    sax_item.name
                    if sax_item.name.startswith("sax_")
                    else f"sax_{sax_item.name}"
                )

                # Check if entity exists in registry and is enabled
                entity_id = entity_registry.async_get_entity_id(
                    "sensor", DOMAIN, unique_id
                ) or entity_registry.async_get_entity_id("number", DOMAIN, unique_id)

                if entity_id:
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and not entity_entry.disabled:
                        enabled_sax_items.append(sax_item)
                else:
                    # Include new entities by default
                    enabled_sax_items.append(sax_item)

            # Performance: Filter calculable items using list comprehension
            calculable_items = [
                sax_item
                for sax_item in enabled_sax_items
                if sax_item.mtype
                in (
                    TypeConstants.SENSOR,
                    TypeConstants.SENSOR_CALC,
                    TypeConstants.NUMBER,
                    TypeConstants.NUMBER_RO,
                )
            ]

            # Performance: Single dictionary update for all calculations
            calculated_values: dict[str, Any] = {}
            for sax_item in calculable_items:
                try:
                    if (
                        not hasattr(sax_item, "coordinators")
                        or not sax_item.coordinators
                    ):
                        sax_item.set_coordinators(self.sax_data.coordinators)

                    if sax_item.name == SAX_COMBINED_SOC:
                        # Compute average SOC across all battery coordinators.
                        # Use fresh data for the current battery; last known
                        # data for other batteries polled on their own interval.
                        soc_values = []
                        for battery_id, coord in self.sax_data.coordinators.items():
                            coord_data = (
                                data
                                if battery_id == self.battery_id
                                else (coord.data or {})
                            )
                            soc = coord_data.get(SAX_SOC)
                            if soc is not None:
                                soc_values.append(float(soc))
                        if soc_values:
                            calculated_values[SAX_COMBINED_SOC] = round(
                                sum(soc_values) / len(soc_values), 1
                            )
                    else:
                        # Passthrough: preserve other calculated values
                        # (e.g. cumulative energy managed by sensor entity)
                        value = self.data.get(sax_item.name)
                        if value is not None:
                            calculated_values[sax_item.name] = value

                except (ValueError, TypeError, ZeroDivisionError) as err:
                    _LOGGER.warning("Failed to calculate %s: %s", sax_item.name, err)
                    # calculated_values[sax_item.name] = None

            # Performance: Single update operation
            data.update(calculated_values)

            _LOGGER.debug(
                "Updated %d calculated values for enabled entities",
                len(calculated_values),
            )

        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error updating calculated values: %s", err)

    async def _get_enabled_modbus_items(self, entity_registry: Any) -> list[ModbusItem]:
        """Get list of ModbusItems that have enabled entities.

        Following Home Assistant guidelines for entity registry disabled_by:
        - Only poll items that are enabled_by_default=True OR explicitly enabled by user
        - Skip items that are disabled_by_default and not explicitly enabled

        Args:
            entity_registry: Home Assistant entity registry

        Returns:
            list[ModbusItem]: Items with at least one enabled entity

        Performance: Efficient filtering using entity registry lookups
        Security: Input validation and safe entity registry access
        """
        try:
            all_items = [
                item
                for item in self.sax_data.get_modbus_items_for_battery(self.battery_id)
                if isinstance(item, ModbusItem)
            ]

            enabled_items = []

            for item in all_items:
                # Check if item is enabled by default
                enabled_by_default = getattr(item, "enabled_by_default", True)

                # Use SAXBatteryData.get_unique_id_for_item() for consistent naming
                unique_id = self.sax_data.get_unique_id_for_item(
                    item,
                    battery_id=self.battery_id
                    if item.device != DeviceConstants.SYS
                    else None,
                )

                if not unique_id:
                    _LOGGER.warning(
                        "Could not generate unique_id for item %s (battery=%s)",
                        item.name,
                        self.battery_id,
                    )
                    continue

                # Determine platform from item type
                if item.mtype in (TypeConstants.SENSOR, TypeConstants.SENSOR_CALC):
                    platform = "sensor"
                elif item.mtype == TypeConstants.SWITCH:
                    platform = "switch"
                elif item.mtype in (
                    TypeConstants.NUMBER,
                    TypeConstants.NUMBER_WO,
                    TypeConstants.NUMBER_RO,
                ):
                    platform = "number"
                else:
                    _LOGGER.warning(
                        "Unknown item type %s for %s", item.mtype, item.name
                    )
                    continue

                # Check if entity exists in registry
                entity_id = entity_registry.async_get_entity_id(
                    platform, DOMAIN, unique_id
                )

                if entity_id:
                    # Entity exists in registry - check if it's enabled
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and not entity_entry.disabled:
                        enabled_items.append(item)
                        _LOGGER.debug("Including existing entity: %s", unique_id)
                    else:
                        _LOGGER.debug("Skipping disabled entity: %s", unique_id)
                elif enabled_by_default:
                    # Include items that are enabled by default
                    enabled_items.append(item)
                    _LOGGER.debug(
                        "Including new entity (enabled by default): %s", unique_id
                    )
                else:
                    # Skip items that are disabled by default and not in registry
                    _LOGGER.debug(
                        "Skipping new entity (disabled by default): %s", unique_id
                    )

            _LOGGER.debug(
                "Filtered %d enabled items from %d total items for %s",
                len(enabled_items),
                len(all_items),
                self.battery_id,
            )

            return enabled_items  # noqa: TRY300

        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Error checking entity registry for %s, polling all items: %s",
                self.battery_id,
                exc,
            )
            # Security: Fallback to polling all items if registry check fails
            return [
                item
                for item in self.sax_data.get_modbus_items_for_battery(self.battery_id)
                if isinstance(item, ModbusItem)
            ]

    async def _update_smart_meter_data_registry_aware(
        self, data: dict[str, Any], entity_registry: Any
    ) -> None:
        """Update smart meter data for enabled entities only.

        Smart meter data is polled through master battery's MODBUS_BATTERY_SMARTMETER_ITEMS,
        not through separate smart meter item lists to prevent duplicates.

        Args:
            data: Dictionary to store the updated values
            entity_registry: Home Assistant entity registry

        Security: Error handling for network communication
        Performance: Only polls enabled smart meter entities, prevents duplicates
        """
        if not self.is_master:
            _LOGGER.debug(
                "Skipping smart meter update for slave battery %s", self.battery_id
            )
            return

        try:
            # Smart meter items are already included in the battery's modbus items
            # for master battery, so no separate polling needed
            _LOGGER.debug(
                "Smart meter data included in master battery polling - no separate update needed"
            )

        except (ModbusException, OSError, builtins.TimeoutError) as err:
            _LOGGER.error("Error in smart meter data handling: %s", err)
            raise

    async def async_write_number_value(
        self,
        modbus_item: ModbusItem,
        value: int,
    ) -> None:
        """Queue a write operation with item-specific handling.

        Args:
            modbus_item: Item to write
            value: Value to write

        Security:
            OWASP A05: Prevents concurrent writes causing device resets
        Performance:
            Item-specific optimizations for battery hardware

        Note:
            This method queues the write and returns immediately.
            The actual write occurs during the next coordinator update cycle.
            Success/failure is reflected in coordinator data and entity state.
        """
        # Set API reference if missing
        if modbus_item.modbus_api is None:
            modbus_item.modbus_api = self.modbus_api
        # Handle nominal power/factor as atomic operation
        if modbus_item.name == SAX_NOMINAL_POWER:
            # Store power value
            self._nominal_power_pending["power"] = value
            self._pending_writes[modbus_item.name] = value

            # If we already have factor, queue atomic write
            if "factor" in self._nominal_power_pending:
                await self._queue_nominal_power_write()
            else:
                # Trigger refresh to show pending state
                await self.async_request_refresh()
            return

        if modbus_item.name == SAX_NOMINAL_FACTOR:
            # Store factor value
            self._nominal_power_pending["factor"] = int(value)
            self._pending_writes[modbus_item.name] = value

            # If we already have power, queue atomic write
            if "power" in self._nominal_power_pending:
                await self._queue_nominal_power_write()
            else:
                # Trigger refresh to show pending state
                await self.async_request_refresh()
            return

        # Normal write for other items
        self._pending_writes[modbus_item.name] = value
        await self._write_queue.put((modbus_item, value, "normal", {}))

        # Trigger coordinator refresh to process queue
        await self.async_request_refresh()

        _LOGGER.debug(
            "Queued write for %s: %s=%s",
            self.battery_id,
            modbus_item.name,
            value,
        )

    async def _queue_nominal_power_write(self) -> None:
        """Queue atomic nominal power write.

        Security:
            OWASP A05: Ensures atomic write for related registers
        """
        power = self._nominal_power_pending.get("power")
        factor = self._nominal_power_pending.get("factor")

        if power is None or factor is None:
            _LOGGER.error(
                "Cannot queue nominal power write: missing values (power=%s, factor=%s)",
                power,
                factor,
            )
            return

        # Create placeholder item for atomic write
        nominal_power_item = self.sax_data.get_item_by_name(SAX_NOMINAL_POWER)

        if not isinstance(nominal_power_item, ModbusItem):
            _LOGGER.error("SAX_NOMINAL_POWER is not a ModbusItem")
            return

        # Queue with special metadata
        metadata = {"factor": factor}
        await self._write_queue.put(
            (nominal_power_item, power, "nominal_power", metadata)
        )

        # Clear pending state
        self._nominal_power_pending.clear()

        # Trigger coordinator refresh to process queue
        await self.async_request_refresh()

        _LOGGER.debug(
            "Queued atomic nominal power write: power=%sW, factor=%s%%",
            power,
            factor,
        )

    async def async_write_switch_value(
        self, modbus_item: ModbusItem, value: bool
    ) -> None:
        """Queue a switch write operation.

        Args:
            modbus_item: Switch item to write
            value: Boolean value to write

        Note:
            This method queues the write and returns immediately.
            The actual write occurs during the next coordinator update cycle.
        """

        # Set API reference if missing
        if modbus_item.modbus_api is None:
            modbus_item.modbus_api = self.modbus_api

        # Convert boolean to register value
        register_value = (
            modbus_item.get_switch_on_value()
            if value
            else modbus_item.get_switch_off_value()
        )

        # Queue the write
        self._pending_writes[modbus_item.name] = int(register_value)
        await self._write_queue.put((modbus_item, int(register_value), "normal", {}))

        # Trigger coordinator refresh
        await self.async_request_refresh()

        _LOGGER.debug(
            "Queued switch write for %s: %s=%s (register=%s)",
            self.battery_id,
            modbus_item.name,
            value,
            register_value,
        )

    async def async_write_power_control_value(
        self,
        power_item: ModbusItem,
        power: int,
        power_factor: int,
    ) -> bool:
        """Write power control values with atomic Modbus operation.

        Args:
            power_item: Power register ModbusItem (for reference only)
            power: Power value to write
            power_factor: Power factor value to write

        Returns:
            bool: True if atomic write successful

        Security: Input validation and atomic write operations
        Performance: Single Modbus write for both registers
        """
        try:
            # Performance: Use atomic write_nominal_power for both registers
            success = await self.modbus_api.write_nominal_power(
                value=power, power_factor=power_factor, modbus_item=power_item
            )

            if success:
                _LOGGER.debug(
                    "Successfully wrote power control values atomically: power=%s, factor=%s",
                    power,
                    power_factor,
                )
            else:
                _LOGGER.error("Failed to write power control values atomically")

            return success  # noqa: TRY300

        except (ModbusException, OSError, builtins.TimeoutError) as err:
            _LOGGER.error("Modbus error in power control write operation: %s", err)
            return False
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Unexpected error in power control write operation: %s", err)
            return False
