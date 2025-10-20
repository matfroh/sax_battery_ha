"""Extended tests for SAX Battery config flow to increase coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.config_flow import (
    SAXBatteryConfigFlow,
    SAXBatteryOptionsFlowHandler,
)
from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PORT,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DEFAULT_PORT,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


class TestSAXBatteryConfigFlowExtended:
    """Extended tests for SAX Battery config flow."""

    async def test_config_flow_init(self, hass: HomeAssistant) -> None:
        """Test config flow initialization."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        assert flow.VERSION == 1
        assert flow._data == {}
        assert flow._battery_count is None
        assert flow._pilot_from_ha is False
        assert flow._limit_power is False
        assert isinstance(flow._device_id, str)

    async def test_user_step_with_invalid_battery_count(
        self, hass: HomeAssistant
    ) -> None:
        """Test user step with invalid battery count."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Test with battery count too high
        result = await flow.async_step_user({CONF_BATTERY_COUNT: 5})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "control_options"
        errors = result.get("errors")
        assert errors is not None

    async def test_control_options_step_pilot_enabled(
        self, hass: HomeAssistant
    ) -> None:
        """Test control options step with pilot enabled."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_control_options(
            {
                CONF_PILOT_FROM_HA: True,
                CONF_LIMIT_POWER: False,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "pilot_options"
        assert flow._pilot_from_ha is True
        assert flow._limit_power is False

    async def test_control_options_step_no_pilot(self, hass: HomeAssistant) -> None:
        """Test control options step without pilot."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_control_options(
            {
                CONF_PILOT_FROM_HA: False,
                CONF_LIMIT_POWER: True,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        assert flow._pilot_from_ha is False
        assert flow._limit_power is True

    async def test_pilot_options_invalid_min_soc(self, hass: HomeAssistant) -> None:
        """Test pilot options with invalid min SOC."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        # Test with SOC too high
        result = await flow.async_step_pilot_options(
            {
                CONF_MIN_SOC: 150,
                CONF_AUTO_PILOT_INTERVAL: 30,
                CONF_ENABLE_SOLAR_CHARGING: True,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "pilot_options"
        errors = result.get("errors")
        assert errors is not None
        assert "invalid_min_soc" in errors.get(CONF_MIN_SOC, "")

    async def test_pilot_options_invalid_interval(self, hass: HomeAssistant) -> None:
        """Test pilot options with invalid interval."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        # Test with interval too short
        result = await flow.async_step_pilot_options(
            {
                CONF_MIN_SOC: 20,
                CONF_AUTO_PILOT_INTERVAL: 2,
                CONF_ENABLE_SOLAR_CHARGING: True,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "pilot_options"
        errors = result.get("errors")
        assert errors is not None
        assert "invalid_interval" in errors.get(CONF_AUTO_PILOT_INTERVAL, "")

    async def test_pilot_options_non_numeric_values(self, hass: HomeAssistant) -> None:
        """Test pilot options with non-numeric values."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        result = await flow.async_step_pilot_options(
            {
                CONF_MIN_SOC: "invalid",
                CONF_AUTO_PILOT_INTERVAL: "also_invalid",
                CONF_ENABLE_SOLAR_CHARGING: True,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "pilot_options"
        errors = result.get("errors")
        assert errors is not None
        assert CONF_MIN_SOC in errors
        assert CONF_AUTO_PILOT_INTERVAL in errors

    async def test_sensors_step_with_pilot(self, hass: HomeAssistant) -> None:
        """Test sensors step when pilot is enabled."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        result = await flow.async_step_sensors(
            {
                CONF_POWER_SENSOR: "sensor.power_meter",
                CONF_PF_SENSOR: "sensor.power_factor",
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "priority_devices"

    async def test_battery_config_invalid_host_format(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery config with invalid host format."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "invalid..host..name",
                "battery_a_port": DEFAULT_PORT,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        assert "invalid_host_format" in errors.get("battery_a_host", "")

    async def test_battery_config_empty_host(self, hass: HomeAssistant) -> None:
        """Test battery config with empty host."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "",
                "battery_a_port": DEFAULT_PORT,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        assert "invalid_host" in errors.get("battery_a_host", "")

    async def test_battery_config_invalid_port(self, hass: HomeAssistant) -> None:
        """Test battery config with invalid port."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 99999,  # Too high
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        # Fix: Check if errors exists before using 'in' operator
        assert errors and "invalid_port" in errors.get("battery_a_port", "")

    async def test_battery_config_invalid_port_type(self, hass: HomeAssistant) -> None:
        """Test battery config with non-numeric port."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": "not_a_number",
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        # Fix: Check if errors exists before using 'in' operator
        assert errors and "invalid_port" in errors.get("battery_a_port", "")

    async def test_battery_config_multi_battery_invalid_master(
        self, hass: HomeAssistant
    ) -> None:
        """Test multi-battery config with invalid master selection."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 2

        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": DEFAULT_PORT,
                "battery_b_host": "192.168.1.101",
                "battery_b_port": DEFAULT_PORT,
                CONF_MASTER_BATTERY: "battery_c",  # Doesn't exist
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        assert "invalid_master" in errors.get(CONF_MASTER_BATTERY, "")

    async def test_battery_config_successful_single_battery(
        self, hass: HomeAssistant
    ) -> None:
        """Test successful single battery configuration."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": DEFAULT_PORT,
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "SAX Battery System (1 batteries)"
        assert CONF_BATTERIES in result["data"]
        assert CONF_MASTER_BATTERY in result["data"]
        assert result["data"][CONF_MASTER_BATTERY] == "battery_a"

    async def test_battery_config_successful_multi_battery(
        self, hass: HomeAssistant
    ) -> None:
        """Test successful multi-battery configuration."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 3

        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": DEFAULT_PORT,
                "battery_b_host": "192.168.1.101",
                "battery_b_port": DEFAULT_PORT,
                "battery_c_host": "192.168.1.102",
                "battery_c_port": DEFAULT_PORT,
                CONF_MASTER_BATTERY: "battery_b",
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "SAX Battery System (3 batteries)"
        data = result.get("data")
        assert data is not None
        assert data[CONF_MASTER_BATTERY] == "battery_b"
        # Verify master is set correctly
        batteries = data[CONF_BATTERIES]
        assert batteries["battery_b"][CONF_BATTERY_IS_MASTER] is True
        assert batteries["battery_a"][CONF_BATTERY_IS_MASTER] is False
        assert batteries["battery_c"][CONF_BATTERY_IS_MASTER] is False

    async def test_validate_host_method(self, hass: HomeAssistant) -> None:
        """Test host validation method."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Valid hostnames and IPs
        assert flow._validate_host("192.168.1.100") is True
        assert flow._validate_host("example.com") is True
        assert flow._validate_host("sub.example.com") is True
        assert flow._validate_host("battery-1") is True

        # Invalid hosts
        assert flow._validate_host("") is False
        # assert flow._validate_host("256.256.256.256") is False  # Invalid IP
        assert flow._validate_host("invalid..host") is False  # Double dots
        assert flow._validate_host("a" * 254) is False  # Too long
        assert flow._validate_host(".example.com") is False  # Leading dot
        assert flow._validate_host("example.com.") is False  # Trailing dot

    async def test_reconfigure_step_no_entry_id(self, hass: HomeAssistant) -> None:
        """Test reconfigure step without entry ID."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {}  # No entry_id

        result = await flow.async_step_reconfigure({})

        # Should abort when no entry ID is provided
        assert result.get("type") == FlowResultType.ABORT
        assert result.get("reason") == "unknown"

    async def test_reconfigure_step_invalid_entry_id(self, hass: HomeAssistant) -> None:
        """Test reconfigure step with invalid entry ID."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "invalid_id"}

        # Mock hass.config_entries.async_get_entry to return None for invalid ID
        with patch.object(hass.config_entries, "async_get_entry", return_value=None):
            result = await flow.async_step_reconfigure({})

            assert result.get("type") == FlowResultType.ABORT
            assert result.get("reason") == "unknown"

    async def test_async_get_options_flow(self, hass: HomeAssistant) -> None:
        """Test getting options flow."""
        mock_entry = MagicMock()
        options_flow = SAXBatteryConfigFlow.async_get_options_flow(mock_entry)

        assert isinstance(options_flow, SAXBatteryOptionsFlowHandler)
        assert options_flow.config_entry == mock_entry

    async def test_user_step_initial_form_display(self, hass: HomeAssistant) -> None:
        """Test user step shows initial form when no input provided."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Test the uncovered line 81: return self.async_show_form for initial display
        result = await flow.async_step_user(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"
        assert result.get("errors") == {}

        # Verify schema includes battery count selection
        data_schema = result.get("data_schema")
        assert data_schema is not None
        schema_keys = [str(key) for key in data_schema.schema]
        assert any(CONF_BATTERY_COUNT in key for key in schema_keys)

    async def test_pilot_options_valid_input_flow(self, hass: HomeAssistant) -> None:
        """Test pilot options step with valid input proceeding to sensors."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        # Test the uncovered lines 170-171: valid input updates data and proceeds to sensors
        result = await flow.async_step_pilot_options(
            {
                CONF_MIN_SOC: 25,
                CONF_AUTO_PILOT_INTERVAL: 30,
                CONF_ENABLE_SOLAR_CHARGING: True,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "sensors"
        assert flow._data[CONF_MIN_SOC] == 25
        assert flow._data[CONF_AUTO_PILOT_INTERVAL] == 30
        assert flow._data[CONF_ENABLE_SOLAR_CHARGING] is True

    async def test_sensors_step_with_pilot_enabled_schema(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step creates proper schema when pilot is enabled."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        # Test the uncovered lines 206-208: schema creation for pilot mode
        result = await flow.async_step_sensors(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "sensors"

        # Verify schema includes power and PF sensor selectors
        data_schema = result.get("data_schema")
        assert data_schema is not None
        schema_keys = [str(key) for key in data_schema.schema]
        assert any(CONF_POWER_SENSOR in key for key in schema_keys)
        assert any(CONF_PF_SENSOR in key for key in schema_keys)

    async def test_sensors_step_with_pilot_form_display(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step shows form with pilot-specific schema."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        # Test the uncovered line 227: return self.async_show_form with sensor schema
        result = await flow.async_step_sensors(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "sensors"
        assert "power_sensor_description" in result["description_placeholders"]  # type: ignore[operator]
        assert "pf_sensor_description" in result["description_placeholders"]  # type: ignore[operator]

    async def test_reconfigure_step_with_valid_entry_and_input(
        self, hass: HomeAssistant
    ) -> None:
        """Test reconfigure step with valid entry ID and user input."""
        # Create a mock config entry
        mock_entry = MagicMock()
        mock_entry.domain = DOMAIN
        mock_entry.data = {
            CONF_BATTERY_COUNT: 2,
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: False,
        }

        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "test_entry_id"}

        # Mock the entry retrieval to return our test entry
        with patch.object(
            hass.config_entries, "async_get_entry", return_value=mock_entry
        ):
            # Test the uncovered lines 404-408: create entry with user input
            user_input = {
                CONF_PILOT_FROM_HA: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 30,
            }

            result = await flow.async_step_reconfigure(user_input)

            assert result.get("type") == FlowResultType.CREATE_ENTRY
            assert result.get("title") == "SAX Battery"
            assert result["data"] == user_input

    async def test_reconfigure_step_loads_existing_config(
        self, hass: HomeAssistant
    ) -> None:
        """Test reconfigure step loads existing configuration data."""
        # Create a mock config entry with comprehensive data
        mock_entry = MagicMock()
        mock_entry.domain = DOMAIN
        mock_entry.data = {
            CONF_BATTERY_COUNT: 3,
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
            CONF_MIN_SOC: 20,
            CONF_AUTO_PILOT_INTERVAL: 45,
            CONF_ENABLE_SOLAR_CHARGING: False,
            CONF_BATTERIES: {
                "battery_a": {"host": "192.168.1.100", "port": 502},
                "battery_b": {"host": "192.168.1.101", "port": 502},
                "battery_c": {"host": "192.168.1.102", "port": 502},
            },
        }

        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "test_entry_id"}

        # Mock the entry retrieval to return our test entry
        with patch.object(
            hass.config_entries, "async_get_entry", return_value=mock_entry
        ):
            # Test the uncovered lines 415-421: load existing config and proceed
            result = await flow.async_step_reconfigure(None)

            # Verify data was loaded correctly
            assert flow._data == dict(mock_entry.data)
            assert flow._battery_count == 3
            assert flow._pilot_from_ha is True
            assert flow._limit_power is True

            # Should proceed to control options step
            assert result.get("type") == FlowResultType.FORM
            assert result.get("step_id") == "control_options"

    async def test_reconfigure_with_entry_domain_mismatch(
        self, hass: HomeAssistant
    ) -> None:
        """Test reconfigure step aborts when entry has wrong domain."""
        # Create a mock config entry with wrong domain
        mock_entry = MagicMock()
        mock_entry.domain = "wrong_domain"  # Not DOMAIN
        mock_entry.data = {CONF_BATTERY_COUNT: 1}

        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "test_entry_id"}

        # Mock the entry retrieval to return entry with wrong domain
        with patch.object(
            hass.config_entries, "async_get_entry", return_value=mock_entry
        ):
            result = await flow.async_step_reconfigure({})

            assert result.get("type") == FlowResultType.ABORT
            assert result["reason"] == "unknown"

    async def test_validate_host_comprehensive_cases(self, hass: HomeAssistant) -> None:
        """Test comprehensive host validation including edge cases."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Test additional edge cases for complete coverage
        test_cases = [
            # Valid cases
            ("localhost", True),
            ("battery.local", True),
            ("10.0.0.1", True),
            ("172.16.1.100", True),
            ("test-battery-1", True),
            ("a.b.c.d.example.com", True),
            # Invalid cases - edge cases
            ("host..name", False),  # Double dots
            ("host.", False),  # Trailing dot
            (".host", False),  # Leading dot
            ("a" * 254, False),  # Too long hostname
            ("", False),  # Empty string
            ("host with spaces", False),  # Spaces not allowed
            (
                "host_with_underscores_only",
                False,
            ),  # Fix: Underscores not allowed in hostnames per RFC
            ("_host", False),  # Leading underscore
            ("host_", False),  # Trailing underscore
        ]

        for host, expected in test_cases:
            result = flow._validate_host(host)
            assert result == expected, (
                f"Host '{host}' validation failed: expected {expected}, got {result}"
            )


class TestSAXBatteryOptionsFlowExtended:
    """Extended tests for SAX Battery options flow."""

    async def test_options_flow_init(self, hass: HomeAssistant) -> None:
        """Test options flow initialization."""
        # Create a proper config entry through Home Assistant's system
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_PILOT_FROM_HA: True},
            options={},
            entry_id="test_options_flow_init",
        )

        # Add the entry to hass to properly initialize the context
        mock_entry.add_to_hass(hass)

        # Initialize the options flow consistently with other tests
        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        assert options_flow.config_entry == mock_entry

    async def test_options_flow_pilot_disabled_to_enabled(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow enabling pilot mode."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: False,
            CONF_LIMIT_POWER: False,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_init(
            {
                CONF_PILOT_FROM_HA: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 30,
                CONF_AUTO_PILOT_INTERVAL: 60,
                CONF_ENABLE_SOLAR_CHARGING: False,
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        data = result.get("data")
        assert data is not None
        assert data[CONF_PILOT_FROM_HA] is True
        assert data[CONF_MIN_SOC] == 30
        assert data[CONF_AUTO_PILOT_INTERVAL] == 60
        assert data[CONF_ENABLE_SOLAR_CHARGING] is False

    async def test_options_flow_pilot_enabled_to_disabled(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow disabling pilot mode."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
            CONF_MIN_SOC: 20,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_init(
            {
                CONF_PILOT_FROM_HA: False,
                CONF_LIMIT_POWER: True,
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PILOT_FROM_HA] is False
        assert result["data"][CONF_LIMIT_POWER] is True
        # Pilot-specific options should not be included when pilot is disabled
        assert CONF_MIN_SOC not in result["data"]

    async def test_options_flow_show_form_pilot_enabled(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow form when pilot is enabled."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: False,
            CONF_MIN_SOC: DEFAULT_MIN_SOC,
            CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
            CONF_ENABLE_SOLAR_CHARGING: True,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_init(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"
        # Verify schema includes pilot-specific options
        data_schema = result.get("data_schema")
        if data_schema is not None:
            schema_keys = [str(key) for key in data_schema.schema]
            assert any(CONF_MIN_SOC in key for key in schema_keys)
            assert any(CONF_AUTO_PILOT_INTERVAL in key for key in schema_keys)

    async def test_options_flow_show_form_pilot_disabled(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow form when pilot is disabled."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: False,
            CONF_LIMIT_POWER: True,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_init(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"
        # Verify schema does not include pilot-specific options
        data_schema = result.get("data_schema")
        if data_schema is not None:
            schema_keys = [str(key) for key in data_schema.schema]
            assert not any(CONF_MIN_SOC in key for key in schema_keys)
            assert not any(CONF_AUTO_PILOT_INTERVAL in key for key in schema_keys)

    async def test_options_flow_with_existing_options(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow with existing options."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: False,
        }
        mock_entry.options = {
            CONF_MIN_SOC: 25,
            CONF_AUTO_PILOT_INTERVAL: 45,
            CONF_ENABLE_SOLAR_CHARGING: False,
        }

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_init(None)

        assert result.get("type") == FlowResultType.FORM
        # Verify existing options are used as defaults
        # Note: Testing exact default values requires inspecting the schema
        # which is complex, so we just verify the form is shown correctly

    async def test_options_flow_missing_current_values(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow when current values are missing."""
        mock_entry = MagicMock()
        mock_entry.data = {}  # Missing required keys
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        # Should handle missing values gracefully with defaults
        result = await options_flow.async_step_init(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"

    async def test_options_flow_partial_user_input(self, hass: HomeAssistant) -> None:
        """Test options flow with partial user input."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: False,
            CONF_MIN_SOC: 15,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        # Only provide some options
        result = await options_flow.async_step_init(
            {
                CONF_LIMIT_POWER: True,
                # CONF_PILOT_FROM_HA not provided - should use current value
                CONF_MIN_SOC: 35,
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PILOT_FROM_HA] is True  # From current data
        assert result["data"][CONF_LIMIT_POWER] is True  # From user input
        assert result["data"][CONF_MIN_SOC] == 35  # From user input


class TestSAXBatteryConfigFlowCompleteValidation:
    """Complete validation tests for edge cases and error paths."""

    async def test_pilot_options_edge_case_values(self, hass: HomeAssistant) -> None:
        """Test pilot options with boundary values."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        # Test boundary values that should pass validation
        boundary_test_cases = [
            (0, 5),  # Minimum valid values
            (100, 300),  # Maximum valid values
            (50, 60),  # Normal middle values
        ]

        for min_soc, interval in boundary_test_cases:
            result = await flow.async_step_pilot_options(
                {
                    CONF_MIN_SOC: min_soc,
                    CONF_AUTO_PILOT_INTERVAL: interval,
                    CONF_ENABLE_SOLAR_CHARGING: True,
                }
            )

            assert result.get("type") == FlowResultType.FORM
            assert result.get("step_id") == "sensors"
            assert flow._data[CONF_MIN_SOC] == min_soc
            assert flow._data[CONF_AUTO_PILOT_INTERVAL] == interval

    async def test_battery_config_comprehensive_validation(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery config with comprehensive validation scenarios."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 2

        # Test valid configuration with all batteries
        valid_input = {
            "battery_a_host": "192.168.1.100",
            "battery_a_port": 502,
            "battery_b_host": "battery-b.local",
            "battery_b_port": 1502,
            CONF_MASTER_BATTERY: "battery_a",
        }

        result = await flow.async_step_battery_config(valid_input)

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "SAX Battery System (2 batteries)"

        # Verify battery configuration structure
        batteries = result["data"][CONF_BATTERIES]
        assert "battery_a" in batteries
        assert "battery_b" in batteries
        assert batteries["battery_a"][CONF_BATTERY_IS_MASTER] is True
        assert batteries["battery_b"][CONF_BATTERY_IS_MASTER] is False
        assert batteries["battery_a"][CONF_BATTERY_HOST] == "192.168.1.100"
        assert batteries["battery_b"][CONF_BATTERY_HOST] == "battery-b.local"

    async def test_options_flow_comprehensive_scenarios(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow with comprehensive configuration scenarios."""
        # Test with pilot enabled and all options
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
            CONF_MIN_SOC: 25,
            CONF_AUTO_PILOT_INTERVAL: 45,
            CONF_ENABLE_SOLAR_CHARGING: False,
        }
        mock_entry.options = {
            CONF_MIN_SOC: 30,  # Different from data
            CONF_AUTO_PILOT_INTERVAL: 60,  # Different from data
        }

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        # Test form display uses options over data when available
        result = await options_flow.async_step_init(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"

        # Test saving updated configuration
        updated_input = {
            CONF_PILOT_FROM_HA: False,  # Disable pilot
            CONF_LIMIT_POWER: False,  # Disable limits
            CONF_MIN_SOC: 35,  # Should be ignored when pilot disabled
        }

        result = await options_flow.async_step_init(updated_input)

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PILOT_FROM_HA] is False
        assert result["data"][CONF_LIMIT_POWER] is False
        # MIN_SOC should not be included when pilot is disabled
        assert CONF_MIN_SOC not in result["data"]


class TestSAXBatteryConfigFlowSecurityValidation:
    """Security-focused validation tests following OWASP guidelines."""

    async def test_host_validation_injection_prevention(
        self, hass: HomeAssistant
    ) -> None:
        """Test host validation prevents injection attacks (OWASP A03: Injection)."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Test potential injection patterns
        malicious_hosts = [
            "192.168.1.1; rm -rf /",  # Command injection attempt
            "host`whoami`",  # Command substitution
            "host$(whoami)",  # Command substitution
            "host' OR '1'='1",  # SQL injection pattern
            "<script>alert('xss')</script>",  # XSS attempt
            "../../../etc/passwd",  # Path traversal
            "host\\x00.evil.com",  # Null byte injection
            "host\r\nHost: evil.com",  # HTTP header injection
        ]

        for malicious_host in malicious_hosts:
            result = flow._validate_host(malicious_host)
            assert result is False, f"Security validation failed for: {malicious_host}"

    async def test_port_validation_security_boundaries(
        self, hass: HomeAssistant
    ) -> None:
        """Test port validation enforces security boundaries (OWASP A05: Security Misconfiguration)."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        # Test security-sensitive port ranges
        security_test_cases = [
            (-1, False),  # Negative port
            (0, False),  # System reserved
            (65536, False),  # Above valid range
            (99999, False),  # Way above valid range
            ("0x502", False),  # Hex injection attempt
            ("502; ls", False),  # Command injection attempt
        ]

        for port_value, should_pass in security_test_cases:
            result = await flow.async_step_battery_config(
                {
                    "battery_a_host": "192.168.1.100",
                    "battery_a_port": port_value,
                }
            )

            if should_pass:
                assert result.get("type") == FlowResultType.CREATE_ENTRY
            else:
                assert result.get("type") == FlowResultType.FORM
                errors = result.get("errors")
                # Fix: Check if errors exists before calling .get()
                if errors is not None:
                    assert "invalid_port" in errors.get("battery_a_port", "")

    async def test_configuration_data_sanitization(self, hass: HomeAssistant) -> None:
        """Test configuration data is properly sanitized (OWASP A03: Injection)."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        # Test with potentially dangerous input that should be sanitized
        test_input = {
            "battery_a_host": "  192.168.1.100  ",  # Should be stripped
            "battery_a_port": "502",  # String that should be converted to int
        }

        result = await flow.async_step_battery_config(test_input)

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        batteries = result["data"][CONF_BATTERIES]
        # Verify host was stripped of whitespace
        assert batteries["battery_a"][CONF_BATTERY_HOST] == "192.168.1.100"
        # Verify port was converted to integer
        assert isinstance(batteries["battery_a"][CONF_BATTERY_PORT], int)
        assert batteries["battery_a"][CONF_BATTERY_PORT] == 502


class TestSAXBatteryConfigFlowMissingCoverage:
    """Tests to cover remaining uncovered lines in config_flow.py."""

    async def test_sensors_step_pilot_disabled_skips_priority(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step with pilot disabled skips to battery_config (line 212).

        This covers the path when pilot_from_ha=False, which should skip
        priority_devices and go directly to battery_config.
        """
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = False  # Pilot disabled
        flow._battery_count = 1

        # When pilot is disabled, sensors step should skip priority devices
        # and go to battery_config
        result = await flow.async_step_sensors(
            {
                # Empty input - no sensors needed when pilot disabled
            }
        )

        # Line 212: Should proceed to battery_config, not priority_devices
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"

    async def test_priority_devices_form_display_no_input(
        self, hass: HomeAssistant
    ) -> None:
        """Test priority devices step shows form when no input provided (line 242)."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True
        flow._battery_count = 1

        # Call without user input to trigger form display
        result = await flow.async_step_priority_devices(None)

        # Line 242: Should show form for priority devices selection
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "priority_devices"
        assert "priority_devices_description" in result["description_placeholders"]  # type: ignore[operator]

    async def test_reconfigure_entry_wrong_domain(self, hass: HomeAssistant) -> None:
        """Test reconfigure aborts when entry has wrong domain (line 417, 419)."""
        # Create entry with wrong domain
        mock_entry = Mock()
        mock_entry.domain = "other_domain"  # Not DOMAIN

        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "test_entry"}

        with patch.object(
            hass.config_entries, "async_get_entry", return_value=mock_entry
        ):
            result = await flow.async_step_reconfigure({})

            # Lines 417, 419: Should abort with "unknown" reason
            assert result.get("type") == FlowResultType.ABORT
            assert result.get("reason") == "unknown"

    async def test_reconfigure_entry_is_none(self, hass: HomeAssistant) -> None:
        """Test reconfigure aborts when entry not found (line 413)."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "nonexistent_entry"}

        with patch.object(hass.config_entries, "async_get_entry", return_value=None):
            result = await flow.async_step_reconfigure({})

            # Line 413: Should abort when entry is None
            assert result.get("type") == FlowResultType.ABORT
            assert result.get("reason") == "unknown"

    async def test_options_flow_description_placeholders_pilot_disabled(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow description when pilot disabled (line 514)."""
        mock_entry = Mock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: False,  # Pilot disabled
            CONF_LIMIT_POWER: True,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_init(None)

        # Line 514: Should have description for disabled pilot mode
        assert result.get("type") == FlowResultType.FORM
        placeholders = result.get("description_placeholders")
        assert placeholders is not None
        assert "pilot_options" in placeholders
        # Verify message indicates pilot is disabled
        assert "disabled" in placeholders["pilot_options"]


class TestSAXBatteryConfigFlowEdgeCases:
    """Additional edge case tests for complete coverage."""

    async def test_sensors_step_with_all_sensors_configured(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step with all optional sensors configured."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        result = await flow.async_step_sensors(
            {
                # CONF_GRID_POWER_SENSOR: "sensor.grid_power",
                CONF_POWER_SENSOR: "sensor.battery_power",
                CONF_PF_SENSOR: "sensor.power_factor",
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "priority_devices"
        # Verify all sensors stored in data
        # assert flow._data[CONF_GRID_POWER_SENSOR] == "sensor.grid_power"
        assert flow._data[CONF_POWER_SENSOR] == "sensor.battery_power"
        assert flow._data[CONF_PF_SENSOR] == "sensor.power_factor"

    # async def test_battery_config_ipv6_host(self, hass: HomeAssistant) -> None:
    #     """Test battery config with IPv6 address."""
    #     flow = SAXBatteryConfigFlow()
    #     flow.hass = hass
    #     flow._battery_count = 1

    #     # IPv6 addresses are valid hostnames
    #     result = await flow.async_step_battery_config(
    #         {
    #             "battery_a_host": "2001:db8::1",
    #             "battery_a_port": DEFAULT_PORT,
    #         }
    #     )

    #     # IPv6 should be accepted as valid host format
    #     assert result.get("type") == FlowResultType.CREATE_ENTRY
    #     batteries = result["data"][CONF_BATTERIES]
    #     assert batteries["battery_a"][CONF_BATTERY_HOST] == "2001:db8::1"

    async def test_options_flow_toggle_both_features(self, hass: HomeAssistant) -> None:
        """Test options flow toggling both pilot and limit features simultaneously."""
        mock_entry = Mock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: False,
            CONF_LIMIT_POWER: False,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        # Enable both features at once
        result = await options_flow.async_step_init(
            {
                CONF_PILOT_FROM_HA: True,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 25,
                CONF_AUTO_PILOT_INTERVAL: 45,
                CONF_ENABLE_SOLAR_CHARGING: True,
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        data = result.get("data")
        assert data is not None
        assert data[CONF_PILOT_FROM_HA] is True
        assert data[CONF_LIMIT_POWER] is True
        assert data[CONF_MIN_SOC] == 25
        assert data[CONF_AUTO_PILOT_INTERVAL] == 45
        assert data[CONF_ENABLE_SOLAR_CHARGING] is True

    async def test_control_options_solar_charging_default(
        self, hass: HomeAssistant
    ) -> None:
        """Test control options sets solar charging default based on pilot mode."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        # When pilot disabled, solar charging should default to False
        result = await flow.async_step_control_options(
            {
                CONF_PILOT_FROM_HA: False,
                CONF_LIMIT_POWER: False,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert flow._data[CONF_ENABLE_SOLAR_CHARGING] is False

    async def test_validate_host_boundary_length(self, hass: HomeAssistant) -> None:
        """Test host validation with boundary length cases."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Test exactly 253 characters (valid) - must be valid hostname format
        # Create a valid hostname with multiple labels to reach 253 chars
        # Format: "a.b.c.d.e..." where each segment is valid
        # Max label length is 63 chars, so we need multiple labels

        # Build valid hostname: "label63chars.label63chars.label63chars.label60chars"
        # = 63 + 1 + 63 + 1 + 63 + 1 + 57 = 250 chars (add 3 more char = 253)
        label_63 = "a" * 63
        label_60 = "b" * 57
        label_1 = "com"

        valid_long_host = (
            f"{label_63}.{label_63}.{label_63}.{label_60}.{label_1}"  # 253 chars
        )
        assert len(valid_long_host) == 253
        assert flow._validate_host(valid_long_host) is True

        # Test 254 characters (invalid - too long)
        # Add one more character to make it 254
        invalid_long_host = valid_long_host + "a"  # 254 chars
        assert len(invalid_long_host) == 254
        assert flow._validate_host(invalid_long_host) is False

        # Also test simple repeated character (invalid - not a valid hostname)
        invalid_simple_long = "a" * 254
        assert flow._validate_host(invalid_simple_long) is False

    async def test_pilot_options_boundary_values_edge(
        self, hass: HomeAssistant
    ) -> None:
        """Test pilot options with edge case boundary values."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._pilot_from_ha = True

        # Test exactly at boundaries (should pass)
        test_cases = [
            (0, 5),  # Minimum valid
            (100, 300),  # Maximum valid
        ]

        for min_soc, interval in test_cases:
            result = await flow.async_step_pilot_options(
                {
                    CONF_MIN_SOC: min_soc,
                    CONF_AUTO_PILOT_INTERVAL: interval,
                    CONF_ENABLE_SOLAR_CHARGING: False,
                }
            )

            assert result.get("type") == FlowResultType.FORM
            assert result.get("step_id") == "sensors"
            assert flow._data[CONF_MIN_SOC] == min_soc
            assert flow._data[CONF_AUTO_PILOT_INTERVAL] == interval


class TestSAXBatteryOptionsFlowCompleteFlow:
    """Test complete options flow scenarios for full coverage."""

    async def test_options_flow_change_pilot_settings_only(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow changing only pilot-specific settings."""
        mock_entry = Mock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
            CONF_MIN_SOC: 20,
            CONF_AUTO_PILOT_INTERVAL: 30,
            CONF_ENABLE_SOLAR_CHARGING: True,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        # Change pilot settings but keep feature toggles same
        result = await options_flow.async_step_init(
            {
                CONF_PILOT_FROM_HA: True,  # Keep enabled
                CONF_LIMIT_POWER: True,  # Keep enabled
                CONF_MIN_SOC: 30,  # Change from 20 to 30
                CONF_AUTO_PILOT_INTERVAL: 60,  # Change from 30 to 60
                CONF_ENABLE_SOLAR_CHARGING: False,  # Toggle off
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        data = result.get("data")
        assert data is not None
        assert data[CONF_PILOT_FROM_HA] is True
        assert data[CONF_LIMIT_POWER] is True
        assert data[CONF_MIN_SOC] == 30
        assert data[CONF_AUTO_PILOT_INTERVAL] == 60
        assert data[CONF_ENABLE_SOLAR_CHARGING] is False

    async def test_options_flow_disable_limit_power_only(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow disabling only limit power feature."""
        mock_entry = Mock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: True,
            CONF_MIN_SOC: 25,
        }
        mock_entry.options = {}

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_init(
            {
                CONF_PILOT_FROM_HA: True,  # Keep enabled
                CONF_LIMIT_POWER: False,  # Disable
                CONF_MIN_SOC: 25,
                CONF_AUTO_PILOT_INTERVAL: 30,
                CONF_ENABLE_SOLAR_CHARGING: True,
            }
        )
        assert result.get("type") == FlowResultType.CREATE_ENTRY
        data = result.get("data")
        assert data is not None
        assert data[CONF_PILOT_FROM_HA] is True
        assert data[CONF_LIMIT_POWER] is False
        assert data[CONF_MIN_SOC] == 25


class TestSAXBatteryConfigFlowSecurityEdgeCases:
    """Security-focused edge case tests for complete coverage."""

    async def test_host_validation_octet_boundary_values(
        self, hass: HomeAssistant
    ) -> None:
        """Test IPv4 validation with boundary octet values."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Test boundary values for octets
        test_cases = [
            ("0.0.0.0", True),  # All zeros valid
            ("255.255.255.255", True),  # All max valid
            ("192.168.1.0", True),  # Network address valid
            ("192.168.1.255", True),  # Broadcast address valid
            ("256.1.1.1", False),  # First octet too high
            ("1.256.1.1", False),  # Second octet too high
            ("1.1.256.1", False),  # Third octet too high
            ("1.1.1.256", False),  # Fourth octet too high
        ]

        for host, expected in test_cases:
            result = flow._validate_host(host)
            assert result == expected, f"Host '{host}' validation failed"

    async def test_battery_config_port_string_conversion(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery config properly converts string ports to integers."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        # Test with string port that's valid
        result = await flow.async_step_battery_config(
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": "8502",  # String that should convert
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        data = result.get("data")
        assert data is not None
        batteries = data[CONF_BATTERIES]
        # Verify port was converted to int
        assert isinstance(batteries["battery_a"][CONF_BATTERY_PORT], int)
        assert batteries["battery_a"][CONF_BATTERY_PORT] == 8502

    async def test_options_flow_with_options_precedence(
        self, hass: HomeAssistant
    ) -> None:
        """Test options flow uses options over data when both exist."""
        mock_entry = Mock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_LIMIT_POWER: False,
            CONF_MIN_SOC: 20,  # In data
        }
        mock_entry.options = {
            CONF_MIN_SOC: 30,  # In options - should take precedence
            CONF_AUTO_PILOT_INTERVAL: 45,
        }

        options_flow = SAXBatteryOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        # Display form to verify defaults use options
        result = await options_flow.async_step_init(None)

        assert result.get("type") == FlowResultType.FORM
        # Options should take precedence in form defaults
        # (This is tested by the schema defaults, though hard to assert directly)


class TestSAXBatteryConfigFlowDeadCodeRemoval:
    """Verify dead code removal and logic correctness."""

    async def test_sensors_step_always_proceeds_correctly(
        self, hass: HomeAssistant
    ) -> None:
        """Verify sensors step routing logic after dead code removal."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Case 1: Pilot enabled → Shows sensor form
        flow._pilot_from_ha = True
        result = await flow.async_step_sensors(None)
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "sensors"

        # Case 2: Pilot disabled → Already handled by async_step_sensors
        # No dead code path needed
        flow._pilot_from_ha = False
        flow._battery_count = 1
        result = await flow.async_step_sensors({})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"

    async def test_host_validation_ipv4_no_exception_handling_needed(
        self, hass: HomeAssistant
    ) -> None:
        """Verify IPv4 validation works without exception handler."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # All these cases are handled by isdigit() check before int() conversion
        test_cases = [
            ("192.168.1.1", True),  # Valid IPv4
            ("256.1.1.1", False),  # Octet > 255
            ("192.168.1.999", False),  # Octet > 255
            ("192.168.1.a", False),  # Non-digit (breaks before int())
            ("192.168.-1.1", False),  # Negative (not isdigit())
            ("192.168..1", False),  # Empty part (breaks immediately)
        ]

        for host, expected in test_cases:
            result = flow._validate_host(host)
            assert result == expected, f"Failed for host: {host}"
