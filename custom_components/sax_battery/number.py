"""Number platform for SAX Battery integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BATTERY_COUNT,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
)
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type
from .enums import TypeConstants
from .items import ModbusItem
from .utils import (
    calculate_system_max_charge,
    calculate_system_max_discharge,
    determine_entity_category,
    format_battery_display_name,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery number entities."""
    # Get data from hass.data
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    # Get battery count from config
    battery_count = config_entry.data.get(CONF_BATTERY_COUNT, 1)

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
                battery_count=battery_count,
            )
            for modbus_item in number_items
        )

        # Read-only number items (NUMBER_WO is write-only, NUMBER_RO is read-only)
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
                read_only=True,
                battery_count=battery_count,
            )
            for modbus_item in number_ro_items
        )

    async_add_entities(entities)


class SAXBatteryNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """Implementation of a SAX Battery number entity."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
        battery_count: int = 1,
        read_only: bool = False,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id
        self._battery_count = battery_count
        self._read_only = read_only

        # Generate unique ID using class name pattern
        item_name = self._modbus_item.name.removeprefix("sax_")
        self._attr_unique_id = f"sax_{self._battery_id}_{item_name}"

        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment]

        # Set name using entity description or fallback
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            base_name = self.entity_description.name
            # Remove "Sax " prefix if it exists
            base_name = base_name.removeprefix("Sax ")
        else:
            # Fallback name generation
            base_name = (
                self._modbus_item.name.removeprefix("sax_").replace("_", " ").title()
            )

        # Format battery display name
        battery_display = format_battery_display_name(self._battery_id)
        self._attr_name = f"Sax {battery_display} {base_name}"

        # Set default properties
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 1.0
        self._attr_native_unit_of_measurement = None
        self._attr_mode = NumberMode.AUTO
        self._attr_entity_category = determine_entity_category(modbus_item)

        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment] # fmt: skip

        if isinstance(self.entity_description.name, str):
            item_name = self.entity_description.name[4:]  # eliminate 'Sax ' # type: ignore[index] # fmt: skip

        # Apply dynamic limits based on battery count for charge/discharge entities
        self._apply_dynamic_limits()

        # Set read-only mode for NUMBER_RO items
        if self._read_only:
            self._attr_mode = NumberMode.BOX

    def _apply_dynamic_limits(self) -> None:
        """Apply dynamic limits based on battery count for specific entities."""
        # Only update max limits for charge and discharge entities
        if self._modbus_item.name == SAX_MAX_CHARGE:
            try:
                max_charge = calculate_system_max_charge(self._battery_count)
                self._attr_native_max_value = float(max_charge)
            except ValueError:
                # Keep original limit if battery count is invalid
                pass
        elif self._modbus_item.name == SAX_MAX_DISCHARGE:
            try:
                max_discharge = calculate_system_max_discharge(self._battery_count)
                self._attr_native_max_value = float(max_discharge)
            except ValueError:
                # Keep original limit if battery count is invalid
                pass

    @property
    def device_info(self) -> Any:
        """Return device info."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)

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

        attributes = {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "raw_value": raw_value,
            "read_only": self._read_only,
            "battery_count": self._battery_count,
        }

        # Add dynamic limit information for charge/discharge entities
        if self._modbus_item.name in [SAX_MAX_CHARGE, SAX_MAX_DISCHARGE]:
            attributes["dynamic_limit_applied"] = True
            if self._modbus_item.name == SAX_MAX_CHARGE:
                attributes["per_battery_limit_charge"] = LIMIT_MAX_CHARGE_PER_BATTERY
            elif self._modbus_item.name == SAX_MAX_DISCHARGE:
                attributes["per_battery_limit_discharge"] = (
                    LIMIT_MAX_DISCHARGE_PER_BATTERY
                )

        return attributes

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
