"""Number platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type
from .enums import TypeConstants
from .items import ApiItem
from .models import SAXBatteryData
from .utils import create_entity_unique_id, determine_entity_category


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery number entities."""
    sax_data: SAXBatteryData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SAXBatteryNumber] = []

    for battery_id, coordinator in sax_data.coordinators.items():
        # Number entities (both read-write and read-only)
        number_items = filter_items_by_type(
            coordinator.api_items,
            TypeConstants.NUMBER,
            config_entry,
            battery_id,
        )

        number_ro_items = filter_items_by_type(
            coordinator.api_items,
            TypeConstants.NUMBER_RO,
            config_entry,
            battery_id,
        )

        # Combine both number types
        all_number_items = [*number_items, *number_ro_items]

        entities.extend(
            SAXBatteryNumber(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
            for index, modbus_item in enumerate(all_number_items)
        )

    async_add_entities(entities)


class SAXBatteryNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """Implementation of a SAX Battery number entity."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ApiItem,
        index: int,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id
        self._attr_unique_id = create_entity_unique_id(battery_id, modbus_item, index)
        self._attr_entity_category = determine_entity_category(modbus_item)
        self._attr_has_entity_name = True

    @property
    def name(self) -> str:
        """Return the name of the number entity."""
        return self._modbus_item.name.replace("_", " ").title()

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.coordinator.data:
            return None

        value = self.coordinator.data.get(self._modbus_item.name)
        if value is None:
            return None

        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        return getattr(self._modbus_item, "min_value", 0.0)

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        return getattr(self._modbus_item, "max_value", 100.0)

    @property
    def native_step(self) -> float:
        """Return the step value."""
        return getattr(self._modbus_item, "step", 1.0)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return getattr(self._modbus_item, "unit", None)

    @property
    def icon(self) -> str | None:
        """Return the icon of the number entity."""
        return getattr(self._modbus_item, "icon", None)

    @property
    def mode(self) -> NumberMode:
        """Return the mode of the number entity."""
        mode_str = getattr(self._modbus_item, "mode", "auto")
        match mode_str:
            case "box":
                return NumberMode.BOX
            case "slider":
                return NumberMode.SLIDER
            case _:
                return NumberMode.AUTO

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
        return {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "read_only": self._modbus_item.mtype == TypeConstants.NUMBER_RO,
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "min_value": self.native_min_value,
            "max_value": self.native_max_value,
            "step": self.native_step,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value of the number entity."""
        # Check if this is a read-only number
        if self._modbus_item.mtype == TypeConstants.NUMBER_RO:
            msg = f"Cannot set value for read-only number entity {self.name}"
            raise HomeAssistantError(msg)

        # Convert to appropriate type based on modbus item configuration
        try:
            if (
                hasattr(self._modbus_item, "value_type")
                and self._modbus_item.value_type == "int"
            ):
                converted_value = int(value)
                success = await self.coordinator.async_write_int_value(
                    self._modbus_item, converted_value
                )
            else:
                success = await self.coordinator.async_write_number_value(
                    self._modbus_item, value
                )

            if not success:
                msg = f"Failed to set value {value} for {self.name}"
                raise HomeAssistantError(msg)

        except (ValueError, TypeError) as err:
            msg = f"Invalid value {value} for {self.name}: {err}"
            raise HomeAssistantError(msg) from err
