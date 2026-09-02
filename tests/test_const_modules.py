"""Regression tests for the split legacy/SunSpec constant modules."""

from custom_components.sax_battery import entity_keys
from custom_components.sax_battery.const import (
    DESCRIPTION_SAX_SCALE_FACTOR_AC_CURRENT,
    DESCRIPTION_SAX_SUNSPEC_CONTROL_MODE,
)
from custom_components.sax_battery.const_legacy import (
    MODBUS_BATTERY_BMS_ITEMS,
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
)
from custom_components.sax_battery.const_sunspec import (
    MODBUS_SUNSPEC_ITEMS,
    SUNSPEC_MODEL_COMMON,
    SUNSPEC_MODEL_IMMEDIATE_CONTROLS,
    SUNSPEC_MODEL_INVERTER,
    SUNSPEC_MODEL_METER,
)


def test_split_constant_modules_expose_expected_items() -> None:
    """Legacy and SunSpec constants should remain importable from the refactored modules."""
    assert MODBUS_BATTERY_POWER_CONTROL_ITEMS
    assert MODBUS_BATTERY_BMS_ITEMS
    assert MODBUS_SUNSPEC_ITEMS
    assert SUNSPEC_MODEL_COMMON == 1
    assert SUNSPEC_MODEL_INVERTER == 103
    assert SUNSPEC_MODEL_IMMEDIATE_CONTROLS == 123
    assert SUNSPEC_MODEL_METER == 203


def test_sunspec_documented_entity_keys_and_descriptions_are_available() -> None:
    """SunSpec documentation-derived entity keys and descriptions should be defined."""
    assert entity_keys.SAX_SMARTMETER_AC_CURRENT_SUM == "ac_current_sum_sm"
    assert entity_keys.SAX_SMARTMETER_FREQUENCY == "frequency_sm"
    assert entity_keys.SAX_SMARTMETER_VOLTAGE_L1_L2 == "voltage_l1_l2_sm"
    assert entity_keys.SAX_SMARTMETER_VOLTAGE_L2_L3 == "voltage_l2_l3_sm"
    assert entity_keys.SAX_SMARTMETER_VOLTAGE_L3_L1 == "voltage_l3_l1_sm"
    assert entity_keys.SAX_SCALE_FACTOR_AC_CURRENT == "scale_factor_ac_current"
    assert entity_keys.SAX_SUNSPEC_CONTROL_MODE == "sunspec_control_mode"
    assert (
        DESCRIPTION_SAX_SCALE_FACTOR_AC_CURRENT.key
        == entity_keys.SAX_SCALE_FACTOR_AC_CURRENT
    )
    assert (
        DESCRIPTION_SAX_SUNSPEC_CONTROL_MODE.key == entity_keys.SAX_SUNSPEC_CONTROL_MODE
    )
