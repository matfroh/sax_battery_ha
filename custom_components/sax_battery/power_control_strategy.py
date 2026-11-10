"""Protocol-specific power control for SAX Battery.

Legacy firmware exposes write-only registers 41 and 42. Its power manager
calculates a Watts setpoint and writes the setpoint and factor atomically.

SunSpec firmware exposes Model 123 controls that are readable and writable:
40049 (``Conn_Win_Pct``) is a signed relative power setpoint, 40050
(``Conn_Win_Tgt``) sets the command timeout, and 40051 (``Mode``) selects
manual setpoint mode (1) or the battery's Smart Meter zero-balancing mode (0).
The setpoint is relative to Model 123 register 40053 (``W_Max_Ref``), so this
module converts a Home Assistant Watts request to a value in [-100, 100].

SunSpec control values are read from the battery's Model 123 block during every
master coordinator update. They are therefore never restored from local entity
state. ``PowerManager`` is a legacy-only software balancing loop and is not
started for SunSpec mode; the battery applies zero balancing itself when Mode
is 0. The strategy classes provide the shared interface for future callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import TYPE_CHECKING

from .const_sunspec import (
    SAX_SUNSPEC_CONTROL_MODE,
    SAX_SUNSPEC_POWER_SETPOINT,
    SAX_SUNSPEC_REFERENCE_POWER,
    SAX_SUNSPEC_SETPOINT_TIMEOUT,
)
from .items import ModbusItem

if TYPE_CHECKING:
    from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


class PowerControlStrategy(ABC):
    """Shared interface for protocol-specific control operations.

    Call ``async_set_power`` when an automation requests a fixed battery power
    target in Watts. Call ``async_set_mode_zero_balance`` when control should be
    returned to the device's Smart Meter balancing behavior, or
    ``async_set_mode_manual`` before configuring an explicit setpoint.
    """

    @abstractmethod
    async def async_set_power(self, target_watts: float, timeout_s: int = 60) -> bool:
        """Set commanded power setpoint in Watts (negative for charge, positive for discharge)."""

    @abstractmethod
    async def async_set_mode_zero_balance(self) -> bool:
        """Set battery system to autonomous 0-grid-balancing mode."""

    @abstractmethod
    def get_max_power_rating(self) -> float:
        """Get the total maximum power rating in Watts."""


class SunSpecPowerControlStrategy(PowerControlStrategy):
    """SunSpec Model 123 strategy for direct device-side power control.

    Fixed-power requests use Mode 1 and write the percentage setpoint plus a
    bounded timeout. Zero-balancing uses Mode 0 only; no calculated legacy
    setpoint is sent because the battery controls the connected Smart Meter.
    """

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize SunSpec strategy."""
        self.coordinator = coordinator

    def get_max_power_rating(self) -> float:
        """Return maximum power reference from register 40053 or calculate."""
        if self.coordinator.data:
            ref_power = self.coordinator.data.get(SAX_SUNSPEC_REFERENCE_POWER)
            if ref_power and isinstance(ref_power, (int, float)) and ref_power > 0:
                return float(ref_power)
        battery_count = len(self.coordinator.sax_data.coordinators) or 1
        return float(battery_count * 4600)

    async def async_set_power(self, target_watts: float, timeout_s: int = 60) -> bool:
        """Apply a fixed power request using Model 123 manual mode.

        This is used when a caller requests direct charge/discharge control.
        ``target_watts`` is converted with ``W_Max_Ref`` (40053), clamped to the
        device's allowed [-100, 100] percent range, and written with a timeout
        limited to the documented 1-300 second range before setting Mode to 1.
        """
        max_power = self.get_max_power_rating()
        if max_power <= 0:
            max_power = 4600.0

        pct = (target_watts / max_power) * 100.0
        pct = max(-100.0, min(100.0, pct))

        setpoint_item = self.coordinator.sax_data.get_item_by_name(
            SAX_SUNSPEC_POWER_SETPOINT
        )
        if setpoint_item and isinstance(setpoint_item, ModbusItem):
            await self.coordinator.async_write_number_value(setpoint_item, int(pct))

        timeout_item = self.coordinator.sax_data.get_item_by_name(
            SAX_SUNSPEC_SETPOINT_TIMEOUT
        )
        if timeout_item and isinstance(timeout_item, ModbusItem):
            await self.coordinator.async_write_number_value(
                timeout_item, min(300, max(1, timeout_s))
            )

        mode_item = self.coordinator.sax_data.get_item_by_name(SAX_SUNSPEC_CONTROL_MODE)
        if mode_item and isinstance(mode_item, ModbusItem):
            await self.coordinator.async_write_number_value(mode_item, 1)

        return True

    async def async_set_mode_zero_balance(self) -> bool:
        """Return control to device-side Smart Meter zero balancing (Mode 0).

        Use this instead of ``PowerManager`` for SunSpec installations with a
        configured Smart Meter. The battery owns the balancing calculation.
        """
        mode_item = self.coordinator.sax_data.get_item_by_name(SAX_SUNSPEC_CONTROL_MODE)
        if not mode_item or not isinstance(mode_item, ModbusItem):
            return False
        await self.coordinator.async_write_number_value(mode_item, 0)
        return True
