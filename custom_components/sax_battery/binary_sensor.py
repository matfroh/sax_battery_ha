"""Configuration status binary sensors for SAX Battery."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CONTROL_POWER,
    CONF_LIMIT_POWER,
    DESCRIPTION_POWER_CONTROL_CONFIGURED,
    DESCRIPTION_POWER_LIMITS_CONFIGURED,
    DOMAIN,
)
from .enums import DeviceConstants, TypeConstants
from .items import SAXItem
from .models import SAXBatteryData


@dataclass(frozen=True, slots=True)
class ConfiguredFeature:
    """Map an automation-facing entity to its config-entry flag."""

    description: BinarySensorEntityDescription
    config_key: str


CONFIGURED_FEATURES = (
    ConfiguredFeature(
        description=DESCRIPTION_POWER_CONTROL_CONFIGURED,
        config_key=CONF_CONTROL_POWER,
    ),
    ConfiguredFeature(
        description=DESCRIPTION_POWER_LIMITS_CONFIGURED,
        config_key=CONF_LIMIT_POWER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors exposing configured power features."""
    integration_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    sax_data: SAXBatteryData | None = integration_data.get("sax_data")
    if sax_data is None:
        return

    async_add_entities(
        SAXBatteryConfiguredFeatureSensor(entry, sax_data, feature)
        for feature in CONFIGURED_FEATURES
    )


class SAXBatteryConfiguredFeatureSensor(BinarySensorEntity):
    """Expose a stored config-entry feature flag to HA automations."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        sax_data: SAXBatteryData,
        feature: ConfiguredFeature,
    ) -> None:
        """Initialize a BMS configuration status entity."""
        self._entry = entry
        self._config_key = feature.config_key
        self.entity_description = feature.description
        entity_item = SAXItem(
            name=feature.description.key,
            mtype=TypeConstants.SENSOR_CALC,
            device=DeviceConstants.SYS,
        )
        self._attr_unique_id = sax_data.get_unique_id_for_item(
            entity_item,
            battery_id=None,
        )
        self._attr_device_info = sax_data.get_device_info(
            "cluster", DeviceConstants.SYS
        )

    @property
    def is_on(self) -> bool:
        """Return whether the feature is configured in the integration."""
        return bool(self._entry.data.get(self._config_key, False))
