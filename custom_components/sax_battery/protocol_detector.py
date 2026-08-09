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
UNIT_ID_SUNSPEC_COMPAT = 40

# SunSpec identifier words ("SunS")
SUNSPEC_ID_WORD_0 = 21365
SUNSPEC_ID_WORD_1 = 28243

# Probe timing
PROBE_RETRIES = 2
PROBE_TIMEOUT_GAP_MIN = 0.2
PROBE_TIMEOUT_GAP_MAX = 0.6


@dataclass(frozen=True)
class ProtocolDetectionResult:
    """Protocol detection output for coordinator setup."""

    mode: ProtocolMode
    detected_device_id: int
    detection_path: str
    reason: str


async def detect_protocol_mode(
    modbus_api: object,
    battery_id: str,
) -> ProtocolDetectionResult:
    """Detect protocol mode by probing documented SunSpec entry points.

    Detection sequence:
    1. Probe SunSpec map at Unit-ID 100, address 40000
    2. Probe compatibility map at Unit-ID 40, address 40071
    3. Fall back to legacy Unit-ID 64

    Args:
        modbus_api: Modbus API instance with read_register_block method
        battery_id: Battery identifier for logging context

    Returns:
        ProtocolDetectionResult with selected mode and slave ID
    """
    # Probe 1: New SunSpec map (Unit-ID 100)
    probe_100 = await _probe_sunspec_unit_100(modbus_api)
    if probe_100:
        _LOGGER.info(
            "%s: Detected SunSpec mode on Unit-ID 100",
            battery_id,
        )
        return ProtocolDetectionResult(
            mode=ProtocolMode.SUNSPEC,
            detected_device_id=UNIT_ID_SUNSPEC_NEW,
            detection_path="probe_unit_100",
            reason="valid_sunspec_common_header",
        )

    # Probe 2: Compatibility map (Unit-ID 40)
    probe_40 = await _probe_sunspec_unit_40(modbus_api)
    if probe_40:
        _LOGGER.info(
            "%s: Detected SunSpec compatibility mode on Unit-ID 40",
            battery_id,
        )
        return ProtocolDetectionResult(
            mode=ProtocolMode.SUNSPEC,
            detected_device_id=UNIT_ID_SUNSPEC_COMPAT,
            detection_path="probe_unit_40",
            reason="valid_sunspec_compat_header",
        )

    _LOGGER.warning(
        "%s: SunSpec detection failed, falling back to legacy Unit-ID 64",
        battery_id,
    )
    return ProtocolDetectionResult(
        mode=ProtocolMode.LEGACY,
        detected_device_id=UNIT_ID_LEGACY,
        detection_path="fallback_legacy",
        reason="sunspec_probe_failed",
    )


async def _probe_sunspec_unit_100(modbus_api: object) -> bool:
    """Probe SunSpec common header at 40000 on Unit-ID 100."""
    # 40000..40003 -> two ID words + model id + model length
    registers = await _probe_read_with_retry(
        modbus_api,
        address=0,
        count=4,
        device_id=UNIT_ID_SUNSPEC_NEW,
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


async def _probe_sunspec_unit_40(modbus_api: object) -> bool:
    """Probe compatibility header at 40071 on Unit-ID 40."""
    # 40071 maps to internal address 70
    registers = await _probe_read_with_retry(
        modbus_api,
        address=70,
        count=2,
        device_id=UNIT_ID_SUNSPEC_COMPAT,
    )
    if not registers or len(registers) < 2:
        return False

    header, length_or_word = registers[0], registers[1]

    # Accept either:
    # - documented compat map form: header + length (>0)
    # - split SunSpec ID words seen on some devices
    is_compat_form = header == SUNSPEC_ID_WORD_0 and length_or_word > 0
    is_split_id_form = (
        header == SUNSPEC_ID_WORD_0 and length_or_word == SUNSPEC_ID_WORD_1
    )
    return is_compat_form or is_split_id_form


async def _probe_read_with_retry(
    modbus_api: object,
    address: int,
    count: int,
    device_id: int,
) -> list[int] | None:
    """Read register block with bounded retries for transient display refresh gaps."""
    read_register_block = getattr(modbus_api, "read_register_block", None)
    if read_register_block is None:
        return None

    for attempt in range(PROBE_RETRIES):
        result = await read_register_block(
            address=address,
            count=count,
            device_id=device_id,
        )
        if isinstance(result, Sequence) and result:
            if all(isinstance(value, int) for value in result):
                return [int(value) for value in result]

        if attempt < PROBE_RETRIES - 1:
            await asyncio.sleep(
                random.uniform(PROBE_TIMEOUT_GAP_MIN, PROBE_TIMEOUT_GAP_MAX)
            )

    return None
