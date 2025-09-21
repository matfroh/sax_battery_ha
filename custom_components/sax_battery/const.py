"""Constants for the SAX Battery integration."""

from dataclasses import dataclass

from pymodbus.client.mixin import ModbusClientMixin  # For DATATYPE

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

from .entity_keys import (
    MANUAL_CONTROL_SWITCH,
    SAX_AC_POWER_TOTAL,
    SAX_APPARENT_POWER,
    SAX_CAPACITY,
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CONSUMED,
    SAX_CUMULATIVE_ENERGY_PRODUCED,
    SAX_CURRENT_L1,
    SAX_CURRENT_L2,
    SAX_CURRENT_L3,
    SAX_CYCLES,
    SAX_ENERGY_CONSUMED,
    SAX_ENERGY_PRODUCED,
    SAX_GRID_FREQUENCY,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
    SAX_PHASE_CURRENTS_SUM,
    SAX_POWER,
    SAX_POWER_FACTOR,
    SAX_POWER_SM,
    SAX_REACTIVE_POWER,
    SAX_SMARTMETER_CURRENT_L1,
    SAX_SMARTMETER_CURRENT_L2,
    SAX_SMARTMETER_CURRENT_L3,
    SAX_SMARTMETER_POWER_L1,
    SAX_SMARTMETER_POWER_L2,
    SAX_SMARTMETER_POWER_L3,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SMARTMETER_VOLTAGE_L1,
    SAX_SMARTMETER_VOLTAGE_L2,
    SAX_SMARTMETER_VOLTAGE_L3,
    SAX_SOC,
    SAX_STATUS,
    SAX_STORAGE_STATUS,
    SAX_TEMPERATURE,
    SAX_VOLTAGE_L1,
    SAX_VOLTAGE_L2,
    SAX_VOLTAGE_L3,
    SOLAR_CHARGING_SWITCH,
)
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem, SAXItem

DOMAIN = "sax_battery"

# Multi-battery configuration keys
CONF_BATTERIES = "batteries"
CONF_BATTERY_HOST = "host"
CONF_BATTERY_PORT = "port"
CONF_BATTERY_ENABLED = "enabled"
CONF_BATTERY_PHASE = "phase"
CONF_BATTERY_IS_MASTER = "is_master"

# Battery ID mapping
BATTERY_IDS = ["battery_a", "battery_b", "battery_c"]
BATTERY_PHASES = {"battery_a": "L1", "battery_b": "L2", "battery_c": "L3"}


# Configuration constants for write access control
CONF_PILOT_FROM_HA = "pilot_from_ha"
CONF_LIMIT_POWER = "limit_power"
# CONF_MAX_CHARGE = "max_charge"
# CONF_MAX_DISCHARGE = "max_discharge"

# Battery limits per individual battery unit 7.5kW model
# Adjusted to realistic values based on SAX service feedback
LIMIT_MAX_CHARGE_PER_BATTERY = 3500  # Watts per battery
LIMIT_MAX_DISCHARGE_PER_BATTERY = 4600  # Watts per battery

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
BATTERY_POLL_SLAVE_INTERVAL = 30  # Standard battery data polling (SOC, Power, Status)
CONF_MIN_SOC = "min_soc"
CONF_PRIORITY_DEVICES = "priority_devices"
CONF_ENABLE_SOLAR_CHARGING = "enable_solar_charging"
CONF_AUTO_PILOT_INTERVAL = "auto_pilot_interval"
CONF_MANUAL_CONTROL = "manual_control"

DEFAULT_PORT = 502  # Default Modbus port
DEFAULT_MIN_SOC = 15
DEFAULT_AUTO_PILOT_INTERVAL = 60  # seconds

# Write-only register addresses that require configuration checks
WRITE_ONLY_REGISTERS = {41, 42, 43, 44}


# fmt: off

