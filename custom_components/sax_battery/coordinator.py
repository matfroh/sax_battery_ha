"""SAX Battery data update coordinator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from pymodbus import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BATTERY_POLL_INTERVAL,
    BATTERY_POLL_SLAVE_INTERVAL,
    CONF_BATTERY_IS_MASTER,
    DOMAIN,
)
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem, SAXItem
from .modbusobject import ModbusAPI
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)


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

        # Set the modbus API reference for all items
        for item in self.sax_data.get_modbus_items_for_battery(battery_id):
            if hasattr(item, "modbus_api"):
                item.modbus_api = self.modbus_api

        if self.sax_data.batteries[self.battery_id].is_master:
            self.update_interval = timedelta(seconds=BATTERY_POLL_INTERVAL)
        else:
            self.update_interval = timedelta(seconds=BATTERY_POLL_SLAVE_INTERVAL)

    @property
    def is_master(self) -> bool:
        """Check if this is the master battery coordinator."""
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
        """Update data via Modbus with entity registry awareness.

        Performance: Only polls entities that are enabled in entity registry
        Security: Validates entity registry access and handles missing entities
        """
        # Security: Initialize with proper type annotation
        data: dict[str, Any] = {}

        try:
            # Check connection health and force reconnect if needed
            if self.modbus_api.should_force_reconnect():
                _LOGGER.info("Poor connection health detected, attempting reconnect")
                self.modbus_api.close()
                if not await self.modbus_api.connect():
                    raise UpdateFailed(  # noqa: TRY301
                        f"Failed to reconnect to battery {self.battery_id} after health check"
                    )

            # Get entity registry to check enabled state
            entity_registry = er.async_get(self.hass)

            # Performance: Filter items to only poll enabled entities
            enabled_items = await self._get_enabled_modbus_items(entity_registry)

            # Batch polls by device for efficiency
            device_batches = self._group_items_by_device(enabled_items)

            # Performance: Use extend pattern for collecting tasks
            polling_tasks = []
            polling_tasks.extend(
                [
                    self._poll_device_batch(device, items)
                    for device, items in device_batches.items()
                ]
            )

            # Execute all polling tasks concurrently
            batch_results = await asyncio.gather(*polling_tasks, return_exceptions=True)

            # Process results and update data dictionary
            for device, result in zip(
                device_batches.keys(), batch_results, strict=True
            ):
                if isinstance(result, Exception):
                    _LOGGER.warning("Failed to poll device %s: %s", device, result)
                    continue

                # Security: Type check before dictionary update to ensure result is a dict
                if isinstance(result, dict):
                    # Performance: Single dictionary update per device
                    data.update(result)
                else:
                    _LOGGER.warning(
                        "Unexpected result type from device %s polling: %s",
                        device,
                        type(result),
                    )

            # Update calculated values for enabled SAX items only
            await self._update_enabled_calculated_values(data, entity_registry)

            # Update smart meter data if this is the master battery
            if self.is_master:
                await self._update_smart_meter_data_registry_aware(
                    data, entity_registry
                )

            _LOGGER.debug(
                "Polled %d enabled entities, skipped %d disabled entities",
                len(enabled_items),
                len(self._get_all_modbus_items()) - len(enabled_items),
            )

            # Security: Update successful polling timestamp
            self.last_update_success_time = datetime.now()

            return data  # noqa: TRY300

        except ModbusException as err:
            _LOGGER.error(
                "Modbus communication error for battery %s: %s", self.battery_id, err
            )
            raise UpdateFailed(
                f"Error communicating with battery {self.battery_id}: {err}"
            ) from err
        except Exception as err:
            _LOGGER.error("Error updating coordinator data: %s", err)
            raise UpdateFailed(f"Error fetching data: {err}") from err

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
            device: Device type to poll
            items: List of items from this device

        Returns:
            dict: Polling results keyed by item name

        Performance: Batch polling for improved efficiency
        """
        batch_data: dict[str, Any] = {}

        try:
            _LOGGER.debug("Polling %d items from device %s", len(items), device.value)

            # Performance: Use list comprehension for concurrent polling
            polling_tasks = [self._poll_single_item(item) for item in items]
            results = await asyncio.gather(*polling_tasks, return_exceptions=True)

            # Collect results
            for item, result in zip(items, results, strict=True):
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

        Performance: Direct item polling with error handling
        """
        try:
            if item.is_read_only() and item.mtype == TypeConstants.NUMBER_WO:
                # Skip polling write-only items
                return None

            return await item.async_read_value()

        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Error polling item %s: %s", item.name, exc)
            return None

    async def _update_enabled_calculated_values(
        self, data: dict[str, Any], entity_registry: Any
    ) -> None:
        """Update calculated SAX values for enabled entities only.

        Args:
            data: Dictionary to store calculated values
            entity_registry: Home Assistant entity registry

        Performance: Only calculates values for enabled SAX entities
        Security: Input validation and safe registry access
        """
        try:
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

                    value = sax_item.calculate_value(self.sax_data.coordinators)
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

                # Generate the unique_id that would be used for this item
                item_name = item.name.removeprefix("sax_")
                if "smartmeter" in item_name.lower():
                    unique_id = f"sax_{item_name}"
                else:
                    unique_id = f"sax_{self.battery_id}_{item_name}"

                # Check if entity exists in registry
                entity_id = (
                    entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
                    or entity_registry.async_get_entity_id("number", DOMAIN, unique_id)
                    or entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)
                )

                if entity_id:
                    # Entity exists in registry - check if it's enabled
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and not entity_entry.disabled:
                        enabled_items.append(item)
                        _LOGGER.debug("Including enabled entity: %s", unique_id)
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

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error("Error in smart meter data handling: %s", err)
            raise

    async def async_write_number_value(self, item: ModbusItem, value: float) -> bool:
        """Write number value using direct ModbusItem communication.

        Args:
            item: ModbusItem to write to
            value: Numeric value to write

        Returns:
            bool: True if write successful

        Security: Input validation and safe numeric conversion
        """
        # Security: Input validation
        if not isinstance(item, ModbusItem):
            _LOGGER.error(  # type: ignore[unreachable]
                "Expected ModbusItem, got %s", type(item)
            )
            return False
        if not isinstance(value, (int, float)):
            _LOGGER.error(  # type: ignore[unreachable]
                "Expected numeric value, got %s", type(value)
            )

        # Ensure API is set
        if item.modbus_api is None:
            item.modbus_api = self.modbus_api

        try:
            # Delegate to ModbusItem for actual write operation
            return await item.async_write_value(float(value))

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error("Failed to write number value to %s: %s", item.name, err)
            return False

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
            _LOGGER.error("Expected ModbusItem, got %s", type(item))  # type: ignore[unreachable]
            return False
        if not isinstance(value, bool):
            _LOGGER.error("Expected bool value, got %s", type(value))  # type: ignore[unreachable]
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
        """Update SAX item state for calculated values.

        Args:
            item: SAXItem instance or item name
            value: New value to set

        Security: Input validation for item existence
        """
        if isinstance(item, str):
            # Find SAXItem by name
            sax_items = self.sax_data.get_sax_items_for_battery(self.battery_id)
            item_obj = next((i for i in sax_items if i.name == item), None)
            if item_obj is None:
                _LOGGER.warning("SAXItem %s not found", item)
                return
            item = item_obj

        # Update the value in coordinator data
        if hasattr(item, "name"):
            if not self.data:
                self.data = {}
            self.data[item.name] = value
            _LOGGER.debug("Updated SAX item %s with value %s", item.name, value)

    async def async_write_pilot_control_value(
        self,
        power_item: ModbusItem,
        power_factor_item: ModbusItem,
        power: float,
        power_factor: int,
    ) -> bool:
        """Write pilot control values with atomic Modbus operation.

        Args:
            power_item: Power register ModbusItem (for reference only)
            power_factor_item: Power factor register ModbusItem (for reference only)
            power: Power value to write
            power_factor: Power factor value to write

        Returns:
            bool: True if atomic write successful

        Security: Input validation and atomic write operations
        Performance: Single Modbus write for both registers
        """
        try:
            # Security: Input validation
            if not all(
                isinstance(item, ModbusItem) for item in [power_item, power_factor_item]
            ):
                _LOGGER.error("Expected ModbusItem instances for pilot control")
                return False

            if not isinstance(power, (int, float)) or not isinstance(
                power_factor, (int, float)
            ):
                _LOGGER.error("Expected numeric values for pilot control")  # type: ignore[unreachable]
                return False

            # Performance: Use atomic write_nominal_power for both registers
            success = await self.modbus_api.write_nominal_power(
                value=power, power_factor=int(power_factor), modbus_item=power_item
            )

            if success:
                _LOGGER.debug(
                    "Successfully wrote pilot control values atomically: power=%s, factor=%s",
                    power,
                    power_factor,
                )
            else:
                _LOGGER.error("Failed to write pilot control values atomically")

            return success  # noqa: TRY300

        except (ModbusException, OSError, TimeoutError) as err:
            _LOGGER.error("Modbus error in pilot control write operation: %s", err)
            return False
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Unexpected error in pilot control write operation: %s", err)
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
            calculated_values: dict[str, Any] = {}
            for sax_item in sax_items:
                if isinstance(sax_item, SAXItem):
                    try:
                        # Security: Validate coordinators are available
                        if (
                            not hasattr(sax_item, "coordinators")
                            or not sax_item.coordinators
                        ):
                            sax_item.set_coordinators(self.sax_data.coordinators)

                        # Calculate value
                        calculated_value = sax_item.calculate_value(
                            self.sax_data.coordinators
                        )
                        calculated_values[sax_item.name] = calculated_value

                    except (ValueError, TypeError, ZeroDivisionError) as calc_err:
                        _LOGGER.warning(
                            "Calculation error for %s: %s", sax_item.name, calc_err
                        )
                        calculated_values[sax_item.name] = None

            # Performance: Single dictionary update
            data.update(calculated_values)

            _LOGGER.debug(
                "Updated %d calculated values for %s",
                len(calculated_values),
                self.battery_id,
            )

        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error updating calculated values: %s", err)
