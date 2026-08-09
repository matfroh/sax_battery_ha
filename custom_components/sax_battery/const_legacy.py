"""Legacy Modbus item definitions for the SAX battery integration."""

from __future__ import annotations

from pymodbus.client.mixin import ModbusClientMixin

from .const import (
    DESCRIPTION_SAX_AC_POWER_TOTAL,
    DESCRIPTION_SAX_APPARENT_POWER,
    # DESCRIPTION_SAX_CAPACITY,
    DESCRIPTION_SAX_CURRENT_L1,
    DESCRIPTION_SAX_CURRENT_L2,
    DESCRIPTION_SAX_CURRENT_L3,
    DESCRIPTION_SAX_GRID_FREQUENCY,
    DESCRIPTION_SAX_MAX_CHARGE,
    DESCRIPTION_SAX_MAX_DISCHARGE,
    DESCRIPTION_SAX_NOMINAL_FACTOR,
    DESCRIPTION_SAX_NOMINAL_POWER,
    DESCRIPTION_SAX_PHASE_CURRENTS_SUM,
    DESCRIPTION_SAX_POWER,
    DESCRIPTION_SAX_POWER_FACTOR,
    DESCRIPTION_SAX_POWER_SM,
    DESCRIPTION_SAX_REACTIVE_POWER,
    DESCRIPTION_SAX_SMARTMETER_CURRENT_L1,
    DESCRIPTION_SAX_SMARTMETER_CURRENT_L2,
    DESCRIPTION_SAX_SMARTMETER_CURRENT_L3,
    DESCRIPTION_SAX_SMARTMETER_ENERGY_CONSUMED,
    DESCRIPTION_SAX_SMARTMETER_ENERGY_PRODUCED,
    DESCRIPTION_SAX_SMARTMETER_POWER_L1,
    DESCRIPTION_SAX_SMARTMETER_POWER_L2,
    DESCRIPTION_SAX_SMARTMETER_POWER_L3,
    DESCRIPTION_SAX_SMARTMETER_SWITCHING_STATE,
    DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER,
    DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1,
    DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2,
    DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3,
    DESCRIPTION_SAX_SOC,
    DESCRIPTION_SAX_STATUS_SWITCH,
    # DESCRIPTION_SAX_TEMPERATURE,
    DESCRIPTION_SAX_VOLTAGE_L1,
    DESCRIPTION_SAX_VOLTAGE_L2,
    DESCRIPTION_SAX_VOLTAGE_L3,
)
from .entity_keys import (
    SAX_AC_POWER_TOTAL,
    SAX_APPARENT_POWER,
    SAX_CURRENT_L1,
    SAX_CURRENT_L2,
    SAX_CURRENT_L3,
    SAX_GRID_FREQUENCY,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
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
    SAX_SMARTMETER_ENERGY_CONSUMED,
    SAX_SMARTMETER_ENERGY_PRODUCED,
    SAX_SMARTMETER_POWER_L1,
    SAX_SMARTMETER_POWER_L2,
    SAX_SMARTMETER_POWER_L3,
    SAX_SMARTMETER_SWITCHING_STATE,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SMARTMETER_VOLTAGE_L1,
    SAX_SMARTMETER_VOLTAGE_L2,
    SAX_SMARTMETER_VOLTAGE_L3,
    SAX_SOC,
    SAX_STATUS,
    SAX_VOLTAGE_L1,
    SAX_VOLTAGE_L2,
    SAX_VOLTAGE_L3,
)
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem

# fmt: off

# Battery items write-only versions: Power limits
MODBUS_BATTERY_POWER_CONTROL_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=64,  address=40042, name=SAX_NOMINAL_POWER, enabled_by_default=False, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_NOMINAL_POWER, translation_key="bms_nominal_power",
    ),
    ModbusItem(battery_device_id=64, address=40043, name=SAX_NOMINAL_FACTOR, enabled_by_default=False, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1000.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_NOMINAL_FACTOR, translation_key="bms_nominal_factor",
    ),
]

# Battery items write-only versions: Power control
MODBUS_BATTERY_POWER_LIMIT_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=64, address=40044, name=SAX_MAX_DISCHARGE, enabled_by_default=False, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MAX_DISCHARGE, translation_key="bms_max_discharge",
    ),
    ModbusItem(battery_device_id=64, address=40045, name=SAX_MAX_CHARGE, enabled_by_default=False, mtype=TypeConstants.NUMBER_WO, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_MAX_CHARGE, translation_key="bms_max_charge",
    ),
]

# Battery items - switch
MODBUS_BATTERY_SWITCH_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=64, address=40046, name=SAX_STATUS, mtype=TypeConstants.SWITCH, data_type=ModbusClientMixin.DATATYPE.UINT16, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_STATUS_SWITCH, translation_key="bess_status",
    ),
]

