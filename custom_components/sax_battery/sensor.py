"""Sensor platform for SAX Battery integration."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAXBatteryCoordinator
from .entity_helpers import (
    build_entity_list,
    create_entity_unique_id,
    determine_entity_category,
)
from .enums import TypeConstants
from .items import ModbusItem
from .models import SAXBatteryData


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery sensor entities."""
    sax_data: SAXBatteryData = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SensorEntity] = []

    # Create sensor entities for each battery
    for battery_id, coordinator in sax_data.coordinators.items():
        api_items = sax_data.get_modbus_items_for_battery(battery_id)

        # Regular sensors
        await build_entity_list(
            entries=entities,
            config_entry=config_entry,
            api_items=api_items,
            item_type=TypeConstants.SENSOR,
            coordinator=coordinator,
            battery_id=battery_id,
        )

        # Read-only number sensors
        await build_entity_list(
            entries=entities,
            config_entry=config_entry,
            api_items=api_items,
            item_type=TypeConstants.NUMBER_RO,
            coordinator=coordinator,
            battery_id=battery_id,
        )

        # Calculated sensors
        await build_entity_list(
            entries=entities,
            config_entry=config_entry,
            api_items=api_items,
            item_type=TypeConstants.SENSOR_CALC,
            coordinator=coordinator,
            battery_id=battery_id,
        )

    async_add_entities(entities)


class SAXBatterySensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """SAX Battery sensor entity using coordinator for data."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
        index: int,
    ) -> None:
        """Initialize the sensor entity."""
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

        # Sensor configuration from ModbusItem
        self._attr_native_unit_of_measurement = getattr(modbus_item, "unit", None)
        self._attr_suggested_display_precision = getattr(modbus_item, "precision", None)

        # Use state class from modbus item description
        if hasattr(modbus_item, "description") and modbus_item.description:
            self._attr_state_class = getattr(
                modbus_item.description, "state_class", None
            )
        else:
            self._attr_state_class = None

        # Device info
        self._attr_device_info = coordinator.sax_data.get_device_info(battery_id)

    @property
    def native_value(self) -> StateType | date | datetime | Decimal | None:
        """Return the current value from coordinator data."""
        if not self.coordinator.last_update_success:
            return None

        value = self.coordinator.data.get(self._modbus_item.name)

        if value is None:
            return None

        # Apply divider if specified and convert to Decimal for precision
        divider = getattr(self._modbus_item, "divider", 1)
        if isinstance(value, (int, float)) and divider and divider != 1:
            return Decimal(str(value)) / Decimal(str(divider))

        # Convert numeric values to Decimal for consistency
        if isinstance(value, (int, float)):
            return Decimal(str(value))

        return str(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if not self.coordinator.last_update_success:
            return None

        attributes = {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_updated": self.coordinator.last_update_success_time,
        }

        # Add divider info if present
        divider = getattr(self._modbus_item, "divider", None)
        if divider:
            attributes["divider"] = divider

        return attributes


class SAXBatteryCalcSensor(SAXBatterySensor):
    """SAX Battery calculated sensor entity."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
        index: int,
    ) -> None:
        """Initialize the calculated sensor entity."""
        super().__init__(coordinator, battery_id, modbus_item, index)

        # Override name for calculated sensors
        self._attr_name = f"{battery_id.title()} {modbus_item.name.replace('_', ' ').title()} (Calculated)"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal | None:
        """Return the calculated value."""
        if not self.coordinator.last_update_success:
            return None

        # Implement calculation logic based on item configuration
        return self._calculate_value()

    def _calculate_value(self) -> StateType | date | datetime | Decimal | None:
        """Calculate the sensor value based on other data points."""
        data = self.coordinator.data

        # Example calculations based on common patterns
        if "total_power" in self._modbus_item.name.lower():
            # Calculate total power from charge/discharge
            charge_power = data.get("sax_charge_power", 0) or 0
            discharge_power = data.get("sax_discharge_power", 0) or 0
            return Decimal(str(discharge_power - charge_power))

        if "efficiency" in self._modbus_item.name.lower():
            # Calculate efficiency from energy in/out
            energy_in = data.get("sax_energy_in", 0) or 0
            energy_out = data.get("sax_energy_out", 0) or 0
            if energy_in > 0:
                return Decimal(str((energy_out / energy_in) * 100))
            return None

        if "remaining_time" in self._modbus_item.name.lower():
            # Calculate remaining time based on SOC and power
            soc = data.get("sax_soc", 0) or 0
            power = data.get("sax_power", 0) or 0
            capacity = data.get("sax_capacity", 0) or 0

            if power > 0 and capacity > 0:  # Discharging
                remaining_energy = (soc / 100) * capacity
                return Decimal(str(remaining_energy / power))  # Hours
            if power < 0 and capacity > 0:  # Charging
                remaining_energy = ((100 - soc) / 100) * capacity
                return Decimal(str(remaining_energy / abs(power)))  # Hours
            return None

        # Default: return raw value as Decimal if numeric
        raw_value = data.get(self._modbus_item.name)
        if isinstance(raw_value, (int, float)):
            return Decimal(str(raw_value))
        return str(raw_value) if raw_value is not None else None
