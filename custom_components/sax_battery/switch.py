"""SAX Battery switch platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_IDS,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    CONF_PILOT_FROM_HA,
    DOMAIN,
    MANUAL_CONTROL_SWITCH,
    SOLAR_CHARGING_SWITCH,
)
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import TypeConstants
from .items import ModbusItem, SAXItem

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery switch platform with multi-battery support."""
    integration_data = hass.data[DOMAIN][entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    entities: list[SwitchEntity] = []
    entity_details: list[dict[str, Any]] = []  # For logging

    # Create switches for each battery using new constants
    for battery_id, coordinator in coordinators.items():
        # Validate battery_id is in allowed list
        if battery_id not in BATTERY_IDS:
            _LOGGER.warning("Invalid battery ID %s, skipping", battery_id)
            continue

        # Get battery-specific configuration
        battery_config = coordinator.battery_config
        is_master = battery_config.get(CONF_BATTERY_IS_MASTER, False)
        phase = battery_config.get(CONF_BATTERY_PHASE, "L1")

        _LOGGER.debug(
            "Setting up switches for %s battery %s (%s)",
            "master" if is_master else "slave",
            battery_id,
            phase,
        )

        # Filter switch items for this battery
        switch_items = filter_items_by_type(
            sax_data.get_modbus_items_for_battery(battery_id),
            TypeConstants.SWITCH,
            entry,
            battery_id,
        )

        for modbus_item in switch_items:
            if isinstance(modbus_item, ModbusItem):
                entity: SAXBatteryControlSwitch | SAXBatterySwitch = SAXBatterySwitch(
                    coordinator=coordinator,
                    battery_id=battery_id,
                    modbus_item=modbus_item,
                )
                entities.append(entity)

                # Collect entity details for logging
                entity_details.append(
                    {
                        "type": "modbus",
                        "battery_id": battery_id,
                        "unique_id": entity.unique_id,
                        "name": entity.name,
                        "enabled_by_default": getattr(
                            modbus_item, "enabled_by_default", True
                        ),
                        "address": getattr(modbus_item, "address", None),
                        "tri_state": getattr(
                            modbus_item, "is_tri_state_switch", lambda: True
                        )(),
                    }
                )

        _LOGGER.info(
            "Added %d modbus switch entities for %s", len(switch_items), battery_id
        )

    # Create system-wide control switches only once (using master battery coordinator)
    master_coordinators = {
        battery_id: coordinator
        for battery_id, coordinator in coordinators.items()
        if coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False)
    }

    if master_coordinators:
        master_coordinator = next(iter(master_coordinators.values()))

        system_switch_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery("battery_a"),
            TypeConstants.SWITCH,
        )

        for sax_item in system_switch_items:
            if isinstance(sax_item, SAXItem):
                entity = SAXBatteryControlSwitch(
                    coordinator=master_coordinator,
                    sax_item=sax_item,
                    coordinators=coordinators,
                )
                entities.append(entity)

                # Collect entity details for logging
                entity_details.append(
                    {
                        "type": "control",
                        "battery_id": "cluster",
                        "unique_id": entity.unique_id,
                        "name": entity.name,
                        "enabled_by_default": True,
                        "sax_item_name": sax_item.name,
                    }
                )

        _LOGGER.info("Added %d control switch entities", len(system_switch_items))

    if entities:
        async_add_entities(entities)

        # Log detailed entity information
        _LOGGER.debug("SAX Battery switch entities created:")
        for detail in entity_details:
            if detail["type"] == "modbus":
                _LOGGER.debug(
                    "  Switch: %s (battery=%s, addr=%s, enabled=%s, tri_state=%s)",
                    detail["unique_id"],
                    detail["battery_id"],
                    detail["address"],
                    detail["enabled_by_default"],
                    detail["tri_state"],
                )
            else:  # control
                _LOGGER.debug(
                    "  Control Switch: %s (type=%s, sax_item=%s)",
                    detail["unique_id"],
                    detail["type"],
                    detail["sax_item_name"],
                )

    async def async_turn_on(self, **kwargs: Any) -> None:  # type:ignore[no-untyped-def]
        """Turn on the control switch."""
        # OWASP A05: Security misconfiguration - Validate config entry exists
        if self.coordinator.config_entry is None:
            msg = "Config entry not available"
            raise HomeAssistantError(msg)

        # Update config entry for control switches
        if self._sax_item.name == SOLAR_CHARGING_SWITCH:
            # Disable manual control when enabling solar charging
            new_data = {
                **self.coordinator.config_entry.data,
                CONF_ENABLE_SOLAR_CHARGING: True,
                CONF_MANUAL_CONTROL: False,
            }
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry, data=new_data
            )
            _LOGGER.info("Solar charging mode enabled, manual control disabled")
        elif self._sax_item.name == MANUAL_CONTROL_SWITCH:
            # Disable solar charging when enabling manual control
            new_data = {
                **self.coordinator.config_entry.data,
                CONF_MANUAL_CONTROL: True,
                CONF_ENABLE_SOLAR_CHARGING: False,
            }
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry, data=new_data
            )
            _LOGGER.info("Manual control mode enabled, solar charging disabled")

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:  # type:ignore[no-untyped-def]
        """Turn off the control switch."""
        # OWASP A05: Security misconfiguration - Validate config entry exists
        if self.coordinator.config_entry is None:
            msg = "Config entry not available"
            raise HomeAssistantError(msg)

        # Update config entry for control switches
        if self._sax_item.name == SOLAR_CHARGING_SWITCH:
            new_data = {
                **self.coordinator.config_entry.data,
                CONF_ENABLE_SOLAR_CHARGING: False,
            }
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry, data=new_data
            )
            _LOGGER.info("Solar charging mode disabled")
        elif self._sax_item.name == MANUAL_CONTROL_SWITCH:
            new_data = {
                **self.coordinator.config_entry.data,
                CONF_MANUAL_CONTROL: False,
            }
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry, data=new_data
            )
            _LOGGER.info("Manual control mode disabled")

        await self.coordinator.async_request_refresh()