# Battery items read-only versions
MODBUS_BATTERY_REALTIME_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=64, address=40047, name=SAX_SOC, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_SOC, translation_key="bess_soc",
    ),
    ModbusItem(battery_device_id=64, address=40048, name=SAX_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, offset=16384, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_POWER, translation_key="bess_power",
    ),
    ModbusItem(battery_device_id=64, address=40049, name=SAX_POWER_SM, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, offset=16384, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_POWER_SM, translation_key="bess_power_sm",
    ),
]

# Battery BMS items - (polled at standard interval) - master battery only
MODBUS_BATTERY_BMS_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=40, address=40073, name=SAX_PHASE_CURRENTS_SUM, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_PHASE_CURRENTS_SUM, translation_key="bms_phase_currents_sum", ),
    ModbusItem(battery_device_id=40, address=40074, name=SAX_CURRENT_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L1, translation_key="bms_current_l1", ),
    ModbusItem(battery_device_id=40, address=40075, name=SAX_CURRENT_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L2, translation_key="bms_current_l2", ),
    ModbusItem(battery_device_id=40, address=40076, name=SAX_CURRENT_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.01, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_CURRENT_L3, translation_key="bms_current_l3", ),
    ModbusItem(battery_device_id=40, address=40081, name=SAX_VOLTAGE_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L1, translation_key="bms_voltage_l1", ),
    ModbusItem(battery_device_id=40, address=40082, name=SAX_VOLTAGE_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L2, translation_key="bms_voltage_l2", ),
    ModbusItem(battery_device_id=40, address=40083, name=SAX_VOLTAGE_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_VOLTAGE_L3, translation_key="bms_voltage_l3", ),
    ModbusItem(battery_device_id=40, address=40085, name=SAX_AC_POWER_TOTAL, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_AC_POWER_TOTAL, translation_key="bms_ac_power_total", ),
    ModbusItem(battery_device_id=40, address=40087, name=SAX_GRID_FREQUENCY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_GRID_FREQUENCY, translation_key="bms_grid_frequency", ),
    ModbusItem(battery_device_id=40, address=40089, name=SAX_APPARENT_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_APPARENT_POWER, translation_key="bms_apparent_power", ),
    ModbusItem(battery_device_id=40, address=40091, name=SAX_REACTIVE_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=10.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_REACTIVE_POWER, translation_key="bms_reactive_power", ),
    ModbusItem(battery_device_id=40, address=40093, name=SAX_POWER_FACTOR, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_POWER_FACTOR, translation_key="bms_power_factor", ),
]

# Battery items - Smartmeter data accessed through battery (polled at standard interval)
MODBUS_BATTERY_SMARTMETER_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=40, address=40096, name=SAX_SMARTMETER_ENERGY_PRODUCED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=10, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_ENERGY_PRODUCED, translation_key="sm_energy_produced", ),
    ModbusItem(battery_device_id=40, address=40097, name=SAX_SMARTMETER_ENERGY_CONSUMED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=10, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_ENERGY_CONSUMED, translation_key="sm_energy_consumed", ),
    ModbusItem(battery_device_id=40, address=40099, name=SAX_SMARTMETER_SWITCHING_STATE, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_SWITCHING_STATE, translation_key="sm_switching_state", ),
    ModbusItem(battery_device_id=40, address=40100, name=SAX_SMARTMETER_CURRENT_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L1, translation_key="sm_current_l1", ),
    ModbusItem(battery_device_id=40, address=40101, name=SAX_SMARTMETER_CURRENT_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L2, translation_key="sm_current_l2", ),
    ModbusItem(battery_device_id=40, address=40102, name=SAX_SMARTMETER_CURRENT_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L3, translation_key="sm_current_l3", ),
    ModbusItem(battery_device_id=40, address=40103, name=SAX_SMARTMETER_POWER_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L1, translation_key="sm_power_l1", ),
    ModbusItem(battery_device_id=40, address=40104, name=SAX_SMARTMETER_POWER_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L2, translation_key="sm_power_l2", ),
    ModbusItem(battery_device_id=40, address=40105, name=SAX_SMARTMETER_POWER_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L3, translation_key="sm_power_l3", ),
    ModbusItem(battery_device_id=40, address=40107, name=SAX_SMARTMETER_VOLTAGE_L1, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1, translation_key="sm_voltage_l1", ),
    ModbusItem(battery_device_id=40, address=40108, name=SAX_SMARTMETER_VOLTAGE_L2, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2, translation_key="sm_voltage_l2", ),
    ModbusItem(battery_device_id=40, address=40109, name=SAX_SMARTMETER_VOLTAGE_L3, enabled_by_default=False, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3, translation_key="sm_voltage_l3", ),
    ModbusItem(battery_device_id=40, address=40110, name=SAX_SMARTMETER_TOTAL_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER, translation_key="sm_total_power", ),
]

# fmt: on
