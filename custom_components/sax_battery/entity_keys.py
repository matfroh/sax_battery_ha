"""Entity key constants for SAX Battery integration."""

# SAX entity keys
SAX_NOMINAL_POWER = "sax_nominal_power"
SAX_NOMINAL_FACTOR = "sax_nominal_factor"
SAX_MAX_CHARGE = "sax_max_charge"
SAX_MAX_DISCHARGE = "sax_max_discharge"
SAX_STATUS = "sax_status"
SAX_SOC = "sax_soc"
SAX_MIN_SOC = "sax_min_soc"
SAX_MAX_SOC_CHARGING = "sax_max_soc_charging"
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
SAX_CUMULATIVE_ENERGY_DISCHARGED = "sax_cumulative_energy_discharged"
SAX_CUMULATIVE_ENERGY_CHARGED = "sax_cumulative_energy_charged"
SAX_COMBINED_SOC = "sax_combined_soc"

# Period-derived energy sensors (daily / monthly)
SAX_ENERGY_DISCHARGED_DAILY = "sax_energy_discharged_daily"
SAX_ENERGY_CHARGED_DAILY = "sax_energy_charged_daily"
SAX_ENERGY_DISCHARGED_MONTHLY = "sax_energy_discharged_monthly"
SAX_ENERGY_CHARGED_MONTHLY = "sax_energy_charged_monthly"

# Power control entities
SAX_CHARGE_FROM_PV_SWITCH = "sax_charge_from_pv_switch"
SAX_CHARGE_FROM_GRID_SWITCH = "sax_charge_from_grid_switch"
# SAX_POWER_CONTROL_SETPOINT removed - replaced by direct SAX_NOMINAL_POWER control

# Diagnostic entities
COORDINATOR_CYCLE_TIME = "coordinator_cycle_time"
COORDINATOR_ERROR_RATE = "coordinator_error_rate"
COORDINATOR_CIRCUIT_BREAKER = "coordinator_circuit_breaker"
BMS_UNAVAILABILITY_RATE = "bms_unavailability_rate"
TXID_ERROR_RATE = "txid_error_rate"