# Number Entity descriptions - keeping existing ones...
DESCRIPTION_SAX_MAX_CHARGE = NumberEntityDescription(
    key=SAX_MAX_CHARGE,
    name="Sax Max Charge",
    mode=NumberMode.SLIDER,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=LIMIT_MAX_CHARGE_PER_BATTERY, # default single battery limit - will be adjusted based on battery count
    native_step=100,
    device_class=NumberDeviceClass.POWER,
)

DESCRIPTION_SAX_MAX_DISCHARGE = NumberEntityDescription(
    key=SAX_MAX_DISCHARGE,
    name="Sax Max Discharge",
    mode=NumberMode.SLIDER,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=LIMIT_MAX_DISCHARGE_PER_BATTERY, # default single battery limit - will be adjusted based on battery count
    native_step=100,
    device_class=NumberDeviceClass.POWER,
)

DESCRIPTION_SAX_NOMINAL_POWER = NumberEntityDescription(
    key=SAX_NOMINAL_POWER,
    name="Nominal Power",
    mode=NumberMode.SLIDER,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=LIMIT_MAX_CHARGE_PER_BATTERY,
    native_step=100,
    device_class=NumberDeviceClass.POWER,
)

DESCRIPTION_SAX_NOMINAL_FACTOR = NumberEntityDescription(
    key=SAX_NOMINAL_FACTOR,
    name="Power cos(Phi)",
    mode=NumberMode.BOX,
    native_unit_of_measurement="",
    native_min_value=0,
    native_max_value=10000,

)

# Number Entity descriptions - Battery switches
DESCRIPTION_SAX_STATUS_SWITCH = SwitchEntityDescription(
    key=SAX_STATUS,
    name="Sax On/Off",
    icon="mdi:battery",

)

DESCRIPTION_SOLAR_CHARGING_SWITCH = SwitchEntityDescription(
    key=SOLAR_CHARGING_SWITCH,
    name="Solar Charging Switch",
    icon="mdi:solar-power",
)

DESCRIPTION_MANUAL_CONTROL_SWITCH = SwitchEntityDescription(
    key=MANUAL_CONTROL_SWITCH,
    name="Manual Control Switch",
    icon="mdi:hand",
)

DESCRIPTION_SAX_SOC = SensorEntityDescription(
    key=SAX_SOC,
    name="Sax SOC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_MIN_SOC = NumberEntityDescription(
    key=SAX_MIN_SOC,
    name="Sax Minimum SOC",
    mode=NumberMode.BOX,
    device_class=NumberDeviceClass.BATTERY,
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=0,
    native_max_value=100,
    entity_category=EntityCategory.CONFIG,
)

