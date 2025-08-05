"""Sensor platform for SAX Battery integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import TypeConstants
from .items import ApiItem, SAXItem
from .models import SAXBatteryData
from .utils import create_entity_unique_id, determine_entity_category


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery sensor entities."""
    sax_data: SAXBatteryData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SAXBatterySensor | SAXBatteryCalcSensor] = []

    for battery_id, coordinator in sax_data.coordinators.items():
        # Regular sensors from Modbus/API items
        sensor_items = filter_items_by_type(
            coordinator.api_items,
            TypeConstants.SENSOR,
            config_entry,
            battery_id,
        )

        entities.extend(
            SAXBatterySensor(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
            for index, modbus_item in enumerate(sensor_items)
        )

        # Calculated sensors from SAX items - use separate filter for SAXItem
        calc_sensor_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery(battery_id),  # Get SAXItem objects
            TypeConstants.SENSOR_CALC,
            config_entry,
            battery_id,
        )

        entities.extend(
            SAXBatteryCalcSensor(
                coordinator=coordinator,
                battery_id=battery_id,
                sax_item=sax_item,  # Now correctly typed as SAXItem
                index=index,
            )
            for index, sax_item in enumerate(calc_sensor_items)
        )

    async_add_entities(entities)


@dataclass(frozen=True, kw_only=True)
class SAXBatterySensorEntityDescription(SensorEntityDescription):
    """Describes SAX Battery sensor entity."""

    value_fn: Callable[[ApiItem], Any] | None = None


class SAXBatterySensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """Implementation of a SAX Battery sensor for ModbusItem/ApiItem data."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ApiItem,
        index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id
        self._attr_unique_id = create_entity_unique_id(battery_id, modbus_item, index)
        self._attr_entity_category = determine_entity_category(modbus_item)
        self._attr_has_entity_name = True

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._modbus_item.name.replace("_", " ").title()

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None

        raw_value = self.coordinator.data.get(self._modbus_item.name)
        if raw_value is None:
            return None

        # Apply the item's conversion logic (including divider)
        return self._modbus_item.convert_raw_value(raw_value)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return getattr(self._modbus_item, "unit", None)

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class of the sensor."""
        return getattr(self._modbus_item, "device_class", None)

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class of the sensor."""
        return getattr(self._modbus_item, "state_class", None)

    @property
    def icon(self) -> str | None:
        """Return the icon of the sensor."""
        return getattr(self._modbus_item, "icon", None)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "sensor_type": "regular",
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)


class SAXBatteryCalcSensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """SAX Battery calculated sensor - specifically for SAXItem calculations."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        sax_item: SAXItem,  # Specifically SAXItem for calculated sensors
        index: int,
    ) -> None:
        """Initialize calculated sensor."""
        super().__init__(coordinator)
        self._battery_id = battery_id
        self._sax_item = sax_item
        self._attr_unique_id = create_entity_unique_id(battery_id, sax_item, index)
        self._attr_entity_category = determine_entity_category(sax_item)
        self._attr_has_entity_name = True

    @property
    def name(self) -> str:
        """Return sensor name."""
        return self._sax_item.name.replace("_", " ").title()

    @property
    def native_value(self) -> float | None:
        """Return the calculated native value."""
        if not self.coordinator.data:
            return None

        # Get the calculated value from the SAXItem - ensure proper type conversion
        state = self._sax_item.state
        if state is None:
            return None

        # Convert to float if possible, otherwise return None
        try:
            return float(state) if state is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return getattr(self._sax_item, "unit", None)

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class of the sensor."""
        return getattr(self._sax_item, "device_class", None)

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class of the sensor."""
        return getattr(self._sax_item, "state_class", None)

    @property
    def icon(self) -> str | None:
        """Return the icon of the sensor."""
        return getattr(self._sax_item, "icon", None)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "battery_id": self._battery_id,
            "calculation": getattr(self._sax_item, "calculation", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "sensor_type": "calculated",
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)
