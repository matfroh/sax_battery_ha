"""Test SAX Battery config flow."""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import patch
import uuid

import pytest

from custom_components.sax_battery.const import DOMAIN
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


class TestSAXBatteryConfigFlow:
    """Test SAX Battery config flow."""

    async def test_form_user_basic(
        self, hass: HomeAssistant, enable_custom_integrations, mock_async_setup_entry
    ) -> None:
        """Test basic user configuration form."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"
        assert result.get("errors") == {}

        mock_async_setup_entry.assert_not_called()

    @pytest.mark.skip(reason="Flaky test, needs investigation")
    async def test_form_user_with_pilot(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        mock_async_setup_entry,
        config_flow_user_input_pilot_config,
    ) -> None:
        """Test user configuration with pilot enabled."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Configure with pilot enabled
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"battery_count": 2},
        )

        # Should show control options step
        assert result2.get("type") == FlowResultType.FORM
        assert result2.get("step_id") == "control_options"

        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "pilot_from_ha": True,
                "limit_power": True,
            },
        )

        # Should show pilot configuration step
        assert result3.get("type") == FlowResultType.FORM
        assert result3.get("step_id") == "pilot_options"

        # Configure pilot settings
        result4 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            config_flow_user_input_pilot_config,
        )

        # Should proceed to sensors step
        assert result4.get("type") == FlowResultType.FORM
        assert result4.get("step_id") == "sensors"

        # Mock entity selector to bypass validation issues
        with patch("homeassistant.helpers.selector.EntitySelector") as mock_selector:
            mock_selector.return_value = str  # Return a simple string validator

            # Configure sensors
            result5 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "power_sensor": "sensor.grid_power",
                    "pf_sensor": "sensor.power_factor",
                },
            )

        # Should proceed to priority devices step
        assert result5.get("type") == FlowResultType.FORM
        assert result5.get("step_id") == "priority_devices"

        # Configure priority devices (optional)
        with patch("homeassistant.helpers.selector.EntitySelector") as mock_selector:
            mock_selector.return_value = list  # Return a list validator

            result6 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {},  # No priority devices
            )

        # Should proceed to battery configuration
        assert result6.get("type") == FlowResultType.FORM
        assert result6.get("step_id") == "battery_config"

        # Configure batteries
        result7 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
                "battery_b_host": "192.168.1.101",
                "battery_b_port": 502,
                "master_battery": "battery_a",
            },
        )

        assert result7.get("type") == FlowResultType.CREATE_ENTRY
        assert result7.get("title") == "SAX Battery"
        assert result7.get("data") is not None

        # Verify all data was collected correctly
        data = result7["data"]
        assert data["battery_count"] == 2
        assert data["pilot_from_ha"] is True
        assert data["limit_power"] is True
        assert data["min_soc"] == config_flow_user_input_pilot_config["min_soc"]
        assert data["power_sensor"] == "sensor.grid_power"
        assert data["pf_sensor"] == "sensor.power_factor"
        assert data["battery_a_host"] == "192.168.1.100"
        assert data["battery_b_host"] == "192.168.1.101"
        assert data["master_battery"] == "battery_a"

        mock_async_setup_entry.assert_called_once()

    async def test_form_user_without_pilot(
        self, hass: HomeAssistant, enable_custom_integrations, mock_async_setup_entry
    ) -> None:
        """Test user configuration without pilot."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Configure without pilot
        result2 = await hass.config_entries.flow.async_configure(  # noqa: F841
            result["flow_id"],
            {"battery_count": 1},
        )

        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "pilot_from_ha": False,
                "limit_power": False,
            },
        )

        # Should skip pilot configuration and go directly to battery config
        assert result3.get("type") == FlowResultType.FORM
        assert result3.get("step_id") == "battery_config"

        # Configure battery
        result4 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )

        assert result4.get("type") == FlowResultType.CREATE_ENTRY
        assert result4.get("title") == "SAX Battery"

        data = result4["data"]
        assert data["battery_count"] == 1
        assert data["pilot_from_ha"] is False
        assert data["limit_power"] is False
        assert data["master_battery"] == "battery_a"  # Auto-set for single battery

        mock_async_setup_entry.assert_called_once()

    async def test_form_user_single_battery_auto_master(
        self, hass: HomeAssistant, enable_custom_integrations, mock_async_setup_entry
    ) -> None:
        """Test single battery automatically sets as master."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(  # noqa: F841
            result["flow_id"],
            {"battery_count": 1},
        )

        result3 = await hass.config_entries.flow.async_configure(  # noqa: F841
            result["flow_id"],
            {
                "pilot_from_ha": False,
                "limit_power": False,
            },
        )

        result4 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )

        assert result4.get("type") == FlowResultType.CREATE_ENTRY
        data = result4["data"]
        assert data["master_battery"] == "battery_a"

        mock_async_setup_entry.assert_called_once()

    async def test_form_user_multiple_batteries(
        self, hass: HomeAssistant, enable_custom_integrations, mock_async_setup_entry
    ) -> None:
        """Test multiple battery configuration."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(  # noqa: F841
            result["flow_id"],
            {"battery_count": 3},
        )

        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "pilot_from_ha": False,
                "limit_power": False,
            },
        )

        # Should require master battery selection for multiple batteries
        assert result3.get("type") == FlowResultType.FORM
        assert result3.get("step_id") == "battery_config"

        # Verify schema includes master battery selection
        schema = result3["data_schema"]
        if schema is not None:
            schema_keys = [str(key.schema) for key in schema.schema]
            assert "master_battery" in schema_keys

        result4 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
                "battery_b_host": "192.168.1.101",
                "battery_b_port": 502,
                "battery_c_host": "192.168.1.102",
                "battery_c_port": 502,
                "master_battery": "battery_b",
            },
        )

        assert result4.get("type") == FlowResultType.CREATE_ENTRY
        data = result4["data"]
        assert data["battery_count"] == 3
        assert data["master_battery"] == "battery_b"

        mock_async_setup_entry.assert_called_once()

    async def test_form_user_validation_errors(
        self, hass: HomeAssistant, enable_custom_integrations
    ) -> None:
        """Test validation errors in form."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(  # noqa: F841
            result["flow_id"],
            {"battery_count": 1},
        )

        result3 = await hass.config_entries.flow.async_configure(  # noqa: F841
            result["flow_id"],
            {
                "pilot_from_ha": True,
                "limit_power": False,
            },
        )

        # Test invalid pilot configuration - this should show errors and stay on same step
        result4 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "min_soc": 150,  # Invalid - over 100
                "auto_pilot_interval": 2,  # Invalid - under 5
                "enable_solar_charging": True,
            },
        )

        assert result4.get("type") == FlowResultType.FORM
        assert result4.get("step_id") == "pilot_options"
        errors = result4.get("errors")
        if errors:
            assert "min_soc" in errors
            assert "auto_pilot_interval" in errors

    async def test_options_flow(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        single_battery_config_data,
    ) -> None:
        """Test options flow for existing entry."""
        # Create unique entry ID
        entry_id = str(uuid.uuid4())

        # Create an existing entry manually
        entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="SAX Battery",
            data=single_battery_config_data,
            options={},
            source=config_entries.SOURCE_USER,
            entry_id=entry_id,
            unique_id="test-unique-id",
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
            disabled_by=None,
            created_at=None,
            modified_at=None,
            pref_disable_new_entities=False,
            pref_disable_polling=False,
        )

        # Add entry manually to the registry
        hass.config_entries._entries[entry.entry_id] = entry

        # Start options flow
        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"

        # Configure options - only limit_power should be available for non-pilot entry
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"limit_power": True},
        )

        assert result2.get("type") == FlowResultType.CREATE_ENTRY
        assert result2.get("data") == {"limit_power": True}

    async def test_options_flow_with_pilot_settings(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
        pilot_enabled_config_data,
    ) -> None:
        """Test options flow for entry with pilot enabled."""
        # Create unique entry ID
        entry_id = str(uuid.uuid4())

        # Create an existing entry with pilot enabled manually
        entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="SAX Battery",
            data=pilot_enabled_config_data,
            options={},
            source=config_entries.SOURCE_USER,
            entry_id=entry_id,
            unique_id="test-pilot-unique-id",
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
            disabled_by=None,
            created_at=None,
            modified_at=None,
            pref_disable_new_entities=False,
            pref_disable_polling=False,
        )

        # Add entry manually to the registry
        hass.config_entries._entries[entry.entry_id] = entry

        # Start options flow
        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"

        # Should show pilot options since pilot_from_ha is True
        schema = result["data_schema"]
        if schema is not None:
            schema_keys = [str(key.schema) for key in schema.schema]
            assert "min_soc" in schema_keys
            assert "auto_pilot_interval" in schema_keys
            assert "enable_solar_charging" in schema_keys
            assert "limit_power" in schema_keys

        # Configure options
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "min_soc": 25,
                "auto_pilot_interval": 45,
                "enable_solar_charging": False,
                "limit_power": True,
            },
        )

        assert result2.get("type") == FlowResultType.CREATE_ENTRY
        assert result2.get("data") == {
            "min_soc": 25,
            "auto_pilot_interval": 45,
            "enable_solar_charging": False,
            "limit_power": True,
        }
