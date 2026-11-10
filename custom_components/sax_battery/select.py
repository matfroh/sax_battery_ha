"""Select platform for SAX Battery (grid power charge/discharge mode)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CONTROL_POWER,
    CONF_GRID_POWER_MODE,
    DEFAULT_GRID_POWER_MODE,
    DESCRIPTION_GRID_POWER_MODE,
    DOMAIN,
    GRID_POWER_MODE_CHARGE,
    GRID_POWER_MODE_DISCHARGE,
)
from .enums import DeviceConstants, TypeConstants
from .items import SAXItem
from .models import SAXBatteryData

_GRID_POWER_MODES = (GRID_POWER_MODE_CHARGE, GRID_POWER_MODE_DISCHARGE)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the grid power mode select."""
    integration_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    sax_data: SAXBatteryData | None = integration_data.get("sax_data")
    if sax_data is None:
        return

    async_add_entities([SAXBatteryGridPowerModeSelect(entry, sax_data)])


class SAXBatteryGridPowerModeSelect(SelectEntity):
    """Select whether grid power mode charges or discharges the battery."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, sax_data: SAXBatteryData) -> None:
        """Initialize the select."""
        self._entry = entry
        self.entity_description = DESCRIPTION_GRID_POWER_MODE
        self._attr_options = list(_GRID_POWER_MODES)
        self._attr_unique_id = sax_data.get_unique_id_for_item(
            SAXItem(
                name=DESCRIPTION_GRID_POWER_MODE.key,
                mtype=TypeConstants.SENSOR_CALC,
                device=DeviceConstants.SYS,
            ),
            battery_id=None,
        )
        self._attr_device_info = sax_data.get_device_info(
            "cluster", DeviceConstants.SYS
        )
        # Without this HA prefixes the area name; existing entities use the unique ID
        if self._attr_unique_id:
            self.entity_id = f"select.{self._attr_unique_id}"
        # Only relevant when power control is configured, like the control switches
        self._attr_entity_registry_enabled_default = bool(
            entry.data.get(CONF_CONTROL_POWER, False)
        )

    @property
    def current_option(self) -> str:
        """Return the stored mode, defaulting to charge."""
        mode = self._entry.data.get(CONF_GRID_POWER_MODE, DEFAULT_GRID_POWER_MODE)
        return mode if mode in _GRID_POWER_MODES else DEFAULT_GRID_POWER_MODE

    async def async_select_option(self, option: str) -> None:
        """Persist the mode; the power manager reacts to the config update."""
        if option not in _GRID_POWER_MODES:
            raise HomeAssistantError(f"Invalid grid power mode: {option}")

        self.hass.config_entries.async_update_entry(
            self._entry,
            data={**self._entry.data, CONF_GRID_POWER_MODE: option},
        )
        self.async_write_ha_state()
