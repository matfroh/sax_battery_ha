"""Entity creation helpers for SAX Battery integration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import Entity

from .enums import TypeConstants
from .items import ModbusItem, SAXItem
from .number import SAXBatteryNumber
from .sensor import SAXBatteryCalcSensor, SAXBatterySensor
from .switch import SAXBatterySwitch


def create_entity_unique_id(
    battery_id: str, modbus_item: ModbusItem | SAXItem, index: int
) -> str:
    """Create a unique ID for an entity."""
    return f"{battery_id}_{modbus_item.name}_{index}"


def determine_entity_category(
    modbus_item: ModbusItem | SAXItem,
) -> EntityCategory | None:
    """Determine the entity category based on modbus item properties."""
    category = getattr(modbus_item, "category", None)
    if category:
        if isinstance(category, EntityCategory):
            return category
        if isinstance(category, str):
            match category.lower():
                case "config":
                    return EntityCategory.CONFIG
                case "diagnostic":
                    return EntityCategory.DIAGNOSTIC

    diagnostic_keywords = ["debug", "diagnostic", "status", "error", "version"]
    config_keywords = ["config", "setting", "limit", "max_", "pilot_", "enable_"]

    item_name_lower = modbus_item.name.lower()

    if any(keyword in item_name_lower for keyword in diagnostic_keywords):
        return EntityCategory.DIAGNOSTIC

    if any(keyword in item_name_lower for keyword in config_keywords):
        return EntityCategory.CONFIG

    return None


def should_include_entity(
    modbus_item: ModbusItem,
    config_entry: ConfigEntry,
    battery_id: str,
) -> bool:
    """Determine if entity should be included based on configuration."""
    device_type = getattr(modbus_item, "device", None)
    if device_type:
        config_device = config_entry.data.get("device_type")
        if config_device and device_type != config_device:
            return False

    master_only = getattr(modbus_item, "master_only", False)
    if master_only:
        battery_configs = config_entry.data.get("batteries", {})
        battery_config = battery_configs.get(battery_id, {})
        return bool(battery_config.get("role") == "master")

    required_features = getattr(modbus_item, "required_features", None)
    if required_features:
        available_features = config_entry.data.get("features", [])
        return bool(all(feature in available_features for feature in required_features))

    return True


async def build_entity_list(
    entries: Sequence[Entity],  # Changed from list to Sequence for covariance
    config_entry: ConfigEntry,
    api_items: list[ModbusItem],
    item_type: TypeConstants,
    coordinator: Any,
    battery_id: str,
) -> None:
    """Build list of entities for a specific type."""

    filtered_items = [
        item
        for item in api_items
        if item._mtype == item_type
        and should_include_entity(item, config_entry, battery_id)
    ]

    # Convert Sequence to list for appending
    entity_list = list(entries) if not isinstance(entries, list) else entries

    for index, modbus_item in enumerate(filtered_items):
        entity: Entity
        if item_type == TypeConstants.SENSOR:
            entity = SAXBatterySensor(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        elif item_type == TypeConstants.SENSOR_CALC:
            entity = SAXBatteryCalcSensor(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        elif item_type in (TypeConstants.NUMBER, TypeConstants.NUMBER_RO):
            entity = SAXBatteryNumber(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        elif item_type == TypeConstants.SWITCH:
            entity = SAXBatterySwitch(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        else:
            continue

        entity_list.append(entity)
