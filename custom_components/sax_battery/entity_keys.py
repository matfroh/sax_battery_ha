"""Entity key constants for SAX Battery integration."""

# SAX entity keys
SAX_NOMINAL_POWER = "sax_nominal_power"
SAX_NOMINAL_FACTOR = "sax_nominal_factor"
SAX_MAX_CHARGE = "sax_max_charge"
SAX_MAX_DISCHARGE = "sax_max_discharge"
SAX_STATUS = "sax_status"
SAX_SOC = "sax_soc"
SAX_MIN_SOC = "sax_min_soc"
SAX_POWER = "sax_power"
SAX_POWER_SM = "sax_power_sm"
SAX_CAPACITY = "sax_capacity"
SAX_CYCLES = "sax_cycles"
SAX_TEMPERATURE = "sax_temperature"

# SAX battery Smartmeter constants
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

# Smartmeter specific entities (master battery only)
# Use _sm suffix to avoid name clashes
SAX_SMARTMETER_ENERGY_PRODUCED = "energy_produced_sm"
SAX_SMARTMETER_ENERGY_CONSUMED = "energy_consumed_sm"
SAX_SMARTMETER_SWITCHING_STATE = "switching_state_sm"
SAX_SMARTMETER_POWER_L1 = "power_l1_sm"
SAX_SMARTMETER_POWER_L2 = "power_l2_sm"
SAX_SMARTMETER_POWER_L3 = "power_l3_sm"
SAX_SMARTMETER_CURRENT_L1 = "current_l1_sm"
SAX_SMARTMETER_CURRENT_L2 = "current_l2_sm"
SAX_SMARTMETER_CURRENT_L3 = "current_l3_sm"
SAX_SMARTMETER_VOLTAGE_L1 = "voltage_l1_sm"
SAX_SMARTMETER_VOLTAGE_L2 = "voltage_l2_sm"
SAX_SMARTMETER_VOLTAGE_L3 = "voltage_l3_sm"
SAX_SMARTMETER_TOTAL_POWER = "total_power_sm"

# Cumulative energy statistics (multiple batteries)
SAX_CUMULATIVE_ENERGY_PRODUCED = "sax_cumulative_energy_produced"
SAX_CUMULATIVE_ENERGY_CONSUMED = "sax_cumulative_energy_consumed"
SAX_COMBINED_SOC = "sax_combined_soc"

# Pilot entities
SOLAR_CHARGING_SWITCH = "solar_charging_switch"
MANUAL_CONTROL_SWITCH = "manual_control_switch"
SAX_PILOT_POWER = "sax_pilot_power"
