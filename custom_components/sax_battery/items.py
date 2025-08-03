"""Item classes for SAX Battery integration."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription

from .enums import DeviceConstants, FormatConstants, TypeConstants


@dataclass
class StatusItem:
    """Status item for result lists."""

    number: int = 0  # default value for status (we use value 1,3,4)
    text: str = ""
    name: str = ""  # translation_key
    # description: str = ""


@dataclass
class BaseItem(ABC):
    """Base class for all items."""

    name: str
    mformat: FormatConstants
    mtype: TypeConstants
    device: DeviceConstants
    translation_key: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    # State management
    _state: Any = field(default=None, init=False)
    _is_invalid: bool = field(default=False, init=False)

    @property
    def state(self) -> Any:
        """Get the current state."""
        return self._state

    @state.setter
    def state(self, value: Any) -> None:
        """Set the current state."""
        self._state = value

    @property
    def is_invalid(self) -> bool:
        """Check if the item is invalid."""
        return self._is_invalid

    @is_invalid.setter
    def is_invalid(self, value: bool) -> None:
        """Set the invalid state."""
        self._is_invalid = value


# Keep ApiItem for backward compatibility with modbusobject.py
@dataclass
class ApiItem(BaseItem):
    """API item for backward compatibility."""

    address: int = 0
    battery_slave_id: int = 1
    divider: float = 1.0
    entitydescription: (
        SensorEntityDescription
        | SwitchEntityDescription
        | NumberEntityDescription
        | None
    ) = None
    resultlist: list[StatusItem] | None = None

    def convert_raw_value(self, raw_value: int) -> float:
        """Convert raw modbus value to real value."""
        if self.mformat == FormatConstants.NUMBER:
            # Handle signed 16-bit values
            if raw_value > 32767:
                raw_value -= 65536

        return raw_value / self.divider if self.divider != 0 else raw_value

    def convert_to_raw_value(self, value: float) -> int:
        """Convert real value to raw modbus value."""
        raw_value = int(value * self.divider)

        # Handle format-specific constraints
        if self.mformat == FormatConstants.PERCENTAGE:
            raw_value = max(0, min(100, raw_value))
        elif self.mformat == FormatConstants.NUMBER:
            raw_value = max(-32768, min(32767, raw_value))
        else:  # UNSIGNED and others
            raw_value = max(0, min(65535, raw_value))

        return raw_value


@dataclass
class ModbusItem(BaseItem):
    """Modbus-specific item with enhanced functionality."""

    address: int = 0
    battery_slave_id: int = 0
    divider: float = 1.0
    entitydescription: (
        SensorEntityDescription
        | SwitchEntityDescription
        | NumberEntityDescription
        | None
    ) = None
    resultlist: list[StatusItem] = []  # noqa: RUF008

    def convert_raw_value(self, raw_value: int) -> float:
        """Convert raw modbus value to real value."""
        if self.mformat == FormatConstants.NUMBER:
            # Handle signed 16-bit values
            if raw_value > 32767:
                raw_value -= 65536

        return raw_value / self.divider if self.divider != 0 else raw_value

    def convert_to_raw_value(self, value: float) -> int:
        """Convert real value to raw modbus value."""
        raw_value = int(value * self.divider)

        # Handle format-specific constraints
        if self.mformat == FormatConstants.PERCENTAGE:
            raw_value = max(0, min(100, raw_value))
        elif self.mformat == FormatConstants.NUMBER:
            raw_value = max(-32768, min(32767, raw_value))
        else:  # UNSIGNED and others
            raw_value = max(0, min(65535, raw_value))

        return raw_value


@dataclass
class SAXItem(BaseItem):
    """SAX-specific item for calculated values and pilot controls."""

    entitydescription: (
        SensorEntityDescription
        | SwitchEntityDescription
        | NumberEntityDescription
        | None
    ) = None
    resultlist: list[StatusItem] | None = None
