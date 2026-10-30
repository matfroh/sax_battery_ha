"""SunSpec register block definitions used by the SAX Battery integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SunSpecRegisterBlock:
    """Definition of a documented SunSpec register block."""

    name: str
    start_address: int
    end_address: int
    required: bool = True

    @property
    def register_count(self) -> int:
        """Return the number of registers in the block."""
        return self.end_address - self.start_address + 1

    def contains(self, address: int) -> bool:
        """Return whether the register address belongs to this block."""
        return self.start_address <= address <= self.end_address


SUNSPEC_REGISTER_BLOCKS: tuple[SunSpecRegisterBlock, ...] = (
    SunSpecRegisterBlock("device_metadata", 40000, 40014),
    SunSpecRegisterBlock("battery_sensor_data", 40015, 40046),
    SunSpecRegisterBlock("battery_controls", 40047, 40053),
    SunSpecRegisterBlock("smartmeter_data", 40054, 40094, required=False),
    SunSpecRegisterBlock("battery_states", 40095, 40114),
)


def get_sunspec_block_for_address(address: int) -> SunSpecRegisterBlock | None:
    """Return the documented SunSpec block for a register address."""
    for block in SUNSPEC_REGISTER_BLOCKS:
        if block.contains(address):
            return block
    return None


def get_sunspec_block_by_name(name: str) -> SunSpecRegisterBlock | None:
    """Return the documented SunSpec block for a logical block name."""
    for block in SUNSPEC_REGISTER_BLOCKS:
        if block.name == name:
            return block
    return None
