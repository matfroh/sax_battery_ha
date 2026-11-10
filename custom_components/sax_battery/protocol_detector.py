"""Startup protocol detection for SAX battery firmware modes."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
import logging
import random

from .protocol_mode import ProtocolMode

_LOGGER = logging.getLogger(__name__)

# Unit IDs documented by SAX protocol manuals
UNIT_ID_LEGACY = 64
UNIT_ID_SUNSPEC_NEW = 100

# SunSpec identifier words ("SunS")
SUNSPEC_ID_WORD_0 = 21365
SUNSPEC_ID_WORD_1 = 28243

# Probe timing
PROBE_RETRIES = 2
PROBE_TIMEOUT_GAP_MIN = 0.2
PROBE_TIMEOUT_GAP_MAX = 0.6
VALIDATION_RETRIES = 1
VALIDATION_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class ProtocolDetectionResult:
    """Protocol detection output for coordinator setup."""

    mode: ProtocolMode
    detected_device_id: int
    detection_path: str
    reason: str


async def validate_sunspec_availability(
    modbus_api: object,
    battery_id: str,
) -> ProtocolDetectionResult:
    """Perform a short SunSpec availability check and fall back to legacy on failure."""
    probe = await _probe_sunspec_unit_100(
        modbus_api,
        retries=VALIDATION_RETRIES,
        timeout_seconds=VALIDATION_TIMEOUT_SECONDS,
    )
    if probe:
        _LOGGER.info("%s: SunSpec validation succeeded", battery_id)
        return ProtocolDetectionResult(
            mode=ProtocolMode.SUNSPEC,
            detected_device_id=UNIT_ID_SUNSPEC_NEW,
            detection_path="validate_sunspec",
            reason="sunspec_validation_succeeded",
        )

    _LOGGER.warning(
        "%s: SunSpec validation failed, falling back to legacy protocol",
        battery_id,
    )
    return ProtocolDetectionResult(
        mode=ProtocolMode.LEGACY,
        detected_device_id=UNIT_ID_LEGACY,
        detection_path="validate_sunspec",
        reason="sunspec_validation_failed",
    )


async def _probe_sunspec_unit_100(
    modbus_api: object,
    retries: int = PROBE_RETRIES,
    timeout_seconds: float = VALIDATION_TIMEOUT_SECONDS,
) -> bool:
    """Probe SunSpec common header at 40000 on Unit-ID 100."""
    # 40000..40003 -> two ID words + model id + model length
    registers = await _probe_read_with_retry(
        modbus_api,
        address=0,
        count=4,
        device_id=UNIT_ID_SUNSPEC_NEW,
        retries=retries,
        timeout_seconds=timeout_seconds,
    )
    if not registers or len(registers) < 4:
        return False

    word0, word1, model_id, model_length = (
        registers[0],
        registers[1],
        registers[2],
        registers[3],
    )

    is_valid_id = word0 == SUNSPEC_ID_WORD_0 and word1 == SUNSPEC_ID_WORD_1
    is_common_model = model_id == 1
    has_length = model_length > 0

    return is_valid_id and is_common_model and has_length


async def _probe_read_with_retry(
    modbus_api: object,
    address: int,
    count: int,
    device_id: int,
    *,
    retries: int = PROBE_RETRIES,
    timeout_seconds: float = VALIDATION_TIMEOUT_SECONDS,
) -> list[int] | None:
    """Read register block with bounded retries for transient display refresh gaps."""
    read_register_block = getattr(modbus_api, "read_register_block", None)
    if read_register_block is None:
        return None

    for attempt in range(retries):
        try:
            result = await asyncio.wait_for(
                read_register_block(
                    address=address,
                    count=count,
                    device_id=device_id,
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError, OSError, ValueError:
            result = None
        if isinstance(result, Sequence) and result:
            if all(isinstance(value, int) for value in result):
                return [int(value) for value in result]

        if attempt < retries - 1:
            await asyncio.sleep(
                random.uniform(PROBE_TIMEOUT_GAP_MIN, PROBE_TIMEOUT_GAP_MAX)
            )

    return None
