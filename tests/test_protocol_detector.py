"""Tests for startup protocol detection."""

from __future__ import annotations

import pytest

from custom_components.sax_battery.protocol_detector import (
    SUNSPEC_ID_WORD_0,
    SUNSPEC_ID_WORD_1,
    validate_sunspec_availability,
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
async def test_validate_sunspec_availability_uses_short_probe() -> None:
    """A short SunSpec validation should succeed when the common header is present."""
    api = _FakeModbusAPI(
        responses={(0, 4, 100): [SUNSPEC_ID_WORD_0, SUNSPEC_ID_WORD_1, 1, 15]}
    )

    result = await validate_sunspec_availability(api, battery_id="bess_a")

    assert result.mode == ProtocolMode.SUNSPEC
    assert result.detected_device_id == 100
    assert result.detection_path == "validate_sunspec"
    assert api.calls == [(0, 4, 100)]
