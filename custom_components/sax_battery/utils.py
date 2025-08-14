"""Utility functions for SAX Battery integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory

from .items import ModbusItem, SAXItem


def create_entity_unique_id(
    battery_id: str, modbus_item: ModbusItem | SAXItem, index: int
) -> str:
    """Create unique ID for an entity.

    Args:
        battery_id: Battery identifier
        modbus_item: Modbus item
        index: Item index

    Returns:
        Unique entity ID

    """
    # Remove semantic suffixes like "(Calculated)" from SAXItem names
    clean_name = modbus_item.name.replace(" (Calculated)", "")
    return f"{battery_id}_{clean_name}_{index}"


def determine_entity_category(
    modbus_item: ModbusItem | SAXItem,
) -> EntityCategory | None:
    """Determine entity category based on modbus item.

    Args:
        modbus_item: Modbus item

    Returns:
        Entity category or None

    """
    # Check entitydescription for entity_category first
    if hasattr(modbus_item, "entitydescription") and modbus_item.entitydescription:
        if (
            hasattr(modbus_item.entitydescription, "entity_category")
            and modbus_item.entitydescription.entity_category
        ):
            return modbus_item.entitydescription.entity_category

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
    """Determine if entity should be included based on configuration.

    Args:
        modbus_item: Modbus item
        config_entry: Config entry
        battery_id: Battery identifier

    Returns:
        True if entity should be included

    """
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
