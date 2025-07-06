"""Constants for the SAX Battery integration."""

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
)

from .enums import DeviceConstants, FormatConstants, TypeConstants
from .items import ModbusItem, StatusItem

DOMAIN = "sax_battery"


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

SAX_STATUS = "sax_status"
SAX_SOC = "sax_soc"
SAX_POWER = "sax_power"
SAX_SMARTMETER = "sax_smartmeter"
SAX_CAPACITY = "sax_capacity"
SAX_CYCLES = "sax_cycles"
SAX_TEMP = "sax_temp"
SAX_ENERGY_PRODUCED = "sax_energy_produced"
SAX_ENERGY_CONSUMED = "sax_energy_consumed"
SAX_COMBINED_POWER = "sax_combined_power"
SAX_COMBINED_SOC = "combined_soc"

CONF_PILOT_FROM_HA = "pilot_from_ha"
CONF_LIMIT_POWER = "limit_power"
CONF_MAX_CHARGE = "max_charge"
CONF_MAX_DISCHARGE = "max_discharge"

CONF_MIN_SOC = "min_soc"
CONF_PRIORITY_DEVICES = "priority_devices"
CONF_ENABLE_SOLAR_CHARGING = "enable_solar_charging"
CONF_AUTO_PILOT_INTERVAL = "auto_pilot_interval"

CONF_MANUAL_CONTROL = "manual_control"

DEFAULT_PORT = 502  # Default Modbus port

DEFAULT_MIN_SOC = 15
DEFAULT_AUTO_PILOT_INTERVAL = 60  # seconds

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


SYS_STATUSANZEIGE: list[StatusItem] = [
    StatusItem(number=1, text="OFF", translation_key="system_operationmode_off"),
    StatusItem(
        number=3, text="Connected", translation_key="system_operationmode_connected"
    ),
    StatusItem(
        number=4, text="Standby", translation_key="system_operationmode_standby"
    ),
]

