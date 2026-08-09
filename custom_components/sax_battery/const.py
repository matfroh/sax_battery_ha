"""Constants for the SAX Battery integration."""

from dataclasses import dataclass

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
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)

from .entity_keys import (
    BMS_UNAVAILABILITY_RATE,
    COORDINATOR_CIRCUIT_BREAKER,
    COORDINATOR_CYCLE_TIME,
    COORDINATOR_ERROR_RATE,
    SAX_AC_CURRENT_A,
    SAX_AC_CURRENT_B,
    SAX_AC_CURRENT_C,
    SAX_AC_CURRENT_SUM,
    SAX_AC_POWER_TOTAL,
    SAX_ACTIVE_POWER,
    SAX_APPARENT_POWER,
    SAX_CAPACITY,
    SAX_CHARGE_FROM_GRID_SWITCH,
    SAX_CHARGE_FROM_PV_SWITCH,
    SAX_CHARGE_POWER,
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CHARGED,
    SAX_CUMULATIVE_ENERGY_DISCHARGED,
    SAX_CURRENT_L1,
    SAX_CURRENT_L2,
    SAX_CURRENT_L3,
    SAX_CURRENT_SOC,
    SAX_CYCLES,
    SAX_DEPTH_OF_DISCHARGE,
    SAX_DISCHARGE_POWER,
    SAX_ENERGY_CHARGED_DAILY,
    SAX_ENERGY_CHARGED_MONTHLY,
    SAX_ENERGY_DISCHARGED_DAILY,
    SAX_ENERGY_DISCHARGED_MONTHLY,
    SAX_GRID_FREQUENCY,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MAX_SOC,
    SAX_MAX_SOC_CHARGING,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
    SAX_PHASE_CURRENTS_SUM,
    SAX_POWER,
    SAX_POWER_FACTOR,
    SAX_POWER_SM,
    SAX_PV_POWER,
    SAX_REACTIVE_POWER,
    SAX_SCALE_FACTOR_AC_CURRENT,
    SAX_SCALE_FACTOR_APPARENT_POWER,
    SAX_SCALE_FACTOR_FREQUENCY,
    SAX_SCALE_FACTOR_POWER,
    SAX_SCALE_FACTOR_POWER_FACTOR,
    SAX_SCALE_FACTOR_REACTIVE_POWER,
    SAX_SCALE_FACTOR_VOLTAGE,
    SAX_SMARTMETER_AC_CURRENT_SUM,
    SAX_SMARTMETER_APPARENT_POWER,
    SAX_SMARTMETER_CURRENT_L1,
    SAX_SMARTMETER_CURRENT_L2,
    SAX_SMARTMETER_CURRENT_L3,
    SAX_SMARTMETER_ENERGY_CONSUMED,
    SAX_SMARTMETER_ENERGY_PRODUCED,
    SAX_SMARTMETER_FREQUENCY,
    SAX_SMARTMETER_POWER_FACTOR,
    SAX_SMARTMETER_POWER_L1,
    SAX_SMARTMETER_POWER_L2,
    SAX_SMARTMETER_POWER_L3,
    SAX_SMARTMETER_REACTIVE_POWER,
    SAX_SMARTMETER_SWITCHING_STATE,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SMARTMETER_VOLTAGE_L1,
    SAX_SMARTMETER_VOLTAGE_L1_L2,
    SAX_SMARTMETER_VOLTAGE_L2,
    SAX_SMARTMETER_VOLTAGE_L2_L3,
    SAX_SMARTMETER_VOLTAGE_L3,
    SAX_SMARTMETER_VOLTAGE_L3_L1,
    SAX_SOC,
    SAX_STATE,
    SAX_STATUS,
    SAX_SUNSPEC_CONTROL_MODE,
    SAX_SUNSPEC_POWER_SETPOINT,
    SAX_SUNSPEC_REFERENCE_POWER,
    SAX_SUNSPEC_SETPOINT_SCALE_FACTOR,
    SAX_SUNSPEC_SETPOINT_TIMEOUT,
    SAX_TEMPERATURE,
    SAX_VOLTAGE_A,
    SAX_VOLTAGE_B,
    SAX_VOLTAGE_C,
    SAX_VOLTAGE_L1,
    SAX_VOLTAGE_L1_L2,
    SAX_VOLTAGE_L2,
    SAX_VOLTAGE_L2_L3,
    SAX_VOLTAGE_L3,
    SAX_VOLTAGE_L3_L1,
    TXID_ERROR_RATE,
)
from .enums import DeviceConstants, TypeConstants
from .items import SAXItem

