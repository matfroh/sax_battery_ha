"""Switch platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up SAX Battery switch entities."""
    sax_data: SAXBatteryData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SAXBatterySwitch] = []

    for battery_id, coordinator in sax_data.coordinators.items():
        switch_items = filter_items_by_type(
            coordinator.api_items,
            TypeConstants.SWITCH,
            config_entry,
            battery_id,
        )

        entities.extend(
            SAXBatterySwitch(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
            for index, modbus_item in enumerate(switch_items)
        )

    async_add_entities(entities)


class SAXBatterySwitch(CoordinatorEntity[SAXBatteryCoordinator], SwitchEntity):
    """Implementation of a SAX Battery switch."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
        index: int,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id
        self._attr_unique_id = create_entity_unique_id(
            battery_id, modbus_item.name, index
        )
        self._attr_entity_category = determine_entity_category(modbus_item)
        self._attr_has_entity_name = True

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return self._modbus_item.name.replace("_", " ").title()

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        if not self.coordinator.data:
            return None

        value = self.coordinator.data.get(self._modbus_item.name)
        if value is None:
            return None

        # Convert various representations to boolean
        match value:
            case bool():
                return value
            case int() | float():
                return value != 0
            case str():
                return value.lower() in ("on", "true", "1", "yes")
            case _:
                return None

    @property
    def icon(self) -> str | None:
        """Return the icon of the switch."""
        return getattr(self._modbus_item, "icon", None)

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
        }

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        success = await self.coordinator.async_write_switch_value(
            self._modbus_item, True
        )

        if not success:
            msg = f"Failed to turn on {self.name}"
            raise HomeAssistantError(msg)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        success = await self.coordinator.async_write_switch_value(
            self._modbus_item, False
        )

        if not success:
            msg = f"Failed to turn off {self.name}"
            raise HomeAssistantError(msg)
