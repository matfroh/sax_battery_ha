"""Test SAX Battery config flow."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.sax_battery.const import DOMAIN
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


class TestSAXBatteryConfigFlow:
    """Test SAX Battery config flow."""

    async def test_form_user_success(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """Test successful user configuration."""
        with patch(
            "custom_components.sax_battery.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry:
            # Step 1: Initial user step - battery count
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            assert result.get("type") == FlowResultType.FORM
            assert result.get("step_id") == "user"
            assert result.get("errors") == {}

            # Step 2: Configure battery count
            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "battery_count": 1,
                },
            )
            assert result2.get("type") == FlowResultType.FORM
            assert result2.get("step_id") == "control_options"

            # Step 3: Configure control options (no pilot)
            result3 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "pilot_from_ha": False,
                    "limit_power": False,
                },
            )
            assert result3.get("type") == FlowResultType.FORM
            assert result3.get("step_id") == "battery_config"

            # Step 4: Configure battery
            result4 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "battery_a_name": "Battery A",
                    "battery_a_host": "192.168.1.100",
                    "battery_a_port": 502,
                },
            )
            assert result4.get("type") == FlowResultType.CREATE_ENTRY
            assert result4.get("title") == "SAX Battery (1 battery)"
            assert result4.get("data") == {
                "battery_count": 1,
                "pilot_from_ha": False,
                "limit_power": False,
                "battery_a_name": "Battery A",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            }

            mock_setup_entry.assert_called_once()

    async def test_form_user_with_pilot(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """Test user configuration with pilot enabled."""
        with patch(
            "custom_components.sax_battery.async_setup_entry",
            return_value=True,
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            # Configure with pilot enabled
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "battery_count": 2,
                },
            )

            result3 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "pilot_from_ha": True,
                    "limit_power": True,
                },
            )

            # Should show pilot configuration step
            assert result3.get("type") == FlowResultType.FORM
            assert result3.get("step_id")
