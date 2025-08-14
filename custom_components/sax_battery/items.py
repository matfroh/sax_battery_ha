"""Item classes for SAX Battery integration."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
import logging
from typing import Any

from pymodbus.client.mixin import ModbusClientMixin  # For DATATYPE

from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import PERCENTAGE

from .enums import DeviceConstants, TypeConstants

_LOGGER = logging.getLogger(__name__)


@dataclass
class StatusItem:
    """Status item for result lists."""

    number: int = 0  # default value for status (we use value 1,3,4)
    text: str = ""
    name: str = ""  # translation_key


@dataclass
class BaseItem(ABC):
    """Base class for all items."""

    name: str
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


@dataclass
class ModbusItem(BaseItem):
    """Modbus-specific item with enhanced functionality."""

    address: int = 0
    battery_slave_id: int = 0
    data_type: ModbusClientMixin.DATATYPE = ModbusClientMixin.DATATYPE.INT16
    divider: float = 1.0
    offset: int = 0
    entitydescription: (
        SensorEntityDescription
        | NumberEntityDescription
        | SwitchEntityDescription
        | None
    ) = None
    resultlist: list[StatusItem] = field(default_factory=list)

    def convert_raw_value(self, raw_value: int) -> float:
        """Convert raw modbus value to real value using entitydescription or defaults."""
        # Always apply signed 16-bit conversion for sensors
        if (self.mtype == TypeConstants.SENSOR and raw_value > 32767) or (
            self.entitydescription
            and getattr(self.entitydescription, "device_class", None)
            == SensorDeviceClass.POWER
        ):
            if raw_value > 32767:
                raw_value -= 65536

        value = raw_value / self.divider if self.divider else raw_value

        # Apply precision if available
        precision = getattr(self.entitydescription, "suggested_display_precision", None)
        if precision is not None:
            return round(value, precision)
        return value

    def convert_to_raw_value(self, value: float) -> int:
        """Convert real value to raw modbus value using entitydescription or defaults."""
        raw_value = int(value * self.divider)

        min_value = getattr(self.entitydescription, "native_min_value", None)
        max_value = getattr(self.entitydescription, "native_max_value", None)
        unit = getattr(self.entitydescription, "native_unit_of_measurement", None)
        device_class = getattr(self.entitydescription, "device_class", None)

        # Clamp value for percentage
        if unit == PERCENTAGE:
            raw_value = max(0, min(100, raw_value))
        # Clamp value for signed 16-bit if power or sensor
        elif (
            device_class == SensorDeviceClass.POWER
            or self.mtype == TypeConstants.SENSOR
        ):
            raw_value = max(-32768, min(32767, raw_value))
        # Clamp using entitydescription min/max if available
        if min_value is not None and max_value is not None:
            raw_value = max(int(min_value), min(int(max_value), raw_value))

        return raw_value


@dataclass
class SAXItem(BaseItem):
    """SAX item for calculated sensors and pilot controls."""

    entitydescription: (
        SensorEntityDescription
        | NumberEntityDescription
        | SwitchEntityDescription
        | None
    ) = None
    _calculation_compiled: Any = field(default=None, init=False)
    _calculation_source: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize compiled calculation after object creation."""
        if self.mtype == TypeConstants.SENSOR_CALC and not self.name.endswith(
            "(Calculated)"
        ):
            self.name = f"{self.name} (Calculated)"
        if self.params and "calculation" in self.params:
            calculation_source = self.params["calculation"]
            if isinstance(calculation_source, str):
                self._calculation_source = calculation_source
                try:
                    # Use compile for calculation expressions
                    self._calculation_compiled = compile(
                        calculation_source, "calculation", "eval"
                    )
                except SyntaxError as exc:
                    _LOGGER.warning(
                        "Syntax error in calculation %s: %s", calculation_source, exc
                    )
                    self._calculation_compiled = None
            else:
                _LOGGER.warning(
                    "Calculation parameter must be a string, got %s",
                    type(calculation_source),
                )
                self._calculation_compiled = None

    def calculate_value(
        self, coordinator_values: dict[str, float | None], val_0: float | None = None
    ) -> float | None:
        """Calculate sensor value from other entity values.

        Args:
            coordinator_values: Dictionary mapping parameter keys to values from coordinator
            val_0: Optional direct value (typically the modbus register value)

        Returns:
            Calculated value or None if calculation fails

        """
        if not self._calculation_source or not self._calculation_compiled:
            return None

        if not self.params:
            return None

        # Build variables dictionary for calculation
        calculation_vars: dict[str, float] = {}

        # Add val_0 if provided
        if val_0 is not None:
            calculation_vars["val_0"] = val_0

        # Process val_1 through val_8 from params
        for i in range(1, 9):
            param_key = f"val_{i}"
            if param_key in self._calculation_source:
                entity_key = self.params.get(param_key)
                if entity_key and entity_key in coordinator_values:
                    value = coordinator_values[entity_key]
                    if value is not None:
                        calculation_vars[param_key] = value
                    else:
                        # Missing required variable
                        _LOGGER.debug(
                            "Missing value for %s in calculation %s",
                            entity_key,
                            self.name,
                        )
                        return None

        # Special handling for "power" variable if referenced
        if "power" in self._calculation_source and "power" in coordinator_values:
            power_value = coordinator_values["power"]
            if power_value is not None:
                calculation_vars["power"] = power_value

        try:
            # Use eval with restricted globals for security
            allowed_names = {"__builtins__": {}, **calculation_vars}
            result = eval(self._calculation_compiled, allowed_names, calculation_vars)  # noqa: S307

            if isinstance(result, (int, float)):
                # Apply precision rounding if available
                precision = getattr(
                    self.entitydescription, "suggested_display_precision", None
                )
                if precision is not None:
                    return float(round(float(result), precision))
                return float(result)
            else:  # noqa: RET505
                _LOGGER.warning(
                    "Calculation returned non-numeric result: %s for %s",
                    type(result),
                    self.name,
                )
                return None

        except ZeroDivisionError:
            _LOGGER.debug("Division by zero in calculation for %s", self.name)
            return None
        except NameError as exc:
            _LOGGER.warning(
                "Variable not defined in calculation %s: %s",
                self._calculation_source,
                exc,
            )
            return None
        except (TypeError, ValueError) as exc:
            _LOGGER.warning("Invalid calculation for %s: %s", self.name, exc)
            return None
        except Exception as exc:  # Catch any other calculation errors  # noqa: BLE001
            _LOGGER.error("Unexpected error in calculation for %s: %s", self.name, exc)
            return None
