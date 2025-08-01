"""Item definitions for SAX Battery integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import EntityCategory

from .enums import DeviceConstants, FormatConstants, TypeConstants


class StatusItem:
    """An item of a status, e.g. error code and error text along with a precise description.

    A class is intentionally defined here because the assignment via dictionaries would not work so elegantly in the end,
    especially when searching backwards. (At least I don't know how...)
    """

    _number: int | None = None
    _text: str | None = None
    _description: str | None = None
    _translation_key: str = ""

    def __init__(
        self,
        number: int,
        text: str,
        translation_key: str | None = None,
        description: str | None = None,
    ) -> None:
        """Initialise StatusItem."""
        self._number = number
        self._text = text
        self._description = description
        self._translation_key = translation_key or ""

    @property
    def number(self) -> int:
        """Return number."""
        return self._number or 0

    @number.setter
    def number(self, value: int) -> None:
        """Set number."""
        self._number = value

    @property
    def text(self) -> str:
        """Return text."""
        return self._text or ""

    @text.setter
    def text(self, value: str) -> None:
        self._text = value

    @property
    def description(self) -> str:
        """Return description."""
        return self._description or ""

    @description.setter
    def description(self, value: str) -> None:
        self._description = value

    @property
    def translation_key(self) -> str:
        """Return translation_key."""
        return self._translation_key

    @translation_key.setter
    def translation_key(self, val: str) -> None:
        """Set translation_key."""
        self._translation_key = val


class ModbusItem:
    """Represents an Modbus item."""

    _address: int
    _mformat: FormatConstants = FormatConstants.UNKNOWN
    _mtype: TypeConstants = TypeConstants.SENSOR
    _entitydescription: (
        SwitchEntityDescription
        | SensorEntityDescription
        | NumberEntityDescription
        | None
    ) = None
    _battery_slave_id: int | None = 1
    on_value: int = 1
    off_value: int = 0
    master_only: bool = False

    def __init__(
        self,
        address: int,
        name: str,
        mformat: FormatConstants,
        mtype: TypeConstants,
        entitydescription: SwitchEntityDescription
        | SensorEntityDescription
        | NumberEntityDescription
        | None = None,
        device: DeviceConstants = DeviceConstants.UNKNOWN,
        translation_key: str | None = None,
        resultlist: Any = None,
        params: dict[Any, Any] | None = None,
        battery_slave_id: int | None = None,
        on_value: int = 1,
        off_value: int = 0,
        conversion_factor: float = 1.0,
        rounding: int = 0,
        write_enabled: bool = False,
        master_only: bool = False,
    ) -> None:
        """Initialize ModbusItem.

        Args:
            address: Modbus register address
            name: Item name
            mformat: Data format constant
            mtype: Item type constant
            entitydescription: Home Assistant entity description
            device: Device type constant
            translation_key: Translation key for entity
            resultlist: List of results for processing
            params: Additional parameters
            battery_slave_id: Slave ID for the battery
            on_value: Value representing "on" state
            off_value: Value representing "off" state
            conversion_factor: Factor for value conversion
            rounding: Number of decimal places for rounding
            write_enabled: Whether write operations are enabled
            master_only: Whether item is only for master battery

        """
        self._address = address
        self._entitydescription = entitydescription
        self._battery_slave_id = battery_slave_id
        self._mformat: FormatConstants = mformat
        self._mtype: TypeConstants = mtype

    @property
    def address(self) -> int:
        """Return address."""
        return self._address

    @address.setter
    def address(self, val: int) -> None:
        """Set address."""
        self._address = val

    @property
    def entitydescription(
        self,
    ) -> (
        SwitchEntityDescription
        | SensorEntityDescription
        | NumberEntityDescription
        | None
    ):
        """Return entitydescription."""
        return self._entitydescription

    @entitydescription.setter
    def entitydescription(
        self,
        val: SwitchEntityDescription
        | SensorEntityDescription
        | NumberEntityDescription
        | None,
    ) -> None:
        """Set entitydescription."""
        self._entitydescription = val

    @property
    def battery_slave_id(self) -> int | None:
        """Return battery slave ID."""
        return self._battery_slave_id

    @battery_slave_id.setter
    def battery_slave_id(self, slave: int) -> None:
        """Set battery slave ID."""
        self._battery_slave_id = slave

    @property
    def mformat(self) -> FormatConstants:
        """Return format."""
        return self._mformat

    @property
    def mtype(self) -> TypeConstants:
        """Return type."""
        return self._mtype


class ApiItem(ModbusItem):
    """Class ApiIem item.

    This can either be a ModbusItem or other
    """

    _name: str = "empty"
    _resultlist: Any = None
    _device: DeviceConstants = DeviceConstants.UNKNOWN
    _state: Any = None
    _is_invalid: bool = False
    _translation_key: str = ""
    _description: SensorEntityDescription | None = None
    _params: dict[Any, Any] | None = None
    _divider: int = 1

    def __init__(
        self,
        name: str,
        device: DeviceConstants = DeviceConstants.UNKNOWN,
        translation_key: str | None = None,
        resultlist: Any = None,
        params: dict[Any, Any] | None = None,
    ) -> None:
        """Initialise ModbusItem."""
        super().__init__(
            address=0,
            name=name,
            mformat=FormatConstants.UNKNOWN,
            mtype=TypeConstants.SENSOR,
            entitydescription=None,
        )
        self._name: str = name
        self._device: DeviceConstants = device
        self._resultlist = resultlist
        self._state = None
        self._is_invalid = False
        self._translation_key = translation_key or ""
        self._description = None
        self._params = params
        self._divider = 1

    @property
    def params(self) -> dict[Any, Any]:
        """Return state."""
        return self._params or {}

    @params.setter
    def params(self, val: dict[Any, Any] | None) -> None:
        self._params = val

    @property
    def description(self) -> SensorEntityDescription | None:
        """Return description."""
        return self._description

    @description.setter
    def description(self, val: SensorEntityDescription | None) -> None:
        """Set description."""
        self._description = val

    @property
    def divider(self) -> int:
        """Return state."""
        return self._divider

    @divider.setter
    def divider(self, val: int) -> None:
        self._divider = val

    @property
    def is_invalid(self) -> bool:
        """Return state."""
        return self._is_invalid

    @is_invalid.setter
    def is_invalid(self, val: bool) -> None:
        self._is_invalid = val

    @property
    def state(self) -> Any:
        """Return the state of the item set by modbusobject."""
        return self._state

    @state.setter
    def state(self, val: Any) -> None:
        """Set the state of the item from modbus."""
        self._state = val

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @name.setter
    def name(self, val: str) -> None:
        """Set name."""
        self._name = val

    @property
    def device(self) -> DeviceConstants:
        """Return device."""
        return self._device

    @device.setter
    def device(self, val: DeviceConstants) -> None:
        """Set device."""
        self._device = val

    @property
    def translation_key(self) -> str:
        """Return translation_key."""
        return self._translation_key

    @translation_key.setter
    def translation_key(self, val: str) -> None:
        """Set translation_key."""
        self._translation_key = val

    @property
    def resultlist(self) -> Any:
        """Return resultlist."""
        return self._resultlist

    def get_text_from_number(self, val: int | None) -> str | None:
        """Get errortext from corresponding number."""
        if val is None:
            return None
        if self._resultlist is None:
            return None
        for _useless, item in enumerate(self._resultlist):
            if val == item.number:
                return str(item.text)
        return f"unknown <{val}>"

    def get_number_from_text(self, val: str) -> int | None:
        """Get number of corresponding errortext."""
        if self._resultlist is None:
            return None
        for _useless, item in enumerate(self._resultlist):
            if val == item.text:
                return int(item.number)
        return -1

    def get_translation_key_from_number(self, val: int | None) -> str | None:
        """Get errortext from corresponding number."""
        if val is None:
            return None
        if self._resultlist is None:
            return None
        for _useless, item in enumerate(self._resultlist):
            if val == item.number:
                return str(item.translation_key)
        return f"unknown <{val}>"

    def get_number_from_translation_key(self, val: str | None) -> int | None:
        """Get number of corresponding errortext."""
        if val is None:
            return None
        if self._resultlist is None:
            return None
        for _useless, item in enumerate(self._resultlist):
            if val == item.translation_key:
                return int(item.number)
        return -1


@dataclass
class SAXItem:
    """SAX item definition for pilot functionality."""

    name: str
    mformat: FormatConstants  # modbus format -> not home assistant formats
    mtype: TypeConstants  # modbus type -> not home assistant type
    device: DeviceConstants
    entitydescription: (
        SwitchEntityDescription
        | SensorEntityDescription
        | NumberEntityDescription
        | None
    ) = None
    translation_key: str = ""
    icon: str | None = None
    category: EntityCategory | str | None = None
    unit: str | None = None
    on_value: int = 1
    off_value: int = 0
    master_only: bool = True
    params: dict[str, Any] = field(default_factory=dict)
    required_features: list[str] = field(default_factory=list)
    _last_update: float = 0.0
    _update_interval: int = 60  # SAX items update every minute

    @property
    def format(self) -> FormatConstants:
        """Return format constant for compatibility."""
        return self.mformat

    @property
    def type(self) -> TypeConstants:
        """Return type constant for compatibility."""
        return self.mtype

    @property
    def last_update(self) -> float:
        """Return timestamp of last update."""
        return self._last_update

    @property
    def update_interval(self) -> int:
        """Return update interval in seconds."""
        return self._update_interval

    def mark_updated(self) -> None:
        """Mark item as recently updated."""
        self._last_update = time.time()

    def needs_update(self) -> bool:
        """Check if item needs updating based on interval."""
        return (time.time() - self._last_update) >= self._update_interval
