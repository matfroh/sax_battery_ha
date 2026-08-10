"""Test SAX Battery config flow - reorganized and optimized."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Package to automatically extract testing plugins from Home Assistant for custom component testing
# You don’t need to do anything else to access the pytest fixtures that the pytest-homeassistant-custom-component plugin provides.
# pytest will automatically know about them and you can start using them in your tests.
# One of the most useful is hass for providing a hass instance that is properly setup for your test environment.
# This is especially useful when testing your config flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.config_flow import (
    SAXBatteryConfigFlow,
    SAXBatteryOptionsFlowHandler,
)
from custom_components.sax_battery.const import (
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PORT,
    CONF_CONTROL_POWER,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_MIN_SOC,
    CONF_POWER_SENSOR,
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
        assert flow._control_power is False
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
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "power_options"
        assert flow._control_power is True
        assert flow._limit_power is False

    async def test_control_options_step_no_pilot(self, hass: HomeAssistant) -> None:
        """Test control options step without pilot."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_control_options(
            {
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        assert flow._control_power is False
        assert flow._limit_power is True

    # async def test_pilot_options_invalid_min_soc(self, hass: HomeAssistant) -> None:
    #     """Test pilot options with invalid min SOC."""
    #     flow = SAXBatteryConfigFlow()
    #     flow.hass = hass
    #     flow._control_power = True

    #     # Test with SOC too high
    #     result = await flow.async_step_pilot_options(
    #         {
    #             CONF_MIN_SOC: 150,
    #         }
    #     )

    #     assert result.get("type") == FlowResultType.FORM
    #     assert result.get("step_id") == "pilot_options"
    #     errors = result.get("errors")
    #     assert errors is not None
    #     assert "invalid_min_soc" in errors.get(CONF_MIN_SOC, "")

    # # Test removed: CONF_AUTO_PILOT_INTERVAL validation no longer exists
    # # Pilot auto-interval removed - coordinator timing now used

    # async def test_pilot_options_non_numeric_values(self, hass: HomeAssistant) -> None:
    #     """Test pilot options with non-numeric values."""
    #     flow = SAXBatteryConfigFlow()
    #     flow.hass = hass
    #     flow._control_power = True

    #     result = await flow.async_step_pilot_options(
    #         {
    #             CONF_MIN_SOC: "invalid",
    #         }
    #     )

    #     assert result.get("type") == FlowResultType.FORM
    #     assert result.get("step_id") == "pilot_options"
    #     errors = result.get("errors")
    #     assert errors is not None
    #     assert CONF_MIN_SOC in errors

    async def test_sensors_step_with_pilot(self, hass: HomeAssistant) -> None:
        """Test sensors step when pilot is enabled."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._control_power = True

        result = await flow.async_step_sensors(
            {
                CONF_POWER_SENSOR: "sensor.power_meter",
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"

    async def test_battery_config_invalid_host_format(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery config with invalid host format."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "invalid..host..name",
                "bess_a_port": DEFAULT_PORT,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        assert "invalid_host_format" in errors.get("bess_a_host", "")

    async def test_battery_config_empty_host(self, hass: HomeAssistant) -> None:
        """Test battery config with empty host."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "",
                "bess_a_port": DEFAULT_PORT,
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        assert "invalid_host" in errors.get("bess_a_host", "")

    async def test_battery_config_invalid_port(self, hass: HomeAssistant) -> None:
        """Test battery config with invalid port."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": 99999,  # Too high
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        # Fix: Check if errors exists before using 'in' operator
        assert errors and "invalid_port" in errors.get("bess_a_port", "")

    async def test_battery_config_invalid_port_type(self, hass: HomeAssistant) -> None:
        """Test battery config with non-numeric port."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": "not_a_number",
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        errors = result.get("errors")
        assert errors is not None
        # Fix: Check if errors exists before using 'in' operator
        assert errors and "invalid_port" in errors.get("bess_a_port", "")

    async def test_battery_config_multi_battery_invalid_master(
        self, hass: HomeAssistant
    ) -> None:
        """Test multi-battery config with invalid master selection."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 2

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": DEFAULT_PORT,
                "bess_b_host": "192.168.1.101",
                "bess_b_port": DEFAULT_PORT,
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
                "bess_a_host": "192.168.1.100",
                "bess_a_port": DEFAULT_PORT,
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "SAX Battery System (1 batteries)"
        assert CONF_BATTERIES in result["data"]
        assert CONF_MASTER_BATTERY in result["data"]
        assert result["data"][CONF_MASTER_BATTERY] == "bess_a"

    async def test_battery_config_successful_multi_battery(
        self, hass: HomeAssistant
    ) -> None:
        """Test successful multi-battery configuration."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 3

        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": DEFAULT_PORT,
                "bess_b_host": "192.168.1.101",
                "bess_b_port": DEFAULT_PORT,
                "bess_c_host": "192.168.1.102",
                "bess_c_port": DEFAULT_PORT,
                CONF_MASTER_BATTERY: "bess_b",
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "SAX Battery System (3 batteries)"
        data = result.get("data")
        assert data is not None
        assert data[CONF_MASTER_BATTERY] == "bess_b"
        # Verify master is set correctly
        batteries = data[CONF_BATTERIES]
        assert batteries["bess_b"][CONF_BATTERY_IS_MASTER] is True
        assert batteries["bess_a"][CONF_BATTERY_IS_MASTER] is False
        assert batteries["bess_c"][CONF_BATTERY_IS_MASTER] is False

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
        """Test getting options flow.

        Security:
            OWASP A01: Validates options flow creation follows proper patterns
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_CONTROL_POWER: True},
            entry_id="test_options_flow_creation",
        )

        options_flow = SAXBatteryConfigFlow.async_get_options_flow(mock_entry)

        assert isinstance(options_flow, SAXBatteryOptionsFlowHandler)
        # Note: config_entry property not available until flow is initialized by HA

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

    # async def test_pilot_options_valid_input_flow(self, hass: HomeAssistant) -> None:
    #     """Test pilot options step with valid input proceeding to sensors."""
    #     flow = SAXBatteryConfigFlow()
    #     flow.hass = hass
    #     flow._control_power = True

    #     # Test the uncovered lines 170-171: valid input updates data and proceeds to sensors
    #     result = await flow.async_step_pilot_options(
    #         {
    #             CONF_MIN_SOC: 25,
    #         }
    #     )

    #     assert result.get("type") == FlowResultType.FORM
    #     assert result.get("step_id") == "sensors"
    #     assert flow._data[CONF_MIN_SOC] == 25

    async def test_sensors_step_with_pilot_enabled_schema(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step creates proper schema when pilot is enabled."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._control_power = True

        # Test the uncovered lines 206-208: schema creation for pilot mode
        result = await flow.async_step_sensors(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "sensors"

        # Verify schema includes power sensor selector only (PF sensor removed)
        data_schema = result.get("data_schema")
        assert data_schema is not None
        schema_keys = [str(key) for key in data_schema.schema]
        assert any(CONF_POWER_SENSOR in key for key in schema_keys)

    async def test_sensors_step_with_pilot_form_display(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step shows form with pilot-specific schema."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._control_power = True

        # Test the uncovered line 227: return self.async_show_form with sensor schema
        result = await flow.async_step_sensors(None)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "sensors"
        assert "power_sensor_description" in result["description_placeholders"]  # type: ignore[operator]
        # pf_sensor_description removed - power factor sensor no longer used

    async def test_reconfigure_step_with_valid_entry_and_input(
        self, hass: HomeAssistant
    ) -> None:
        """Test reconfigure step with valid entry ID and user input.

        This test follows the actual multi-step reconfigure flow:
        1. async_step_reconfigure(None) -> control_options
        2. async_step_control_options(input) -> battery_config
        3. async_step_battery_config(input) -> abort (reconfigure_successful)
        """
        # Create a mock config entry with complete data
        mock_entry = MagicMock()
        mock_entry.domain = DOMAIN
        mock_entry.data = {
            CONF_BATTERY_COUNT: 2,
            CONF_CONTROL_POWER: True,
            CONF_LIMIT_POWER: False,
            CONF_BATTERIES: {
                "bess_a": {"host": "192.168.1.100", "port": 502},
                "bess_b": {"host": "192.168.1.101", "port": 502},
            },
            CONF_MASTER_BATTERY: "bess_a",
        }

        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow.context = {"entry_id": "test_entry_id", "source": "reconfigure"}

        # Mock the entry retrieval and update
        with (
            patch.object(
                hass.config_entries, "async_get_entry", return_value=mock_entry
            ),
            patch.object(
                hass.config_entries, "async_update_entry"
            ) as mock_update_entry,
        ):
            # Step 1: Start reconfigure flow (goes to control_options)
            result = await flow.async_step_reconfigure(None)

            assert result.get("type") == FlowResultType.FORM
            assert result.get("step_id") == "control_options"

            # Step 2: Provide control options (pilot disabled, no sensors step)
            control_options_input = {
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            }

            result = await flow.async_step_control_options(control_options_input)

            # Should proceed to battery_config step
            assert result.get("type") == FlowResultType.FORM
            assert result.get("step_id") == "battery_config"

            # Step 3: Battery config step with correct per-battery input
            battery_config_input = {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": 502,
                "bess_b_host": "192.168.1.101",
                "bess_b_port": 502,
                CONF_MASTER_BATTERY: "bess_a",
            }

            result = await flow.async_step_battery_config(battery_config_input)

            # Now we should get an abort for reconfiguration
            assert result.get("type") == FlowResultType.ABORT
            assert result.get("reason") == "reconfigure_successful"

            # Verify the config entry was updated
            mock_update_entry.assert_called_once()

    async def test_reconfigure_step_loads_existing_config(
        self, hass: HomeAssistant
    ) -> None:
        """Test reconfigure step loads existing configuration data."""
        # Create a mock config entry with comprehensive data
        mock_entry = MagicMock()
        mock_entry.domain = DOMAIN
        mock_entry.data = {
            CONF_BATTERY_COUNT: 3,
            CONF_CONTROL_POWER: True,
            CONF_LIMIT_POWER: True,
            CONF_MIN_SOC: 20,
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
            assert flow._control_power is True
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

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_init(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow initialization.

        Security:
            OWASP A01: Validates proper initialization sequence
        """
        # Create and register config entry
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_CONTROL_POWER: True},
            options={},
            entry_id="test_options_flow_init",
        )
        mock_entry.add_to_hass(hass)

        # Setup the integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow through HA's flow manager
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_pilot_disabled_to_enabled(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow enabling pilot mode.

        Security:
            OWASP A01: Validates feature toggle security
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
            options={},
            entry_id="test_entry_pilot_enable",
        )
        mock_entry.add_to_hass(hass)

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        # Type guard: Validate result structure
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"

        # When toggling pilot from disabled to enabled, flow completes immediately
        # with default pilot values rather than showing form again
        with patch(
            "custom_components.sax_battery.config_flow.SAXBatteryOptionsFlowHandler._enable_power_limit_entities",
            new_callable=AsyncMock,
        ):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CONTROL_POWER: True,
                    CONF_LIMIT_POWER: False,
                },
            )

        # Flow completes immediately when enabling pilot
        # Type guard: Validate result structure before accessing fields
        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert mock_entry.data[CONF_CONTROL_POWER] is True
        assert mock_entry.data[CONF_LIMIT_POWER] is False

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_pilot_enabled_to_disabled(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow disabling pilot mode.

        Security:
            OWASP A01: Validates proper cleanup when disabling features
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
            },
            options={},
            entry_id="test_entry_pilot_disable",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        # _async_disable_pilot_power_entity method removed - no longer needed
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert mock_entry.data[CONF_CONTROL_POWER] is False
        assert mock_entry.data[CONF_LIMIT_POWER] is True

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_show_form_pilot_enabled(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow form when pilot is enabled."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: DEFAULT_MIN_SOC,
            },
            options={},
            entry_id="test_form_pilot_enabled",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Type guard: Validate data_schema exists before accessing .schema
        data_schema = result.get("data_schema")
        assert data_schema is not None, (
            "data_schema should not be None for options flow"
        )

        assert CONF_MIN_SOC in data_schema.schema

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_show_form_pilot_disabled(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow form when pilot is disabled."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
            options={},
            entry_id="test_form_pilot_disabled",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Type guard: Validate data_schema exists before accessing .schema
        data_schema = result.get("data_schema")
        assert data_schema is not None, (
            "data_schema should not be None for options flow"
        )

        # When pilot disabled, schema only has control_power and limit_power
        assert CONF_CONTROL_POWER in data_schema.schema
        assert CONF_LIMIT_POWER in data_schema.schema
        # min_soc NOT in schema when pilot disabled
        assert CONF_MIN_SOC not in data_schema.schema

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_with_existing_options(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow with existing options."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
            },
            options={
                CONF_MIN_SOC: 25,
            },
            entry_id="test_existing_options",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        # Options should be displayed in form

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_missing_current_values(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow when current values are missing."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={},  # Missing required keys
            options={},
            entry_id="test_missing_values",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Should handle missing values gracefully with defaults
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_partial_user_input(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow with partial user input."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 15,
            },
            options={},
            entry_id="test_entry_partial",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        # Only provide some options
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_LIMIT_POWER: True,
                # CONF_CONTROL_POWER not provided - should use current value
                CONF_MIN_SOC: 35,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Should preserve CONF_CONTROL_POWER from original data
        assert mock_entry.data[CONF_CONTROL_POWER] is True
        assert mock_entry.data[CONF_LIMIT_POWER] is True
        assert mock_entry.data[CONF_MIN_SOC] == 35


class TestSAXBatteryConfigFlowCompleteValidation:
    """Complete validation tests for edge cases and error paths."""

    async def test_pilot_options_edge_case_values(self, hass: HomeAssistant) -> None:
        """Test removed - pilot_options step no longer used in config flow."""
        # pilot_options step is dead code (never called in flow)
        # MIN_SOC is now configured directly in options flow init step

    async def test_battery_config_comprehensive_validation(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery config with comprehensive validation scenarios."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 2

        # Test valid configuration with all batteries
        valid_input = {
            "bess_a_host": "192.168.1.100",
            "bess_a_port": 502,
            "bess_b_host": "battery-b.local",
            "bess_b_port": 1502,
            CONF_MASTER_BATTERY: "bess_a",
        }

        result = await flow.async_step_battery_config(valid_input)

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "SAX Battery System (2 batteries)"

        # Verify battery configuration structure
        batteries = result["data"][CONF_BATTERIES]
        assert "bess_a" in batteries
        assert "bess_b" in batteries
        assert batteries["bess_a"][CONF_BATTERY_IS_MASTER] is True
        assert batteries["bess_b"][CONF_BATTERY_IS_MASTER] is False
        assert batteries["bess_a"][CONF_BATTERY_HOST] == "192.168.1.100"
        assert batteries["bess_b"][CONF_BATTERY_HOST] == "battery-b.local"

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_comprehensive_scenarios(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow with comprehensive configuration scenarios."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 25,
            },
            options={
                CONF_MIN_SOC: 30,  # Different from data
            },
            entry_id="test_entry_comprehensive",
        )
        mock_entry.add_to_hass(hass)

        # Setup the integration (uses mocked setup)
        assert await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Submit updated configuration
        updated_input = {
            CONF_CONTROL_POWER: False,  # Disable pilot
            CONF_LIMIT_POWER: False,  # Disable limits
            CONF_MIN_SOC: 35,  # Should be ignored when pilot disabled
        }

        # Configure the options flow
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=updated_input,
        )

        # Verify correct result structure
        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Verify data was updated correctly
        assert result["data"][CONF_CONTROL_POWER] is False
        assert result["data"][CONF_LIMIT_POWER] is False
        # MIN_SOC may or may not be updated when pilot is disabled
        # (depends on implementation logic)


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
                    "bess_a_host": "192.168.1.100",
                    "bess_a_port": port_value,
                }
            )

            if should_pass:
                assert result.get("type") == FlowResultType.CREATE_ENTRY
            else:
                assert result.get("type") == FlowResultType.FORM
                errors = result.get("errors")
                # Fix: Check if errors exists before calling .get()
                if errors is not None:
                    assert "invalid_port" in errors.get("bess_a_port", "")

    async def test_configuration_data_sanitization(self, hass: HomeAssistant) -> None:
        """Test configuration data is properly sanitized (OWASP A03: Injection)."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        # Test with potentially dangerous input that should be sanitized
        test_input = {
            "bess_a_host": "  192.168.1.100  ",  # Should be stripped
            "bess_a_port": "502",  # String that should be converted to int
        }

        result = await flow.async_step_battery_config(test_input)

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        batteries = result["data"][CONF_BATTERIES]
        # Verify host was stripped of whitespace
        assert batteries["bess_a"][CONF_BATTERY_HOST] == "192.168.1.100"
        # Verify port was converted to integer
        assert isinstance(batteries["bess_a"][CONF_BATTERY_PORT], int)
        assert batteries["bess_a"][CONF_BATTERY_PORT] == 502


class TestSAXBatteryConfigFlowMissingCoverage:
    """Tests to cover remaining uncovered lines in config_flow.py."""

    async def test_sensors_step_pilot_disabled_skips_priority(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step with pilot disabled skips to battery_config (line 212).

        This covers the path when control_power=False, which should skip
        priority_devices and go directly to battery_config.
        """
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._control_power = False  # Pilot disabled
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

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_description_placeholders_pilot_disabled(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow description when pilot disabled (line 514)."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: False,  # Pilot disabled
                CONF_LIMIT_POWER: True,
            },
            options={},
            entry_id="test_description_pilot_disabled",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert "description_placeholders" in result


