"""Enum constants for SAX Battery integration."""

from __future__ import annotations

from enum import Enum


class DeviceConstants(Enum):
    """Device type constants."""

    SYS = "cluster"  # device handles entities for batteries
    SM = "smartmeter"  # always one smart meter
    BESS = "battery"  # One or more batteries [1..3]


# fmt: off
# Modbus data model
# Modbus defines its data model based on a series of tables of four primary types:
#
# Primary tables         | Master | Slave  | Size                   | Features
#                        | Access | Access |                        |
#------------------------|--------|--------|------------------------|--------------------------------
# Discrete input         | R      | R/W    | 1 bit (0-1)            | Read on/off value
# Coil (discrete output) | R      | R/W    | 1 bit (0-1)            | Read/Write on/off value
# Input register         | R      | R/W    | 16 bit words (0-65535) | Read measurements and statuses
# Holding register       | R/W    | R/W    | 16 bit words (0-65535) | Read/Write configuration values
#------------------------|--------|------------------------|-----------------------------------------
#
# Note: SAX Battery write only registers 41, 42, 43, 44. These registers are not readable.
#
# SAX Battery Modbus commands:
# 03 (0x03) Read Multiple Holding Registers
# 16 (0x10) Write Multiple Holding Registers
#
# fmt: on


class TypeConstants(Enum):  # item types -> not home assistant types
    """Modbus type constants mapped to Home Assistant entity types."""

    SENSOR = "sensor"  # holding read only
    SENSOR_CALC = "sensor_calc"  # none
    NUMBER = "number"  # holding read/write
    NUMBER_RO = "number_ro"  # holding read only
    NUMBER_WO = "number_wo"  # holding write only -> holding registers 41, 42, 43, 44
    SWITCH = "switch"  # holding  on (02),off (01) values for write, read battery status values off (01), on (02), connected (03), standby (04)