DOMAIN = "sax_battery"
# Attribution
ATTR_ATTRIBUTION = "attribution"
ATTRIBUTION = "Data provided by SAX Battery System"

# Multi-battery configuration keys
CONF_BATTERIES = "batteries"
CONF_BATTERY_HOST = "host"
CONF_BATTERY_PORT = "port"
CONF_BATTERY_ENABLED = "enabled"
CONF_BATTERY_PHASE = "phase"
CONF_BATTERY_IS_MASTER = "is_master"

# Battery ID mapping
BATTERY_IDS = ["bess_a", "bess_b", "bess_c"]
BATTERY_PHASES = {"bess_a": "L1", "bess_b": "L2", "bess_c": "L3"}


# Configuration constants for write access control
CONF_CONTROL_POWER = "control_power"  # Renamed from CONF_PILOT_FROM_HA
CONF_LIMIT_POWER = "limit_power"

# Smart meter and balanced loading configuration
CONF_SM_CONNECTED = "sm_connected"
CONF_BALANCED_LOADING = "balanced_loading"

# Protocol selection configuration
CONF_PROTOCOL_MODE = "protocol_mode"
CONF_VERIFY_SUNSPEC = "verify_sunspec"
CONF_EFFECTIVE_PROTOCOL_MODE = "effective_protocol_mode"

# Control modes
PV_CHARGING_MODE = "enable_pv_charging"
GRID_CHARGING_MODE = "enable_grid_charging"

# ╔════════════════════════════════════════════════════════════════════════╗
# ║ CRITICAL HARDWARE SAFETY LIMITS - DO NOT EXCEED                        ║
# ║                                                                        ║
# ║ These are absolute per-battery hardware limits for the SAX 7.5kW model.║
# ║ The master battery distributes the nominal_power register value        ║
# ║ WITHOUT modification to ALL batteries (master + slaves).               ║
# ║ Each battery receives the EXACT same value written to the master.      ║
# ║                                                                        ║
# ║ Example (3-battery system):                                            ║
# ║   Write 3500W to master register → each battery gets 3500W             ║
# ║   Write 5000W to master register → each battery gets 5000W ⚠ DANGER   ║
# ║                                                                        ║
# ║ Values exceeding these limits WILL damage battery hardware.            ║
# ║ All control values written to registers MUST be clamped to these       ║
# ║ per-battery limits, NOT to battery_count * limit.                      ║
# ║                                                                        ║
# ║ The cluster-wide values (battery_count * limit) are for UI display     ║
# ║ only (entity native_max_value) and must NEVER be used for register     ║
# ║ writes.                                                                ║
# ╚════════════════════════════════════════════════════════════════════════╝
LIMIT_MAX_CHARGE_PER_BATTERY = 3500  # Watts - ABSOLUTE hardware limit per battery
LIMIT_MAX_DISCHARGE_PER_BATTERY = 4600  # Watts - ABSOLUTE hardware limit per battery
LIMIT_REFRESH_INTERVAL = (
    3  # minutes for periodic refresh of write-only limits registers
)
# Refresh/register sets are derived from ModbusItem definitions below.
# SAX_NOMINAL_POWER and SAX_NOMINAL_FACTOR are managed by power manager,
# so periodic refresh covers only SAX_MAX_DISCHARGE and SAX_MAX_CHARGE.


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
CONF_POWER_SENSOR = "power_sensor"  # power sensor for balanced charging
CONF_PF_SENSOR = "pf_sensor_entity_id"
CONF_MASTER_BATTERY = "master_battery"
CONF_DEVICE_ID = "device_id"

