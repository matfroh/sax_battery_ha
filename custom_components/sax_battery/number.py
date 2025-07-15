"""Number platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .entity_helpers import build_entity_list
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
    sax_data: SAXBatteryData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[NumberEntity] = []

    # Create number entities for each battery
    for battery_id, coordinator in sax_data.coordinators.items():
        api_items = sax_data.get_modbus_items_for_battery(battery_id)

        await build_entity_list(
            entries=entities,
            config_entry=config_entry,
            api_items=api_items,
            item_type=TypeConstants.NUMBER,
            coordinator=coordinator,
            battery_id=battery_id,
        )

    async_add_entities(entities)


class SAXBatteryNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """SAX Battery number entity using coordinator for Modbus operations."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
        index: int,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._battery_id = battery_id
        self._modbus_item = modbus_item
        self._index = index

        # Entity configuration
        self._attr_unique_id = create_entity_unique_id(battery_id, modbus_item, index)
        self._attr_name = (
            f"{battery_id.title()} {modbus_item.name.replace('_', ' ').title()}"
        )
        self._attr_entity_category = determine_entity_category(modbus_item)

        # Number configuration from ModbusItem
        self._attr_native_unit_of_measurement = getattr(modbus_item, "unit", None)

        # Set min/max values based on description or defaults
        if hasattr(modbus_item, "description") and modbus_item.entitydescription:
            self._attr_native_min_value = getattr(
                modbus_item.entitydescription, "native_min_value", 0
            )
            self._attr_native_max_value = getattr(
                modbus_item.entitydescription, "native_max_value", 100
            )
            self._attr_native_step = getattr(
                modbus_item.entitydescription, "native_step", 1
            )
        else:
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100
            self._attr_native_step = 1

        # Device info
        self._attr_device_info = coordinator.sax_data.get_device_info(battery_id)

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        success = await self.coordinator.async_write_number_value(
            self._modbus_item, value
        )

        if not success:
            raise HomeAssistantError(
                f"Failed to set {self._modbus_item.name} to {value}"
            )

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.coordinator.last_update_success:
            return None

        value = self.coordinator.data.get(self._modbus_item.name)
        if value is None:
            return None

        # Apply divider if specified
        divider = getattr(self._modbus_item, "divider", 1)
        if divider and divider != 1:
            return float(value) / divider

        return float(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if not self.coordinator.last_update_success:
            return None

        return {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_updated": self.coordinator.last_update_success_time,
        }
