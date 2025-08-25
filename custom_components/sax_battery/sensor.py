"""SAX Battery sensor platform."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SAX_AC_POWER_TOTAL,
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CONSUMED,
    SAX_CUMULATIVE_ENERGY_PRODUCED,
    SAX_ENERGY_CONSUMED,
    SAX_ENERGY_PRODUCED,
    SAX_SOC,
)
from .coordinator import SAXBatteryCoordinator
from .enums import TypeConstants
from .items import ModbusItem, SAXItem
from .utils import format_battery_display_name

_LOGGER = logging.getLogger(__name__)


# Calculation functions for SAXItem values
def calculate_combined_soc(
    coordinators: dict[str, SAXBatteryCoordinator],
) -> float | None:
    """Calculate combined SOC from all battery coordinators."""
    try:
        soc_values = []
        for coordinator in coordinators.values():
            if coordinator.data and SAX_SOC in coordinator.data:
                soc_value = coordinator.data[SAX_SOC]
                if soc_value is not None:
                    soc_values.append(float(soc_value))

        if not soc_values:
            return None

        # Return average SOC
        return sum(soc_values) / len(soc_values)
    except (ValueError, TypeError, ZeroDivisionError) as err:
        _LOGGER.debug("Error calculating combined SOC: %s", err)
        return None


def calculate_cumulative_energy_produced(
    coordinators: dict[str, SAXBatteryCoordinator],
) -> float | None:
    """Calculate cumulative energy produced from all battery coordinators."""
    try:
        total_energy = 0.0
        has_data = False

        for coordinator in coordinators.values():
            if coordinator.data and SAX_ENERGY_PRODUCED in coordinator.data:
                energy_value = coordinator.data[SAX_ENERGY_PRODUCED]
                if energy_value is not None:
                    total_energy += float(energy_value)
                    has_data = True

        return total_energy if has_data else None  # noqa: TRY300
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Error calculating cumulative energy produced: %s", err)
        return None


def calculate_cumulative_energy_consumed(
    coordinators: dict[str, SAXBatteryCoordinator],
) -> float | None:
    """Calculate cumulative energy consumed from all battery coordinators."""
    try:
        total_energy = 0.0
        has_data = False

        for coordinator in coordinators.values():
            if coordinator.data and SAX_ENERGY_CONSUMED in coordinator.data:
                energy_value = coordinator.data[SAX_ENERGY_CONSUMED]
                if energy_value is not None:
                    total_energy += float(energy_value)
                    has_data = True

        return total_energy if has_data else None  # noqa: TRY300
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Error calculating cumulative energy consumed: %s", err)
        return None


def get_ac_power_total(coordinators: dict[str, SAXBatteryCoordinator]) -> float | None:
    """Get AC power total from master battery coordinator."""
    try:
        # Find master battery coordinator (should be the first one that has AC power data)
        for coordinator in coordinators.values():
            if coordinator.data and SAX_AC_POWER_TOTAL in coordinator.data:
                power_value = coordinator.data[SAX_AC_POWER_TOTAL]
                if power_value is not None:
                    return float(power_value)
        return None  # noqa: TRY300
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Error getting AC power total: %s", err)
        return None


# Mapping of SAXItem names to their calculation functions
CALCULATION_FUNCTIONS: dict[
    str, Callable[[dict[str, SAXBatteryCoordinator]], float | None]
] = {
    SAX_COMBINED_SOC: calculate_combined_soc,
    SAX_CUMULATIVE_ENERGY_PRODUCED: calculate_cumulative_energy_produced,
    SAX_CUMULATIVE_ENERGY_CONSUMED: calculate_cumulative_energy_consumed,
    SAX_AC_POWER_TOTAL: get_ac_power_total,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery sensor platform."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    entities: list[SensorEntity] = []

    # Create sensor entities for each battery
    for battery_id, coordinator in coordinators.items():
        if not isinstance(coordinator, SAXBatteryCoordinator):
            continue

        # Add modbus sensor items using extend
        modbus_items = sax_data.get_modbus_items_for_battery(battery_id)
        entities.extend(
            SAXBatteryModbusSensor(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=item,
            )
            for item in modbus_items
            if item.mtype == TypeConstants.SENSOR
        )

        # Add SAX sensor items (calculated sensors) using extend
        sax_items = sax_data.get_sax_items_for_battery(battery_id)
        entities.extend(
            SAXBatteryCalcSensor(
                coordinator=coordinator,
                battery_id=battery_id,
                sax_item=sax_item,
                coordinators=coordinators,
            )
            for sax_item in sax_items
            if sax_item.mtype == TypeConstants.SENSOR_CALC
        )

    if entities:
        async_add_entities(entities, update_before_add=True)


class SAXBatteryModbusSensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """SAX Battery modbus sensor entity."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
    ) -> None:
        """Initialize SAX Battery modbus sensor entity."""
        super().__init__(coordinator)

        self._battery_id = battery_id
        self._modbus_item = modbus_item

        # Generate unique ID using class name pattern
        item_name = self._modbus_item.name.removeprefix("sax_")
        self._attr_unique_id = f"sax_{self._battery_id}_{item_name}"

        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment] # fmt: skip

        if isinstance(self.entity_description.name, str):
            item_name = self.entity_description.name[4:]  # eliminate 'Sax ' # type: ignore[index] # fmt: skip

        self.name = f"Sax {format_battery_display_name(self._battery_id)} {item_name}"

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get(self._modbus_item.name)

    @property
    def state_class(self) -> str | None:
        """Return state class."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "state_class")
        ):
            return self.entity_description.state_class
        return None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return device class."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "device_class")
        ):
            return self.entity_description.device_class
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "native_unit_of_measurement")
        ):
            return self.entity_description.native_unit_of_measurement
        return None

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return entity category."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "entity_category")
        ):
            return self.entity_description.entity_category
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        return {
            "battery_id": self._battery_id,
            "modbus_address": self._modbus_item.address,
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
        }

    async def async_update(self) -> None:
        """Update the sensor by recalculating combined values."""
        # Force coordinator update first
        await self.coordinator.async_request_refresh()


class SAXBatteryCalcSensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """SAX Battery calculated sensor entity."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        sax_item: SAXItem,
        coordinators: dict[str, SAXBatteryCoordinator],
    ) -> None:
        """Initialize SAX Battery calculated sensor entity."""
        super().__init__(coordinator)

        self._battery_id = battery_id
        self._sax_item = sax_item
        self._coordinators = coordinators

        # Generate unique ID using class name pattern (without "(Calculated)" suffix)
        item_name = self._sax_item.name.removeprefix("sax_")
        self._attr_unique_id = f"sax_{self._battery_id}_{item_name}"

        # Set entity description from sax item if available
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment] # fmt: skip
        if isinstance(self.entity_description.name, str):
            item_name = self.entity_description.name[4:]  # eliminate 'Sax ' # type: ignore[index] # fmt: skip

        self.name = f"Sax {format_battery_display_name(self._battery_id)} {item_name}"

        # Call post-init to add "(Calculated)" suffix to display name
        self.__post_init__()

    def __post_init__(self) -> None:
        """Initialize compiled calculation after object creation."""
        if self._sax_item.mtype == TypeConstants.SENSOR_CALC and isinstance(self.name, str):  # fmt: skip
            if not self.name.endswith("(Calculated)"):
                self.name = f"{self.name} (Calculated)"

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)

    @property
    def native_value(self) -> Any:
        """Return the calculated state of the sensor."""
        # Use the calculation function if available
        calculation_func = CALCULATION_FUNCTIONS.get(self._sax_item.name)
        if calculation_func:
            try:
                return calculation_func(self._coordinators)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Error calculating value for %s: %s", self._sax_item.name, err
                )
                return None

        # Fallback to coordinator data if no calculation function
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get(self._sax_item.name)

    @property
    def state_class(self) -> str | None:
        """Return state class."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "state_class")
        ):
            return self.entity_description.state_class
        return None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return device class."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "device_class")
        ):
            return self.entity_description.device_class
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "native_unit_of_measurement")
        ):
            return self.entity_description.native_unit_of_measurement
        return None

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return entity category."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "entity_category")
        ):
            return self.entity_description.entity_category
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        return {
            "battery_id": self._battery_id,
            "calculation_type": "function_based",
            "calculation_function": self._sax_item.name,
            "battery_count": len(self._coordinators),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
        }