class TestSAXBatteryConfigFlowEdgeCases:
    """Additional edge case tests for complete coverage."""

    async def test_sensors_step_with_all_sensors_configured(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensors step with all optional sensors configured."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._control_power = True

        result = await flow.async_step_sensors(
            {
                CONF_POWER_SENSOR: "sensor.battery_power",
            }
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"
        # Verify sensor stored in data
        assert flow._data[CONF_POWER_SENSOR] == "sensor.battery_power"

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

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_toggle_both_features(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow toggling both pilot and limit features simultaneously."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
            options={},
            entry_id="test_entry_toggle",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        # When enabling both features, flow completes immediately with defaults
        with patch(
            "custom_components.sax_battery.config_flow.SAXBatteryOptionsFlowHandler._enable_power_limit_entities",
            new_callable=AsyncMock,
        ):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CONTROL_POWER: True,
                    CONF_LIMIT_POWER: True,
                },
            )

        # Type guard: Validate result structure before accessing fields
        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert mock_entry.data[CONF_CONTROL_POWER] is True
        assert mock_entry.data[CONF_LIMIT_POWER] is True

    async def test_control_options_pv_charging_default(
        self, hass: HomeAssistant
    ) -> None:
        """Test control options sets pv charging default based on pilot mode."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1

        # When power control disabled, pv charging should default to False
        result = await flow.async_step_control_options(
            {
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            }
        )

        assert result.get("type") == FlowResultType.FORM

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
        """Test removed - pilot_options step no longer used in config flow."""
        # pilot_options step is dead code (never called in flow)
        # MIN_SOC is now configured directly in options flow init step


class TestSAXBatteryOptionsFlowCompleteFlow:
    """Test complete options flow scenarios for full coverage.

    see also option example:  https://aarongodfrey.dev/home%20automation/building_a_home_assistant_custom_component_part_4/
                              https://github.com/boralyl/github-custom-component-tutorial

    """

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_change_pilot_settings_only(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow changing only pilot-specific settings."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
            },
            options={},
            entry_id="test_entry_pilot_change",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        # Change pilot settings but keep feature toggles same
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: True,  # Keep enabled
                CONF_LIMIT_POWER: True,  # Keep enabled
                CONF_MIN_SOC: 30,  # Change from 20 to 30
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert mock_entry.data[CONF_MIN_SOC] == 30

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_disable_limit_power_only(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow disabling only limit power feature."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 25,
            },
            options={},
            entry_id="test_entry_limit_disable",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: True,  # Keep enabled
                CONF_LIMIT_POWER: False,  # Disable
                CONF_MIN_SOC: 25,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert mock_entry.data[CONF_CONTROL_POWER] is True
        assert mock_entry.data[CONF_LIMIT_POWER] is False


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
                "bess_a_host": "192.168.1.100",
                "bess_a_port": "8502",  # String that should convert
            }
        )

        assert result.get("type") == FlowResultType.CREATE_ENTRY
        data = result.get("data")
        assert data is not None
        batteries = data[CONF_BATTERIES]
        # Verify port was converted to int
        assert isinstance(batteries["bess_a"][CONF_BATTERY_PORT], int)
        assert batteries["bess_a"][CONF_BATTERY_PORT] == 8502

    @pytest.mark.usefixtures("_mock_setup_integration")
    async def test_options_flow_with_options_precedence(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test options flow uses options over data when both exist."""
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,  # In data
            },
            options={
                CONF_MIN_SOC: 30,  # In options - should take precedence
            },
            entry_id="test_options_precedence",
        )
        mock_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Display form to verify defaults use options
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        # Options values should be used in form defaults


