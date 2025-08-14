"""Number platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type
from .enums import TypeConstants
from .items import ModbusItem
from .models import SAXBatteryData
from .utils import create_entity_unique_id, determine_entity_category


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery number entities."""
    # Get data from hass.data
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators: dict[str, SAXBatteryCoordinator] = data["coordinators"]
    sax_data: SAXBatteryData = data["sax_data"]

    entities: list[SAXBatteryNumber] = []

    # Create numbers for each battery
    for battery_id, coordinator in coordinators.items():
        # Regular writable number items
        number_items = filter_items_by_type(
            sax_data.get_modbus_items_for_battery(battery_id),
            TypeConstants.NUMBER,
            config_entry,
            battery_id,
        )

        entities.extend(
            SAXBatteryNumber(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
            for index, modbus_item in enumerate(number_items)
        )

        # Read-only number items
        number_ro_items = filter_items_by_type(
            sax_data.get_modbus_items_for_battery(battery_id),
            TypeConstants.NUMBER_RO,
            config_entry,
            battery_id,
        )

        entities.extend(
            SAXBatteryNumber(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index + len(number_items),  # Offset index
                read_only=True,
            )
            for index, modbus_item in enumerate(number_ro_items)
        )

    async_add_entities(entities)


class SAXBatteryNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """Implementation of a SAX Battery number entity."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
        index: int,
        read_only: bool = False,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id
        self._read_only = read_only
        self._attr_unique_id = create_entity_unique_id(battery_id, modbus_item, index)
        self._attr_entity_category = determine_entity_category(modbus_item)

        # Apply entity description from ModbusItem if available
        if modbus_item.entitydescription and isinstance(
            modbus_item.entitydescription, NumberEntityDescription
        ):
            # Copy attributes from the entity description
            desc = modbus_item.entitydescription
            if desc.native_min_value is not None and isinstance(
                desc.native_min_value, (int, float)
            ):
                self._attr_native_min_value = float(desc.native_min_value)
            if desc.native_max_value is not None and isinstance(
                desc.native_max_value, (int, float)
            ):
                self._attr_native_max_value = float(desc.native_max_value)
            if desc.native_step is not None and isinstance(
                desc.native_step, (int, float)
            ):
                self._attr_native_step = float(desc.native_step)

            self._attr_native_unit_of_measurement = desc.native_unit_of_measurement
            self._attr_device_class = desc.device_class
            self._attr_mode = desc.mode or NumberMode.AUTO
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

        # Set read-only mode for NUMBER_RO items
        if self._read_only:
            self._attr_mode = NumberMode.BOX

        # Set device info
        self._attr_device_info = coordinator.sax_data.get_device_info(battery_id)
        self._attr_has_entity_name = True

    @property
    def name(self) -> str:
        """Return the name of the number entity."""
        # Extract base name from entity description, remove "Sax" prefix if present
        if (
            self._modbus_item.entitydescription
            and hasattr(self._modbus_item.entitydescription, "name")
            and isinstance(self._modbus_item.entitydescription.name, str)
        ):
            entity_name = self._modbus_item.entitydescription.name
            entity_name = entity_name.removeprefix("Sax ")  # Remove "Sax " prefix
            result_name = entity_name
        else:
            result_name = self._modbus_item.name.replace("_", " ").title()

        battery_name = self._battery_id.replace("_", " ").title()
        return f"Sax {battery_name} {result_name}"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.coordinator.data:
            return None

        raw_value = self.coordinator.data.get(self._modbus_item.name)
        if raw_value is None:
            return None

        # Convert to float if needed
        try:
            return float(raw_value)
        except (ValueError, TypeError):
            return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._modbus_item.name in self.coordinator.data
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        raw_value = (
            self.coordinator.data.get(self._modbus_item.name)
            if self.coordinator.data
            else None
        )

        return {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "raw_value": raw_value,
            "read_only": self._read_only,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        if self._read_only:
            msg = f"Cannot set value on read-only number entity {self.name}"
            raise HomeAssistantError(msg)

        success = await self.coordinator.async_write_number_value(
            self._modbus_item, value
        )

        if not success:
            msg = f"Failed to set value {value} for {self.name}"
            raise HomeAssistantError(msg)

        # Request coordinator update after write
        await self.coordinator.async_request_refresh()