class SAXBatterySwitch(CoordinatorEntity[SAXBatteryCoordinator], SwitchEntity):
    """SAX Battery switch entity for individual battery control."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
    ) -> None:
        """Initialize SAX Battery switch entity."""
        super().__init__(coordinator)

        self._battery_id = battery_id
        self._modbus_item = modbus_item

        # Generate unique ID  - no battery prefix needed
        self._attr_unique_id = self._modbus_item.name

        # Set entity registry enabled state
        self._attr_entity_registry_enabled_default = getattr(
            self._modbus_item, "enabled_by_default", True
        )

        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment]

        # Set entity name - let HA combine with device name automatically
        # Don't add battery prefix since device already provides it
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            # Remove "Sax " prefix from entity description name
            entity_name = self.entity_description.name.removeprefix("Sax ")
            self._attr_name = entity_name
        else:
            # Fallback: use clean item name without prefixes
            clean_name = (
                self._attr_unique_id.replace("_", " ").title().removeprefix("Sax ")
            )
            self._attr_name = clean_name

        # Set device info for the specific battery
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            battery_id, self._modbus_item.device
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        # Security: Safe data access with proper validation
        if not self.coordinator.data:
            return None

        value = self.coordinator.data.get(self._modbus_item.name)
        if value is None:
            return None

        # Performance: Direct comparison for boolean determination
        try:
            # Handle string values by converting them
            if isinstance(value, str):
                # Security: Normalize string input to prevent injection
                normalized_value = value.strip().lower()

                # First try to convert numeric strings to integers for SAX Battery comparison
                try:
                    int_value = int(normalized_value)
                    return self._evaluate_switch_state(int_value)
                except (ValueError, TypeError):
                    # If not numeric, handle common boolean string representations
                    if normalized_value in ("true", "on", "yes"):
                        return True
                    if normalized_value in ("false", "off", "no"):
                        return False
                    if normalized_value == "connected":
                        # For Home Assistant binary switch, "connected" is considered "on"
                        return True
                    _LOGGER.warning(
                        "Invalid string value '%s' for switch %s",
                        value,
                        self._modbus_item.name,
                    )
                    return None

            # Convert to int for comparison
            if isinstance(value, (int, float)):
                int_value = int(value)
                return self._evaluate_switch_state(int_value)

            # Handle boolean values directly
            if isinstance(value, bool):
                return value

            return None  # noqa: TRY300

        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error determining switch state for %s: %s", self._modbus_item.name, err
            )
            return None

    def _evaluate_switch_state(self, int_value: int) -> bool:
        """Evaluate switch state based on SAX Battery values.

        Args:
            int_value: Integer value from the switch

        Returns:
            bool: True for on/connected states, False for off/standby states

        Security: Validates input and provides safe evaluation
        Performance: Efficient state comparison
        """
        on_value = self._modbus_item.get_switch_on_value()  # 2 = on
        connected_value = (
            self._modbus_item.get_switch_connected_value()
        )  # 3 = connected

        # Both "on" (2) and "connected" (3) are considered "True" for HA switch
        if int_value in (on_value, connected_value):
            return True

        # All other values (1=off, 4=standby) are considered "False"
        return False

    @property
    def state_attributes(self) -> dict[str, Any] | None:
        """Return state attributes including detailed switch state."""
        if not self.coordinator.data:
            return None

        raw_value = self.coordinator.data.get(self._modbus_item.name)
        if raw_value is None:
            return None

        try:
            int_value = int(raw_value)
            state_name = self._modbus_item.get_switch_state_name(int_value)

            return {
                "raw_state_value": int_value,
                "detailed_state": state_name,
                "switch_states": {
                    "off": self._modbus_item.get_switch_off_value(),
                    "on": self._modbus_item.get_switch_on_value(),
                    "connected": self._modbus_item.get_switch_connected_value(),
                    "standby": self._modbus_item.get_switch_standby_value(),
                },
            }
        except (ValueError, TypeError):
            return {"raw_state_value": raw_value, "detailed_state": "unknown"}

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        base_attributes = {
            "battery_id": self._battery_id,
            "modbus_address": self._modbus_item.address,
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "raw_value": self.coordinator.data.get(self._modbus_item.name)
            if self.coordinator.data
            else None,
        }

        # Add detailed state information
        state_attrs = self.state_attributes
        if state_attrs:
            base_attributes.update(state_attrs)

        return base_attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (set to 'on' state, value 2)."""
        # When user clicks "turn on", we want the battery to be actively "on" (value 2)
        # not just "connected" (value 3)
        success = await self.coordinator.async_write_switch_value(
            self._modbus_item,
            True,  # This will write the "on" value (2)
        )

        if not success:
            msg = f"Failed to turn on {self.name}"
            raise HomeAssistantError(msg)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (set to 'off' state, value 1)."""
        success = await self.coordinator.async_write_switch_value(
            self._modbus_item,
            False,  # This will write the "off" value (1)
        )

        if not success:
            msg = f"Failed to turn off {self.name}"
            raise HomeAssistantError(msg)

        await self.coordinator.async_request_refresh()

    @property
    def icon(self) -> str | None:
        """Return icon based on current switch state."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "icon")
        ):
            # Use entity description icon as base
            base_icon = self.entity_description.icon
        else:
            base_icon = "mdi:battery"

        # Override icon based on detailed state if available
        if self.coordinator.data:
            raw_value = self.coordinator.data.get(self._modbus_item.name)
            if raw_value is not None:
                try:
                    int_value = int(raw_value)
                    state_name = self._modbus_item.get_switch_state_name(int_value)

                    # Custom icons for different states
                    state_icons = {
                        "off": "mdi:battery-off",
                        "on": "mdi:battery",
                        "connected": "mdi:battery-plus",
                        "standby": "mdi:battery-clock",
                        "unknown": "mdi:battery-unknown",
                    }

                    return state_icons.get(state_name, base_icon)
                except (ValueError, TypeError):
                    pass

        return base_icon

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._modbus_item.name in self.coordinator.data
        )

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return entity category."""
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "entity_category")
        ):
            return self.entity_description.entity_category
        return EntityCategory.CONFIG  # Default for switch entities


class SAXBatteryControlSwitch(CoordinatorEntity[SAXBatteryCoordinator], SwitchEntity):
    """SAX Battery control switch entity for system-wide settings."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
        coordinators: dict[str, SAXBatteryCoordinator],
    ) -> None:
        """Initialize the control switch."""
        super().__init__(coordinator)
        self._sax_item = sax_item
        self._coordinators = coordinators

        # Set coordinators on the SAX item for calculations
        self._sax_item.set_coordinators(coordinators)

        # Generate unique ID using simple pattern
        item_name = self._sax_item.name.removeprefix("sax_")
        self._attr_unique_id = item_name

        # Set entity description from sax item if available
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment]

        # Set entity name
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            entity_name = str(self.entity_description.name)
            self._attr_name = entity_name
        else:
            # Fallback: use clean item name without prefixes
            clean_name = item_name.replace("_", " ").title()
            self._attr_name = clean_name

        # Set cluster device info
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            "cluster", self._sax_item.device
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if switch is on."""
        # OWASP A05: Security misconfiguration - Validate config entry exists
        if self.coordinator.config_entry is None:
            _LOGGER.warning(
                "Config entry is None for control switch %s", self._sax_item.name
            )
            return None

        # Get state from config entry or SAX item calculation
        if self._sax_item.name == SOLAR_CHARGING_SWITCH:
            # ✅ Only enable if pilot mode is also enabled
            pilot_enabled = bool(
                self.coordinator.config_entry.data.get(CONF_PILOT_FROM_HA, False)
            )
            solar_enabled = bool(
                self.coordinator.config_entry.data.get(
                    CONF_ENABLE_SOLAR_CHARGING, False
                )  # Changed default to False
            )
            return pilot_enabled and solar_enabled

        if self._sax_item.name == MANUAL_CONTROL_SWITCH:
            return bool(
                self.coordinator.config_entry.data.get(CONF_MANUAL_CONTROL, False)
            )

        # Default SAX item calculation
        return bool(self._sax_item.calculate_value(self._coordinators))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.config_entry is not None
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the control switch."""
        # OWASP A05: Security misconfiguration - Validate config entry exists
        if self.coordinator.config_entry is None:
            msg = f"Cannot turn on {self.name}: config entry is None"
            raise HomeAssistantError(msg)

        # Update config entry for control switches
        if self._sax_item.name == SOLAR_CHARGING_SWITCH:
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry,
                data={
                    **self.coordinator.config_entry.data,
                    CONF_ENABLE_SOLAR_CHARGING: True,
                },
            )
        elif self._sax_item.name == MANUAL_CONTROL_SWITCH:
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry,
                data={
                    **self.coordinator.config_entry.data,
                    CONF_MANUAL_CONTROL: True,
                },
            )

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the control switch."""
        # OWASP A05: Security misconfiguration - Validate config entry exists
        if self.coordinator.config_entry is None:
            msg = f"Cannot turn off {self.name}: config entry is None"
            raise HomeAssistantError(msg)

        # Update config entry for control switches
        if self._sax_item.name == SOLAR_CHARGING_SWITCH:
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry,
                data={
                    **self.coordinator.config_entry.data,
                    CONF_ENABLE_SOLAR_CHARGING: False,
                },
            )
        elif self._sax_item.name == MANUAL_CONTROL_SWITCH:
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry,
                data={
                    **self.coordinator.config_entry.data,
                    CONF_MANUAL_CONTROL: False,
                },
            )

        await self.coordinator.async_request_refresh()
