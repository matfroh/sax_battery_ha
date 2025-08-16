"""Sensor platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import TypeConstants
from .items import ModbusItem, SAXItem
from .models import SAXBatteryData
from .utils import create_entity_unique_id, determine_entity_category


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery sensor platform."""
    # Get data from hass.data
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators: dict[str, SAXBatteryCoordinator] = data["coordinators"]
    sax_data: SAXBatteryData = data["sax_data"]

    entities: list[SAXBatterySensor | SAXBatteryCalcSensor] = []

    # Create sensors for each battery
    for battery_id, coordinator in coordinators.items():
        # Get sensor items for this battery
        sensor_items = filter_items_by_type(
            sax_data.get_modbus_items_for_battery(battery_id),
            TypeConstants.SENSOR,
            config_entry,
            battery_id,
        )

        # Create sensor entities from ModbusItems
        entities.extend(
            SAXBatterySensor(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
            for index, modbus_item in enumerate(sensor_items)
        )

        # Get calculated sensor items (SAXItems)
        calc_sensor_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery(battery_id),
            TypeConstants.SENSOR,
            config_entry,
            battery_id,
        )

        # Create calculated sensor entities from SAXItems
        entities.extend(
            SAXBatteryCalcSensor(
                coordinator=coordinator,
                battery_id=battery_id,
                sax_item=sax_item,
                index=index + len(sensor_items),  # Offset index
            )
            for index, sax_item in enumerate(calc_sensor_items)
        )

    async_add_entities(entities)


class SAXBatterySensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """Implementation of a SAX Battery sensor for ModbusItem data."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
        index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id
        self._attr_unique_id = create_entity_unique_id(battery_id, modbus_item, index)
        self._attr_entity_category = determine_entity_category(modbus_item)

        # Apply entity description from ModbusItem if available
        if modbus_item.entitydescription and isinstance(
            modbus_item.entitydescription, SensorEntityDescription
        ):
            # Copy attributes from the entity description
            desc = modbus_item.entitydescription
            self._attr_device_class = desc.device_class
            self._attr_native_unit_of_measurement = desc.native_unit_of_measurement
            self._attr_state_class = desc.state_class
            self._attr_suggested_display_precision = desc.suggested_display_precision
            if desc.entity_category:
                self._attr_entity_category = desc.entity_category
            if desc.icon:
                self._attr_icon = desc.icon
            if hasattr(desc, "name") and isinstance(desc.name, str):
                self._attr_name = desc.name
            if (
                hasattr(desc, "translation_key")
                and desc.translation_key
                and desc.translation_key != ""
            ):
                if isinstance(desc.translation_key, str):
                    self._attr_translation_key = desc.translation_key

        # Set device info
        self._attr_device_info = coordinator.sax_data.get_device_info(battery_id)
        self._attr_has_entity_name = True

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        # Extract base name from entity description, remove "Sax" prefix if present
        if (
            self._modbus_item.entitydescription
            and hasattr(self._modbus_item.entitydescription, "name")
            and isinstance(self._modbus_item.entitydescription.name, str)
        ):
            entity_name = self._modbus_item.entitydescription.name
            entity_name = entity_name.removeprefix("Sax ")  # Remove "Sax " prefix
            base_name = entity_name
        else:
            base_name = self._modbus_item.name.replace("_", " ").title()

        battery_name = self._battery_id.replace("_", " ").title()
        return f"Sax {battery_name} {base_name}"

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None

        value = self.coordinator.data.get(self._modbus_item.name)
        if value is None:
            return None

        return value

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


class SAXBatteryCalcSensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """SAX Battery calculated sensor - specifically for SAXItem calculations."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        sax_item: SAXItem,
        index: int,
    ) -> None:
        """Initialize calculated sensor."""
        super().__init__(coordinator)
        self._battery_id = battery_id
        self._sax_item = sax_item
        self._attr_unique_id = create_entity_unique_id(battery_id, sax_item, index)
        self._attr_entity_category = determine_entity_category(sax_item)

        # Apply entity description from SAXItem if available
        if sax_item.entitydescription and isinstance(
            sax_item.entitydescription, SensorEntityDescription
        ):
            # Copy attributes from the entity description
            desc = sax_item.entitydescription
            self._attr_device_class = desc.device_class
            self._attr_native_unit_of_measurement = desc.native_unit_of_measurement
            self._attr_state_class = desc.state_class
            self._attr_suggested_display_precision = desc.suggested_display_precision
            if desc.entity_category:
                self._attr_entity_category = desc.entity_category
            if desc.icon:
                self._attr_icon = desc.icon
            if hasattr(desc, "name") and isinstance(desc.name, str):
                self._attr_name = desc.name
            if (
                hasattr(desc, "translation_key")
                and desc.translation_key
                and desc.translation_key != ""
            ):
                if isinstance(desc.translation_key, str):
                    self._attr_translation_key = desc.translation_key

        # Set device info
        self._attr_device_info = coordinator.sax_data.get_device_info(battery_id)
        self._attr_has_entity_name = True

    @property
    def name(self) -> str:
        """Return sensor name."""
        # Extract base name from entity description, remove "Sax" prefix if present
        if (
            self._sax_item.entitydescription
            and hasattr(self._sax_item.entitydescription, "name")
            and isinstance(self._sax_item.entitydescription.name, str)
        ):
            entity_name = self._sax_item.entitydescription.name
            entity_name = entity_name.removeprefix("Sax ")  # Remove "Sax " prefix
            final_name = entity_name
        else:
            final_name = self._sax_item.name.replace("_", " ").title()

        battery_name = self._battery_id.replace("_", " ").title()
        return f"Sax {battery_name} {final_name}"

    @property
    def native_value(self) -> float | None:
        """Return the calculated native value."""
        if not self.coordinator.data:
            return None

        # Get the calculated value from coordinator data
        return self.coordinator.data.get(self._sax_item.name)

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