# fmt: off
# Battery items - real-time data (polled at standard interval)
MODBUS_BATTERY_REALTIME_ITEMS: list[ModbusItem] = [
    ModbusItem(slave=64, address=45, name=SAX_STATUS, mformat=FormatConstants.STATUS, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, resultlist=SYS_STATUSANZEIGE),
    ModbusItem(slave=64, address=46, name=SAX_SOC, mformat=FormatConstants.PERCENTAGE, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS),
    ModbusItem(slave=64, address=47, name=SAX_POWER, mformat=FormatConstants.STATUS, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS),
    ModbusItem(slave=64, address=48, name=SAX_SMARTMETER, mformat=FormatConstants.STATUS, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
]
# Battery items - static/accumulated data (polled at lower frequency)
MODBUS_BATTERY_STATIC_ITEMS: list[ModbusItem] = [
    ModbusItem(slave=40, address=40115, name=SAX_CAPACITY, mformat=FormatConstants.STATUS, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40116, name=SAX_CYCLES, mformat=FormatConstants.STATUS, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40117, name=SAX_TEMP, mformat=FormatConstants.STATUS, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40096, name=SAX_ENERGY_PRODUCED, mformat=FormatConstants.PERCENTAGE, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40097, name=SAX_ENERGY_CONSUMED, mformat=FormatConstants.PERCENTAGE, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
]
# Battery items - smart meter data accessed through battery (polled at standard interval)
MODBUS_BATTERY_SMARTMETER_ITEMS: list[ModbusItem] = [
    ModbusItem(slave=40, address=40073, name=SAX_PHASE_CURRENTS_SUM, mformat=FormatConstants.PERCENTAGE, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40103, name=SAX_ACTIVE_POWER_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40104, name=SAX_ACTIVE_POWER_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40105, name=SAX_ACTIVE_POWER_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40074, name=SAX_CURRENT_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40075, name=SAX_CURRENT_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40076, name=SAX_CURRENT_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40081, name=SAX_VOLTAGE_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40082, name=SAX_VOLTAGE_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40083, name=SAX_VOLTAGE_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40085, name=SAX_AC_POWER_TOTAL, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40087, name=SAX_GRID_FREQUENCY, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40089, name=SAX_APPARENT_POWER, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40091, name=SAX_REACTIVE_POWER, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40093, name=SAX_POWER_FACTOR, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
    ModbusItem(slave=40, address=40099, name=SAX_STORAGE_STATUS, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SYS),
]
# Combined battery items (all battery data)
MODBUS_BATTERY_ITEMS: list[ModbusItem] = MODBUS_BATTERY_REALTIME_ITEMS + MODBUS_BATTERY_STATIC_ITEMS + MODBUS_BATTERY_SMARTMETER_ITEMS
# Smart meter items - basic data (polled at standard interval)
MODBUS_SMARTMETER_BASIC_ITEMS: list[ModbusItem] = [
    ModbusItem(slave=40, address=40110, name=SAX_SMARTMETER_TOTAL_POWER, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SM),
]
# Smart meter items - phase-specific data (polled at lower frequency)
MODBUS_SMARTMETER_PHASE_ITEMS: list[ModbusItem] = [
    ModbusItem(slave=40, address=40100, name=SAX_SMARTMETER_CURRENT_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SM),
    ModbusItem(slave=40, address=40101, name=SAX_SMARTMETER_CURRENT_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SM),
    ModbusItem(slave=40, address=40102, name=SAX_SMARTMETER_CURRENT_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SM),
    ModbusItem(slave=40, address=40107, name=SAX_SMARTMETER_VOLTAGE_L1, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SM),
    ModbusItem(slave=40, address=40108, name=SAX_SMARTMETER_VOLTAGE_L2, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SM),
    ModbusItem(slave=40, address=40109, name=SAX_SMARTMETER_VOLTAGE_L3, mformat=FormatConstants.NUMBER, mtype=TypeConstants.NUMBER_RO, device=DeviceConstants.SM),
]
# Combined smart meter items (all smart meter data)
MODBUS_SMARTMETER_ITEMS: list[ModbusItem] = MODBUS_SMARTMETER_BASIC_ITEMS + MODBUS_SMARTMETER_PHASE_ITEMS
# Complete modbus items (battery + smart meter) - used by master battery only
MODBUS_ALL_ITEMS: list[ModbusItem] = MODBUS_BATTERY_ITEMS + MODBUS_SMARTMETER_ITEMS
# fmt: on

SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    SAX_STATUS: SensorEntityDescription(
        key=SAX_STATUS,
        name="SAX Battery Status",
        device_class=SensorDeviceClass.ENUM,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SAX_SOC: SensorEntityDescription(
        key=SAX_SOC,
        name="SAX Battery SOC",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SAX_POWER: SensorEntityDescription(
        key=SAX_POWER,
        name="SAX Battery Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    SAX_SMARTMETER: SensorEntityDescription(
        key=SAX_SMARTMETER,
        name="SAX Battery Smartmeter",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    SAX_CAPACITY: SensorEntityDescription(
        key=SAX_CAPACITY,
        name="SAX Battery Capacity",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    ),
    SAX_CYCLES: SensorEntityDescription(
        key=SAX_CYCLES,
        name="SAX Battery Cycles",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SAX_TEMP: SensorEntityDescription(
        key=SAX_TEMP,
        name="SAX Battery Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    # Smart meter sensors
    SAX_PHASE_CURRENTS_SUM: SensorEntityDescription(
        key=SAX_PHASE_CURRENTS_SUM,
        name="SAX Phase Currents Sum",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    SAX_CURRENT_L1: SensorEntityDescription(
        key=SAX_CURRENT_L1,
        name="SAX Current L1",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    SAX_CURRENT_L2: SensorEntityDescription(
        key=SAX_CURRENT_L2,
        name="SAX Current L2",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    SAX_CURRENT_L3: SensorEntityDescription(
        key=SAX_CURRENT_L3,
        name="SAX Current L3",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    SAX_VOLTAGE_L1: SensorEntityDescription(
        key=SAX_VOLTAGE_L1,
        name="SAX Voltage L1",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    ),
    SAX_VOLTAGE_L2: SensorEntityDescription(
        key=SAX_VOLTAGE_L2,
        name="SAX Voltage L2",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    ),
    SAX_VOLTAGE_L3: SensorEntityDescription(
        key=SAX_VOLTAGE_L3,
        name="SAX Voltage L3",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    ),
    SAX_AC_POWER_TOTAL: SensorEntityDescription(
        key=SAX_AC_POWER_TOTAL,
        name="SAX AC Power Total",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    SAX_GRID_FREQUENCY: SensorEntityDescription(
        key=SAX_GRID_FREQUENCY,
        name="SAX Grid Frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
    ),
    SAX_APPARENT_POWER: SensorEntityDescription(
        key=SAX_APPARENT_POWER,
        name="SAX Apparent Power",
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="VA",  # Volt-ampere
    ),
    SAX_REACTIVE_POWER: SensorEntityDescription(
        key=SAX_REACTIVE_POWER,
        name="SAX Reactive Power",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="VAR",  # Volt-ampere reactive
    ),
    SAX_POWER_FACTOR: SensorEntityDescription(
        key=SAX_POWER_FACTOR,
        name="SAX Power Factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SAX_STORAGE_STATUS: SensorEntityDescription(
        key=SAX_STORAGE_STATUS,
        name="SAX Storage Status",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Smart meter specific sensors
    SAX_SMARTMETER_CURRENT_L1: SensorEntityDescription(
        key=SAX_SMARTMETER_CURRENT_L1,
        name="SAX Smart Meter Current L1",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    SAX_SMARTMETER_CURRENT_L2: SensorEntityDescription(
        key=SAX_SMARTMETER_CURRENT_L2,
        name="SAX Smart Meter Current L2",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    SAX_SMARTMETER_CURRENT_L3: SensorEntityDescription(
        key=SAX_SMARTMETER_CURRENT_L3,
        name="SAX Smart Meter Current L3",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    ),
    SAX_ACTIVE_POWER_L1: SensorEntityDescription(
        key=SAX_ACTIVE_POWER_L1,
        name="SAX Active Power L1",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    SAX_ACTIVE_POWER_L2: SensorEntityDescription(
        key=SAX_ACTIVE_POWER_L2,
        name="SAX Active Power L2",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    SAX_ACTIVE_POWER_L3: SensorEntityDescription(
        key=SAX_ACTIVE_POWER_L3,
        name="SAX Active Power L3",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    SAX_SMARTMETER_VOLTAGE_L1: SensorEntityDescription(
        key=SAX_SMARTMETER_VOLTAGE_L1,
        name="SAX Smart Meter Voltage L1",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    ),
    SAX_SMARTMETER_VOLTAGE_L2: SensorEntityDescription(
        key=SAX_SMARTMETER_VOLTAGE_L2,
        name="SAX Smart Meter Voltage L2",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    ),
    SAX_SMARTMETER_VOLTAGE_L3: SensorEntityDescription(
        key=SAX_SMARTMETER_VOLTAGE_L3,
        name="SAX Smart Meter Voltage L3",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    ),
    SAX_SMARTMETER_TOTAL_POWER: SensorEntityDescription(
        key=SAX_SMARTMETER_TOTAL_POWER,
        name="SAX Smart Meter Total Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
}
