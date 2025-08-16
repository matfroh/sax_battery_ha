"""Utility functions for entity creation."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .enums import TypeConstants
from .items import ModbusItem, SAXItem
from .utils import should_include_entity


def filter_items_by_type(
    api_items: list[ModbusItem],
    item_type: TypeConstants,
    config_entry: ConfigEntry,
    battery_id: str,
) -> list[ModbusItem]:
    """Filter modbus items by type and inclusion criteria."""
    return [
        item
        for item in api_items
        if item.mtype == item_type
        and should_include_entity(item, config_entry, battery_id)
    ]


def filter_sax_items_by_type(
    sax_items: list[SAXItem],
    item_type: TypeConstants,
    config_entry: ConfigEntry,
    battery_id: str,
) -> list[SAXItem]:
    """Filter SAXItem objects by type."""
    return [item for item in sax_items if item.mtype == item_type]
