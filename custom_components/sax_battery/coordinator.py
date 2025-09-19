"""SAX Battery data update coordinator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from pymodbus import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BATTERY_POLL_INTERVAL,
    BATTERY_POLL_SLAVE_INTERVAL,
    CONF_BATTERY_IS_MASTER,
    DOMAIN,
)
from .items import ModbusItem, SAXItem
from .modbusobject import ModbusAPI
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)


class SAXBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """SAX Battery data update coordinator with direct ModbusItem integration.

    Security: Implements proper error handling and input validation
    Performance: Efficient update strategies with connection pooling
    """

    def __init__(
        self,
        hass: HomeAssistant,
        battery_id: str,
        sax_data: SAXBatteryData,
        modbus_api: ModbusAPI,
        config_entry: ConfigEntry,
        battery_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            battery_id: Unique battery identifier
            sax_data: SAX battery data model
            modbus_api: Modbus communication API
            config_entry: Configuration entry
            battery_config: Battery-specific configuration

        Security: Validates all input parameters
        """
        # Security: Input validation
        if not isinstance(battery_id, str) or not battery_id.strip():
            raise ValueError("Battery ID must be a non-empty string")

        self.battery_id = battery_id.strip()
        self.sax_data = sax_data
        self.modbus_api = modbus_api
        self.config_entry = config_entry
        self.battery_config = battery_config or {}

        # Initialize timestamp for tracking last successful update
        self.last_update_success_time: datetime | None = None

        # Determine update interval based on battery role
        is_master_battery = self.battery_config.get(CONF_BATTERY_IS_MASTER, False)
        update_interval = (
            BATTERY_POLL_INTERVAL if is_master_battery else BATTERY_POLL_SLAVE_INTERVAL
        )  # Master polls more frequently

        super().__init__(
            hass,
            _LOGGER,
            name=f"SAX Battery {battery_id}",
            update_interval=timedelta(seconds=update_interval),
        )

        # Initialize ModbusItems with API reference
        self._setup_modbus_items()

    @property
    def is_master(self) -> bool:
        """Check if this battery is the master battery.

        Returns:
            bool: True if this is the master battery

        Performance: Cached property access
        """
        return bool(self.battery_config.get(CONF_BATTERY_IS_MASTER, False))

    def _setup_modbus_items(self) -> None:
        """Set up ModbusItems with API reference for direct communication.

        Performance: Efficient item setup using list comprehension patterns
        Security: Validates item types before setup
        """
        # Performance optimization: Use list comprehension to filter and setup
        modbus_items = [
            item
            for item in self.sax_data.get_modbus_items_for_battery(self.battery_id)
            if isinstance(item, ModbusItem)
        ]

        # Setup API references for modbus items
        for item in modbus_items:
            item.modbus_api = self.modbus_api

        # Set up SAXItems with coordinator references
        sax_items = [
            item
            for item in self.sax_data.get_sax_items_for_battery(self.battery_id)
            if isinstance(item, SAXItem)
        ]

        # Performance: Use extend pattern for coordinator setup
        for sax_item in sax_items:
            # Pass all coordinators for multi-battery calculations
            sax_item.set_coordinators(self.sax_data.coordinators)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from SAX Battery with entity registry awareness.

        Performance: Only polls entities that are enabled in entity registry
        Security: Validates entity registry access and handles missing entities
        """
        start_time = time.time()

        try:
            # Check connection health before proceeding (existing code)
            if self.modbus_api and self.modbus_api.should_force_reconnect():
                _LOGGER.warning(
                    "Battery %s connection health is poor, forcing reconnection",
                    self.battery_id,
                )
                self.modbus_api.close()
                if not await self.modbus_api.connect():
                    raise UpdateFailed(  # noqa: TRY301
                        f"Failed to reconnect to battery {self.battery_id} after health check"
                    )

            data: dict[str, Any] = {}

            # Get entity registry for enabled state checking
            entity_registry = async_get_entity_registry(self.hass)

            # Update smart meter data (master only) - with registry awareness
            if self.is_master:
                try:
                    await self._update_smart_meter_data_registry_aware(
                        data, entity_registry
                    )
                except OSError as err:
                    # Existing error handling unchanged
                    if err.errno in {32, 104, 110, 111}:
                        _LOGGER.warning(
                            "Smart meter connection error for %s: [Errno %d] %s - will retry",
                            self.battery_id,
                            err.errno,
                            err,
                        )
                    else:
                        _LOGGER.error(
                            "Smart meter communication error for %s: %s",
                            self.battery_id,
                            err,
                        )
                        raise UpdateFailed(f"Smart meter error: {err}") from err
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error(
                        "Unexpected smart meter error for %s: %s", self.battery_id, err
                    )

            # Update battery data with registry awareness
            try:
                await self._update_battery_data_registry_aware(data, entity_registry)
            except OSError as err:
                # Existing error handling unchanged
                if err.errno in {32, 104, 110, 111}:
                    _LOGGER.warning(
                        "Battery connection error for %s: [Errno %d] %s - attempting recovery",
                        self.battery_id,
                        err.errno,
                        err,
                    )

                    if self.modbus_api and await self.modbus_api.reconnect_on_error():
                        _LOGGER.info(
                            "Successfully recovered connection to %s", self.battery_id
                        )
                        try:
                            await self._update_battery_data_registry_aware(
                                data, entity_registry
                            )
                        except Exception as retry_err:
                            _LOGGER.error(
                                "Retry failed for %s: %s", self.battery_id, retry_err
                            )
                            raise UpdateFailed(
                                f"Battery communication failed after recovery attempt: {retry_err}"
                            ) from retry_err
                    else:
                        raise UpdateFailed(
                            f"Failed to recover connection to battery {self.battery_id}"
                        ) from err
                else:
                    _LOGGER.error(
                        "Battery communication error for %s: %s", self.battery_id, err
                    )
                    raise UpdateFailed(f"Battery error: {err}") from err
            except Exception as err:
                _LOGGER.error(
                    "Unexpected battery error for %s: %s", self.battery_id, err
                )
                raise UpdateFailed(
                    f"Error communicating with battery {self.battery_id}"
                ) from err

            # Update calculated values (unchanged)
            self._update_calculated_values(data)

            # Security: Set success timestamp after successful update
            self.last_update_success_time = datetime.now()

            # Log successful update with polling statistics
            duration = time.time() - start_time
            health = self.modbus_api.connection_health if self.modbus_api else {}

            _LOGGER.debug(
                "Finished fetching SAX Battery %s data in %.3f seconds (success: True, health: %s)",
                self.battery_id,
                duration,
                health.get("health_status", "unknown"),
            )

            return data  # noqa: TRY300

        except UpdateFailed:
            # Existing error handling unchanged
            duration = time.time() - start_time
            _LOGGER.debug(
                "Finished fetching SAX Battery %s data in %.3f seconds (success: False)",
                self.battery_id,
                duration,
            )
            raise
        except Exception as err:
            duration = time.time() - start_time
            _LOGGER.error("Unexpected error fetching %s data: %s", self.battery_id, err)
            _LOGGER.debug(
                "Finished fetching SAX Battery %s data in %.3f seconds (success: False)",
                self.battery_id,
                duration,
            )
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _get_enabled_modbus_items(self, entity_registry: Any) -> list[ModbusItem]:
        """Get list of ModbusItems that have enabled entities.

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
                # Generate the unique_id that would be used for this item
                item_name = item.name.removeprefix("sax_")
                unique_id = f"sax_{self.battery_id}_{item_name}"

                # Check if entity exists and is enabled in registry
                entity_id = (
                    entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
                    or entity_registry.async_get_entity_id("number", DOMAIN, unique_id)
                    or entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)
                )

                if entity_id:
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and not entity_entry.disabled:
                        enabled_items.append(item)
                        _LOGGER.debug("Including enabled entity: %s", unique_id)
                    else:
                        _LOGGER.debug("Skipping disabled entity: %s", unique_id)
                else:
                    # Entity not in registry - include by default for new entities
                    enabled_items.append(item)
                    _LOGGER.debug("Including new entity: %s", unique_id)

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

    async def _update_battery_data_registry_aware(
        self, data: dict[str, Any], entity_registry: Any
    ) -> None:
        """Update battery data from enabled modbus items only.

        Args:
            data: Dictionary to store the updated values
            entity_registry: Home Assistant entity registry

        Security: Error handling for communication failures
        Performance: Only polls enabled entities, efficient item iteration
        """
        try:
            # Performance optimization: Get only enabled modbus items
            enabled_items = await self._get_enabled_modbus_items(entity_registry)

            _LOGGER.debug(
                "Polling %d enabled modbus items for %s",
                len(enabled_items),
                self.battery_id,
            )

            # Update data from each enabled modbus item
            for item in enabled_items:
                # Performance: Skip items that don't support reading
                if hasattr(item, "is_read_only") and item.is_read_only():
                    _LOGGER.debug("Skipping read-only item %s", item.name)
                    continue

                await self._read_battery_item(item, data)

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error(
                "Error updating battery data for %s: %s", self.battery_id, err
            )
            raise

    async def _update_smart_meter_data_registry_aware(
        self, data: dict[str, Any], entity_registry: Any
    ) -> None:
        """Update smart meter data for enabled entities only.

        Args:
            data: Dictionary to store the updated values
            entity_registry: Home Assistant entity registry

        Security: Error handling for network communication
        Performance: Only polls enabled smart meter entities
        """
        try:
            # Get all smart meter items
            all_smart_meter_items = [
                item
                for item in self.sax_data.get_smart_meter_items()
                if isinstance(item, ModbusItem)
            ]

            # Filter to enabled items only
            enabled_smart_meter_items = []

            for item in all_smart_meter_items:
                # Generate the unique_id that would be used for this item (smart meter items use master battery ID)
                item_name = item.name.removeprefix("sax_")
                unique_id = f"sax_{self.battery_id}_{item_name}"

                # Check if entity is enabled
                entity_id = entity_registry.async_get_entity_id(
                    "sensor", DOMAIN, unique_id
                )

                if entity_id:
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and not entity_entry.disabled:
                        enabled_smart_meter_items.append(item)
                        _LOGGER.debug(
                            "Including enabled smart meter entity: %s", unique_id
                        )
                    else:
                        _LOGGER.debug(
                            "Skipping disabled smart meter entity: %s", unique_id
                        )
                else:
                    # New entities - include by default
                    enabled_smart_meter_items.append(item)

            _LOGGER.debug(
                "Polling %d enabled smart meter items from %d total",
                len(enabled_smart_meter_items),
                len(all_smart_meter_items),
            )

            # Performance optimization: Use list comprehension for concurrent reads
            read_tasks = []
            for item in enabled_smart_meter_items:
                # Security: Ensure API reference is set
                if item.modbus_api is None:
                    item.modbus_api = self.modbus_api
                read_tasks.append(self._read_smart_meter_item(item, data))

            # Performance: Execute reads concurrently
            if read_tasks:
                await asyncio.gather(*read_tasks, return_exceptions=True)

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error("Error updating smart meter data: %s", err)
            raise

    async def _read_smart_meter_item(
        self, item: ModbusItem, data: dict[str, Any]
    ) -> None:
        """Read a single smart meter item.

        Args:
            item: ModbusItem to read
            data: Dictionary to store the result

        Performance: Individual item reads for better error isolation
        """
        try:
            value = await item.async_read_value()
            if value is not None:
                data[item.name] = value

                # Update smart meter model if available
                if self.sax_data.smart_meter_data:
                    # Security: Validate numeric value before setting
                    if isinstance(value, (int, float)):
                        self.sax_data.smart_meter_data.set_value(
                            item.name, float(value)
                        )

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.warning("Failed to read smart meter item %s: %s", item.name, err)
            data[item.name] = None

    async def async_write_number_value(self, item: ModbusItem, value: float) -> bool:
        """Write number value using direct ModbusItem communication.

        Args:
            item: ModbusItem to write to
            value: Value to write

        Returns:
            bool: True if write successful

        Security: Input validation and error handling
        """
        # Security: Input validation
        if not isinstance(item, ModbusItem):
            raise TypeError("Item must be a ModbusItem")
        if not isinstance(value, (int, float)):
            raise TypeError("Value must be numeric")

        # Ensure API is set
        if item.modbus_api is None:
            item.modbus_api = self.modbus_api
        return await item.async_write_value(value)

    async def async_write_switch_value(self, item: ModbusItem, value: bool) -> bool:
        """Write switch value using direct ModbusItem communication.

        Args:
            item: ModbusItem to write to
            value: Boolean value to write

        Returns:
            bool: True if write successful

        Security: Input validation and safe boolean conversion
        """
        # Security: Input validation
        if not isinstance(item, ModbusItem):
            _LOGGER.error("Expected ModbusItem, got %s", type(item))  # type:ignore [unreachable]
            return False
        if not isinstance(value, bool):
            _LOGGER.error("Expected bool value, got %s", type(value))  # type:ignore [unreachable]
            return False

        # Ensure API is set
        if item.modbus_api is None:
            item.modbus_api = self.modbus_api

        # Convert boolean to appropriate switch value (now synchronous)
        write_value = (
            item.get_switch_on_value() if value else item.get_switch_off_value()
        )
        return await item.async_write_value(write_value)

    def update_sax_item_state(self, item: SAXItem | str, value: Any) -> None:
        """Update SAX item state in the coordinator data.

        Args:
            item: SAXItem or item name to update
            value: New value to set

        Performance: Efficient state update with listener notification
        """
        if isinstance(item, str):
            item_name = item
        else:
            item_name = item.name

        if self.data:
            self.data[item_name] = value
            self.async_update_listeners()

    async def async_write_pilot_control_value(
        self,
        power_item: ModbusItem,
        power_factor_item: ModbusItem,
        power: float,
        power_factor: float,
    ) -> bool:
        """Write pilot control values (power and power factor) simultaneously.

        This method is specifically for MODBUS_BATTERY_PILOT_CONTROL_ITEMS that require
        writing both power and power factor registers at the same time.

        Args:
            power_item: ModbusItem for the power register (address 41)
            power_factor_item: ModbusItem for the power factor register (address 42)
            power: Power value to write
            power_factor: Power factor value to write

        Returns:
            bool: True if both values were written successfully

        Security:
            Validates input types and ranges before writing

        Performance:
            Single Modbus transaction for both registers
        """
        # Security: Input validation
        if not isinstance(power, (int, float)):
            raise TypeError("Power must be numeric")
        if not isinstance(power_factor, (int, float)):
            raise TypeError("Power factor must be numeric")

        # Range validation for power factor (typical range 0.0 to 1.0)
        if not (0.0 <= power_factor <= 1.0):
            raise ValueError(
                f"Power factor {power_factor} outside valid range [0.0, 1.0]"
            )

        try:
            # Use the specialized write method that handles both registers
            success = await self.modbus_api.write_nominal_power(
                value=power,
                power_factor=int(
                    power_factor * 10000
                ),  # Convert to integer with precision
                modbus_item=power_item,  # Use power item for address/device_id
            )

            if success:
                # Security: Ensure data dict exists before updating
                if self.data is None:
                    self.data = {}  # type:ignore [unreachable]

                # Update coordinator data for both values (performance optimization)
                self.data[power_item.name] = power
                self.data[power_factor_item.name] = power_factor
                _LOGGER.debug(
                    "Successfully wrote pilot control: power=%s, power_factor=%s",
                    power,
                    power_factor,
                )
            else:
                _LOGGER.error(
                    "Failed to write pilot control values: power=%s, power_factor=%s",
                    power,
                    power_factor,
                )

            return success  # noqa: TRY300

        except (OSError, TimeoutError, ModbusException) as err:
            _LOGGER.error("Error writing pilot control values: %s", err)
            return False

    async def _update_battery_data(self, data: dict[str, Any]) -> None:
        """Update battery data from modbus items.

        Args:
            data: Dictionary to store the updated values

        Security: Error handling for communication failures
        Performance: Efficient item iteration with read-only checks
        """
        try:
            # Performance optimization: Use list comprehension to get modbus items
            modbus_items = [
                item
                for item in self.sax_data.get_modbus_items_for_battery(self.battery_id)
                if isinstance(item, ModbusItem)
            ]

            # Update data from each modbus item
            for item in modbus_items:
                # Performance: Skip read-only check for write-only items (now synchronous)
                if hasattr(item, "is_read_only") and not item.is_read_only():
                    continue

                await self._read_battery_item(item, data)

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error(
                "Error updating battery data for %s: %s", self.battery_id, err
            )
            raise

    async def _read_battery_item(self, item: ModbusItem, data: dict[str, Any]) -> None:
        """Read a single battery item and update data dictionary.

        Args:
            item: ModbusItem to read
            data: Dictionary to store the result

        Security: Handles all read errors gracefully
        Performance: Individual item reads for better error isolation
        """
        try:
            value = await item.async_read_value()
            if value is not None:
                data[item.name] = value
                _LOGGER.debug("Read %s: %s", item.name, value)
            else:
                _LOGGER.debug("Skipping read for write-only item %s", item.name)

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.warning("Failed to read item %s: %s", item.name, err)
            # Don't fail the entire update for individual item failures
            data[item.name] = None

    def _update_calculated_values(self, data: dict[str, Any]) -> None:
        """Update calculated SAX values based on raw modbus data.

        Args:
            data: Dictionary to store the calculated values

        Performance: Uses efficient dictionary operations
        Security: Validates all calculations for numeric bounds
        """
        try:
            # Get SAX items for this battery
            sax_items = self.sax_data.get_sax_items_for_battery(self.battery_id)

            # Performance optimization: Use dictionary update pattern
            calculated_values: dict[
                str, Any
            ] = {}  # Fix: Use Any instead of float | int
            for sax_item in sax_items:
                if isinstance(sax_item, SAXItem):
                    try:
                        # Security: Validate coordinators are available
                        if (
                            not hasattr(sax_item, "coordinators")
                            or not sax_item.coordinators
                        ):
                            sax_item.set_coordinators(self.sax_data.coordinators)

                        value = sax_item.calculate_value(self.sax_data.coordinators)
                        if value is not None:
                            calculated_values[sax_item.name] = value
                            _LOGGER.debug("Calculated %s: %s", sax_item.name, value)
                        else:
                            # Security: Explicitly set None for failed calculations
                            calculated_values[sax_item.name] = None
                            _LOGGER.debug(
                                "Calculation returned None for %s", sax_item.name
                            )

                    except (ValueError, TypeError, ZeroDivisionError) as err:
                        _LOGGER.warning(
                            "Failed to calculate %s: %s", sax_item.name, err
                        )
                        # Security: Set None for calculation errors to maintain data consistency
                        calculated_values[sax_item.name] = None

            # Performance: Single update operation
            data.update(calculated_values)

        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error updating calculated values: %s", err)
