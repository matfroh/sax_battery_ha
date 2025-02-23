"""Constants for the SAX Battery integration."""

DOMAIN = "sax_battery"

CONF_BATTERY_COUNT = "battery_count"
CONF_POWER_SENSOR = "power_sensor_entity_id"
CONF_PF_SENSOR = "pf_sensor_entity_id"
CONF_MASTER_BATTERY = "master_battery"  # Add this for master battery selection
CONF_DEVICE_ID = "device_id"

# Constants for Modbus register names (from your example and likely others)
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
# ... Add any other register names you are using as constants

# Other potential constants (if needed)
DEFAULT_PORT = 502  # Default Modbus port