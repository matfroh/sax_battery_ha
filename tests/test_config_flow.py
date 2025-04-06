"""Tests for the SAX Battery config flow."""

from unittest.mock import patch

import pytest
import voluptuous as vol

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
)


@pytest.fixture(name="mock_entity_selector")
def mock_entity_selector_fixture():
    """Mock the entity selector."""
    with patch("homeassistant.helpers.selector.EntitySelector") as mock:
        yield mock


@pytest.fixture(name="config_flow")
def config_flow_fixture(hass):
    """Create a config flow instance."""
    return SAXBatteryConfigFlow()


class TestSAXBatteryConfigFlow:
    """Test the SAX Battery config flow."""

    @pytest.fixture(autouse=True)
    def setup_config_flow(self, config_flow):
        """Set up the config flow for testing."""
        config_flow._data = {}
        config_flow._battery_count = 1
        config_flow._pilot_from_ha = True
        return config_flow

    async def test_user_step(self, hass, config_flow, mock_entity_selector):
        """Test the user step."""
        # Test initial form
        result = await config_flow.async_step_user()
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        # Test with valid input
        result = await config_flow.async_step_user({CONF_BATTERY_COUNT: 2})
        assert result["type"] == "form"
        assert result["step_id"] == "control_options"
        assert config_flow._battery_count == 2
        assert config_flow._data[CONF_DEVICE_ID] is not None

    async def test_control_options_step(self, hass, config_flow, mock_entity_selector):
        """Test the control options step."""
        config_flow._battery_count = 2

        # Test initial form
        result = await config_flow.async_step_control_options()
        assert result["type"] == "form"
        assert result["step_id"] == "control_options"

        # Test with pilot from HA enabled
        result = await config_flow.async_step_control_options(
            {CONF_PILOT_FROM_HA: True, CONF_LIMIT_POWER: True}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "pilot_options"
        assert config_flow._pilot_from_ha is True
        assert config_flow._limit_power is True


class TestPilotOptionsFlow:
    """Test the pilot options configuration flow."""

    @pytest.fixture(autouse=True)
    def setup_pilot_options(self, config_flow):
        """Set up pilot options tests."""
        config_flow._battery_count = 1
        config_flow._pilot_from_ha = True
        config_flow._data = {}
        return config_flow

    async def test_valid_input(self, hass, config_flow, mock_entity_selector):
        """Test pilot options with valid input."""
        user_input = {
            CONF_MIN_SOC: DEFAULT_MIN_SOC,
            CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
            CONF_ENABLE_SOLAR_CHARGING: True,
        }
        result = await config_flow.async_step_pilot_options(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "sensors"

    async def test_pilot_options_invalid_values(self, hass, config_flow):
        """Test pilot options with invalid values."""
        config_flow._battery_count = 1
        config_flow._data = {}

        # Test with invalid AUTO_PILOT_INTERVAL
        user_input = {
            CONF_MIN_SOC: DEFAULT_MIN_SOC,
            CONF_AUTO_PILOT_INTERVAL: "invalid",
            CONF_ENABLE_SOLAR_CHARGING: True,
        }
        result = await config_flow.async_step_pilot_options(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "pilot_options"
        assert result["errors"][CONF_AUTO_PILOT_INTERVAL] == "invalid_interval"

    async def test_pilot_options_voluptuous_invalid(self, hass, config_flow):
        """Test pilot options with input that triggers voluptuous.Invalid."""
        config_flow._battery_count = 1
        config_flow._data = {}

        with patch("voluptuous.Schema.__call__", side_effect=vol.Invalid("test error")):
            user_input = {
                CONF_MIN_SOC: DEFAULT_MIN_SOC,
                CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
                CONF_ENABLE_SOLAR_CHARGING: True,
            }
            result = await config_flow.async_step_pilot_options(user_input)
            assert result["type"] == "form"
            assert result["step_id"] == "pilot_options"
            assert result["errors"]["base"] == "invalid_pilot_options"

    async def test_pilot_options_validation_errors(self, hass, config_flow):
        """Test pilot options with various validation errors."""
        test_cases = [
            (
                {
                    CONF_MIN_SOC: "invalid",
                    CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
                    CONF_ENABLE_SOLAR_CHARGING: True,
                },
                "invalid_min_soc",
            ),
            (
                {
                    CONF_MIN_SOC: DEFAULT_MIN_SOC,
                    CONF_AUTO_PILOT_INTERVAL: "invalid",
                    CONF_ENABLE_SOLAR_CHARGING: True,
                },
                "invalid_interval",
            ),
            (
                {
                    CONF_MIN_SOC: 101,  # Above max
                    CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
                    CONF_ENABLE_SOLAR_CHARGING: True,
                },
                "invalid_min_soc",
            ),
            (
                {
                    CONF_MIN_SOC: DEFAULT_MIN_SOC,
                    CONF_AUTO_PILOT_INTERVAL: 4,  # Below min
                    CONF_ENABLE_SOLAR_CHARGING: True,
                },
                "invalid_interval",
            ),
        ]

        for user_input, expected_error in test_cases:
            result = await config_flow.async_step_pilot_options(user_input)
            assert result["type"] == "form"
            assert result["step_id"] == "pilot_options"
            assert any(expected_error in error for error in result["errors"].values())

    async def test_pilot_options_invalid_input(self, hass, config_flow):
        """Test pilot options with invalid inputs."""
        config_flow._battery_count = 1
        config_flow._data = {}

        test_cases = [
            # Test MIN_SOC validation
            {
                CONF_MIN_SOC: 101,  # Too high
                CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
                CONF_ENABLE_SOLAR_CHARGING: True,
            },
            {
                CONF_MIN_SOC: -1,  # Too low
                CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
                CONF_ENABLE_SOLAR_CHARGING: True,
            },
            {
                CONF_MIN_SOC: "invalid",  # Invalid type
                CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
                CONF_ENABLE_SOLAR_CHARGING: True,
            },
            # Test AUTO_PILOT_INTERVAL validation
            {
                CONF_MIN_SOC: DEFAULT_MIN_SOC,
                CONF_AUTO_PILOT_INTERVAL: 4,  # Too low
                CONF_ENABLE_SOLAR_CHARGING: True,
            },
            {
                CONF_MIN_SOC: DEFAULT_MIN_SOC,
                CONF_AUTO_PILOT_INTERVAL: 301,  # Too high
                CONF_ENABLE_SOLAR_CHARGING: True,
            },
            {
                CONF_MIN_SOC: DEFAULT_MIN_SOC,
                CONF_AUTO_PILOT_INTERVAL: "invalid",  # Invalid type
                CONF_ENABLE_SOLAR_CHARGING: True,
            },
        ]

        for user_input in test_cases:
            result = await config_flow.async_step_pilot_options(user_input)
            assert result["type"] == "form"
            assert result["step_id"] == "pilot_options"
            assert len(result["errors"]) > 0
            # Verify either MIN_SOC or AUTO_PILOT_INTERVAL has an error
            assert any(
                key in result["errors"]
                for key in [CONF_MIN_SOC, CONF_AUTO_PILOT_INTERVAL]
            )


class TestSensorsFlow:
    """Test the sensors configuration flow."""

    @pytest.fixture(autouse=True)
    def setup_sensors(self, config_flow):
        """Set up sensors tests."""
        config_flow._data = {}
        config_flow._pilot_from_ha = True
        return config_flow

    async def test_sensors_with_pilot_from_ha(
        self, hass, config_flow, mock_entity_selector
    ):
        """Test sensors step with pilot from HA enabled."""
        result = await config_flow.async_step_sensors()
        assert result["type"] == "form"
        assert result["step_id"] == "sensors"

        user_input = {
            CONF_POWER_SENSOR: "sensor.power",
            CONF_PF_SENSOR: "sensor.pf",
        }
        result = await config_flow.async_step_sensors(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "priority_devices"
        assert config_flow._data[CONF_POWER_SENSOR] == "sensor.power"
        assert config_flow._data[CONF_PF_SENSOR] == "sensor.pf"

    async def test_sensors_without_pilot_from_ha(
        self, hass, config_flow, mock_entity_selector
    ):
        """Test sensors step with pilot from HA disabled."""
        config_flow._pilot_from_ha = False
        result = await config_flow.async_step_sensors()
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"

    async def test_sensors_step_skip_when_not_pilot_from_ha(self, hass, config_flow):
        """Test that sensors step is skipped when not piloting from HA."""
        # Set pilot_from_ha to False
        config_flow._pilot_from_ha = False
        config_flow._data = {}

        # Call async_step_sensors without user_input
        result = await config_flow.async_step_sensors()

        # Verify it skips to battery config
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"


class TestPriorityDevicesFlow:
    """Test the priority devices configuration flow."""

    @pytest.fixture(autouse=True)
    def setup_priority_devices(self, config_flow):
        """Set up priority devices tests."""
        config_flow._data = {}
        return config_flow

    async def test_priority_devices_with_devices(
        self, hass, config_flow, mock_entity_selector
    ):
        """Test priority devices step with devices selected."""
        result = await config_flow.async_step_priority_devices()
        assert result["type"] == "form"
        assert result["step_id"] == "priority_devices"

        user_input = {CONF_PRIORITY_DEVICES: ["sensor.device1", "sensor.device2"]}
        result = await config_flow.async_step_priority_devices(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"
        assert config_flow._data[CONF_PRIORITY_DEVICES] == [
            "sensor.device1",
            "sensor.device2",
        ]

    async def test_priority_devices_without_devices(
        self, hass, config_flow, mock_entity_selector
    ):
        """Test priority devices step with no devices selected."""
        user_input = {CONF_PRIORITY_DEVICES: []}
        result = await config_flow.async_step_priority_devices(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"


class TestBatteryConfigFlow:
    """Test the battery configuration flow."""

    @pytest.fixture(autouse=True)
    def setup_battery_config(self, config_flow):
        """Set up battery config tests."""
        config_flow._data = {}
        config_flow._battery_count = 2
        return config_flow

    async def test_battery_config_single_battery(self, hass, config_flow):
        """Test battery configuration with a single battery."""
        config_flow._battery_count = 1
        result = await config_flow.async_step_battery_config()
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"

        user_input = {
            "battery_a_host": "192.168.1.10",
            "battery_a_port": DEFAULT_PORT,
            CONF_MASTER_BATTERY: "battery_a",
        }
        result = await config_flow.async_step_battery_config(user_input)
        assert result["type"] == "create_entry"
        assert result["title"] == "SAX Battery"
        assert result["data"][CONF_MASTER_BATTERY] == "battery_a"

    async def test_battery_config_multiple_batteries(self, hass, config_flow):
        """Test battery configuration with multiple batteries."""
        result = await config_flow.async_step_battery_config()
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"

        user_input = {
            "battery_a_host": "192.168.1.10",
            "battery_a_port": DEFAULT_PORT,
            "battery_b_host": "192.168.1.11",
            "battery_b_port": DEFAULT_PORT,
            CONF_MASTER_BATTERY: "battery_a",
        }
        result = await config_flow.async_step_battery_config(user_input)
        assert result["type"] == "create_entry"
        assert result["title"] == "SAX Battery"
        assert result["data"][CONF_MASTER_BATTERY] == "battery_a"

    async def test_battery_config_none_battery_count(self, hass, config_flow):
        """Test battery configuration with None battery count."""
        config_flow._battery_count = None
        result = await config_flow.async_step_battery_config()
        assert result["type"] == "form"
        assert result["step_id"] == "battery_config"


@pytest.mark.asyncio
async def test_config_flow_initialization():
    """Test ConfigFlow initialization and attribute access."""
    flow = SAXBatteryConfigFlow()
    # Force attribute access to ensure coverage
    assert isinstance(flow._data, dict)
    assert len(flow._data) == 0
    assert flow._battery_count is None
    assert flow._pilot_from_ha is False
    assert flow._limit_power is False
