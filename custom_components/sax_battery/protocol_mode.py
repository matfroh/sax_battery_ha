"""Protocol mode definitions for SAX battery communication."""

from __future__ import annotations

from enum import StrEnum


class ProtocolMode(StrEnum):
    """Supported protocol modes."""

    LEGACY = "legacy"
    SUNSPEC = "sunspec"
