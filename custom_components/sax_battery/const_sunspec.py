"""SunSpec-related entity definitions and constants for the SAX battery integration."""

from __future__ import annotations

from pymodbus.client.mixin import ModbusClientMixin

from .const import (
    DESCRIPTION_SAX_CAPACITY,
    DESCRIPTION_SAX_POWER,
    DESCRIPTION_SAX_POWER_SM,
    DESCRIPTION_SAX_SCALE_FACTOR_AC_CURRENT,
    DESCRIPTION_SAX_SCALE_FACTOR_APPARENT_POWER,
    DESCRIPTION_SAX_SCALE_FACTOR_FREQUENCY,
    DESCRIPTION_SAX_SCALE_FACTOR_POWER,
    DESCRIPTION_SAX_SCALE_FACTOR_POWER_FACTOR,
    DESCRIPTION_SAX_SCALE_FACTOR_REACTIVE_POWER,
    DESCRIPTION_SAX_SCALE_FACTOR_VOLTAGE,
    DESCRIPTION_SAX_SMARTMETER_AC_CURRENT_SUM,
    DESCRIPTION_SAX_SMARTMETER_APPARENT_POWER,
    DESCRIPTION_SAX_SMARTMETER_CURRENT_L1,
    DESCRIPTION_SAX_SMARTMETER_CURRENT_L2,
    DESCRIPTION_SAX_SMARTMETER_CURRENT_L3,
    DESCRIPTION_SAX_SMARTMETER_ENERGY_CONSUMED,
    DESCRIPTION_SAX_SMARTMETER_ENERGY_PRODUCED,
    DESCRIPTION_SAX_SMARTMETER_FREQUENCY,
    DESCRIPTION_SAX_SMARTMETER_POWER_FACTOR,
    DESCRIPTION_SAX_SMARTMETER_POWER_L1,
    DESCRIPTION_SAX_SMARTMETER_POWER_L2,
    DESCRIPTION_SAX_SMARTMETER_POWER_L3,
    DESCRIPTION_SAX_SMARTMETER_REACTIVE_POWER,
    DESCRIPTION_SAX_SMARTMETER_SWITCHING_STATE,
    DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER,
    DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1,
    DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2,
    DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3,
    DESCRIPTION_SAX_SOC,
    DESCRIPTION_SAX_STATUS_SWITCH,
    DESCRIPTION_SAX_SUNSPEC_CONTROL_MODE,
    DESCRIPTION_SAX_SUNSPEC_POWER_SETPOINT,
    DESCRIPTION_SAX_SUNSPEC_REFERENCE_POWER,
    DESCRIPTION_SAX_SUNSPEC_SETPOINT_SCALE_FACTOR,
    DESCRIPTION_SAX_SUNSPEC_SETPOINT_TIMEOUT,
    DESCRIPTION_SAX_TEMPERATURE,
)
from .entity_keys import (
    SAX_CAPACITY,
    SAX_POWER,
    SAX_POWER_SM,
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
    SAX_SMARTMETER_VOLTAGE_L2,
    SAX_SMARTMETER_VOLTAGE_L3,
    SAX_SOC,
    SAX_STATUS,
    SAX_SUNSPEC_CONTROL_MODE,
    SAX_SUNSPEC_POWER_SETPOINT,
    SAX_SUNSPEC_REFERENCE_POWER,
    SAX_SUNSPEC_SETPOINT_SCALE_FACTOR,
    SAX_SUNSPEC_SETPOINT_TIMEOUT,
    SAX_TEMPERATURE,
)
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem

# SunSpec protocol identifiers and model IDs
SUNSPEC_ID_WORD_0 = 21365
SUNSPEC_ID_WORD_1 = 28243
SUNSPEC_MODEL_COMMON = 1
SUNSPEC_MODEL_INVERTER = 103
SUNSPEC_MODEL_IMMEDIATE_CONTROLS = 123
SUNSPEC_MODEL_METER = 203

# fmt: off

# SunSpec entity definitions for the new firmware line
MODBUS_SUNSPEC_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=100, address=40000, name=SAX_SOC, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_SOC, translation_key="bess_soc",  ),
    ModbusItem(battery_device_id=100, address=40001, name=SAX_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_POWER, translation_key="bess_power", ),
    ModbusItem(battery_device_id=100, address=40002, name=SAX_POWER_SM, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_POWER_SM, translation_key="bess_power_sm", ),
    ModbusItem(battery_device_id=100, address=40003, name=SAX_STATUS, mtype=TypeConstants.SWITCH, data_type=ModbusClientMixin.DATATYPE.UINT16, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_STATUS_SWITCH, translation_key="bess_status", ),
]

