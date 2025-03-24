"""Tests for the SAX Battery config flow."""

from unittest.mock import patch

import pytest

from custom_components.sax_battery.config_flow import SAXBatteryConfigFlow

# filepath: custom_components/sax_battery/test_config_flow.py
from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_BATTERY_COUNT,
    CONF_DEVICE_ID,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    CONF_PRIORITY_DEVICES,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DEFAULT_PORT,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector


@pytest.fixture
def config_flow():
    """Fixture to initialize the config flow."""
    return SAXBatteryConfigFlow()


async def test_async_step_user(hass, config_flow):
    """Test the initial step."""
    with patch("homeassistant.helpers.selector.EntitySelector"):
        result = await config_flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        user_input = {CONF_BATTERY_COUNT: 2}
        result = await config_flow.async_step_user(user_input=user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "control_options"
        assert config_flow._battery_count == 2
        assert config_flow._data[CONF_DEVICE_ID] is not None


async def test_async_step_control_options(hass, config_flow):
    """Test the control options step."""
    config_flow._battery_count = 2
    with patch("homeassistant.helpers.selector.EntitySelector"):
        result = await config_flow.async_step_control_options(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "control_options"

        user_input = {CONF_PILOT_FROM_HA: True, CONF_LIMIT_POWER: True}
        result = await config_flow.async_step_control_options(user_input=user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "pilot_options"
        assert config_flow._pilot_from_ha is True
        assert config_flow._limit_power is True


async def test_async_step_pilot_options(hass, config_flow):
    """Test the pilot options step."""
    with patch("homeassistant.helpers.selector.EntitySelector"):
        result = await config_flow.async_step_pilot_options(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "pilot_options"

        user_input = {
            CONF_MIN_SOC: DEFAULT_MIN_SOC,
            CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
            CONF_ENABLE_SOLAR_CHARGING: True,
        }
        result = await config_flow.async_step_pilot_options(user_input=user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "sensors"


async def test_async_step_sensors(hass, config_flow):
    """Test the sensors step."""
    config_flow._pilot_from_ha = True
    with patch("homeassistant.helpers.selector.EntitySelector"):
        result = await config_flow.async_step_sensors(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "sensors"

        user_input = {
            CONF_POWER_SENSOR: "sensor.power",
            CONF_PF_SENSOR: "sensor.pf",
        }
        result = await config_flow.async_step_sensors(user_input=user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "priority_devices"


async def test_async_step_priority_devices(hass, config_flow):
    """Test the priority devices step."""
    with patch("homeassistant.helpers.selector.EntitySelector"):
        result = await config_flow.async_step_priority_devices(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "priority_devices"

        user_input = {CONF_PRIORITY_DEVICES: ["sensor.device_1", "sensor.device_2"]}
        result = await config_flow.async_step_priority_devices(user_input=user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"


async def test_async_step_battery_config(hass, config_flow):
    """Test the battery config step."""
    config_flow._battery_count = 2
    with patch("homeassistant.helpers.selector.EntitySelector"):
        result = await config_flow.async_step_battery_config(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"

        user_input = {
            "battery_a_host": "192.168.1.10",
            "battery_a_port": DEFAULT_PORT,
            "battery_b_host": "192.168.1.11",
            "battery_b_port": DEFAULT_PORT,
            CONF_MASTER_BATTERY: "battery_a",
        }
        result = await config_flow.async_step_battery_config(user_input=user_input)
        assert result["type"] == "create_entry"
        assert result["title"] == "SAX Battery"
        assert result["data"][CONF_MASTER_BATTERY] == "battery_a"