# config flow constants
CONF_MIN_SOC = "min_soc"
CONF_ENABLE_GRID_CHARGING = "enable_grid_charging"

DEFAULT_PORT = 502  # Default Modbus port
DEFAULT_MIN_SOC = 15  # 15% default minimum
DEFAULT_MAX_SOC_CHARGING = 90  # 90% default maximum for charging


# Number Entity descriptions - keeping existing ones...
DESCRIPTION_SAX_MAX_CHARGE = NumberEntityDescription(
    key=SAX_MAX_CHARGE,
    name="Sax Max Charge",
    mode=NumberMode.BOX,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=LIMIT_MAX_CHARGE_PER_BATTERY,  # default single battery limit - will be adjusted based on battery count
    native_step=100,
    device_class=NumberDeviceClass.POWER,
    entity_category=EntityCategory.CONFIG,
)

DESCRIPTION_SAX_MAX_DISCHARGE = NumberEntityDescription(
    key=SAX_MAX_DISCHARGE,
    name="Sax Max Discharge",
    mode=NumberMode.BOX,
    native_unit_of_measurement=UnitOfPower.WATT,
    native_min_value=0,
    native_max_value=LIMIT_MAX_DISCHARGE_PER_BATTERY,  # default single battery limit - will be adjusted based on battery count
    native_step=100,
    device_class=NumberDeviceClass.POWER,
    entity_category=EntityCategory.CONFIG,
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
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_NOMINAL_FACTOR = NumberEntityDescription(
    key=SAX_NOMINAL_FACTOR,
    name="Power Factor (cos φ)",  # Dimensionless (0.0-1.0 range displayed)
    mode=NumberMode.BOX,
    native_unit_of_measurement="",
    native_min_value=0,
    native_max_value=1.0,  # User sees 0.0-1.0 range
    native_step=0.01,  # 0.01 step for user interface
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SUNSPEC_POWER_SETPOINT = SensorEntityDescription(
    key=SAX_SUNSPEC_POWER_SETPOINT,
    name="SunSpec Power Setpoint",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SUNSPEC_SETPOINT_TIMEOUT = SensorEntityDescription(
    key=SAX_SUNSPEC_SETPOINT_TIMEOUT,
    name="SunSpec Setpoint Timeout",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SUNSPEC_CONTROL_MODE = SensorEntityDescription(
    key=SAX_SUNSPEC_CONTROL_MODE,
    name="SunSpec Control Mode",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SUNSPEC_SETPOINT_SCALE_FACTOR = SensorEntityDescription(
    key=SAX_SUNSPEC_SETPOINT_SCALE_FACTOR,
    name="SunSpec Setpoint Scale Factor",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SUNSPEC_REFERENCE_POWER = SensorEntityDescription(
    key=SAX_SUNSPEC_REFERENCE_POWER,
    name="SunSpec Reference Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

# Number Entity descriptions - Battery switches
DESCRIPTION_SAX_STATUS_SWITCH = SwitchEntityDescription(
    key=SAX_STATUS,
    device_class=SwitchDeviceClass.SWITCH,
    name="Sax On/Off",
    icon="mdi:battery",
)

# Register 45 (40046): Switching state of the storage unit
# Write commands: "Off" = 1, "On" = 2
# Read commands: "Off" = 1, "On" = 2, "Connected" = 3, "Standby" = 4
SAX_STATUS_STATES: dict[int, str] = {
    1: "Off",  # Battery disabled
    2: "On",  # Normal operation
    3: "Connected",  # Read-only: Battery connected to grid
    4: "Standby",  # Read-only: Requires power cycle
}


DESCRIPTION_CHARGE_FROM_PV_SWITCH = SwitchEntityDescription(
    key=SAX_CHARGE_FROM_PV_SWITCH,
    name="PV Charging Switch",
    icon="mdi:solar-power",
)

DESCRIPTION_CHARGE_FROM_GRID_SWITCH = SwitchEntityDescription(
    key=SAX_CHARGE_FROM_GRID_SWITCH,
    name="Grid Charging Switch",
    icon="transmission-tower-export",
)

DESCRIPTION_SAX_SOC = SensorEntityDescription(
    key=SAX_SOC,
    name="Sax SOC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_MIN_SOC_LIMIT = NumberEntityDescription(
    key=SAX_MIN_SOC,
    name="Sax Minimum SOC",
    mode=NumberMode.BOX,
    device_class=NumberDeviceClass.BATTERY,
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=0,
    native_max_value=100,
    entity_category=EntityCategory.CONFIG,
)

DESCRIPTION_SAX_MAX_SOC_CHARGING = NumberEntityDescription(
    key=SAX_MAX_SOC_CHARGING,
    name="Max SOC for Charging",
    mode=NumberMode.BOX,
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=0,
    native_max_value=100,
    native_step=5,
    device_class=NumberDeviceClass.BATTERY,
    entity_category=EntityCategory.CONFIG,
    icon="mdi:battery-charging-high",
)

# SAX_POWER_CONTROL_SETPOINT entity description removed - replaced by direct SAX_NOMINAL_POWER control

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

DESCRIPTION_SAX_AC_CURRENT_SUM = SensorEntityDescription(
    key=SAX_AC_CURRENT_SUM,
    name="Storage AC Current Sum",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_AC_CURRENT_A = SensorEntityDescription(
    key=SAX_AC_CURRENT_A,
    name="Storage AC Current A",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_AC_CURRENT_B = SensorEntityDescription(
    key=SAX_AC_CURRENT_B,
    name="Storage AC Current B",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_AC_CURRENT_C = SensorEntityDescription(
    key=SAX_AC_CURRENT_C,
    name="Storage AC Current C",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_VOLTAGE_L1_L2 = SensorEntityDescription(
    key=SAX_VOLTAGE_L1_L2,
    name="Storage Voltage L1-L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_L2_L3 = SensorEntityDescription(
    key=SAX_VOLTAGE_L2_L3,
    name="Storage Voltage L2-L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_L3_L1 = SensorEntityDescription(
    key=SAX_VOLTAGE_L3_L1,
    name="Storage Voltage L3-L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_A = SensorEntityDescription(
    key=SAX_VOLTAGE_A,
    name="Storage Voltage A",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_B = SensorEntityDescription(
    key=SAX_VOLTAGE_B,
    name="Storage Voltage B",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_VOLTAGE_C = SensorEntityDescription(
    key=SAX_VOLTAGE_C,
    name="Storage Voltage C",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_ACTIVE_POWER = SensorEntityDescription(
    key=SAX_ACTIVE_POWER,
    name="Storage Active Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_APPARENT_POWER = SensorEntityDescription(
    key=SAX_APPARENT_POWER,
    name="Storage Apparent Power",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="VA",
)

DESCRIPTION_SAX_REACTIVE_POWER = SensorEntityDescription(
    key=SAX_REACTIVE_POWER,
    name="Storage Reactive Power",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="var",
)

DESCRIPTION_SAX_POWER_FACTOR = SensorEntityDescription(
    key=SAX_POWER_FACTOR,
    name="Storage Power Factor",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_TEMPERATURE = SensorEntityDescription(
    key=SAX_TEMPERATURE,
    name="Storage Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
)

DESCRIPTION_SAX_STATE = SensorEntityDescription(
    key=SAX_STATE,
    name="Storage State",
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_PV_POWER = SensorEntityDescription(
    key=SAX_PV_POWER,
    name="PV Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_CAPACITY = SensorEntityDescription(
    key=SAX_CAPACITY,
    name="Storage Capacity",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CHARGE_POWER = SensorEntityDescription(
    key=SAX_CHARGE_POWER,
    name="Storage Charge Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_DISCHARGE_POWER = SensorEntityDescription(
    key=SAX_DISCHARGE_POWER,
    name="Storage Discharge Power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_MAX_SOC = SensorEntityDescription(
    key=SAX_MAX_SOC,
    name="Storage Maximum SoC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_MIN_SOC = SensorEntityDescription(
    key=SAX_MIN_SOC,
    name="Storage Minimum SoC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_CURRENT_SOC = SensorEntityDescription(
    key=SAX_CURRENT_SOC,
    name="Storage Current SoC",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

DESCRIPTION_SAX_DEPTH_OF_DISCHARGE = SensorEntityDescription(
    key=SAX_DEPTH_OF_DISCHARGE,
    name="Storage Depth of Discharge",
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
)

# Additional sensor descriptions...
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

# Smartmeter specific sensors
DESCRIPTION_SAX_SMARTMETER_ENERGY_PRODUCED = SensorEntityDescription(
    key=SAX_SMARTMETER_ENERGY_PRODUCED,
    name="Sax Energy Produced",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_SMARTMETER_AC_CURRENT_SUM = SensorEntityDescription(
    key=SAX_SMARTMETER_AC_CURRENT_SUM,
    name="Smart Meter AC Current Sum",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_FREQUENCY = SensorEntityDescription(
    key=SAX_SMARTMETER_FREQUENCY,
    name="Smart Meter Frequency",
    device_class=SensorDeviceClass.FREQUENCY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfFrequency.HERTZ,
)

DESCRIPTION_SAX_SMARTMETER_APPARENT_POWER = SensorEntityDescription(
    key=SAX_SMARTMETER_APPARENT_POWER,
    name="Smart Meter Apparent Power",
    device_class=SensorDeviceClass.APPARENT_POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="VA",
)

DESCRIPTION_SAX_SMARTMETER_REACTIVE_POWER = SensorEntityDescription(
    key=SAX_SMARTMETER_REACTIVE_POWER,
    name="Smart Meter Reactive Power",
    device_class=SensorDeviceClass.REACTIVE_POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="var",
)

DESCRIPTION_SAX_SMARTMETER_POWER_FACTOR = SensorEntityDescription(
    key=SAX_SMARTMETER_POWER_FACTOR,
    name="Smart Meter Power Factor",
    device_class=SensorDeviceClass.POWER_FACTOR,
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_SCALE_FACTOR_AC_CURRENT = SensorEntityDescription(
    key=SAX_SCALE_FACTOR_AC_CURRENT,
    name="Scale Factor AC Current",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SCALE_FACTOR_VOLTAGE = SensorEntityDescription(
    key=SAX_SCALE_FACTOR_VOLTAGE,
    name="Scale Factor Voltage",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SCALE_FACTOR_POWER = SensorEntityDescription(
    key=SAX_SCALE_FACTOR_POWER,
    name="Scale Factor Power",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SCALE_FACTOR_FREQUENCY = SensorEntityDescription(
    key=SAX_SCALE_FACTOR_FREQUENCY,
    name="Scale Factor Frequency",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SCALE_FACTOR_APPARENT_POWER = SensorEntityDescription(
    key=SAX_SCALE_FACTOR_APPARENT_POWER,
    name="Scale Factor Apparent Power",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SCALE_FACTOR_REACTIVE_POWER = SensorEntityDescription(
    key=SAX_SCALE_FACTOR_REACTIVE_POWER,
    name="Scale Factor Reactive Power",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SCALE_FACTOR_POWER_FACTOR = SensorEntityDescription(
    key=SAX_SCALE_FACTOR_POWER_FACTOR,
    name="Scale Factor Power Factor",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

DESCRIPTION_SAX_SMARTMETER_ENERGY_CONSUMED = SensorEntityDescription(
    key=SAX_SMARTMETER_ENERGY_CONSUMED,
    name="Sax Energy Consumed",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_SMARTMETER_SWITCHING_STATE = SensorEntityDescription(
    key=SAX_SMARTMETER_SWITCHING_STATE,
    name="Sax Mem Switching State",
    state_class=SensorStateClass.MEASUREMENT,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L1,
    name="Sax Current L1",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L2,
    name="Sax Current L2",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_CURRENT_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_CURRENT_L3,
    name="Sax Current L3",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
)

DESCRIPTION_SAX_SMARTMETER_POWER_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_POWER_L1,
    name="Sax Active Power L1",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_SMARTMETER_POWER_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_POWER_L2,
    name="Sax Active Power L2",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)

DESCRIPTION_SAX_SMARTMETER_POWER_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_POWER_L3,
    name="Sax Active Power L3",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)
DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L1,
    name="Sax Voltage L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L1_L2,
    name="Sax Voltage L1-L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L2,
    name="Sax Voltage L2",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L2_L3,
    name="Sax Voltage L2-L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L3,
    name="Sax Voltage L3",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3_L1 = SensorEntityDescription(
    key=SAX_SMARTMETER_VOLTAGE_L3_L1,
    name="Sax Voltage L3-L1",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
)

DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER = SensorEntityDescription(
    key=SAX_SMARTMETER_TOTAL_POWER,
    name="Sax Total Power",
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
    suggested_display_precision=0,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_DISCHARGED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_DISCHARGED,
    name="Sax Cumulative Energy Discharged",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_CUMULATIVE_ENERGY_CHARGED = SensorEntityDescription(
    key=SAX_CUMULATIVE_ENERGY_CHARGED,
    name="Sax Cumulative Energy Charged",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
)

DESCRIPTION_SAX_ENERGY_DISCHARGED_DAILY = SensorEntityDescription(
    key=SAX_ENERGY_DISCHARGED_DAILY,
    name="Sax Energy Discharged Daily",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    suggested_display_precision=0,
)

DESCRIPTION_SAX_ENERGY_CHARGED_DAILY = SensorEntityDescription(
    key=SAX_ENERGY_CHARGED_DAILY,
    name="Sax Energy Charged Daily",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    suggested_display_precision=0,
)

DESCRIPTION_SAX_ENERGY_DISCHARGED_MONTHLY = SensorEntityDescription(
    key=SAX_ENERGY_DISCHARGED_MONTHLY,
    name="Sax Energy Discharged Monthly",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    suggested_display_precision=0,
)

DESCRIPTION_SAX_ENERGY_CHARGED_MONTHLY = SensorEntityDescription(
    key=SAX_ENERGY_CHARGED_MONTHLY,
    name="Sax Energy Charged Monthly",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    suggested_display_precision=0,
)

DESCRIPTION_COORDINATOR_CYCLE_TIME = SensorEntityDescription(
    key=COORDINATOR_CYCLE_TIME,
    name="Coordinator Cycle Time",
    device_class=SensorDeviceClass.DURATION,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:timer-outline",
)


DESCRIPTION_COORDINATOR_ERROR_RATE = SensorEntityDescription(
    key=COORDINATOR_ERROR_RATE,
    name="Coordinator Error Rate",
    native_unit_of_measurement="errors/hr",  # More actionable than percentage
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:alert-circle-outline",
)

DESCRIPTION_COORDINATOR_CIRCUIT_BREAKER = SensorEntityDescription(
    key=COORDINATOR_CIRCUIT_BREAKER,
    name="Coordinator Circuit Breaker",
    device_class=SensorDeviceClass.ENUM,
    options=["CLOSED", "OPEN"],
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:power-plug-off-outline",
)

DESCRIPTION_BMS_UNAVAILABILITY_RATE = SensorEntityDescription(
    key=BMS_UNAVAILABILITY_RATE,
    name="BMS Unavailability Rate",
    native_unit_of_measurement="unavailability/hr",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:battery-alert-variant-outline",
)

DESCRIPTION_TXID_ERROR_RATE = SensorEntityDescription(
    key=TXID_ERROR_RATE,
    name="Transaction ID Error Rate",
    native_unit_of_measurement="errors/hr",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    icon="mdi:swap-horizontal-bold",
)

# fmt: off

##############################################################################################################################
# Here are some lists that represent the entities of each device that will be created.
# Every list contains of some ModbusItem objects that have a constructor with the following parameters:
#
# address: The Modbus address as it is mentioned in the sax battery documentation
# name:    The entity name. Please note: This entry today only is used to automatically generate translation files.
#          It will be removed in future versions
# device: The device this entity is assigned to. Devices are used here to group the entities in a meaningful way
# entitydescription: The entity description that is used to create the Home Assistant entity.
# translation_key: The identifier that points to the right translation key. Therefore, the files strings.json and the
#                  language specific files in the subfolder "translations" have to be up-to-date
##############################################################################################################################

# Aggregated items - calculated values (e.g., combined power) from all available batteries
AGGREGATED_ITEMS: list[SAXItem] = [
    SAXItem(name=SAX_CUMULATIVE_ENERGY_DISCHARGED, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_DISCHARGED, translation_key="bms_cumulative_energy_discharged"),
    SAXItem(name=SAX_CUMULATIVE_ENERGY_CHARGED, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CUMULATIVE_ENERGY_CHARGED, translation_key="bms_cumulative_energy_charged"),
    SAXItem(name=SAX_COMBINED_SOC, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_COMBINED_SOC, translation_key="bms_combined_soc"),
    SAXItem(name=SAX_ENERGY_DISCHARGED_DAILY, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_DISCHARGED_DAILY, translation_key="bms_energy_discharged_daily"),
    SAXItem(name=SAX_ENERGY_CHARGED_DAILY, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_CHARGED_DAILY, translation_key="bms_energy_charged_daily"),
    SAXItem(name=SAX_ENERGY_DISCHARGED_MONTHLY, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_DISCHARGED_MONTHLY, translation_key="bms_energy_discharged_monthly"),
    SAXItem(name=SAX_ENERGY_CHARGED_MONTHLY, mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_ENERGY_CHARGED_MONTHLY, translation_key="bms_energy_charged_monthly"),
]
# Pilot items - switches for grid charing control and PV charging
PILOT_ITEMS: list[SAXItem] = [
    SAXItem(name=SAX_CHARGE_FROM_PV_SWITCH,  mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_CHARGE_FROM_PV_SWITCH, translation_key="bms_charge_from_pv"),
    SAXItem(name=SAX_CHARGE_FROM_GRID_SWITCH,  mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_CHARGE_FROM_GRID_SWITCH, translation_key="bms_charge_from_grid"),
    SAXItem(name=SAX_MIN_SOC, mtype=TypeConstants.NUMBER, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MIN_SOC_LIMIT, translation_key="bms_min_soc"),
    SAXItem(name=SAX_MAX_SOC_CHARGING, mtype=TypeConstants.NUMBER, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MAX_SOC_CHARGING, translation_key="bms_max_soc_charging"),
]


DIAGNOSTIC_ITEMS: list[SAXItem] = [
    SAXItem(name=COORDINATOR_CYCLE_TIME, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_COORDINATOR_CYCLE_TIME, translation_key="coordinator_cycle_time"),
    SAXItem(name=COORDINATOR_ERROR_RATE, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_COORDINATOR_ERROR_RATE, translation_key="coordinator_error_rate"),
    SAXItem(name=COORDINATOR_CIRCUIT_BREAKER, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_COORDINATOR_CIRCUIT_BREAKER, translation_key="coordinator_circuit_breaker"),
    SAXItem(name=BMS_UNAVAILABILITY_RATE, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_BMS_UNAVAILABILITY_RATE, translation_key="bms_unavailability_rate"),
    SAXItem(name=TXID_ERROR_RATE, mtype=TypeConstants.SENSOR, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_TXID_ERROR_RATE, translation_key="txid_error_rate"),
]

# fmt: on
