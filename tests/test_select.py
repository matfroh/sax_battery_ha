"""Tests for the grid power mode select."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.const import (
    CONF_CONTROL_POWER,
    CONF_GRID_POWER_MODE,
    DOMAIN,
    GRID_POWER_MODE_CHARGE,
    GRID_POWER_MODE_DISCHARGE,
)
from custom_components.sax_battery.models import SAXBatteryData
from custom_components.sax_battery.select import SAXBatteryGridPowerModeSelect
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


def _select(hass: HomeAssistant, data: dict) -> SAXBatteryGridPowerModeSelect:
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    select = SAXBatteryGridPowerModeSelect(entry, SAXBatteryData(hass, entry))
    select.hass = hass
    select.async_write_ha_state = MagicMock()  # type: ignore[method-assign, misc]
    return select


async def test_entity_id_has_no_area_prefix(hass: HomeAssistant) -> None:
    """The suggested entity ID follows the other SAX BMS entities."""
    select = _select(hass, {CONF_CONTROL_POWER: True})

    assert select.entity_id == "select.sax_bms_grid_power_mode"


async def test_default_option_is_charge(hass: HomeAssistant) -> None:
    """Charge is selected when nothing is stored."""
    select = _select(hass, {CONF_CONTROL_POWER: True})

    assert select.current_option == GRID_POWER_MODE_CHARGE
    assert select.options == [GRID_POWER_MODE_CHARGE, GRID_POWER_MODE_DISCHARGE]


async def test_select_option_persists_in_config_entry(hass: HomeAssistant) -> None:
    """Selecting discharge is stored so the power manager and restarts see it."""
    select = _select(hass, {CONF_CONTROL_POWER: True})

    await select.async_select_option(GRID_POWER_MODE_DISCHARGE)

    assert select._entry.data[CONF_GRID_POWER_MODE] == GRID_POWER_MODE_DISCHARGE
    assert select.current_option == GRID_POWER_MODE_DISCHARGE


async def test_invalid_option_is_rejected(hass: HomeAssistant) -> None:
    """Unknown modes never reach the config entry."""
    select = _select(hass, {CONF_CONTROL_POWER: True})

    with pytest.raises(HomeAssistantError):
        await select.async_select_option("sideways")
