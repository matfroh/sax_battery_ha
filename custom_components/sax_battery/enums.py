"""Enum constants for SAX Battery integration."""

from __future__ import annotations

from enum import Enum


class DeviceConstants(Enum):
    """Device type constants."""

    SYS = "sys"  # One or more batteries [1..3]
    SM = "sm"  # always one smart meter
    UNKNOWN = "unknown"


# fmt: off
# Modbus data model
# Modbus defines its data model based on a series of tables of four primary types:
#
# Primary tables	       | Access | Size                   | Features
#------------------------|--------|------------------------|---------------------------------
# Discrete input	     | R      | 1 bit (01)            | Read on/off value
# Coil (discrete output) | R/W    | 1 bit (01)            | Read/Write on/off value
# Input register	     | R      | 16 bit words (065,535)| Read measurements and statuses
# Holding register	     | R/W    | 16 bit words (065,535)| Read/Write configuration values
# fmt: on


class FormatConstants(Enum):  # modbus format -> not home assistant formats
    """Modbus format constants for data adaptation."""

    PERCENTAGE = "percentage"
    TEMPERATURE = "temperature"
    NUMBER = "number"
    STATUS = "status"
    UNKNOWN = "unknown"  # Used for error scenarios which should not happen e.g. uninitialized items


class TypeConstants(Enum):  # item types -> not home assistant types
    """Modbus type constants mapped to Home Assistant entity types."""

    SENSOR = "sensor"
    SENSOR_CALC = "sensor_calc"
    NUMBER = "number"
    NUMBER_RO = "number_ro"
    SWITCH = "switch"
    BINARY_SENSOR = "binary_sensor"
    SELECT = "select"
