"""SunSpec block read helpers for SAX Battery integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from pymodbus import ModbusException

from .items import ModbusItem
from .sunspec_map import SunSpecRegisterBlock

_LOGGER = logging.getLogger(__name__)

SUNSPEC_BLOCK_READ_RETRIES = 2
SUNSPEC_BLOCK_RETRY_DELAY_SECONDS = 0.2


async def read_sunspec_register_block(
    modbus_api: Any,
    *,
    start_address: int,
    register_count: int,
    device_id: int,
    retries: int = SUNSPEC_BLOCK_READ_RETRIES,
    retry_delay_seconds: float = SUNSPEC_BLOCK_RETRY_DELAY_SECONDS,
) -> list[int] | None:
    """Read one SunSpec register block with bounded retry handling.

    Returns a typed list of register words on success, otherwise None.
    """
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            block_values = await modbus_api.read_register_block(
                address=start_address,
                count=register_count,
                device_id=device_id,
            )
        except (ModbusException, OSError, TimeoutError) as err:
            last_error = err
            block_values = None

        if isinstance(block_values, list) and all(
            isinstance(value, int) for value in block_values
        ):
            return cast(list[int], block_values)

        if attempt < retries:
            await asyncio.sleep(retry_delay_seconds)

    if last_error is not None:
        _LOGGER.debug(
            "SunSpec block read failed after retries for %s-%s (device=%s): %s",
            start_address,
            start_address + register_count - 1,
            device_id,
            last_error,
        )
    else:
        _LOGGER.debug(
            "SunSpec block read returned invalid/empty payload after retries for %s-%s (device=%s)",
            start_address,
            start_address + register_count - 1,
            device_id,
        )

    return None


def decode_sunspec_block_values(
    modbus_api: Any,
    *,
    block: SunSpecRegisterBlock,
    block_values: list[int],
    item_pairs: list[tuple[ModbusItem, ModbusItem]],
) -> dict[str, Any]:
    """Decode one SunSpec block payload into logical entity values.

    The first item in each pair is the logical entity item, and the second item
    is the mapped SunSpec register definition used for addressing and scaling.
    """
    values: dict[str, Any] = {}
    for logical_item, sunspec_item in item_pairs:
        register_index = sunspec_item.address - block.start_address
        if register_index < 0 or register_index >= len(block_values):
            continue

        decoded_value = modbus_api.decode_register_block_value(
            [block_values[register_index]],
            sunspec_item,
        )
        if decoded_value is not None:
            values[logical_item.name] = decoded_value

    return values
