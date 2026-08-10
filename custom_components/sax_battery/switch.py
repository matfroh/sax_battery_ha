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
    CONF_CONTROL_POWER,
    CONF_ENABLE_GRID_CHARGING,
    DOMAIN,
    SAX_CHARGE_FROM_GRID_SWITCH,
    SAX_CHARGE_FROM_PV_SWITCH,
)
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import TypeConstants
from .items import ModbusItem, SAXItem

_LOGGER = logging.getLogger(__name__)

# Serialize switch updates to prevent state conflicts
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery switch platform with multi-battery support."""
    integration_data = hass.data[DOMAIN][entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    #  Use union type to allow both SAXBatterySwitch and SAXBatteryControlSwitch
    entities: list[SAXBatterySwitch | SAXBatteryControlSwitch] = []
    entity_details: list[dict[str, Any]] = []

    # Create switches for each battery
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
                entity: SAXBatterySwitch | SAXBatteryControlSwitch = SAXBatterySwitch(
                    coordinator=coordinator,
                    battery_id=battery_id,
                    modbus_item=modbus_item,
                )
                entities.append(entity)

                # Access name attributes directly
                entity_name = getattr(entity, "_attr_name", None) or (
                    entity.entity_description.name
                    if hasattr(entity, "entity_description")
                    and entity.entity_description
                    else modbus_item.name
                )

                # Collect entity details for logging
                entity_details.append(
                    {
                        "type": "modbus",
                        "battery_id": battery_id,
                        "unique_id": entity.unique_id,
                        "name": entity_name,
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
            sax_data.get_sax_items_for_battery("bess_a"),
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

                # Access name attributes directly
                entity_name = getattr(entity, "_attr_name", None) or (
                    entity.entity_description.name
                    if hasattr(entity, "entity_description")
                    and entity.entity_description
                    else sax_item.name
                )

                # Collect entity details for logging
                entity_details.append(
                    {
                        "type": "control",
                        "battery_id": "cluster",
                        "unique_id": entity.unique_id,
                        "name": entity_name,
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
                    "  ✓ switch: %s (battery=%s, addr=%s, enabled=%s, tri_state=%s)",
                    detail["name"],
                    detail["battery_id"],
                    detail["address"],
                    detail["enabled_by_default"],
                    detail["tri_state"],
                )
            else:  # control switch
                _LOGGER.debug(
                    "  ✓ Control Switch: %s (type=%s, sax_item=%s)",
                    detail["name"],
                    detail["type"],
                    detail["sax_item_name"],
                )


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
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=modbus_item,
            battery_id=battery_id,  # For per-battery entities
        )
        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment]

        # Set entity registry enabled state
        self._attr_entity_registry_enabled_default = getattr(
            self._modbus_item, "enabled_by_default", True
        )

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
                except ValueError, TypeError:
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
        standby_value = self._modbus_item.get_switch_standby_value()  # 4 = standby

        # Both "on" (2) and "connected" (3) are considered "True" for HA switch
        if int_value in (on_value, connected_value, standby_value):
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
        except ValueError, TypeError:
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
        await self.coordinator.async_write_switch_value(
            self._modbus_item,
            True,  # This will write the "on" value (2)
        )

        # Request refresh without checking success (write is queued)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (set to 'off' state, value 1)."""
        await self.coordinator.async_write_switch_value(
            self._modbus_item,
            False,  # This will write the "off" value (1)
        )

        # Request refresh without checking success (write is queued)
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
                except ValueError, TypeError:
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
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=sax_item,
            battery_id=None,  # For per-battery entities
        )

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

        # Set cluster device info
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            "cluster", self._sax_item.device
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if entity should be enabled by default.

        This property is evaluated dynamically and overrides the static
        _attr_entity_registry_enabled_default from entity description.

        Control switches (solar_charging, grid_charging) are enabled/disabled
        based on CONF_CONTROL_POWER option.

        Returns:
            True if entity should be enabled by default

        Security:
            OWASP A01: Access control based on integration configuration
        """
        # Control switches require CONF_PILOT_FROM_HA enabled
        if self._sax_item.name in (
            SAX_CHARGE_FROM_PV_SWITCH,
            SAX_CHARGE_FROM_GRID_SWITCH,
        ):
            # Check config entry options for CONF_PILOT_FROM_HA
            control_power = (
                self.coordinator.config_entry.options.get(CONF_CONTROL_POWER, False)
                if self.coordinator.config_entry
                else False
            )

            _LOGGER.debug(
                "Control switch %s: CONF_PILOT_FROM_HA=%s, enabled_default=%s",
                self.entity_id or self._attr_unique_id,
                control_power,
                control_power,
            )

            return control_power

        # All other control switches use static enabled_by_default from SAXItem
        return getattr(self._sax_item, "enabled_by_default", True)

    @property
    def is_on(self) -> bool | None:
        """Return True if switch is on."""
        # OWASP A05: Security misconfiguration - Validate config entry exists
        if self.coordinator.config_entry is None:
            _LOGGER.warning(
                "Config entry is None for control switch %s", self._sax_item.name
            )
            return None

        # Get state from coordinator data (stored by switch toggle actions)
        if self._sax_item.name == SAX_CHARGE_FROM_PV_SWITCH:
            # Read switch state from coordinator data
            pv_enabled = bool(
                self.coordinator.data.get(SAX_CHARGE_FROM_PV_SWITCH, False)
            )
            _LOGGER.debug(
                "PV charging switch state check: pv_enabled=%s",
                pv_enabled,
            )
            return pv_enabled

        if self._sax_item.name == SAX_CHARGE_FROM_GRID_SWITCH:
            grid_enabled = bool(
                self.coordinator.config_entry.data.get(CONF_ENABLE_GRID_CHARGING, False)
            )
            _LOGGER.debug(
                "Grid charging switch state check: grid_enabled=%s",
                grid_enabled,
            )
            return grid_enabled

        # Default SAX item calculation
        if hasattr(self.coordinator, "power_manager"):
            if self._sax_item.name == "pv_charging":
                return bool(self.coordinator.power_manager.get_pv_charging_enabled())
            if self._sax_item.name == "grid_charging":
                return bool(self.coordinator.power_manager.get_grid_charging_enabled())
        return False

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

        _LOGGER.info("Turning ON control switch: %s", self._sax_item.name)

        # Mutual exclusion: Ensure only one control switch is active at a time
        if self._sax_item.name == SAX_CHARGE_FROM_PV_SWITCH:
            # Check if grid control is currently enabled
            grid_enabled = bool(
                self.coordinator.data.get(SAX_CHARGE_FROM_GRID_SWITCH, False)
            )

            if grid_enabled:
                _LOGGER.warning(
                    "Cannot enable PV charging: grid control is active. "
                    "Disabling grid control first."
                )
                # Auto-disable grid control
                self.coordinator.data[SAX_CHARGE_FROM_GRID_SWITCH] = False

                # Trigger power manager update if it exists
                if (
                    hasattr(self.coordinator, "power_manager")
                    and self.coordinator.power_manager
                ):
                    await self.coordinator.power_manager.set_grid_control_mode(
                        False, 0.0
                    )

            # Enable PV charging in coordinator data
            self.coordinator.data[SAX_CHARGE_FROM_PV_SWITCH] = True

            _LOGGER.info(
                "Switch state updated: PV charging enabled, grid control disabled"
            )

            # Trigger power manager update if it exists
            if (
                hasattr(self.coordinator, "power_manager")
                and self.coordinator.power_manager
            ):
                _LOGGER.info("Triggering power manager PV charging mode")
                await self.coordinator.power_manager.set_pv_charging_mode(True)

        elif self._sax_item.name == SAX_CHARGE_FROM_GRID_SWITCH:
            # Check if PV charging is currently enabled
            pv_enabled = bool(
                self.coordinator.data.get(SAX_CHARGE_FROM_PV_SWITCH, False)
            )

            if pv_enabled:
                _LOGGER.warning(
                    "Cannot enable grid control: PV charging is active. "
                    "Disabling PV charging first."
                )
                # Auto-disable PV charging
                self.coordinator.data[SAX_CHARGE_FROM_PV_SWITCH] = False

                # Trigger power manager update if it exists
                if (
                    hasattr(self.coordinator, "power_manager")
                    and self.coordinator.power_manager
                ):
                    await self.coordinator.power_manager.set_pv_charging_mode(False)

            # Enable grid control (keep in config entry for now)
            new_data = {
                **self.coordinator.config_entry.data,
                CONF_ENABLE_GRID_CHARGING: True,
            }
            self.coordinator.data[SAX_CHARGE_FROM_GRID_SWITCH] = True

            _LOGGER.info(
                "Switch state updated: Grid control enabled, PV charging disabled"
            )
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry,
                data=new_data,
            )

            # Trigger power manager update if it exists
            if (
                hasattr(self.coordinator, "power_manager")
                and self.coordinator.power_manager
            ):
                _LOGGER.info("Triggering power manager grid charging mode")
                await self.coordinator.power_manager.set_grid_control_mode(True, 0.0)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the control switch."""
        # OWASP A05: Security misconfiguration - Validate config entry exists
        if self.coordinator.config_entry is None:
            msg = f"Cannot turn off {self.name}: config entry is None"
            raise HomeAssistantError(msg)

        _LOGGER.info("Turning OFF control switch: %s", self._sax_item.name)

        # Update config entry for control switches
        if self._sax_item.name == SAX_CHARGE_FROM_PV_SWITCH:
            # Disable PV charging in coordinator data
            self.coordinator.data[SAX_CHARGE_FROM_PV_SWITCH] = False

            _LOGGER.info("Switch state updated: PV charging disabled")

            # Trigger power manager update if it exists
            if (
                hasattr(self.coordinator, "power_manager")
                and self.coordinator.power_manager
            ):
                _LOGGER.info("Disabling power manager PV charging mode")
                await self.coordinator.power_manager.set_pv_charging_mode(False)

        elif self._sax_item.name == SAX_CHARGE_FROM_GRID_SWITCH:
            new_data = {
                **self.coordinator.config_entry.data,
                CONF_ENABLE_GRID_CHARGING: False,
            }
            _LOGGER.info(
                "Updating config entry for grid charging: CONF_ENABLE_GRID_CHARGING=False"
            )
            self.hass.config_entries.async_update_entry(
                self.coordinator.config_entry,
                data=new_data,
            )

            # Trigger power manager update if it exists
            if (
                hasattr(self.coordinator, "power_manager")
                and self.coordinator.power_manager
            ):
                _LOGGER.info("Disabling power manager grid charging mode")
                await self.coordinator.power_manager.set_grid_control_mode(False, 0.0)

        await self.coordinator.async_request_refresh()
