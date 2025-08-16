"""Constants for the SAX Battery integration."""

from dataclasses import dataclass

from pymodbus.client.mixin import ModbusClientMixin  # For DATATYPE

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

from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem, SAXItem, StatusItem

DOMAIN = "sax_battery"

# Configuration constants for write access control
CONF_PILOT_FROM_HA = "pilot_from_ha"
CONF_LIMIT_POWER = "limit_power"
CONF_MAX_CHARGE = "max_charge"
CONF_MAX_DISCHARGE = "max_discharge"

# Battery limits per individual battery unit
LIMIT_MAX_CHARGE_PER_BATTERY = 3500  # Watts per battery
LIMIT_MAX_DISCHARGE_PER_BATTERY = 4600  # Watts per battery

# Legacy constants for backward compatibility
LIMIT_MAX_CHARGE = LIMIT_MAX_CHARGE_PER_BATTERY  # Single battery default
LIMIT_MAX_DISCHARGE = LIMIT_MAX_DISCHARGE_PER_BATTERY  # Single battery default

# Maximum supported batteries in a system
MAX_SUPPORTED_BATTERIES = 3


@dataclass(frozen=True)
class SAXDeviceInfo:
    """SAX device information."""

    manufacturer: str = "SAX"
    model: str = "Battery System"
    sw_version: str = "1.0"


# Default device info instance
DEFAULT_DEVICE_INFO = SAXDeviceInfo()

# Configuration constants
CONF_BATTERY_COUNT = "battery_count"
CONF_POWER_SENSOR = "power_sensor_entity_id"
CONF_PF_SENSOR = "pf_sensor_entity_id"
CONF_MASTER_BATTERY = "master_battery"
CONF_DEVICE_ID = "device_id"

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

# Write-only register addresses that require configuration checks
WRITE_ONLY_REGISTERS = {41, 42, 43, 44}

# Register access control mapping
REGISTER_ACCESS_CONTROL = {
    41: CONF_PILOT_FROM_HA,
    42: CONF_PILOT_FROM_HA,
    43: CONF_LIMIT_POWER,
    44: CONF_LIMIT_POWER,
}


# fmt: off

SYS_STATUSANZEIGE: list[StatusItem] = [
    StatusItem(number=1, text="OFF", name="system_operationmode_off"),
    StatusItem(number=3, text="Connected", name="system_operationmode_connected"),
    StatusItem(number=4, text="Standby", name="system_operationmode_standby"),
]

# Entity descriptions - keeping existing ones...
DESCRIPTION_SAX_MAX_CHARGE = NumberEntityDescription(
    key=SAX_MAX_CHARGE,
    name="Sax Max Charge",
    mode=NumberMode.SLIDER,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=LIMIT_MAX_CHARGE_PER_BATTERY,
    native_step=100,
)