DESCRIPTION_SAX_POWER = SensorEntityDescription(
    key=SAX_POWER,
    name="Sax Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_POWER_SM = SensorEntityDescription(
    key=SAX_POWER_SM,
    name="Sax Power Smartmeter",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_CAPACITY = SensorEntityDescription(
    key=SAX_CAPACITY,
    name="Sax Capacity",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CYCLES = SensorEntityDescription(
    key=SAX_CYCLES,
    name="Sax Cycles",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="cycles",  # No standard unit, using "cycles"
)

DESCRIPTION_SAX_TEMPERATURE = SensorEntityDescription(
    key=SAX_TEMPERATURE,
    name="Sax Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    suggested_display_precision=1,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    )

# Additional sensor descriptions...
DESCRIPTION_SAX_ENERGY_PRODUCED = SensorEntityDescription(
    key=SAX_ENERGY_PRODUCED,
    name="Sax Energy Produced",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
)

DESCRIPTION_SAX_ENERGY_CONSUMED = SensorEntityDescription(
    key=SAX_ENERGY_CONSUMED,
    name="Sax Energy Consumed",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
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
    native_unit_of_measurement="var",  # Volt-Ampere reactive
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
# Smartmeter specific sensors
DESCRIPTION_SAX_SMARTMETER_CURRENT_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L1,
    name="Sax Smartmeter Current L1",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L2,
    name="Sax Smartmeter Current L2",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L3,
    name="Sax Smartmeter Current L3",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_POWER_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_POWER_L1,
    name="Sax Smartmeter Active Power L1",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_SMARTMETER_POWER_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_POWER_L2,
    name="Sax Smartmeter Active Power L2",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_SMARTMETER_POWER_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_POWER_L3,
    name="Sax Smartmeter Active Power L3",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L1,
    name="Sax Smartmeter Voltage L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)
DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L2,
    name="Sax Smartmeter Voltage L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L3,
    name="Sax Smartmeter Voltage L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER = SensorEntityDescription(
    key=SAX_SMARTMETER_TOTAL_POWER,
    name="Sax Smartmeter Total Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_PRODUCED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_PRODUCED,
    name="Sax Cumulative Energy Produced",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_COMBINED_SOC = SensorEntityDescription(
    key=SAX_COMBINED_SOC,
    name="Sax Combined SOC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_CONSUMED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_CONSUMED,
    name="Sax Cumulative Energy Consumed",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

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
#                           of this integration.
#              SELECT: A select entity
#              NUMBER: A number entity. The value of this entity can be changed by the user interface
#              NUMBER_RO: In principle, this is also a number entity that ir writable. But to avoid damages
#                         we decided to make this entity read only.
# device: The device this entity is assigned to. Devices are used here to group the entities in a meaningful way
# entitydescription: The entity description that is used to create the Home Assistant entity.
# translation_key: The identifier that points to the right translation key. Therefore, the files strings.json and the
#                  language specific files in the subfolder "translations" have to be up-to-date
##############################################################################################################################

# Battery items write-only versions: Power limits
MODBUS_BATTERY_PILOT_CONTROL_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=64, address=41, name=SAX_NOMINAL_POWER, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_NOMINAL_POWER,),
    ModbusItem(battery_slave_id=64, address=42, name=SAX_NOMINAL_FACTOR, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_NOMINAL_FACTOR,),
]
# Battery items write-only versions: Power control
MODBUS_BATTERY_POWER_LIMIT_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=64, address=43, name=SAX_MAX_CHARGE, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MAX_CHARGE,),
    ModbusItem(battery_slave_id=64, address=44, name=SAX_MAX_DISCHARGE, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MAX_DISCHARGE,),
]
# Battery items - switch
MODBUS_BATTERY_SWITCH_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=64, address=45, name=SAX_STATUS, mtype=TypeConstants.SWITCH, data_type=ModbusClientMixin.DATATYPE.UINT16, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_STATUS_SWITCH,),
]
# Battery items read-only versions
MODBUS_BATTERY_REALTIME_ITEMS: list[ModbusItem] = [
        ModbusItem(battery_slave_id=64, address=46, name=SAX_SOC, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_SOC,),
        ModbusItem(battery_slave_id=64, address=47, name=SAX_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, offset=16384, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_POWER,),
        ModbusItem(battery_slave_id=64, address=48, name=SAX_POWER_SM, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, offset=16384, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_POWER_SM,),
]
# Battery items - static/accumulated data (polled at lower frequency)
MODBUS_BATTERY_STATIC_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40096, name=SAX_ENERGY_PRODUCED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.001, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_PRODUCED),
    ModbusItem(battery_slave_id=40, address=40097, name=SAX_ENERGY_CONSUMED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.001, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_CONSUMED),
    ModbusItem(battery_slave_id=40, address=40099, name=SAX_STORAGE_STATUS, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_STORAGE_STATUS),
    ModbusItem(battery_slave_id=40, address=40115, name=SAX_CAPACITY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=10.0 ,device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CAPACITY),
    ModbusItem(battery_slave_id=40, address=40116, name=SAX_CYCLES,  mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CYCLES),
    ModbusItem(battery_slave_id=40, address=40117, name=SAX_TEMPERATURE, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_TEMPERATURE,),
]
# Battery items - Smartmeter data accessed through battery (polled at standard interval)
MODBUS_BATTERY_SMARTMETER_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40073, name=SAX_PHASE_CURRENTS_SUM, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01,device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_PHASE_CURRENTS_SUM),
    ModbusItem(battery_slave_id=40, address=40074, name=SAX_CURRENT_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_CURRENT_L1),
    ModbusItem(battery_slave_id=40, address=40075, name=SAX_CURRENT_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01,device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_CURRENT_L2),
    ModbusItem(battery_slave_id=40, address=40076, name=SAX_CURRENT_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_CURRENT_L3),
    ModbusItem(battery_slave_id=40, address=40081, name=SAX_VOLTAGE_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_VOLTAGE_L1),
    ModbusItem(battery_slave_id=40, address=40082, name=SAX_VOLTAGE_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_VOLTAGE_L2),
    ModbusItem(battery_slave_id=40, address=40083, name=SAX_VOLTAGE_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_VOLTAGE_L3),
    ModbusItem(battery_slave_id=40, address=40085, name=SAX_AC_POWER_TOTAL, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_AC_POWER_TOTAL),
    ModbusItem(battery_slave_id=40, address=40087, name=SAX_GRID_FREQUENCY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1,device=DeviceConstants.SM,entitydescription=DESCRIPTION_SAX_GRID_FREQUENCY),
    ModbusItem(battery_slave_id=40, address=40089, name=SAX_APPARENT_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_APPARENT_POWER),
    ModbusItem(battery_slave_id=40, address=40091, name=SAX_REACTIVE_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_REACTIVE_POWER),
    ModbusItem(battery_slave_id=40, address=40093, name=SAX_POWER_FACTOR, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_POWER_FACTOR),
]
# Smartmeter items - phase-specific data (polled at lower frequency)
MODBUS_SMARTMETER_PHASE_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40100, name=SAX_SMARTMETER_CURRENT_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L1),
    ModbusItem(battery_slave_id=40, address=40101, name=SAX_SMARTMETER_CURRENT_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L2),
    ModbusItem(battery_slave_id=40, address=40102, name=SAX_SMARTMETER_CURRENT_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L3),
    ModbusItem(battery_slave_id=40, address=40103, name=SAX_SMARTMETER_POWER_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L1),
    ModbusItem(battery_slave_id=40, address=40104, name=SAX_SMARTMETER_POWER_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L2),
    ModbusItem(battery_slave_id=40, address=40105, name=SAX_SMARTMETER_POWER_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L3),
    ModbusItem(battery_slave_id=40, address=40107, name=SAX_SMARTMETER_VOLTAGE_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1),
    ModbusItem(battery_slave_id=40, address=40108, name=SAX_SMARTMETER_VOLTAGE_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2),
    ModbusItem(battery_slave_id=40, address=40109, name=SAX_SMARTMETER_VOLTAGE_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3),
]
# Smartmeter items - basic data (polled at standard interval)
MODBUS_SMARTMETER_BASIC_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_slave_id=40, address=40110, name=SAX_SMARTMETER_TOTAL_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER),
]
# Aggregated items - calculated values (e.g., combined power) from all available batteries
AGGREGATED_ITEMS: list[SAXItem] = [
    SAXItem(name=SAX_CUMULATIVE_ENERGY_PRODUCED, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_PRODUCED, translation_key="sax_cumulative_energy_produced"),
    SAXItem(name=SAX_CUMULATIVE_ENERGY_CONSUMED, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_CONSUMED, translation_key="sax_cumulative_energy_consumed"),
    SAXItem(name=SAX_COMBINED_SOC, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_COMBINED_SOC, translation_key="sax_combined_soc"),
]
# Pilot items - switches for manual control and solar charging
PILOT_ITEMS: list[SAXItem] = [
    SAXItem(name=SOLAR_CHARGING_SWITCH,  mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SOLAR_CHARGING_SWITCH),
    SAXItem(name=MANUAL_CONTROL_SWITCH,  mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_MANUAL_CONTROL_SWITCH),
    SAXItem(name=SAX_MIN_SOC, mtype=TypeConstants.NUMBER, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MIN_SOC, translation_key="sax_min_soc")
]
# fmt: on