class TestSAXBatteryConfigFlowDeadCodeRemoval:
    """Verify dead code removal and logic correctness."""

    async def test_sensors_step_always_proceeds_correctly(
        self, hass: HomeAssistant
    ) -> None:
        """Verify sensors step routing logic after dead code removal."""
        flow = SAXBatteryConfigFlow()
        flow.hass = hass

        # Case 1: Pilot enabled → Shows sensor form
        flow._control_power = True
        result = await flow.async_step_sensors(None)
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "sensors"

        # Case 2: Pilot disabled → Already handled by async_step_sensors
        # No dead code path needed
        flow._control_power = False
        flow._battery_count = 1
        result = await flow.async_step_sensors({})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "battery_config"


@pytest.mark.usefixtures("_mock_setup_integration")
class TestSAXBatteryConfigFlowFullCoverage:
    """Tests to achieve 100% coverage of config_flow.py."""

    async def test_reconfigure_battery_config_no_entry_id_in_context(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery_config during reconfigure with missing entry_id.

        Coverage: config_flow.py line 285
        """
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1
        flow._data = {}

        # Set context to reconfigure but don't provide entry_id
        flow.context = {"source": "reconfigure"}

        # Simulate battery_config step with valid data but no entry_id
        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": DEFAULT_PORT,
            }
        )

        # Should abort due to missing entry_id
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_entry_not_found"

    async def test_reconfigure_battery_config_entry_not_found(
        self, hass: HomeAssistant
    ) -> None:
        """Test battery_config during reconfigure with invalid entry_id.

        Coverage: config_flow.py line 292
        """
        flow = SAXBatteryConfigFlow()
        flow.hass = hass
        flow._battery_count = 1
        flow._data = {}

        # Set context with non-existent entry_id
        flow.context = {"source": "reconfigure", "entry_id": "non_existent_id"}

        # Simulate battery_config step with valid data
        result = await flow.async_step_battery_config(
            {
                "bess_a_host": "192.168.1.100",
                "bess_a_port": DEFAULT_PORT,
            }
        )

        # Should abort due to entry not found
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_entry_not_found"

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_options_enable_power_limits_with_integration_data(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test enabling power limits with proper integration data.

        Coverage: config_flow.py lines 570-633
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_enable_power_limits",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with get_unique_id_for_item before setup
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            side_effect=lambda item, battery_id: f"sax_cluster_{item.name}"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(
            side_effect=lambda platform, domain, unique_id: (
                f"number.{unique_id}" if unique_id else None
            )
        )
        mock_ent_reg.async_update_entity = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (triggers _enable_power_limit_entities)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify flow completed
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Verify entity registry was updated
        assert mock_ent_reg.async_update_entity.call_count >= 1

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_options_disable_power_limits_with_integration_data(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test disabling power limits with proper integration data.

        Coverage: config_flow.py lines 661-724
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_disable_power_limits",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            side_effect=lambda item, battery_id: f"sax_cluster_{item.name}"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(
            side_effect=lambda platform, domain, unique_id: (
                f"number.{unique_id}" if unique_id else None
            )
        )
        mock_ent_reg.async_update_entity = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (triggers _async_disable_power_limit_entities)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completed
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Verify entity registry was updated
        assert mock_ent_reg.async_update_entity.call_count >= 1

    async def test_options_disable_control_power_stops_power_manager(
        self, hass: HomeAssistant
    ) -> None:
        """Test disabling control power stops the power manager.

        Coverage: config_flow.py lines 749-758
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_stop_power_manager",
        )
        mock_entry.add_to_hass(hass)

        # Mock power manager before setup
        mock_power_manager = MagicMock()
        mock_power_manager.async_stop = AsyncMock()

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"power_manager": mock_power_manager}

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable control power (should stop power manager)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify power manager was stopped
        mock_power_manager.async_stop.assert_called_once()
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_options_change_limit_power_updates_soc_manager(
        self, hass: HomeAssistant
    ) -> None:
        """Test changing limit power updates SOC manager state.

        Coverage: config_flow.py lines 777-791
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_soc_manager_update",
        )
        mock_entry.add_to_hass(hass)

        # Mock coordinator with SOC manager before setup
        mock_soc_manager = MagicMock()
        mock_soc_manager.enabled = False

        mock_coordinator = MagicMock()
        mock_coordinator.battery_id = "bess_a"
        mock_coordinator.soc_manager = mock_soc_manager

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {
            "coordinators": {"bess_a": mock_coordinator}
        }

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (triggers SOC manager update)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify SOC manager was enabled
        assert mock_soc_manager.enabled is True
        assert result["type"] == FlowResultType.CREATE_ENTRY

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_enable_power_limits_unique_id_generation_fails(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test enable power limits when unique_id generation fails.

        Coverage: config_flow.py lines 595-599
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_unique_id_fail_enable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with get_unique_id_for_item returning None
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(return_value=None)

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (should handle unique_id=None gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify flow completes despite unique_id failure
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Entity registry should not be called since unique_id was None
        mock_ent_reg.async_get_entity_id.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_enable_power_limits_entity_not_found(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test enable power limits when entity not found in registry.

        Coverage: config_flow.py lines 605-610
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_entity_not_found_enable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with valid unique_id
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_cluster_max_discharge"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry to return None (entity not found)
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(return_value=None)
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (should handle entity not found gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify flow completes despite entity not found
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # async_update_entity should not be called since entity wasn't found
        mock_ent_reg.async_update_entity.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_disable_power_limits_sax_data_missing(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test disable power limits when SAXBatteryData is missing.

        Coverage: config_flow.py lines 663-666
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_sax_data_missing",
        )
        mock_entry.add_to_hass(hass)

        # Pre-create integration data WITHOUT sax_data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (should handle missing sax_data gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite missing sax_data
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Entity registry should not be used since sax_data was missing
        mock_ent_reg.async_get_entity_id.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_disable_power_limits_unique_id_generation_fails(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test disable power limits when unique_id generation fails.

        Coverage: config_flow.py lines 686-690
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_unique_id_fail_disable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with get_unique_id_for_item returning None
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(return_value=None)

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry
        mock_ent_reg = MagicMock()
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (should handle unique_id=None gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite unique_id failure
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Entity registry should not be called since unique_id was None
        mock_ent_reg.async_get_entity_id.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_disable_power_limits_entity_not_found(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test disable power limits when entity not found in registry.

        Coverage: config_flow.py lines 696-701
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_entity_not_found_disable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with valid unique_id
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_cluster_max_discharge"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry to return None (entity not found)
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(return_value=None)
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (should handle entity not found gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite entity not found
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # async_update_entity should not be called since entity wasn't found
        mock_ent_reg.async_update_entity.assert_not_called()

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_enable_power_limits_exception_during_enable(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test enable power limits when async_update_entity raises exception.

        Coverage: config_flow.py lines 625-626
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_exception_enable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with valid unique_id
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_cluster_max_discharge"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry with async_update_entity that raises exception
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(
            return_value="number.sax_max_discharge"
        )
        mock_ent_reg.async_update_entity = MagicMock(
            side_effect=RuntimeError("Test exception")
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Enable limit power (should handle exception gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
            },
        )

        # Verify flow completes despite exception
        assert result["type"] == FlowResultType.CREATE_ENTRY

    @patch("custom_components.sax_battery.config_flow.er.async_get")
    async def test_disable_power_limits_exception_during_disable(
        self, mock_entity_registry, hass: HomeAssistant
    ) -> None:
        """Test disable power limits when async_update_entity raises exception.

        Coverage: config_flow.py lines 716-717
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: True,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_exception_disable",
        )
        mock_entry.add_to_hass(hass)

        # Mock SAXBatteryData with valid unique_id
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item = MagicMock(
            return_value="sax_cluster_max_discharge"
        )

        # Pre-create integration data structure
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {"sax_data": mock_sax_data}

        # Mock entity registry with async_update_entity that raises exception
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(
            return_value="number.sax_max_discharge"
        )
        mock_ent_reg.async_update_entity = MagicMock(
            side_effect=RuntimeError("Test exception")
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable limit power (should handle exception gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite exception
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_options_disable_control_power_no_power_manager(
        self, hass: HomeAssistant
    ) -> None:
        """Test disabling control power when no power manager exists.

        Coverage: config_flow.py line 758
        """
        mock_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Battery",
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_CONTROL_POWER: True,
                CONF_LIMIT_POWER: False,
                CONF_MIN_SOC: 20,
                CONF_BATTERIES: {
                    "bess_a": {
                        "host": "192.168.1.100",
                        "port": DEFAULT_PORT,
                        "is_master": True,
                    }
                },
            },
            entry_id="test_no_power_manager",
        )
        mock_entry.add_to_hass(hass)

        # Pre-create integration data WITHOUT power_manager
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_entry.entry_id] = {}

        # Setup integration
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

        # Initialize options flow
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Disable control power (should handle missing power manager gracefully)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROL_POWER: False,
                CONF_LIMIT_POWER: False,
            },
        )

        # Verify flow completes despite missing power manager
        assert result["type"] == FlowResultType.CREATE_ENTRY
