"""Constants for the SAX Battery integration."""

DOMAIN = "sax_battery"

CONF_BATTERY_COUNT = "battery_count"
CONF_POWER_SENSOR = "power_sensor_entity_id"
CONF_PF_SENSOR = "pf_sensor_entity_id"
CONF_MASTER_BATTERY = "master_battery"
CONF_DEVICE_ID = "device_id"

SAX_STATUS = "sax_status"
SAX_SOC = "sax_soc"
SAX_SMARTMETER = "sax_smartmeter"
SAX_CAPACITY = "sax_capacity"
SAX_CYCLES = "sax_cycles"
SAX_TEMP = "sax_temp"
SAX_ENERGY_PRODUCED = "sax_energy_produced"
SAX_ENERGY_CONSUMED = "sax_energy_consumed"

# Combined sensor keys (matching old implementation exactly)
SAX_COMBINED_SOC = "sax_battery_combined_soc"
SAX_COMBINED_POWER = "sax_battery_combined_power"

# Individual sensor keys (for reference)
SAX_SOC = "soc"
SAX_POWER = "power"

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

# Modbus configuration
SLAVE_ID_SMARTMETER = 1
SLAVE_ID_BATTERY = 120
SLAVE_ID_CHOKING = 123  # New slave ID for choking control

# Register addresses for choking control
CHOKING_POWER_SETPOINT_REG = 348  # Register for power setpoint (40349)
CHOKING_CONTROL_MODE_REG = 352    # Register for control mode (40353)

# Choking control constants
CHOKING_FACTOR = 100
CHOKING_MIN_VALUE = -10000
CHOKING_MAX_VALUE = 10000
CHOKING_TIMEOUT_MINUTES = 5

# Control modes
CONTROL_MODE_SMARTMETER = 0
CONTROL_MODE_SETPOINT = 1

# Services
SERVICE_SET_CHOKING_POWER = "set_choking_power"
