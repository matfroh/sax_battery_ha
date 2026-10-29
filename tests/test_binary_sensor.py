"""Tests for configuration-state binary sensors."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.binary_sensor import (
    CONFIGURED_FEATURES,
    SAXBatteryConfiguredFeatureSensor,
)
from custom_components.sax_battery.const import (
    CONF_CONTROL_POWER,
    CONF_LIMIT_POWER,
    DOMAIN,
)
from custom_components.sax_battery.models import SAXBatteryData
from homeassistant.core import HomeAssistant


async def test_configured_feature_entities_reflect_config_entry(
    hass: HomeAssistant,
) -> None:
    """Both configured flags are independently exposed on the BMS device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CONTROL_POWER: True, CONF_LIMIT_POWER: False},
    )
    entry.add_to_hass(hass)
    sax_data = SAXBatteryData(hass, entry)
    entities = {
        feature.config_key: SAXBatteryConfiguredFeatureSensor(entry, sax_data, feature)
        for feature in CONFIGURED_FEATURES
    }

    assert entities[CONF_CONTROL_POWER].is_on is True
    assert entities[CONF_LIMIT_POWER].is_on is False
    assert (
        entities[CONF_CONTROL_POWER].unique_id != entities[CONF_LIMIT_POWER].unique_id
    )

    hass.config_entries.async_update_entry(
        entry,
        data={CONF_CONTROL_POWER: False, CONF_LIMIT_POWER: True},
    )

    assert entities[CONF_CONTROL_POWER].is_on is False
    assert entities[CONF_LIMIT_POWER].is_on is True
