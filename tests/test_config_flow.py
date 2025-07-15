"""Test config flow for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sax_battery.const import DOMAIN
from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ModbusItem, SAXItem
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component


@pytest.fixture
def mock_modbus_api():
    """Create a mock ModbusAPI."""
    api = MagicMock()
    api.async_write_holding_register = MagicMock(return_value=True)
    api.read_holding_registers = MagicMock(return_value=[42])
    return api


@pytest.fixture
def sample_modbus_item():
    """Create a sample ModbusItem for testing."""
    return ModbusItem(
        battery_slave_id=1,
        address=100,
        name="test_sensor",
        mformat=FormatConstants.NUMBER,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
    )


@pytest.fixture
def sample_sax_item():
    """Create a sample SAXItem for testing."""
    return SAXItem(
        name="test_pilot",
        mformat=FormatConstants.STATUS,
        mtype=TypeConstants.SWITCH,
        device=DeviceConstants.SYS,
    )


@pytest.fixture
async def hass_with_sax(hass: HomeAssistant, mock_sax_data):
    """Set up Home Assistant with SAX Battery integration."""
    hass.data[DOMAIN] = {"test_entry": mock_sax_data}

    with patch("custom_components.sax_battery.async_setup_entry", return_value=True):
        assert await async_setup_component(hass, DOMAIN, {})

    return hass


class TestSAXBatteryConfigFlow:
    """Test config flow."""

    async def test_form_user_success(
        self,
        hass: HomeAssistant,
        mock_setup_entry,
    ) -> None:
        """Test successful user configuration."""
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

    async def test_form_user_with_pilot(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test user configuration with pilot enabled."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Configure battery count
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "battery_count": 1,
            },
        )
        assert result2.get("type") == FlowResultType.FORM

        # Enable pilot options
        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "pilot_from_ha": True,
                "limit_power": True,
            },
        )
        assert result3.get("type") == FlowResultType.FORM
        assert result3.get("step_id") == "pilot_options"
