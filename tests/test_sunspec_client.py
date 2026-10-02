"""Tests for SunSpec block helper functions."""

from __future__ import annotations

from custom_components.sax_battery.entity_keys import SAX_CAPACITY, SAX_TEMPERATURE
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.sunspec_client import decode_sunspec_block_values
from custom_components.sax_battery.sunspec_map import SunSpecRegisterBlock


class _DecodeAPI:
    """Minimal decode API used by helper tests."""

    def decode_register_block_value(
        self,
        registers: list[int],
        modbus_item: ModbusItem,
    ) -> int | float | None:
        if not registers:
            return None
        value: int | float = registers[0]
        if modbus_item.factor != 1.0:
            value *= modbus_item.factor
        return value


def test_decode_sunspec_block_values_decodes_expected_items() -> None:
    """Helper should decode mapped values and keep logical item names."""
    block = SunSpecRegisterBlock("battery_sensor_data", 40015, 40046)
    block_values = [0] * block.register_count
    block_values[0] = 830
    block_values[1] = 215

    logical_capacity = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    mapped_capacity = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
        address=40015,
        factor=1.0,
    )

    logical_temperature = ModbusItem(
        name=SAX_TEMPERATURE,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    mapped_temperature = ModbusItem(
        name=SAX_TEMPERATURE,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
        address=40016,
        factor=1.0,
    )

    result = decode_sunspec_block_values(
        _DecodeAPI(),
        block=block,
        block_values=block_values,
        item_pairs=[
            (logical_capacity, mapped_capacity),
            (logical_temperature, mapped_temperature),
        ],
    )

    assert result == {
        SAX_CAPACITY: 830,
        SAX_TEMPERATURE: 215,
    }


def test_decode_sunspec_block_values_skips_out_of_range_items() -> None:
    """Helper should ignore mapped items outside the provided block payload."""
    block = SunSpecRegisterBlock("battery_sensor_data", 40015, 40046)
    block_values = [0] * block.register_count

    logical_capacity = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    mapped_capacity = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
        address=40150,
        factor=1.0,
    )

    result = decode_sunspec_block_values(
        _DecodeAPI(),
        block=block,
        block_values=block_values,
        item_pairs=[(logical_capacity, mapped_capacity)],
    )

    assert result == {}
