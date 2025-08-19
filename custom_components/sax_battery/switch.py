"""Switch platform for SAX Battery integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_SOLAR_CHARGING, CONF_MANUAL_CONTROL, DOMAIN
from .coordinator import SAXBatteryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SAX Battery switches."""
    coordinator: SAXBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SAXBatterySolarChargingSwitch(coordinator),
        SAXBatteryManualControlSwitch(coordinator),
    ]

    async_add_entities(entities)


class SAXBatterySolarChargingSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable solar charging."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_name = "SAX Battery Solar Charging"
        self._attr_unique_id = f"{DOMAIN}_solar_charging"
        self._attr_icon = "mdi:solar-power"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.coordinator.config_entry.data.get(CONF_ENABLE_SOLAR_CHARGING, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (enable solar charging)."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_ENABLE_SOLAR_CHARGING] = True
        # When solar charging is enabled, manual control must be disabled
        new_data[CONF_MANUAL_CONTROL] = False

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Update pilot mode
        if hasattr(self.coordinator, "_pilot") and self.coordinator._pilot:
            self.coordinator._pilot.solar_charging_enabled = True
            await self.coordinator._pilot._async_update_pilot()

        self.async_write_ha_state()
        # Trigger update of manual control switch
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (disable solar charging)."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_ENABLE_SOLAR_CHARGING] = False

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Update pilot mode
        if hasattr(self.coordinator, "_pilot") and self.coordinator._pilot:
            self.coordinator._pilot.solar_charging_enabled = False
            await self.coordinator._pilot._async_update_pilot()

        self.async_write_ha_state()


class SAXBatteryManualControlSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable manual control mode."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_name = "SAX Battery Manual Control"
        self._attr_unique_id = f"{DOMAIN}_manual_control"
        self._attr_icon = "mdi:hand-back-right"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.coordinator.config_entry.data.get(CONF_MANUAL_CONTROL, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (enable manual control)."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_MANUAL_CONTROL] = True
        # When manual control is enabled, solar charging must be disabled
        new_data[CONF_ENABLE_SOLAR_CHARGING] = False

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Update pilot mode
        if hasattr(self.coordinator, "_pilot") and self.coordinator._pilot:
            self.coordinator._pilot.solar_charging_enabled = False
            await self.coordinator._pilot._async_update_pilot()

        self.async_write_ha_state()
        # Trigger update of solar charging switch
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (disable manual control)."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_MANUAL_CONTROL] = False

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Force pilot back to automatic mode
        if hasattr(self.coordinator, "_pilot") and self.coordinator._pilot:
            await self.coordinator._pilot._async_update_pilot()

        self.async_write_ha_state()
