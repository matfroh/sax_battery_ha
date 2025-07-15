"""Entity creation helpers for SAX Battery integration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity

from .enums import TypeConstants
from .items import ModbusItem
from .utils import should_include_entity


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
            from .sensor import SAXBatterySensor

            entity = SAXBatterySensor(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        elif item_type == TypeConstants.SENSOR_CALC:
            from .sensor import SAXBatteryCalcSensor

            entity = SAXBatteryCalcSensor(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        elif item_type in (TypeConstants.NUMBER, TypeConstants.NUMBER_RO):
            from .number import SAXBatteryNumber

            entity = SAXBatteryNumber(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        elif item_type == TypeConstants.SWITCH:
            from .switch import SAXBatterySwitch

            entity = SAXBatterySwitch(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
                index=index,
            )
        else:
            continue

        entity_list.append(entity)
