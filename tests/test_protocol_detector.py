"""Tests for startup protocol detection."""

from __future__ import annotations

import pytest

from custom_components.sax_battery.protocol_detector import (
    SUNSPEC_ID_WORD_0,
    SUNSPEC_ID_WORD_1,
    detect_protocol_mode,
)
from custom_components.sax_battery.protocol_mode import ProtocolMode


class _FakeModbusAPI:
    """Minimal fake Modbus API for protocol detector tests."""

    def __init__(self, responses: dict[tuple[int, int, int], list[int] | None]) -> None:
        """Initialize fake API with keyed responses.

        Response key format: (address, count, device_id)
        """
        self._responses = responses
        self.calls: list[tuple[int, int, int]] = []

    async def read_register_block(
        self,
        address: int,
        count: int,
        device_id: int,
    ) -> list[int] | None:
        """Return configured response for probe call."""
        key = (address, count, device_id)
        self.calls.append(key)
        return self._responses.get(key)


@pytest.mark.asyncio
async def test_detect_protocol_mode_prefers_unit_100() -> None:
    """Detect SunSpec via Unit-ID 100 before trying compatibility map."""
    api = _FakeModbusAPI(
        responses={
            # Unit-ID 100 probe: 40000..40003 (address 0, count 4)
            (0, 4, 100): [SUNSPEC_ID_WORD_0, SUNSPEC_ID_WORD_1, 1, 15],
        }
    )

    result = await detect_protocol_mode(api, battery_id="bess_a")

    assert result.mode == ProtocolMode.SUNSPEC
    assert result.detected_device_id == 100
    assert result.detection_path == "probe_unit_100"
    assert result.reason == "valid_sunspec_common_header"
    assert api.calls == [(0, 4, 100)]


@pytest.mark.asyncio
async def test_detect_protocol_mode_falls_back_to_unit_40() -> None:
    """Use Unit-ID 40 compatibility probe when Unit-ID 100 fails."""
    api = _FakeModbusAPI(
        responses={
            (0, 4, 100): None,
            # Unit-ID 40 compat probe: 40071..40072 (address 70, count 2)
            (70, 2, 40): [SUNSPEC_ID_WORD_0, 40],
        }
    )

    result = await detect_protocol_mode(api, battery_id="bess_a")

    assert result.mode == ProtocolMode.SUNSPEC
    assert result.detected_device_id == 40
    assert result.detection_path == "probe_unit_40"
    assert result.reason == "valid_sunspec_compat_header"
    assert (0, 4, 100) in api.calls
    assert (70, 2, 40) in api.calls


@pytest.mark.asyncio
async def test_detect_protocol_mode_falls_back_to_legacy() -> None:
    """Fall back to legacy Unit-ID 64 when SunSpec probes fail."""
    api = _FakeModbusAPI(
        responses={
            (0, 4, 100): None,
            (70, 2, 40): None,
        }
    )

    result = await detect_protocol_mode(api, battery_id="bess_a")

    assert result.mode == ProtocolMode.LEGACY
    assert result.detected_device_id == 64
    assert result.detection_path == "fallback_legacy"
    assert result.reason == "sunspec_probe_failed"
