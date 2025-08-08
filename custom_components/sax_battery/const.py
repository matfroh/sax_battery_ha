"""Constants for the SAX Battery integration."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntityDescription, NumberMode
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

from .enums import DeviceConstants, FormatConstants, TypeConstants
from .items import ModbusItem, SAXItem, StatusItem

DOMAIN = "sax_battery"

# Configuration constants for write access control
CONF_PILOT_FROM_HA = "pilot_from_ha"
CONF_LIMIT_POWER = "limit_power"
CONF_MAX_CHARGE = "max_charge"
CONF_MAX_DISCHARGE = "max_discharge"


@dataclass(frozen=True)
class SAXDeviceInfo:
    """Device information for SAX Battery entities."""

    name: str = "SAX Battery System"
    manufacturer: str = "SAX"
    model: str = "SAX Battery"
    sw_version: str = "1.0"


# Default device info instance
DEFAULT_DEVICE_INFO = SAXDeviceInfo()

# Configuration constants
CONF_BATTERY_COUNT = "battery_count"
CONF_POWER_SENSOR = "power_sensor_entity_id"
CONF_PF_SENSOR = "pf_sensor_entity_id"
CONF_MASTER_BATTERY = "master_battery"
CONF_DEVICE_ID = "device_id"

# Communication constants
CONF_BATTERY_ROLE = "battery_role"
CONF_SMART_METER_HOST = "smart_meter_host"
CONF_SMART_METER_PORT = "smart_meter_port"
CONF_COMMUNICATION_TYPE = "communication_type"

# Battery roles
BATTERY_ROLE_MASTER = "master"
BATTERY_ROLE_SLAVE = "slave"

# Communication types
COMM_MODBUS_TCP = "modbus_tcp"
COMM_MODBUS_RTU = "modbus_rtu"

# Polling intervals (in seconds)
BATTERY_POLL_INTERVAL = 10  # Standard battery data polling (SOC, Power, Status)
BATTERY_STATIC_POLL_INTERVAL = 300  # Static/accumulated data polling (5 minutes)
SMARTMETER_POLL_INTERVAL = 10  # Basic smart meter data polling
SMARTMETER_PHASE_POLL_INTERVAL = 60  # L1/L2/L3 phase-specific data polling

# SAX entity keys
SAX_NOMINAL_POWER = "sax_nominal_power"
SAX_NOMINAL_FACTOR = "sax_nominal_factor"
SAX_MAX_CHARGE = "sax_max_charge"
SAX_MAX_DISCHARGE = "sax_max_discharge"
SAX_STATUS = "sax_status"
SAX_BATTERY_SWITCH = "sax_battery_switch"
SAX_SOC = "sax_soc"
SAX_POWER = "sax_power"
SAX_SMARTMETER = "sax_smartmeter"
SAX_CAPACITY = "sax_capacity"
SAX_CYCLES = "sax_cycles"
SAX_TEMP = "sax_temp"
SAX_ENERGY_PRODUCED = "sax_energy_produced"
SAX_CUMULATIVE_ENERGY_PRODUCED = "sax_cumulative_energy_produced"
SAX_ENERGY_CONSUMED = "sax_energy_consumed"
SAX_CUMULATIVE_ENERGY_CONSUMED = "sax_cumulative_energy_consumed"
SAX_COMBINED_POWER = "sax_combined_power"
SAX_COMBINED_SOC = "combined_soc"

CONF_MIN_SOC = "min_soc"
CONF_PRIORITY_DEVICES = "priority_devices"
CONF_ENABLE_SOLAR_CHARGING = "enable_solar_charging"
CONF_AUTO_PILOT_INTERVAL = "auto_pilot_interval"
CONF_MANUAL_CONTROL = "manual_control"

DEFAULT_PORT = 502  # Default Modbus port
DEFAULT_MIN_SOC = 15
DEFAULT_AUTO_PILOT_INTERVAL = 60  # seconds

# Phase and smart meter constants
SAX_PHASE_CURRENTS_SUM = "phase_currents_sum"
SAX_CURRENT_L1 = "current_l1"
SAX_CURRENT_L2 = "current_l2"
SAX_CURRENT_L3 = "current_l3"
SAX_VOLTAGE_L1 = "voltage_l1"
SAX_VOLTAGE_L2 = "voltage_l2"
SAX_VOLTAGE_L3 = "voltage_l3"
SAX_AC_POWER_TOTAL = "ac_power_total"
SAX_GRID_FREQUENCY = "grid_frequency"
SAX_APPARENT_POWER = "apparent_power"
SAX_REACTIVE_POWER = "reactive_power"
SAX_POWER_FACTOR = "power_factor"
SAX_SMARTMETER_CURRENT_L1 = "smartmeter_current_l1"
SAX_SMARTMETER_CURRENT_L2 = "smartmeter_current_l2"
SAX_SMARTMETER_CURRENT_L3 = "smartmeter_current_l3"
SAX_ACTIVE_POWER_L1 = "active_power_l1"
SAX_ACTIVE_POWER_L2 = "active_power_l2"
SAX_ACTIVE_POWER_L3 = "active_power_l3"
SAX_SMARTMETER_VOLTAGE_L1 = "smartmeter_voltage_l1"
SAX_SMARTMETER_VOLTAGE_L2 = "smartmeter_voltage_l2"
SAX_SMARTMETER_VOLTAGE_L3 = "smartmeter_voltage_l3"
SAX_SMARTMETER_TOTAL_POWER = "smartmeter_total_power"
SAX_STORAGE_STATUS = "storage_status"

SOLAR_CHARGING_SWITCH = "solar_charging_switch"
MANUAL_CONTROL_SWITCH = "manual_control_switch"

# fmt: off

SYS_STATUSANZEIGE: list[StatusItem] = [
    StatusItem(number=1, text="OFF", name="system_operationmode_off"),
    StatusItem(number=3, text="Connected", name="system_operationmode_connected"),
    StatusItem(number=4, text="Standby", name="system_operationmode_standby"),
]


# Write-only register addresses that require configuration checks
WRITE_ONLY_REGISTERS = {41, 42, 43, 44}

# Register access control mapping
REGISTER_ACCESS_CONTROL = {
    41: CONF_PILOT_FROM_HA,  # SAX_NOMINAL_POWER
    42: CONF_PILOT_FROM_HA,  # SAX_NOMINAL_FACTOR
    43: CONF_LIMIT_POWER,    # SAX_MAX_DISCHARGE
    44: CONF_LIMIT_POWER,    # SAX_MAX_CHARGE
}

@dataclass(frozen=True)
class RegisterAccessConfig:
    """Configuration for register write access control."""

    pilot_from_ha: bool = False
    limit_power: bool = False
    is_master_battery: bool = False

    def can_write_register(self, address: int) -> bool:
        """Check if register can be written based on configuration.

        Args:
            address: Register address to check

        Returns:
            True if write access is allowed, False otherwise

        """
        # Only master battery can write to any register
        if not self.is_master_battery:
            return False

        # Check if register requires specific configuration
        if address not in WRITE_ONLY_REGISTERS:
            return True

        required_config = REGISTER_ACCESS_CONTROL.get(address)
        if required_config == CONF_PILOT_FROM_HA:
            return self.pilot_from_ha
        elif required_config == CONF_LIMIT_POWER:  # noqa: RET505
            return self.limit_power

        return False

    def get_entity_type(self, address: int, default_type: TypeConstants) -> TypeConstants:
        """Get appropriate entity type based on write access."""
        if self.can_write_register(address):
            return default_type

        # Convert writable types to read-only equivalents
        if default_type in (TypeConstants.NUMBER, TypeConstants.SWITCH):
            return TypeConstants.SENSOR

        return default_type

    def should_load_pilot_module(self) -> bool:
        """Determine if pilot.py module should be loaded."""
        return self.pilot_from_ha and self.is_master_battery

    def get_writable_registers(self) -> set[int]:
        """Get set of registers that are writable based on current configuration."""
        return {
            addr for addr in WRITE_ONLY_REGISTERS
            if self.can_write_register(addr)
        }

##############################################################################################################################
# Home Assistant EntityDescription
#
# class EntityDescription(metaclass=FrozenOrThawed, frozen_or_thawed=True):
#     """A class that describes Home Assistant entities."""
#
#     # This is the key identifier for this entity
#     key: str
#
#     device_class: str | None = None
#     entity_category: EntityCategory | None = None
#     entity_registry_enabled_default: bool = True
#     entity_registry_visible_default: bool = True
#     force_update: bool = False
#     icon: str | None = None
#     has_entity_name: bool = False
#     name: str | UndefinedType | None = UNDEFINED
#     translation_key: str | None = None
#     translation_placeholders: Mapping[str, str] | None = None
#     unit_of_measurement: str | None = None
#
##############################################################################################################################

##############################################################################################################################
# Home Assistant NumberEntityDescription
#
# class NumberEntityDescription(EntityDescription, frozen_or_thawed=True):
#     """A class that describes number entities."""
#
#     device_class: NumberDeviceClass | None = None
#     max_value: None = None
#     min_value: None = None
#     mode: NumberMode | None = None
#     native_max_value: float | None = None
#     native_min_value: float | None = None
#     native_step: float | None = None
#     native_unit_of_measurement: str | None = None
#     step: None = None
#     unit_of_measurement: None = None  # Type override, use native_unit_of_measurement
#
##############################################################################################################################

DESCRIPTION_SAX_MAX_CHARGE= NumberEntityDescription(
    key=SAX_MAX_CHARGE,
    name="SAX Max Charge",
    mode= NumberMode.SLIDER,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=10000,
    native_step=100,
)

DESCRIPTION_SAX_MAX_DISCHARGE= NumberEntityDescription(
    key=SAX_MAX_DISCHARGE,
    name="SAX Max Discharge",
    mode= NumberMode.SLIDER,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=10000,
    native_step=100,
)

##############################################################################################################################
# Home Assistant SensorEntityDescription
#
# class SensorEntityDescription(EntityDescription, frozen_or_thawed=True):
#     """A class that describes sensor entities."""
#
#     device_class: SensorDeviceClass | None = None
#     last_reset: datetime | None = None
#     native_unit_of_measurement: str | None = None
#     options: list[str] | None = None
#     state_class: SensorStateClass | str | None = None
#     suggested_display_precision: int | None = None
#     suggested_unit_of_measurement: str | None = None
#     unit_of_measurement: None = None  # Type override, use native_unit_of_measurement
#
##############################################################################################################################

DESCRIPTION_SAX_NOMINAL_POWER = SensorEntityDescription(
    key=SAX_NOMINAL_POWER,
    name="SAX Nominal Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,  # Maybe NUMBER
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_NOMINAL_FACTOR = SensorEntityDescription(
    key=SAX_NOMINAL_FACTOR,
    name="SAX Nominal Factor",
    device_class=SensorDeviceClass.POWER_FACTOR,
    state_class=SensorStateClass.MEASUREMENT,  # Maybe NUMBER
)

DESCRIPTION_SAX_SOC = SensorEntityDescription(
    key=SAX_SOC,
    name="SAX Battery SOC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_POWER = SensorEntityDescription(
    key=SAX_POWER,
    name="SAX Battery Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_SMARTMETER = SensorEntityDescription(
    key=SAX_SMARTMETER,
    name="SAX Battery Smartmeter",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_CAPACITY = SensorEntityDescription(
    key=SAX_CAPACITY,
    name="SAX Battery Capacity",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CYCLES = SensorEntityDescription(
    key=SAX_CYCLES,
    name="SAX Battery Cycles",
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_TEMP = SensorEntityDescription(
    key=SAX_TEMP,
    name="SAX Battery Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    suggested_display_precision=1,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
)

DESCRIPTION_SAX_BATTERY_SWITCH = SwitchEntityDescription(
    key=SAX_BATTERY_SWITCH,
    name="SAX Battery On/Off",
    icon="mdi:battery",
)

# Additional sensor descriptions...
DESCRIPTION_SAX_ENERGY_PRODUCED = SensorEntityDescription(
    key=SAX_ENERGY_PRODUCED,
    name="SAX Energy Produced",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_PRODUCED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_PRODUCED,
    name="SAX Cumulative Energy Produced",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_ENERGY_CONSUMED = SensorEntityDescription(
    key=SAX_ENERGY_CONSUMED,
    name="SAX Energy Consumed",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_CONSUMED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_CONSUMED,
    name="SAX Cumulative Energy Consumed",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_PHASE_CURRENTS_SUM = SensorEntityDescription(
    key=SAX_PHASE_CURRENTS_SUM,
    name="SAX Phase Currents Sum",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)
DESCRIPTION_SAX_CURRENT_L1 = SensorEntityDescription(
    key=SAX_CURRENT_L1,
    name="SAX Current L1",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_CURRENT_L2 = SensorEntityDescription(
    key=SAX_CURRENT_L2,
    name="SAX Current L2",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)
DESCRIPTION_SAX_CURRENT_L3 = SensorEntityDescription(
    key=SAX_CURRENT_L3,
    name="SAX Current L3",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_VOLTAGE_L1 = SensorEntityDescription(
    key=SAX_VOLTAGE_L1,
    name="SAX Voltage L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_L2 = SensorEntityDescription(
    key=SAX_VOLTAGE_L2,
    name="SAX Voltage L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_L3 = SensorEntityDescription(
    key=SAX_VOLTAGE_L3,
    name="SAX Voltage L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_AC_POWER_TOTAL = SensorEntityDescription(
    key=SAX_AC_POWER_TOTAL,
    name="SAX AC Power Total",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_GRID_FREQUENCY = SensorEntityDescription(
    key=SAX_GRID_FREQUENCY,
    name="SAX Grid Frequency",
    device_class=SensorDeviceClass.FREQUENCY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfFrequency.HERTZ,
)

DESCRIPTION_SAX_APPARENT_POWER = SensorEntityDescription(
    key=SAX_APPARENT_POWER,
    name="SAX Apparent Power",
    device_class=SensorDeviceClass.APPARENT_POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="VA",  # Volt-ampere
)

DESCRIPTION_SAX_REACTIVE_POWER = SensorEntityDescription(
    key=SAX_REACTIVE_POWER,
    name="SAX Reactive Power",
    device_class=SensorDeviceClass.REACTIVE_POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="VAR",  # Volt-ampere reactive
)

DESCRIPTION_SAX_POWER_FACTOR = SensorEntityDescription(
    key=SAX_POWER_FACTOR,
    name="SAX Power Factor",
    device_class=SensorDeviceClass.POWER_FACTOR,
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_STORAGE_STATUS = SensorEntityDescription(
    key=SAX_STORAGE_STATUS,
    name="SAX Storage Status",
    state_class=SensorStateClass.MEASUREMENT,
)
# Smart meter specific sensors
DESCRIPTION_SAX_SMARTMETER_CURRENT_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L1,
    name="SAX Smart Meter Current L1",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L2,
    name="SAX Smart Meter Current L2",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L3,
    name="SAX Smart Meter Current L3",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_ACTIVE_POWER_L1 = SensorEntityDescription(
    key=SAX_ACTIVE_POWER_L1,
    name="SAX Active Power L1",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_ACTIVE_POWER_L2 = SensorEntityDescription(
    key=SAX_ACTIVE_POWER_L2,
    name="SAX Active Power L2",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_ACTIVE_POWER_L3 = SensorEntityDescription(
    key=SAX_ACTIVE_POWER_L3,
    name="SAX Active Power L3",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L1,
    name="SAX Smart Meter Voltage L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)
DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L2,
    name="SAX Smart Meter Voltage L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L3,
    name="SAX Smart Meter Voltage L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER = SensorEntityDescription(
    key=SAX_SMARTMETER_TOTAL_POWER,
    name="SAX Smart Meter Total Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_COMBINED_POWER = SensorEntityDescription(
    key=SAX_COMBINED_POWER,
    name="SAX Combined Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_COMBINED_SOC = SensorEntityDescription(
    key=SAX_COMBINED_SOC,
    name="SAX Combined SOC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

##############################################################################################################################
# Home Assistant EntityDescription
# class SwitchEntityDescription(ToggleEntityDescription, frozen_or_thawed=True):
#     """A class that describes switch entities."""
#
#     device_class: SwitchDeviceClass | None = None
#
# CACHED_PROPERTIES_WITH_ATTR_ = {
#     "device_class",
# }


DESCRIPTION_SAX_BATTERY_SWITCH = SwitchEntityDescription(
    key=SAX_BATTERY_SWITCH,
    name="SAX Battery On/Off",
    icon="mdi:battery",
  )

DESCRIPTION_SOLAR_CHARGING_SWITCH = SwitchEntityDescription(
    key="solar_charging_switch",
    name="Solar Charging Switch",
    icon="mdi:solar-power",
)

DESCRIPTION_MANUAL_CONTROL_SWITCH = SwitchEntityDescription(
    key="manual_control_switch",
    name="Manual Control Switch",
    icon="mdi:hand",
)

##############################################################################################################################
# A parameter list that can contain the following elements:
# all of the entries are optional on general
# "min": The lowest allowed value of the entity that can be set by the user if read/write.
#        Not needed for SENSOR, SELECT, SENSOR_CALC
# "dynamic_min": The translation key of another entity of this integration. The content of this entity will be used as min val
# "max": The highest allowed value of the entity that can be set by the user if read/write.
#        Not needed for SENSOR, SELECT, SENSOR_CALC
# "dynamic_max": The translation key of another entity of this integration. The content of this entity will be used as max val
# "step": the step when entity is r/w, values can only be set according this step
# "divider": On modbus, values usually are coded as int. To get the real float number,
#            the modbus value has to be divided by this value
# "precision": number of digits after the decimal point
# "icon": The icon name as it is used in Home Assistant
#
# For SENSOR_CALC only:
# "val_1" .. "val_8": translation keys of other entities that should be used to calculate the value of this entity
# "calculation": A string that can be used by the eval() command to calculate the sensor value. All Python operations
#                and the variables val_0 .. val_8 can be used here
#                The value of the modbus address of the entity itself is available in val_0
##############################################################################################################################

PARAMS_SAX_TEMP: dict = {
    "min": 16,
    "max": 28,
    "step": 0.5,
    "divider": 10,
    "precision": 1,
}

PARAMS_SAX_COMBINED_POWER: dict = {
    "min": 0,
    "max": 999999999999,
    "val_0": "power battery A",
    "val_1": "power battery B",
    "val_2": "power battery C",
    "calculation": "val_0 + val_1 + val_2",
}

PARAMS_SAX_CUMULATIVE_ENERGY: dict = {
    "min": 0,
    "max": 999999999999,
    "val_0": "energy battery A",
    "val_1": "energy battery B",
    "val_2": "energy battery C",
    "calculation": "val_0 + val_1 + val_2",
}

PARAMS_SAX_COMBINED_SOC: dict = {
    "min": 0,
    "max": 100,
    "val_0": "SOC battery A",
    "val_1": "SOC battery B",
    "val_2": "SOC battery C",
    "val_3": "Number of batteries",
    "calculation": "(val_0 + val_1 + val_2)/val_3",
}


# Battery registers (slave 64)
BATTERY_REGISTERS = {
    SAX_STATUS: {"address": 45, "slave": 64, "type": "holding"},
    SAX_SOC: {"address": 46, "slave": 64, "type": "holding"},
    SAX_POWER: {"address": 47, "slave": 64, "type": "holding", "offset": -16384},
    SAX_SMARTMETER: {"address": 48, "slave": 64, "type": "holding", "offset": -16384},
}

# Smart meter registers (slave 40)
SMARTMETER_REGISTERS = {
    SAX_CAPACITY: {"address": 40115, "slave": 40, "type": "holding", "scale": 10},
    SAX_CYCLES: {"address": 40116, "slave": 40, "type": "holding"},
    SAX_TEMP: {"address": 40117, "slave": 40, "type": "holding"},
    SAX_ENERGY_PRODUCED: {"address": 40096, "slave": 40, "type": "holding"},
    SAX_ENERGY_CONSUMED: {"address": 40097, "slave": 40, "type": "holding"},
    SAX_PHASE_CURRENTS_SUM: {"address": 40073, "slave": 40, "type": "holding", "scale": 0.01},
    SAX_CURRENT_L1: {"address": 40074, "slave": 40, "type": "holding", "scale": 0.01},
    SAX_CURRENT_L2: {"address": 40075, "slave": 40, "type": "holding", "scale": 0.01},
    SAX_CURRENT_L3: {"address": 40076, "slave": 40, "type": "holding", "scale": 0.01},
    SAX_VOLTAGE_L1: {"address": 40081, "slave": 40, "type": "holding", "scale": 0.1},
    SAX_VOLTAGE_L2: {"address": 40082, "slave": 40, "type": "holding", "scale": 0.1},
    SAX_VOLTAGE_L3: {"address": 40083, "slave": 40, "type": "holding", "scale": 0.1},
    SAX_SMARTMETER_TOTAL_POWER: {"address": 40110, "slave": 40, "type": "holding"},
}

# fmt: off

##############################################################################################################################
# Modbus Register List:                                                                                                      #
# https://docs.google.com/spreadsheets/d/1EZ3QgyB41xaXo4B5CfZe0Pi8KPwzIGzK/edit?gid=1730751621#gid=1730751621                #
##############################################################################################################################

##############################################################################################################################
# Here are some lists that represent the entities of each device that will be created.
# Every list contains of some ModbusItem objects that have a constructor with the following parameters:
#
# address: The Modbus address as it is mentioned in the sax battery documentation
# name:    The entity name. Please note: This entry today only is used to automatically generate translation files.
#          It will be removed in future versions
# mformat: One of the formats defined in FORMATS as they are TEMPERATURE, PERCENTAGE, NUMBER, STATUS or UNKNOWN (should be removed in future versions).
#          The format is used to control the conversion of the modbus register entry to the entity variable and back
# mtype:   The type of entity. Currently supported are:
#              SENSOR: A standard sensor entity
#              SENSOR_CALC: A "calculated" sensor. That means, the content of this entity is derived from other entities
#                           of this integration. The definition of the calculation is done in params
#              SELECT: A select entity
#              NUMBER: A number entity. The value of this entity can be changed by the user interface
#              NUMBER_RO: In principle, this is also a number entity that ir writable. But to avoid damages
#                         we decided to make this entity read only.
# device: The device this entity is assigned to. Devices are used here to group the entities in a meaningful way
# entitydescription: The entity description that is used to create the Home Assistant entity.
# params: Parameters to control the behavior of the entity, see description of the params lists
# translation_key: The identifier that points to the right translation key. Therefore, the files strings.json and the
#                  language specific files in the subfolder "translations" have to be up-to-date
##############################################################################################################################

# Entity descriptions for read-only versions
DESCRIPTION_SAX_NOMINAL_POWER_RO = SensorEntityDescription(
    key=f"{SAX_NOMINAL_POWER}_ro",
    name="SAX Nominal Power (Read Only)",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_NOMINAL_FACTOR_RO = SensorEntityDescription(
    key=f"{SAX_NOMINAL_FACTOR}_ro",
    name="SAX Nominal Factor (Read Only)",
    device_class=SensorDeviceClass.POWER_FACTOR,
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_MAX_DISCHARGE_RO = SensorEntityDescription(
    key=f"{SAX_MAX_DISCHARGE}_ro",
    name="SAX Max Discharge (Read Only)",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_MAX_CHARGE_RO = SensorEntityDescription(
    key=f"{SAX_MAX_CHARGE}_ro",
    name="SAX Max Charge (Read Only)",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

# Updated battery items with dynamic entity types based on configuration
def get_battery_realtime_items(access_config: RegisterAccessConfig) -> list[ModbusItem]:
    """Get battery realtime items with proper entity types based on configuration."""
    return [
        ModbusItem(
            battery_slave_id=64,
            address=41,
            name=SAX_NOMINAL_POWER,
            mformat=FormatConstants.NUMBER,
            mtype=access_config.get_entity_type(41, TypeConstants.NUMBER),
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_POWER
        ),
        ModbusItem(
            battery_slave_id=64,
            address=42,
            name=SAX_NOMINAL_FACTOR,
            mformat=FormatConstants.NUMBER,
            mtype=access_config.get_entity_type(42, TypeConstants.NUMBER),
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_FACTOR
        ),
        ModbusItem(
            battery_slave_id=64,
            address=43,
            name=SAX_MAX_DISCHARGE,
            mformat=FormatConstants.NUMBER,
            mtype=access_config.get_entity_type(43, TypeConstants.NUMBER),
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_MAX_DISCHARGE
        ),
        ModbusItem(
            battery_slave_id=64,
            address=44,
            name=SAX_MAX_CHARGE,
            mformat=FormatConstants.NUMBER,
            mtype=access_config.get_entity_type(44, TypeConstants.NUMBER),
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_MAX_CHARGE
        ),
        ModbusItem(
            battery_slave_id=64,
            address=45,
            name=SAX_BATTERY_SWITCH,
            mformat=FormatConstants.STATUS,
            mtype=access_config.get_entity_type(45, TypeConstants.SWITCH),
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_BATTERY_SWITCH,
            resultlist=SYS_STATUSANZEIGE
        ),
        ModbusItem(
            battery_slave_id=64,
            address=46,
            name=SAX_SOC,
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_SOC
        ),
        ModbusItem(
            battery_slave_id=64,
            address=47,
            name=SAX_POWER,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_POWER
        ),
        ModbusItem(
            battery_slave_id=64,
            address=48,
            name=SAX_SMARTMETER,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_SMARTMETER
        ),
    ]

def create_register_access_config(config_data: dict[str, Any], is_master: bool = False) -> RegisterAccessConfig:
    """Create RegisterAccessConfig from configuration data.

    Args:
        config_data: Configuration dictionary
        is_master: Whether this is the master battery

    Returns:
        RegisterAccessConfig instance

    """
    return RegisterAccessConfig(
        pilot_from_ha=config_data.get(CONF_PILOT_FROM_HA, False),
        limit_power=config_data.get(CONF_LIMIT_POWER, False),
        is_master_battery=is_master
    )

def should_load_pilot_module(config_data: dict[str, Any], is_master: bool = False) -> bool:
    """Determine if pilot.py module should be loaded based on configuration."""
    access_config = create_register_access_config(config_data, is_master)
    return access_config.should_load_pilot_module()

def get_writable_registers(config_data: dict[str, Any], is_master: bool = False) -> set[int]:
    """Get set of registers that are writable based on current configuration."""
    access_config = create_register_access_config(config_data, is_master)
    return access_config.get_writable_registers()

def validate_write_access(address: int, config_data: dict[str, Any], is_master: bool = False) -> bool:
    """Validate if a write operation to a register is allowed."""
    access_config = create_register_access_config(config_data, is_master)
    return access_config.can_write_register(address)

def get_modbus_battery_items(config_data: dict[str, Any], is_master: bool = False) -> list[ModbusItem]:
    """Get all battery modbus items with proper configuration."""
    access_config = create_register_access_config(config_data, is_master)

    return (
        get_battery_realtime_items(access_config) +
        MODBUS_BATTERY_STATIC_ITEMS +
        MODBUS_BATTERY_SMARTMETER_ITEMS
    )

# Configuration validation helpers
def validate_configuration(config_data: dict[str, Any]) -> list[str]:
    """Validate configuration and return list of warnings/errors."""
    warnings = []

    pilot_from_ha = config_data.get(CONF_PILOT_FROM_HA, False)
    limit_power = config_data.get(CONF_LIMIT_POWER, False)

    if not pilot_from_ha:
        warnings.append(
            "Pilot control disabled: Registers 41 (Nominal Power) and 42 (Nominal Factor) not writeable"
        )

    if not limit_power:
        warnings.append(
            "Power limiting disabled: Registers 43 (Max Discharge) and 44 (Max Charge) not writeable"
        )

    if not pilot_from_ha and not limit_power:
        warnings.append(
            "All write operations disabled: System is in monitoring-only mode"
        )

    return warnings


# Configuration defaults with descriptions
DEFAULT_CONFIG = {
    CONF_PILOT_FROM_HA: False,  # Disable pilot control by default for safety
    CONF_LIMIT_POWER: False,    # Disable power limiting by default for safety
    CONF_MAX_CHARGE: 3500,      # Default max charge power (W)
    CONF_MAX_DISCHARGE: 4600,   # Default max discharge power (W)
}

CONFIG_DESCRIPTIONS = {
    CONF_PILOT_FROM_HA: "Enable Home Assistant pilot control (allows writing to registers 41, 42)",
    CONF_LIMIT_POWER: "Enable power limiting control (allows writing to registers 43, 44)",
    CONF_MAX_CHARGE: "Maximum charge power limit (Watts)",
    CONF_MAX_DISCHARGE: "Maximum discharge power limit (Watts)",
}

# Battery items - static/accumulated data (polled at lower frequency)
MODBUS_BATTERY_STATIC_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40115, name=SAX_CAPACITY, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CAPACITY),
    ModbusItem(battery_slave_id=40, address=40116, name=SAX_CYCLES, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CYCLES),
    ModbusItem(battery_slave_id=40, address=40117, name=SAX_TEMP, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_TEMP),
    ModbusItem(battery_slave_id=40, address=40096, name=SAX_ENERGY_PRODUCED, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_PRODUCED),
    ModbusItem(battery_slave_id=40, address=40097, name=SAX_ENERGY_CONSUMED, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_CONSUMED),
]
# Battery items - smart meter data accessed through battery (polled at standard interval)
MODBUS_BATTERY_SMARTMETER_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40073, name=SAX_PHASE_CURRENTS_SUM, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_PHASE_CURRENTS_SUM),
    ModbusItem(battery_slave_id=40, address=40103, name=SAX_ACTIVE_POWER_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ACTIVE_POWER_L1),
    ModbusItem(battery_slave_id=40, address=40104, name=SAX_ACTIVE_POWER_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS,entitydescription=DESCRIPTION_SAX_ACTIVE_POWER_L2),
    ModbusItem(battery_slave_id=40, address=40105, name=SAX_ACTIVE_POWER_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS,entitydescription=DESCRIPTION_SAX_ACTIVE_POWER_L3),
    ModbusItem(battery_slave_id=40, address=40074, name=SAX_CURRENT_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L1),
    ModbusItem(battery_slave_id=40, address=40075, name=SAX_CURRENT_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L2),
    ModbusItem(battery_slave_id=40, address=40076, name=SAX_CURRENT_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L3),
    ModbusItem(battery_slave_id=40, address=40081, name=SAX_VOLTAGE_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L1),
    ModbusItem(battery_slave_id=40, address=40082, name=SAX_VOLTAGE_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L2),
    ModbusItem(battery_slave_id=40, address=40083, name=SAX_VOLTAGE_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L3),
    ModbusItem(battery_slave_id=40, address=40085, name=SAX_AC_POWER_TOTAL, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_AC_POWER_TOTAL),
    ModbusItem(battery_slave_id=40, address=40087, name=SAX_GRID_FREQUENCY, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS,entitydescription=DESCRIPTION_SAX_GRID_FREQUENCY),
    ModbusItem(battery_slave_id=40, address=40089, name=SAX_APPARENT_POWER, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_APPARENT_POWER),
    ModbusItem(battery_slave_id=40, address=40091, name=SAX_REACTIVE_POWER, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_REACTIVE_POWER),
    ModbusItem(battery_slave_id=40, address=40093, name=SAX_POWER_FACTOR, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_POWER_FACTOR),
    ModbusItem(battery_slave_id=40, address=40099, name=SAX_STORAGE_STATUS, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_STORAGE_STATUS),
]

# Smart meter items - basic data (polled at standard interval)
MODBUS_SMARTMETER_BASIC_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40110, name=SAX_SMARTMETER_TOTAL_POWER, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER),
]
# Smart meter items - phase-specific data (polled at lower frequency)
MODBUS_SMARTMETER_PHASE_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40100, name=SAX_SMARTMETER_CURRENT_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L1),
    ModbusItem(battery_slave_id=40, address=40101, name=SAX_SMARTMETER_CURRENT_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L2),
    ModbusItem(battery_slave_id=40, address=40102, name=SAX_SMARTMETER_CURRENT_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L3),
    ModbusItem(battery_slave_id=40, address=40107, name=SAX_SMARTMETER_VOLTAGE_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1),
    ModbusItem(battery_slave_id=40, address=40108, name=SAX_SMARTMETER_VOLTAGE_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2),
    ModbusItem(battery_slave_id=40, address=40109, name=SAX_SMARTMETER_VOLTAGE_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3),
]

# Aggregated items - calculated values (e.g., combined power) from all available batteries
AGGREGATED_ITEMS: list[SAXItem] = [
    SAXItem(name=SAX_CUMULATIVE_ENERGY_PRODUCED, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_PRODUCED, params=PARAMS_SAX_CUMULATIVE_ENERGY),
    SAXItem(name=SAX_CUMULATIVE_ENERGY_CONSUMED, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_CONSUMED, params=PARAMS_SAX_CUMULATIVE_ENERGY),
    SAXItem(name=SAX_COMBINED_POWER, mformat=FormatConstants.NUMBER, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_COMBINED_POWER, params=PARAMS_SAX_COMBINED_POWER),
    SAXItem(name=SAX_COMBINED_SOC, mformat=FormatConstants.PERCENTAGE, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_COMBINED_SOC, params=PARAMS_SAX_COMBINED_SOC),
]

# Pilot items - switches for manual control and solar charging
PILOT_ITEMS: list[SAXItem] = [
    SAXItem(name=SOLAR_CHARGING_SWITCH, mformat=FormatConstants.STATUS, mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SOLAR_CHARGING_SWITCH),
    SAXItem(name=MANUAL_CONTROL_SWITCH, mformat=FormatConstants.STATUS, mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_MANUAL_CONTROL_SWITCH),
]
# fmt: on
