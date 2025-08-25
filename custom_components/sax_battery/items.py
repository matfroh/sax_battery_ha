"""Item classes for SAX Battery integration."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
import logging
from typing import Any

from pymodbus.client.mixin import ModbusClientMixin  # For DATATYPE

from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription

from .enums import DeviceConstants, TypeConstants

_LOGGER = logging.getLogger(__name__)


@dataclass
class BaseItem(ABC):
    """Base class for all items."""

    name: str
    mtype: TypeConstants
    device: DeviceConstants
    translation_key: str = ""

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


@dataclass
class ModbusItem(BaseItem):
    """Modbus-specific item with enhanced functionality."""

    address: int = 0
    battery_slave_id: int = 0
    data_type: ModbusClientMixin.DATATYPE = ModbusClientMixin.DATATYPE.INT16
    factor: float = 1.0
    offset: int = 0
    entitydescription: (
        SensorEntityDescription
        | NumberEntityDescription
        | SwitchEntityDescription
        | None
    ) = None


@dataclass
class SAXItem(BaseItem):
    """SAX item for calculated sensors and pilot controls."""

    entitydescription: (
        SensorEntityDescription
        | NumberEntityDescription
        | SwitchEntityDescription
        | None
    ) = None
