"""SAX Battery sensor platform."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import RestoreSensor, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ATTRIBUTION,
    ATTRIBUTION,
    BATTERY_IDS,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    DOMAIN,
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CONSUMED,
    SAX_CUMULATIVE_ENERGY_PRODUCED,
    SAX_SMARTMETER_ENERGY_CONSUMED,
    SAX_SMARTMETER_ENERGY_PRODUCED,
    SAX_SOC,
)
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem, SAXItem

_LOGGER = logging.getLogger(__name__)

# Coordinator-based sensors don't need update serialization
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery sensor platform with multi-battery support."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    entities: list[SensorEntity] = []

    # Create sensors for each battery using new constants
    for battery_id, coordinator in coordinators.items():
        # Validate battery_id is in allowed list
        if battery_id not in BATTERY_IDS:
            _LOGGER.warning("Invalid battery ID %s, skipping", battery_id)
            continue

        # Get battery-specific configuration
        battery_config = coordinator.battery_config
        is_master = battery_config.get(CONF_BATTERY_IS_MASTER, False)
        phase = battery_config.get(CONF_BATTERY_PHASE, "L1")

        _LOGGER.debug(
            "Setting up sensors for %s battery %s (%s)",
            "master" if is_master else "slave",
            battery_id,
            phase,
        )

        # Filter sensor items for this battery
        sensor_items = filter_items_by_type(
            sax_data.get_modbus_items_for_battery(battery_id),
            TypeConstants.SENSOR,
            config_entry,
            battery_id,
        )

        for modbus_item in sensor_items:
            if isinstance(modbus_item, ModbusItem):
                entities.append(  # noqa: PERF401
                    SAXBatteryModbusSensor(
                        coordinator=coordinator,
                        battery_id=battery_id,
                        modbus_item=modbus_item,
                    )
                )

        _LOGGER.info(
            "Added %d modbus sensor entities for %s", len(sensor_items), battery_id
        )

    # Create system-wide calculated sensors only once (using master battery coordinator)
    # Find master coordinator - check both the coordinator's battery_config AND sax_data
    master_coordinator = None
    for battery_id, coordinator in coordinators.items():
        # Check coordinator's battery_config first
        is_master = coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False)

        # If not found in coordinator, check sax_data as fallback
        if not is_master and battery_id in sax_data.batteries:
            battery_model = sax_data.batteries[battery_id]
            is_master = battery_model.is_master

        if is_master:
            master_coordinator = coordinator
            _LOGGER.debug(
                "Found master battery coordinator: %s (is_master=%s)",
                battery_id,
                is_master,
            )
            break

    if master_coordinator:
        # Get calculated sensor items
        sax_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery(
                sax_data.master_battery_id or "battery_a"
            ),
            TypeConstants.SENSOR,
        )

        # Create calculated sensors
        for sax_item in sax_items:
            sax_item.set_coordinators(coordinators)
            entities.append(
                SAXBatteryCalculatedSensor(
                    master_coordinator,
                    sax_item,
                    coordinators,
                )
            )

        _LOGGER.debug(
            "Created %d calculated sensors using master coordinator", len(sax_items)
        )
    else:
        _LOGGER.warning(
            "No master battery found for cumulative energy calculation. "
            "Available batteries: %s, battery configs: %s",
            list(coordinators.keys()),
            {
                bid: coord.battery_config.get(CONF_BATTERY_IS_MASTER, "not set")
                for bid, coord in coordinators.items()
            },
        )

    if entities:
        async_add_entities(entities)
        _LOGGER.info(
            "Set up %d sensor entities across %d batteries",
            len(entities),
            len(coordinators),
        )


class SAXBatteryModbusSensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """Implementation of a SAX Battery modbus sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
    ) -> None:
        """Initialize the modbus sensor."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id

        # Generate unique ID using class name pattern
        item_name: str = self._modbus_item.name.removeprefix("sax_")

        if item_name.endswith("_sm"):
            self._attr_unique_id = f"sax_{item_name}"
        else:
            self._attr_unique_id = f"sax_{self._battery_id}_{item_name}"

        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment]

        # Set entity registry enabled state from ModbusItem
        self._attr_entity_registry_enabled_default = getattr(
            self._modbus_item, "enabled_by_default", True
        )

        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            # Remove "Sax " prefix from entity description name
            self.entity_description.key.removeprefix("Smartmeter ")  # beautify the key
            entity_name = str(self.entity_description.name)
            entity_name = entity_name.removeprefix("Sax ")
            self._attr_name = entity_name
        else:
            # Fallback: use clean item name without prefixes
            clean_name = item_name.replace("_", " ").title()
            self._attr_name = clean_name

        # Set device info
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            battery_id, self._modbus_item.device
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._modbus_item.name)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        return {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "raw_value": self.coordinator.data.get(self._modbus_item.name)
            if self.coordinator.data
            else None,
        }


class SAXBatteryCalculatedSensor(
    CoordinatorEntity[SAXBatteryCoordinator], RestoreSensor
):
    """SAX Battery calculated sensor entity with system-wide aggregation."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({ATTR_ATTRIBUTION})

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
        coordinators: dict[str, SAXBatteryCoordinator],
    ) -> None:
        """Initialize the calculated sensor entity.

        Args:
            coordinators: Dictionary of battery_id -> coordinator for aggregation
            sax_item: SAXItem containing entity configuration
            coordinator: Coordinator for the master battery

        Security:
            OWASP A05: Validates coordinators and item configuration
        """
        super().__init__(coordinator)
        self._sax_item = sax_item
        self._coordinators = coordinators

        # Cache the master coordinator during initialization
        self._master_coordinator = self._find_master_coordinator()

        # Set coordinators on the SAX item for calculations
        self._sax_item.set_coordinators(coordinators)

        # Generate unique ID using class name pattern (without "(Calculated)" suffix)
        clean_name: str = self._sax_item.name.removeprefix("sax_")
        self._attr_unique_id = clean_name

        # Set entity description from sax item if available
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment]

        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            self._attr_name = self.entity_description.name.removeprefix("Sax ")

        # State management for TOTAL_INCREASING sensors
        self._previous_reading_produced: float | None = None
        self._previous_reading_consumed: float | None = None
        self._cumulative_produced: float = 0.0
        self._cumulative_consumed: float = 0.0
        self._last_update_time: datetime | None = None

        # Set system device info
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            "cluster", DeviceConstants.SYS
        )

    @property
    def native_value(self) -> float | None:
        """Return the calculated sensor value.

        Performance:
            O(n) iteration over coordinators - efficient for small battery counts

        Security:
            OWASP A05: Validates coordinator data availability
        """
        if self._sax_item.name == SAX_COMBINED_SOC:
            return self._calculate_combined_soc()
        if self._sax_item.name == SAX_CUMULATIVE_ENERGY_PRODUCED:
            return self._calculate_cumulative_energy_produced()
        if self._sax_item.name == SAX_CUMULATIVE_ENERGY_CONSUMED:
            return self._calculate_cumulative_energy_consumed()

        _LOGGER.warning("Unknown calculation type for sensor: %s", self._sax_item.name)
        return None

    def _calculate_combined_soc(self) -> float | None:
        """Calculate combined SOC from all batteries."""
        total_soc = 0.0
        battery_count = 0

        for coordinator in self._coordinators.values():
            if not coordinator.data:
                continue

            soc_value = coordinator.data.get(SAX_SOC)
            if soc_value is not None:
                try:
                    total_soc += float(soc_value)
                    battery_count += 1
                except (ValueError, TypeError):
                    _LOGGER.debug(
                        "Invalid SOC value for battery %s: %s",
                        coordinator.battery_id,
                        soc_value,
                    )

        if battery_count == 0:
            return None

        return round(total_soc / battery_count, 1)

    def _calculate_cumulative_energy_produced(self) -> float:
        """Calculate cumulative energy produced from master battery smart meter.

        For TOTAL_INCREASING sensors, accumulates hourly deltas from the master
        battery's smart meter reading.

        Returns:
            Total accumulated energy in Wh (always >= 0.0)

        Performance:
            Only updates once per hour to match smart meter reading interval

        Security:
            OWASP A05: Validates coordinator data availability
        """
        current_time = datetime.now()

        # Only update once per hour (matches smart meter update interval)
        should_update = (
            self._last_update_time is None
            or (current_time - self._last_update_time).total_seconds() >= 3600
        )

        if not should_update:
            _LOGGER.debug(
                "Cumulative energy produced: Too soon to update (last: %s)",
                self._last_update_time,
            )
            return self._cumulative_produced

        # Use cached master coordinator
        if not self._master_coordinator:
            _LOGGER.warning("No master battery found for cumulative energy calculation")
            if isinstance(self._attr_native_value, float):
                return self._attr_native_value
            return 0.0

        if not self._master_coordinator.data:
            if isinstance(self._attr_native_value, float):
                return self._attr_native_value
            return 0.0

        # Get smart meter energy produced value
        current_reading = self._master_coordinator.data.get(
            SAX_SMARTMETER_ENERGY_PRODUCED
        )
        if current_reading is None:
            return self._cumulative_produced

        # Calculate and accumulate delta
        delta = self._calculate_energy_delta(
            current_reading,
            self._previous_reading_produced,
            "produced",
        )
        if delta > 0:
            old_cumulative = self._cumulative_produced
            self._cumulative_produced += delta

            _LOGGER.info(
                "Cumulative energy produced updated: +%s Wh (total: %s Wh, was: %s Wh)",
                delta,
                self._cumulative_produced,
                old_cumulative,
            )

        # Update state
        self._previous_reading_produced = current_reading
        self._last_update_time = current_time

        return self._cumulative_produced

    def _calculate_cumulative_energy_consumed(self) -> float:
        """Calculate cumulative energy consumed from master battery smart meter.

        For TOTAL_INCREASING sensors, accumulates hourly deltas from the master
        battery's smart meter reading.

        Returns:
            Total accumulated energy in Wh (always >= 0.0)

        Performance:
            Only updates once per hour to match smart meter reading interval

        Security:
            OWASP A05: Validates coordinator data availability
        """
        current_time = datetime.now()

        # Only update once per hour (matches smart meter update interval)
        should_update = (
            self._last_update_time is None
            or (current_time - self._last_update_time).total_seconds() >= 3600
        )

        if not should_update:
            _LOGGER.debug(
                "Cumulative energy consumed: Too soon to update (last: %s)",
                self._last_update_time,
            )
            return self._cumulative_consumed

        if not self._master_coordinator:
            _LOGGER.warning("No master battery found for cumulative energy calculation")
            if isinstance(self._attr_native_value, float):
                return self._attr_native_value
            return 0.0

        if not self._master_coordinator.data:
            if isinstance(self._attr_native_value, float):
                return self._attr_native_value
            return 0.0

        # Get smart meter energy consumed value
        current_reading = self._master_coordinator.data.get(
            SAX_SMARTMETER_ENERGY_CONSUMED
        )

        if current_reading is None:
            return self._cumulative_consumed

        # Calculate and accumulate delta
        delta = self._calculate_energy_delta(
            current_reading,
            self._previous_reading_consumed,
            "consumed",
        )

        if delta > 0:
            old_cumulative = self._cumulative_consumed
            self._cumulative_consumed += delta

            _LOGGER.info(
                "Cumulative energy consumed updated: +%s Wh (total: %s Wh, was: %s Wh)",
                delta,
                self._cumulative_consumed,
                old_cumulative,
            )

        # Update state
        self._previous_reading_consumed = current_reading
        self._last_update_time = current_time

        return self._cumulative_consumed

    def _find_master_coordinator(self) -> SAXBatteryCoordinator | None:
        """Find the master coordinator from available coordinators.

        Returns:
            Master coordinator if found, None otherwise
        """
        for coordinator in self._coordinators.values():
            # Check coordinator's battery_config for is_master flag
            if coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False):
                _LOGGER.debug("Found master coordinator: %s", coordinator.battery_id)
                return coordinator

        _LOGGER.debug(
            "No master coordinator found in %d coordinators", len(self._coordinators)
        )
        return None

    def _get_smart_meter_reading(
        self,
        coordinator: SAXBatteryCoordinator,
        key: str,
    ) -> float | None:
        """Get smart meter reading from coordinator data.

        Args:
            coordinator: Coordinator to read from
            key: Data key (SAX_SMARTMETER_ENERGY_PRODUCED or _CONSUMED)

        Returns:
            Reading value or None if unavailable/invalid
        """
        if not coordinator.data or key not in coordinator.data:
            _LOGGER.debug("No %s data in coordinator", key)
            return None

        reading = coordinator.data[key]

        if reading is None or reading <= 0:
            _LOGGER.debug("Invalid reading for %s: %s", key, reading)
            return None

        return float(reading)

    def _calculate_energy_delta(
        self,
        current_reading: float,
        previous_reading: float | None,
        energy_type: str,
    ) -> float:
        """Calculate energy delta with counter reset handling.

        Args:
            current_reading: Current meter reading
            previous_reading: Previous meter reading (None for first reading)
            energy_type: "produced" or "consumed" for logging

        Returns:
            Energy delta (>= 0), or 0 for first reading

        Security:
            OWASP A05: Handles counter resets safely
        """
        if previous_reading is None:
            # First reading - initialize but don't accumulate
            _LOGGER.info(
                "First energy %s reading: %s Wh",
                energy_type,
                current_reading,
            )
            return 0.0

        delta = current_reading - previous_reading

        # Handle counter reset (meter rolled over or was reset)
        if delta < 0:
            _LOGGER.warning(
                "Energy %s counter reset: %s -> %s (treating as new baseline)",
                energy_type,
                previous_reading,
                current_reading,
            )
            return current_reading  # Treat as new baseline

        return delta

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass.

        Security:
            OWASP A05: Validates restored state before use
        """
        await super().async_added_to_hass()

        # Restore previous state for TOTAL_INCREASING sensors
        if self._sax_item.name in (
            SAX_CUMULATIVE_ENERGY_PRODUCED,
            SAX_CUMULATIVE_ENERGY_CONSUMED,
        ):
            await self._restore_cumulative_state()

    async def _restore_cumulative_state(self) -> None:
        """Restore cumulative energy state from last known value.

        Security:
            OWASP A05: Validates restored state
        """
        last_state = await self.async_get_last_state()

        if not last_state or last_state.state in (
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ):
            _LOGGER.debug("No previous state to restore for %s", self._sax_item.name)
            return

        try:
            restored_value = float(last_state.state)

            if self._sax_item.name == SAX_CUMULATIVE_ENERGY_PRODUCED:
                self._cumulative_produced = restored_value
                _LOGGER.info(
                    "Restored cumulative energy produced: %s Wh", restored_value
                )
            elif self._sax_item.name == SAX_CUMULATIVE_ENERGY_CONSUMED:
                self._cumulative_consumed = restored_value
                _LOGGER.info(
                    "Restored cumulative energy consumed: %s Wh", restored_value
                )

        except (ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Failed to restore state for %s: %s",
                self._sax_item.name,
                exc,
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes.

        Returns:
            Dictionary of extra attributes for diagnostics
        """
        # Use dict[str, Any] to allow mixed value types
        attrs: dict[str, Any] = {ATTR_ATTRIBUTION: ATTRIBUTION}

        # Add diagnostic info for energy sensors
        if self._sax_item.name == SAX_CUMULATIVE_ENERGY_PRODUCED:
            attrs.update(
                {
                    "last_reading": self._previous_reading_produced,
                    "last_update": self._last_update_time.isoformat()
                    if self._last_update_time
                    else None,
                }
            )
        elif self._sax_item.name == SAX_CUMULATIVE_ENERGY_CONSUMED:
            attrs.update(
                {
                    "last_reading": self._previous_reading_consumed,
                    "last_update": self._last_update_time.isoformat()
                    if self._last_update_time
                    else None,
                }
            )

        return attrs