DESCRIPTION_SAX_MAX_DISCHARGE = NumberEntityDescription(
    key=SAX_MAX_DISCHARGE,
    name="Sax Max Discharge",
    mode=NumberMode.SLIDER,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=LIMIT_MAX_DISCHARGE_PER_BATTERY,
    native_step=100,
)
DESCRIPTION_SAX_NOMINAL_POWER = SensorEntityDescription(
    key=SAX_NOMINAL_POWER,
    name="Sax Nominal Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,  # Maybe NUMBER
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_NOMINAL_FACTOR = SensorEntityDescription(
    key=SAX_NOMINAL_FACTOR,
    name="Sax Nominal Factor",
    device_class=SensorDeviceClass.POWER_FACTOR,
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_SOC = SensorEntityDescription(
    key=SAX_SOC,
    name="Sax SOC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_POWER = SensorEntityDescription(
    key=SAX_POWER,
    name="Sax Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_SMARTMETER = SensorEntityDescription(
    key=SAX_SMARTMETER,
    name="Sax Smartmeter",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_CAPACITY = SensorEntityDescription(
    key=SAX_CAPACITY,
    name="Sax Capacity",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CYCLES = SensorEntityDescription(
    key=SAX_CYCLES,
    name="Sax Cycles",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="",
)

DESCRIPTION_SAX_TEMP = SensorEntityDescription(
    key=SAX_TEMP,
    name="Sax Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    suggested_display_precision=1,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
)

# Battery switches

DESCRIPTION_SAX_BATTERY_SWITCH = SwitchEntityDescription(
    key=SAX_BATTERY_SWITCH,
    name="Sax On/Off",
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

# Additional sensor descriptions...
DESCRIPTION_SAX_ENERGY_PRODUCED = SensorEntityDescription(
    key=SAX_ENERGY_PRODUCED,
    name="Sax Energy Produced",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_PRODUCED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_PRODUCED,
    name="Sax Cumulative Energy Produced",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_ENERGY_CONSUMED = SensorEntityDescription(
    key=SAX_ENERGY_CONSUMED,
    name="Sax Energy Consumed",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_CONSUMED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_CONSUMED,
    name="Sax Cumulative Energy Consumed",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_PHASE_CURRENTS_SUM = SensorEntityDescription(
    key=SAX_PHASE_CURRENTS_SUM,
    name="Sax Phase Currents Sum",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)
DESCRIPTION_SAX_CURRENT_L1 = SensorEntityDescription(
    key=SAX_CURRENT_L1,
    name="Sax Current L1",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_CURRENT_L2 = SensorEntityDescription(
    key=SAX_CURRENT_L2,
    name="Sax Current L2",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)
DESCRIPTION_SAX_CURRENT_L3 = SensorEntityDescription(
    key=SAX_CURRENT_L3,
    name="Sax Current L3",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_VOLTAGE_L1 = SensorEntityDescription(
    key=SAX_VOLTAGE_L1,
    name="Sax Voltage L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_L2 = SensorEntityDescription(
    key=SAX_VOLTAGE_L2,
    name="Sax Voltage L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_L3 = SensorEntityDescription(
    key=SAX_VOLTAGE_L3,
    name="Sax Voltage L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_AC_POWER_TOTAL = SensorEntityDescription(
    key=SAX_AC_POWER_TOTAL,
    name="Sax AC Power Total",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_GRID_FREQUENCY = SensorEntityDescription(
    key=SAX_GRID_FREQUENCY,
    name="Sax Grid Frequency",
    device_class=SensorDeviceClass.FREQUENCY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfFrequency.HERTZ,
)

DESCRIPTION_SAX_APPARENT_POWER = SensorEntityDescription(
    key=SAX_APPARENT_POWER,
    name="Sax Apparent Power",
    device_class=SensorDeviceClass.APPARENT_POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="VA",  # Volt-Ampere
)

DESCRIPTION_SAX_REACTIVE_POWER = SensorEntityDescription(
    key=SAX_REACTIVE_POWER,
    name="Sax Reactive Power",
    device_class=SensorDeviceClass.REACTIVE_POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="VAR",  # Volt-Ampere reactive
)

DESCRIPTION_SAX_POWER_FACTOR = SensorEntityDescription(
    key=SAX_POWER_FACTOR,
    name="Sax Power Factor",
    device_class=SensorDeviceClass.POWER_FACTOR,
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_STORAGE_STATUS = SensorEntityDescription(
    key=SAX_STORAGE_STATUS,
    name="Sax Storage Status",
    state_class=SensorStateClass.MEASUREMENT,
)
# Smart meter specific sensors
DESCRIPTION_SAX_SMARTMETER_CURRENT_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L1,
    name="Sax Smart Meter Current L1",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L2,
    name="Sax Smart Meter Current L2",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L3,
    name="Sax Smart Meter Current L3",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_ACTIVE_POWER_L1 = SensorEntityDescription(
    key=SAX_ACTIVE_POWER_L1,
    name="Sax Active Power L1",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_ACTIVE_POWER_L2 = SensorEntityDescription(
    key=SAX_ACTIVE_POWER_L2,
    name="Sax Active Power L2",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_ACTIVE_POWER_L3 = SensorEntityDescription(
    key=SAX_ACTIVE_POWER_L3,
    name="Sax Active Power L3",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L1,
    name="Sax Smart Meter Voltage L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)
DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L2,
    name="Sax Smart Meter Voltage L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L3,
    name="Sax Smart Meter Voltage L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER = SensorEntityDescription(
    key=SAX_SMARTMETER_TOTAL_POWER,
    name="Sax Smart Meter Total Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_COMBINED_POWER = SensorEntityDescription(
    key=SAX_COMBINED_POWER,
    name="Sax Combined Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_COMBINED_SOC = SensorEntityDescription(
    key=SAX_COMBINED_SOC,
    name="Sax Combined SOC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)


# fmt: off
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
# "factor": On modbus, values usually are coded as int. To get the real float number,
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
    "factor": 10,
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

# fmt: off

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

# Battery items read-only versions
MODBUS_BATTERY_REALTIME_ITEMS: list[ModbusItem] = [
        ModbusItem(battery_slave_id=64, address=46, name=SAX_SOC, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_SOC,),
        ModbusItem(battery_slave_id=64, address=47, name=SAX_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_POWER,),
]

# Battery items read-only versions
MODBUS_BATTERY_PILOT_ITEMS: list[ModbusItem] = [
        ModbusItem(battery_slave_id=64, address=43, name=SAX_MAX_CHARGE, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MAX_CHARGE,),
        ModbusItem(battery_slave_id=64, address=44, name=SAX_MAX_DISCHARGE, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MAX_DISCHARGE,),
]

# Battery items - switch
MODBUS_BATTERY_SWITCH_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=64, address=45, name=SAX_STATUS, mtype=TypeConstants.SWITCH, data_type=ModbusClientMixin.DATATYPE.INT16, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_BATTERY_SWITCH,),
]

# Battery items - static/accumulated data (polled at lower frequency)
MODBUS_BATTERY_STATIC_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40117, name=SAX_TEMP, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_TEMP,),
    ModbusItem(battery_slave_id=40, address=40115, name=SAX_CAPACITY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=10.0 ,device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CAPACITY),
    ModbusItem(battery_slave_id=40, address=40116, name=SAX_CYCLES,  mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CYCLES),
    ModbusItem(battery_slave_id=40, address=40096, name=SAX_ENERGY_PRODUCED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_PRODUCED),
    ModbusItem(battery_slave_id=40, address=40097, name=SAX_ENERGY_CONSUMED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_CONSUMED),
]
# Battery items - smart meter data accessed through battery (polled at standard interval)
MODBUS_BATTERY_SMARTMETER_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40073, name=SAX_PHASE_CURRENTS_SUM, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01,device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_PHASE_CURRENTS_SUM),
    ModbusItem(battery_slave_id=40, address=40103, name=SAX_ACTIVE_POWER_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ACTIVE_POWER_L1),
    ModbusItem(battery_slave_id=40, address=40104, name=SAX_ACTIVE_POWER_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS,entitydescription=DESCRIPTION_SAX_ACTIVE_POWER_L2),
    ModbusItem(battery_slave_id=40, address=40105, name=SAX_ACTIVE_POWER_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS,entitydescription=DESCRIPTION_SAX_ACTIVE_POWER_L3),
    ModbusItem(battery_slave_id=40, address=40074, name=SAX_CURRENT_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L1),
    ModbusItem(battery_slave_id=40, address=40075, name=SAX_CURRENT_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01,device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L2),
    ModbusItem(battery_slave_id=40, address=40076, name=SAX_CURRENT_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L3),
    ModbusItem(battery_slave_id=40, address=40081, name=SAX_VOLTAGE_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L1),
    ModbusItem(battery_slave_id=40, address=40082, name=SAX_VOLTAGE_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L2),
    ModbusItem(battery_slave_id=40, address=40083, name=SAX_VOLTAGE_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L3),
    ModbusItem(battery_slave_id=40, address=40085, name=SAX_AC_POWER_TOTAL, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_AC_POWER_TOTAL),
    ModbusItem(battery_slave_id=40, address=40087, name=SAX_GRID_FREQUENCY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1,device=DeviceConstants.SYS,entitydescription=DESCRIPTION_SAX_GRID_FREQUENCY),
    ModbusItem(battery_slave_id=40, address=40089, name=SAX_APPARENT_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_APPARENT_POWER),
    ModbusItem(battery_slave_id=40, address=40091, name=SAX_REACTIVE_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_REACTIVE_POWER),
    ModbusItem(battery_slave_id=40, address=40093, name=SAX_POWER_FACTOR, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_POWER_FACTOR),
    ModbusItem(battery_slave_id=40, address=40099, name=SAX_STORAGE_STATUS, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_STORAGE_STATUS),
]

# Smart meter items - basic data (polled at standard interval)
MODBUS_SMARTMETER_BASIC_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40110, name=SAX_SMARTMETER_TOTAL_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER),
]
# Smart meter items - phase-specific data (polled at lower frequency)
MODBUS_SMARTMETER_PHASE_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40100, name=SAX_SMARTMETER_CURRENT_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L1),
    ModbusItem(battery_slave_id=40, address=40101, name=SAX_SMARTMETER_CURRENT_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L2),
    ModbusItem(battery_slave_id=40, address=40102, name=SAX_SMARTMETER_CURRENT_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L3),
    ModbusItem(battery_slave_id=40, address=40107, name=SAX_SMARTMETER_VOLTAGE_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1),
    ModbusItem(battery_slave_id=40, address=40108, name=SAX_SMARTMETER_VOLTAGE_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2),
    ModbusItem(battery_slave_id=40, address=40109, name=SAX_SMARTMETER_VOLTAGE_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3),
]

# Aggregated items - calculated values (e.g., combined power) from all available batteries
AGGREGATED_ITEMS: list[SAXItem] = [
    SAXItem(name=SAX_CUMULATIVE_ENERGY_PRODUCED, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_PRODUCED, params=PARAMS_SAX_CUMULATIVE_ENERGY),
    SAXItem(name=SAX_CUMULATIVE_ENERGY_CONSUMED, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_CONSUMED, params=PARAMS_SAX_CUMULATIVE_ENERGY),
    SAXItem(name=SAX_COMBINED_POWER, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_COMBINED_POWER, params=PARAMS_SAX_COMBINED_POWER),
    SAXItem(name=SAX_COMBINED_SOC, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_COMBINED_SOC, params=PARAMS_SAX_COMBINED_SOC),
]

# Pilot items - switches for manual control and solar charging
PILOT_ITEMS: list[SAXItem] = [
    SAXItem(name=SOLAR_CHARGING_SWITCH,  mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SOLAR_CHARGING_SWITCH),
    SAXItem(name=MANUAL_CONTROL_SWITCH,  mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_MANUAL_CONTROL_SWITCH),
]
# fmt: on
