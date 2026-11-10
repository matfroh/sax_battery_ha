"""Utility functions for entity creation."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry

from .enums import TypeConstants
from .items import ModbusItem, SAXItem
from .utils import should_include_entity

_LOGGER = logging.getLogger(__name__)


def filter_items_by_type(
    items: list[ModbusItem | SAXItem],
    target_type: TypeConstants,
    config_entry: ConfigEntry,
    battery_id: str,
) -> list[ModbusItem | SAXItem]:
    """Filter items by type with proper entity description validation."""
    filtered_items = []

    for item in items:
        # Handle multiple number types for number platform
        if target_type == TypeConstants.NUMBER:
            if item.mtype not in (
                TypeConstants.NUMBER,
                TypeConstants.NUMBER_RO,
                TypeConstants.NUMBER_WO,
            ):
                continue
        # Handle multiple sensor types for sensor platform
        elif target_type == TypeConstants.SENSOR:
            if item.mtype not in (TypeConstants.SENSOR, TypeConstants.SENSOR_CALC):
                continue
        # Exact match for other types
        elif item.mtype != target_type:
            continue

        # Validate entity description type matches platform (only for ModbusItem)
        if isinstance(item, ModbusItem) and item.entitydescription:
            # Use more flexible type checking - check class name instead of isinstance
            desc_type_name = type(item.entitydescription).__name__

            if target_type == TypeConstants.NUMBER:
                # Accept both NumberEntityDescription and frozen variants
                if "NumberEntityDescription" not in desc_type_name:
                    _LOGGER.warning(
                        "Item %s has wrong entity description type for number platform: %s",
                        item.name,
                        desc_type_name,
                    )
                    continue

            elif target_type == TypeConstants.SENSOR:
                # Accept both SensorEntityDescription and frozen variants
                if "SensorEntityDescription" not in desc_type_name:
                    _LOGGER.warning(
                        "Item %s has wrong entity description type for sensor platform: %s",
                        item.name,
                        desc_type_name,
                    )
                    continue

            elif target_type == TypeConstants.SWITCH:
                # Accept both SwitchEntityDescription and frozen variants
                if "SwitchEntityDescription" not in desc_type_name:
                    _LOGGER.warning(
                        "Item %s has wrong entity description type for switch platform: %s",
                        item.name,
                        desc_type_name,
                    )
                    continue

        # Use centralized should_include_entity function from utils
        if should_include_entity(item, config_entry, battery_id):
            filtered_items.append(item)

    return filtered_items


def filter_sax_items_by_type(
    items: list[SAXItem],
    target_type: TypeConstants,
) -> list[SAXItem]:
    """Filter SAX items by type."""
    filtered_items = []

    for item in items:
        # Handle multiple number types for number platform
        if target_type == TypeConstants.NUMBER:
            if item.mtype not in (
                TypeConstants.NUMBER,
                TypeConstants.NUMBER_RO,
                TypeConstants.NUMBER_WO,
            ):
                continue
        # Handle multiple sensor types for sensor platform
        elif target_type == TypeConstants.SENSOR:
            if item.mtype not in (TypeConstants.SENSOR, TypeConstants.SENSOR_CALC):
                continue
        # Exact match for other types
        elif item.mtype != target_type:
            continue

        # For SAXItem, validate entity description type if present
        if item.entitydescription:
            desc_type_name = type(item.entitydescription).__name__

            if target_type == TypeConstants.NUMBER:
                if "NumberEntityDescription" not in desc_type_name:
                    _LOGGER.debug(
                        "SAX Item %s has entity description type %s for number platform",
                        item.name,
                        desc_type_name,
                    )
                    # Don't continue - allow it through for SAX items

            elif target_type == TypeConstants.SENSOR:
                if "SensorEntityDescription" not in desc_type_name:
                    _LOGGER.debug(
                        "SAX Item %s has entity description type %s for sensor platform",
                        item.name,
                        desc_type_name,
                    )
                    # Don't continue - allow it through for SAX items

        filtered_items.append(item)

    return filtered_items
