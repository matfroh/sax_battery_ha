"""Enum constants for SAX Battery integration."""

from __future__ import annotations

from enum import Enum


class TypeConstants(Enum):
    """Types for Modbus items."""

    SENSOR = "Sensor"
    SENSOR_CALC = "Sensor_Calc"
    SELECT = "Select"
    SWITCH = "Switch"
    NUMBER = "Number"
    NUMBER_RO = "Number_RO"


class FormatConstants(Enum):
    """Format constants for Modbus items."""

    TEMPERATURE = "temperature"  # redundant - should be removed
    PERCENTAGE = "percentage"  # redundant - should be removed
    NUMBER = "number"
    STATUS = "status"
    UNKNOWN = "unknown"


class DeviceConstants(Enum):
    """Device constants."""

    SYS = "dev_battery"
    SM = "dev_smartmeter"
    UK = "dev_unknown"