# Additional SunSpec-specific entity definitions (kept scaffolded for later mapping)
MODBUS_SUNSPEC_EXTENDED_ITEMS: list[ModbusItem] = [
    ModbusItem(battery_device_id=100, address=40015, name=SAX_CAPACITY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_CAPACITY, translation_key="bess_capacity", ),
    ModbusItem(battery_device_id=100, address=40016, name=SAX_TEMPERATURE, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.BESS, entitydescription=DESCRIPTION_SAX_TEMPERATURE, translation_key="bess_temperature", ),
    ModbusItem(battery_device_id=100, address=40049, name=SAX_SUNSPEC_POWER_SETPOINT, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.01, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_SUNSPEC_POWER_SETPOINT, translation_key="sunspec_power_setpoint", ),
    ModbusItem(battery_device_id=100, address=40050, name=SAX_SUNSPEC_SETPOINT_TIMEOUT, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_SUNSPEC_SETPOINT_TIMEOUT, translation_key="sunspec_setpoint_timeout", ),
    ModbusItem(battery_device_id=100, address=40051, name=SAX_SUNSPEC_CONTROL_MODE, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_SUNSPEC_CONTROL_MODE, translation_key="sunspec_control_mode", ),
    ModbusItem(battery_device_id=100, address=40052, name=SAX_SUNSPEC_SETPOINT_SCALE_FACTOR, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_SUNSPEC_SETPOINT_SCALE_FACTOR, translation_key="sunspec_setpoint_scale_factor", ),
    ModbusItem(battery_device_id=100, address=40053, name=SAX_SUNSPEC_REFERENCE_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SYS, entitydescription=DESCRIPTION_SAX_SUNSPEC_REFERENCE_POWER, translation_key="sunspec_reference_power", ),
    ModbusItem(battery_device_id=100, address=40054, name=SAX_SMARTMETER_ENERGY_PRODUCED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_ENERGY_PRODUCED, translation_key="sm_energy_produced", ),
    ModbusItem(battery_device_id=100, address=40097, name=SAX_SMARTMETER_ENERGY_CONSUMED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_ENERGY_CONSUMED, translation_key="sm_energy_consumed", ),
    ModbusItem(battery_device_id=100, address=40099, name=SAX_SMARTMETER_SWITCHING_STATE, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_SWITCHING_STATE, translation_key="sm_switching_state", ),
    ModbusItem(battery_device_id=100, address=40096, name=SAX_SMARTMETER_ENERGY_PRODUCED, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=10.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_ENERGY_PRODUCED, translation_key="sm_energy_produced", ),
    ModbusItem(battery_device_id=100, address=40100, name=SAX_SMARTMETER_CURRENT_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L1, translation_key="sm_current_l1", ),
    ModbusItem(battery_device_id=100, address=40101, name=SAX_SMARTMETER_CURRENT_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L2, translation_key="sm_current_l2", ),
    ModbusItem(battery_device_id=100, address=40102, name=SAX_SMARTMETER_CURRENT_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L3, translation_key="sm_current_l3", ),
    ModbusItem(battery_device_id=100, address=40103, name=SAX_SMARTMETER_POWER_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L1, translation_key="sm_power_l1", ),
    ModbusItem(battery_device_id=100, address=40104, name=SAX_SMARTMETER_POWER_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L2, translation_key="sm_power_l2", ),
    ModbusItem(battery_device_id=100, address=40105, name=SAX_SMARTMETER_POWER_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L3, translation_key="sm_power_l3", ),
    ModbusItem(battery_device_id=100, address=40107, name=SAX_SMARTMETER_VOLTAGE_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1, translation_key="sm_voltage_l1", ),
    ModbusItem(battery_device_id=100, address=40108, name=SAX_SMARTMETER_VOLTAGE_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2, translation_key="sm_voltage_l2", ),
    ModbusItem(battery_device_id=100, address=40109, name=SAX_SMARTMETER_VOLTAGE_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=0.1, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3, translation_key="sm_voltage_l3", ),
    ModbusItem(battery_device_id=100, address=40110, name=SAX_SMARTMETER_TOTAL_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER, translation_key="sm_total_power", ),
    ModbusItem(battery_device_id=100, address=40056, name=SAX_SMARTMETER_AC_CURRENT_SUM, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_AC_CURRENT_SUM, translation_key="sm_ac_current_sum", ),
    ModbusItem(battery_device_id=100, address=40057, name=SAX_SMARTMETER_CURRENT_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L1, translation_key="sm_current_l1", ),
    ModbusItem(battery_device_id=100, address=40058, name=SAX_SMARTMETER_CURRENT_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L2, translation_key="sm_current_l2", ),
    ModbusItem(battery_device_id=100, address=40059, name=SAX_SMARTMETER_CURRENT_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_CURRENT_L3, translation_key="sm_current_l3", ),
    ModbusItem(battery_device_id=100, address=40060, name=SAX_SCALE_FACTOR_AC_CURRENT, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SCALE_FACTOR_AC_CURRENT, translation_key="sm_scale_factor_ac_current", ),
    ModbusItem(battery_device_id=100, address=40062, name=SAX_SMARTMETER_VOLTAGE_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L1, translation_key="sm_voltage_l1", ),
    ModbusItem(battery_device_id=100, address=40063, name=SAX_SMARTMETER_VOLTAGE_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L2, translation_key="sm_voltage_l2", ),
    ModbusItem(battery_device_id=100, address=40064, name=SAX_SMARTMETER_VOLTAGE_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_VOLTAGE_L3, translation_key="sm_voltage_l3", ),
    ModbusItem(battery_device_id=100, address=40069, name=SAX_SCALE_FACTOR_VOLTAGE, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SCALE_FACTOR_VOLTAGE, translation_key="sm_scale_factor_voltage", ),
    ModbusItem(battery_device_id=100, address=40070, name=SAX_SMARTMETER_FREQUENCY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_FREQUENCY, translation_key="sm_frequency", ),
    ModbusItem(battery_device_id=100, address=40071, name=SAX_SCALE_FACTOR_FREQUENCY, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SCALE_FACTOR_FREQUENCY, translation_key="sm_scale_factor_frequency", ),
    ModbusItem(battery_device_id=100, address=40072, name=SAX_SMARTMETER_TOTAL_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_TOTAL_POWER, translation_key="sm_total_power", ),
    ModbusItem(battery_device_id=100, address=40073, name=SAX_SMARTMETER_POWER_L1, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L1, translation_key="sm_power_l1", ),
    ModbusItem(battery_device_id=100, address=40074, name=SAX_SMARTMETER_POWER_L2, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L2, translation_key="sm_power_l2", ),
    ModbusItem(battery_device_id=100, address=40075, name=SAX_SMARTMETER_POWER_L3, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_L3, translation_key="sm_power_l3", ),
    ModbusItem(battery_device_id=100, address=40076, name=SAX_SCALE_FACTOR_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SCALE_FACTOR_POWER, translation_key="sm_scale_factor_power", ),
    ModbusItem(battery_device_id=100, address=40077, name=SAX_SMARTMETER_APPARENT_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.UINT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_APPARENT_POWER, translation_key="sm_apparent_power", ),
    ModbusItem(battery_device_id=100, address=40081, name=SAX_SCALE_FACTOR_APPARENT_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SCALE_FACTOR_APPARENT_POWER, translation_key="sm_scale_factor_apparent_power", ),
    ModbusItem(battery_device_id=100, address=40082, name=SAX_SMARTMETER_REACTIVE_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_REACTIVE_POWER, translation_key="sm_reactive_power", ),
    ModbusItem(battery_device_id=100, address=40086, name=SAX_SCALE_FACTOR_REACTIVE_POWER, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SCALE_FACTOR_REACTIVE_POWER, translation_key="sm_scale_factor_reactive_power", ),
    ModbusItem(battery_device_id=100, address=40087, name=SAX_SMARTMETER_POWER_FACTOR, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SMARTMETER_POWER_FACTOR, translation_key="sm_power_factor", ),
    ModbusItem(battery_device_id=100, address=40091, name=SAX_SCALE_FACTOR_POWER_FACTOR, mtype=TypeConstants.SENSOR, data_type=ModbusClientMixin.DATATYPE.INT16, factor=1.0, device=DeviceConstants.SM, entitydescription=DESCRIPTION_SAX_SCALE_FACTOR_POWER_FACTOR, translation_key="sm_scale_factor_power_factor", ),
]

# fmt: on


def get_canonical_sunspec_items_by_name() -> dict[str, ModbusItem]:
    """Return canonical SunSpec items keyed by name.

    When one logical key appears in multiple documented areas, prefer the
    highest register address so state-block aliases in 40095+ override older
    smart-meter aliases from 40054+.
    """
    canonical_items: dict[str, ModbusItem] = {}

    for item in [*MODBUS_SUNSPEC_ITEMS, *MODBUS_SUNSPEC_EXTENDED_ITEMS]:
        current = canonical_items.get(item.name)
        if current is None or item.address > current.address:
            canonical_items[item.name] = item

    return canonical_items
