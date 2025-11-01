"""Number platform for SAX Battery integration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_IDS,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_MIN_SOC,
    CONF_PILOT_FROM_HA,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    LIMIT_REFRESH_INTERVAL,
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
    REFRESH_REGISTERS,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
    SAX_PILOT_POWER,
    WRITE_ONLY_REGISTERS,
)
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import TypeConstants
from .items import ModbusItem, SAXItem
from .utils import get_battery_count, should_enable_entity_by_default

_LOGGER = logging.getLogger(__name__)

# custom_components/sax_battery/number.py
PARALLEL_UPDATES = 0  # Coordinator-based, no limit needed


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery number entities with multi-battery support."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    entities: list[NumberEntity] = []
    entity_details: list[dict[str, Any]] = []  # For logging

    # Create numbers for each battery using new constants
    for battery_id, coordinator in coordinators.items():
        # Validate battery_id
        if battery_id not in BATTERY_IDS:
            _LOGGER.warning("Invalid battery ID %s, skipping", battery_id)
            continue

        # Get battery configuration
        battery_config = coordinator.battery_config
        is_master = battery_config.get(CONF_BATTERY_IS_MASTER, False)
        phase = battery_config.get(CONF_BATTERY_PHASE, "L1")

        _LOGGER.debug(
            "Setting up numbers for %s battery %s (%s)",
            "master" if is_master else "slave",
            battery_id,
            phase,
        )

        # Filter number items for this battery
        number_items = filter_items_by_type(
            sax_data.get_modbus_items_for_battery(battery_id),
            TypeConstants.NUMBER,
            config_entry,
            battery_id,
        )

        for modbus_item in number_items:
            if isinstance(modbus_item, ModbusItem):
                entity: SAXBatteryModbusNumber | SAXBatteryConfigNumber = (
                    SAXBatteryModbusNumber(
                        coordinator=coordinator,
                        battery_id=battery_id,
                        modbus_item=modbus_item,
                    )
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
                        "write_only": getattr(entity, "_is_write_only", False),
                        "pilot_control": getattr(
                            entity, "_is_pilot_control_item", False
                        ),
                    }
                )

        _LOGGER.info(
            "Added %d modbus number entities for %s", len(number_items), battery_id
        )

    # Create system-wide configuration numbers only once (using master coordinator)
    master_coordinators = {
        battery_id: coordinator
        for battery_id, coordinator in coordinators.items()
        if coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False)
    }

    if master_coordinators:
        master_coordinator = next(iter(master_coordinators.values()))

        # number entity for cluster is only created for master battery
        system_number_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery("battery_a"),
            TypeConstants.NUMBER,
        )

        for sax_item in system_number_items:
            if isinstance(sax_item, SAXItem):
                entity = SAXBatteryConfigNumber(
                    coordinator=master_coordinator,
                    sax_item=sax_item,
                    # Removed: battery_count parameter
                )
                entities.append(entity)

                # Collect entity details for logging
                entity_details.append(
                    {
                        "type": "config",
                        "battery_id": "cluster",
                        "unique_id": entity.unique_id,
                        "name": entity.name,
                        "enabled_by_default": True,
                        "sax_item_name": sax_item.name,
                    }
                )

        _LOGGER.info("Added %d config number entities", len(system_number_items))

    if entities:
        async_add_entities(entities)

        # Log detailed entity information
        _LOGGER.debug("SAX Battery number entities created:")
        for detail in entity_details:
            if detail["type"] == "modbus":
                _LOGGER.debug(
                    "  Number: %s (battery=%s, addr=%s, enabled=%s, write_only=%s, pilot=%s)",
                    detail["unique_id"],
                    detail["battery_id"],
                    detail["address"],
                    detail["enabled_by_default"],
                    detail["write_only"],
                    detail["pilot_control"],
                )
            else:  # config
                _LOGGER.debug(
                    "  Config Number: %s (type=%s, sax_item=%s)",
                    detail["unique_id"],
                    detail["type"],
                    detail["sax_item_name"],
                )


class SAXBatteryModbusNumber(CoordinatorEntity[SAXBatteryCoordinator], RestoreNumber):
    """Implementation of a SAX Battery number entity backed by ModbusItem.

    This class handles ONLY hardware-backed number entities that directly interact
     with SAX battery Modbus registers. These entities read from and write to physical
     battery hardware via Modbus TCP/IP protocol.

    Architecture Separation:
        - **SAXBatteryModbusNumber** (this class): Hardware-backed Modbus registers
            * Examples: max_discharge, max_charge, nominal_power, nominal_factor
            * Data source: Physical SAX battery hardware via Modbus TCP/IP
            * Availability: Depends on Modbus connection and coordinator state
            * Write operations: Direct hardware register writes with confirmation
            * Scope: Per-battery entities (battery_a, battery_b, battery_c)

    Write-Only Register Behavior:
        Certain Modbus registers (addresses 41-44) are write-only in SAX battery
        hardware and cannot be read back. For these registers:
        - Values are stored locally in `_local_value` cache
        - `native_value` returns cached value instead of coordinator data
        - UI updates are immediate via `async_write_ha_state()`
        - Values persist across Home Assistant restarts via local cache
        - Registers 41-44: nominal_power, nominal_factor, max_discharge, max_charge

    Pilot Control Registers (41, 42):
        These registers are written atomically by power_manager or coordinator:
        - SAX_NOMINAL_POWER and SAX_NOMINAL_FACTOR are DIAGNOSTIC entities
        - Users cannot write directly via UI (entity_category=DIAGNOSTIC)
        - Coordinator handles atomic writes via async_write_pilot_control_value()
        - No transaction coordination needed at entity level

    SOC Constraint Enforcement:
        For power-related registers (SAX_NOMINAL_POWER, SAX_MAX_DISCHARGE):
        - Coordinator's SOC manager validates requested power values
        - When SOC < min_soc, discharge power is constrained to 0W
        - Constraint is applied silently (no user error displayed)
        - Local cache updated with constrained value for UI synchronization
        - Hardware write enforced by coordinator's SOC manager

    Security:
        - OWASP A03: Input validation with explicit min/max range checks
        - OWASP A05: SOC constraint enforcement prevents battery damage
        - OWASP A01: Validates coordinator availability before operations
        - Only writes to validated Modbus registers from WRITE_ONLY_REGISTERS

    Performance:
        - Local cache eliminates repeated reads for write-only registers
        - Batch coordinator updates minimize network overhead
        - Early returns in validation minimize unnecessary processing
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
    ) -> None:
        """Initialize the modbus number entity."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id

        # Local value cache for write-only registers
        self._local_value: float | None = None
        self._is_write_only = (
            hasattr(modbus_item, "address")
            and modbus_item.address in WRITE_ONLY_REGISTERS
        )

        # Set entity registry enabled state based on configuration
        if coordinator.config_entry:
            self._attr_entity_registry_enabled_default = (
                should_enable_entity_by_default(
                    self._modbus_item, coordinator.config_entry
                )
            )
        else:
            self._attr_entity_registry_enabled_default = getattr(
                self._modbus_item, "enabled_by_default", True
            )

        # Generate unique ID using simple pattern
        clean_name: str = self._modbus_item.name.removeprefix("sax_")
        self._attr_unique_id = clean_name

        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment]

        # Set entity name
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            entity_name = str(self.entity_description.name)
            entity_name = entity_name.removeprefix("Sax ")
            self._attr_name = entity_name
        else:
            clean_name = (
                self._attr_unique_id.removeprefix("sax_").replace("_", " ").title()
            )
            self._attr_name = clean_name

        # Set up periodic writes
        self._track_time_remove: Callable[[], None] | None = None

        # Set device info for the specific battery
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            battery_id, self._modbus_item.device
        )

        # Initialize with default values for write-only registers
        if self._is_write_only:
            self._initialize_write_only_defaults()

    def _initialize_write_only_defaults(self) -> None:
        """Initialize default values for write-only registers based on config.

        Uses master coordinator data cache if available (restored from entity states),
        otherwise falls back to config entry defaults.

        Security:
            OWASP A05: Validates data sources and applies safe defaults

        Performance:
            Single data access per register type
        """
        if not self.coordinator.config_entry:
            return

        if not self.coordinator.is_master:
            return

        config_data = self.coordinator.config_entry.data
        battery_count = get_battery_count(self.coordinator.config_entry)

        # Try to get cached value from master coordinator data first
        cached_value = None
        if self.coordinator.data:
            cached_value = self.coordinator.data.get(self._modbus_item.name)
            if cached_value is not None:
                _LOGGER.debug(
                    "Found cached value for write-only register %s: %sW (from entity state restoration)",
                    self._modbus_item.name,
                    cached_value,
                )

        # Set default values based on register type
        if self._modbus_item.name == SAX_MAX_CHARGE:
            default_value = LIMIT_MAX_CHARGE_PER_BATTERY * battery_count
            self.native_max_value = float(default_value)

            # Priority: cached > config > default
            if cached_value is not None:
                self._local_value = float(cached_value)
                _LOGGER.debug(
                    "Restored cached value for %s: %sW",
                    self._modbus_item.name,
                    cached_value,
                )
            else:
                self._local_value = float(config_data.get("max_charge", default_value))

        elif self._modbus_item.name == SAX_MAX_DISCHARGE:
            default_value = LIMIT_MAX_DISCHARGE_PER_BATTERY * battery_count
            self.native_max_value = float(default_value)

            # Priority: cached > config > default
            if cached_value is not None:
                self._local_value = float(cached_value)
                _LOGGER.debug(
                    "Restored cached value for %s: %sW",
                    self._modbus_item.name,
                    cached_value,
                )
            else:
                self._local_value = float(
                    config_data.get("max_discharge", default_value)
                )

        # Initialize pilot control items ONLY from cached/config - no dangerous defaults
        elif self._modbus_item.name in (SAX_NOMINAL_POWER, SAX_NOMINAL_FACTOR):
            # Use cached value if available, otherwise 0.0
            if cached_value is not None:
                self._local_value = float(cached_value)
                _LOGGER.debug(
                    "Restored cached value for pilot control %s: %s",
                    self._modbus_item.name,
                    cached_value,
                )
            else:
                self._local_value = 0.0

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # For write-only registers, use local state
        if self._is_write_only:
            return self._local_value

        # For readable registers, use coordinator data
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self._modbus_item.name)
        return float(value) if value is not None else None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Write-only registers are always available if coordinator is available
        if self._is_write_only:
            return super().available

        # Readable registers need data presence
        return (
            super().available
            and self.coordinator.data is not None
            and self._modbus_item.name in self.coordinator.data
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._track_time_remove:
            self._track_time_remove()

    async def _periodic_write(self, _: Any) -> None:
        """Write the value periodically."""
        if self._local_value is not None:
            if self._modbus_item.address in REFRESH_REGISTERS:
                await self.coordinator.async_write_number_value(
                    self._modbus_item, self._local_value
                )
            await self.async_set_native_value(self._local_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value for number entity with comprehensive validation and side effects.

        This is the main method that Home Assistant calls when a user changes the value
        of a number entity through the UI or via service calls. It handles:

        1. **Input Validation**: Validates value against min/max bounds
        2. **SOC Constraint Enforcement**: For power-related registers (SAX_NOMINAL_POWER,
        SAX_MAX_DISCHARGE), applies battery protection constraints via SOC manager
        3. **Direct Modbus Write**: All registers use direct Modbus write via coordinator
        (Pilot control registers 41, 42 are typically written via coordinator's atomic
        method, but direct write still works)
        4. **Local State Management**: Updates `_local_value` cache for write-only registers
        (addresses 41-44) which cannot be read back from hardware
        5. **Power Manager Notification**: Notifies power management system of power changes
        6. **Coordinator Refresh**: Triggers data refresh to update dependent entities

        Args:
            value: New value to set. Must be within entity's min/max bounds.

        Raises:
            HomeAssistantError: If value is out of valid range, write operation fails,
                            or SOC manager is unavailable when needed

        Write-Only Register Behavior:
            For registers 41-44 (pilot control and power limits), the value is stored
            locally in `_local_value` and returned by `native_value` property since
            these registers cannot be read back from SAX battery hardware.

        Pilot Control Coordination:
            SAX_NOMINAL_POWER (register 41) and SAX_NOMINAL_FACTOR (register 42) are
            typically written atomically via coordinator's `async_write_pilot_control_value()`
            method by power_manager or SAXBatteryConfigNumber. Direct writes to individual
            registers still work but may not maintain coordination.

            These entities have `entity_category=DIAGNOSTIC` which makes them read-only
            in the UI, preventing user-initiated writes. Updates come from:
            - Power manager's automatic control loop
            - SAX_PILOT_POWER config number entity (derives and writes both atomically)

        SOC Constraint Behavior:
            When SOC drops below min_soc threshold:
            - User's requested power value is replaced with constrained value (typically 0W)
            - Local cache is updated with constrained value for UI synchronization
            - No error is raised (silent constraint application)
            - Hardware write is enforced by SOC manager's check_discharge_allowed()

        Security:
            OWASP A03: Input validation with explicit range checks
            OWASP A05: Enforces battery protection constraints via SOC manager
            OWASP A01: Validates coordinator and SOC manager availability

        Performance:
            - Direct Modbus write for all register types
            - Single state update after successful write (no intermediate updates)
            - Early returns in constraint checking minimize coordinator overhead
            - Local cache eliminates read attempts for write-only registers

        Example Usage:
            # Standard write (readable register)
            await entity.async_set_native_value(3000.0)  # Direct Modbus write

            # Write-only register (address 43 - SAX_MAX_DISCHARGE)
            await entity.async_set_native_value(4000.0)  # Writes to hardware + updates local cache

            # Pilot control (address 41 - SAX_NOMINAL_POWER)
            # Note: Typically written via coordinator's atomic method, not user-initiated
            await entity.async_set_native_value(2500.0)  # Direct write (works but not coordinated)

            # SOC constrained write
            # When SOC < min_soc, user's 3000W request becomes 0W constraint
            await entity.async_set_native_value(3000.0)  # Actually writes 0W to hardware

        Side Effects:
            - Updates `_local_value` for write-only registers
            - Triggers `async_write_ha_state()` for UI update
            - Notifies power manager of power changes (if SAX_NOMINAL_POWER)
            - Triggers coordinator refresh
            - Persists SOC constraints to hardware via coordinator
        """
        _LOGGER.debug("%s: Setting value to %s", self.entity_id, value)

        # Validate input range
        min_value = self.native_min_value
        max_value = self.native_max_value

        if min_value is not None and value < min_value:
            msg = f"Value {value} below minimum {min_value}"
            raise HomeAssistantError(msg)

        if max_value is not None and value > max_value:
            msg = f"Value {value} above maximum {max_value}"
            raise HomeAssistantError(msg)

        try:
            # Apply SOC constraints for power-related entities
            if (
                hasattr(self.coordinator, "soc_manager")
                and self.coordinator.soc_manager is not None
                and self._modbus_item.name in [SAX_NOMINAL_POWER, SAX_MAX_DISCHARGE]
            ):
                _LOGGER.debug(
                    "Applying SOC constraints to %s: %s",
                    self._modbus_item.name,
                    value,
                )
                constraint_result = (
                    await self.coordinator.soc_manager.check_discharge_allowed(value)
                )

                if not constraint_result.allowed:
                    _LOGGER.warning(
                        "%s: Power value constrained by SOC manager: %sW -> %sW (%s)",
                        self.entity_id,
                        value,
                        constraint_result.constrained_value,
                        constraint_result.reason,
                    )
                    # Use constrained value instead of blocking
                    value = constraint_result.constrained_value
                    self._local_value = value  # Update local cache for UI sync

            # Direct modbus write for all registers
            # Note: Pilot control registers (41, 42) should be written via
            # coordinator's atomic method, but direct write still works
            success = await self.coordinator.async_write_number_value(
                self._modbus_item, value
            )

            if not success:
                msg = f"Failed to write value to {self.name}"
                raise HomeAssistantError(msg)  # noqa: TRY301

            # CRITICAL: Update local state for write-only registers
            if self._is_write_only:
                self._local_value = value
                self.async_write_ha_state()
                _LOGGER.debug(
                    "Updated local cache for write-only register %s to %s",
                    self._modbus_item.name,
                    value,
                )

            # Notify power manager of power changes (if exists)
            await self._notify_power_manager_update(value)

            await self.coordinator.async_request_refresh()

        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Error setting value for %s", self.name)
            msg = f"Unexpected error: {err}"
            raise HomeAssistantError(msg) from err

    async def _notify_power_manager_update(self, value: float) -> None:
        """Notify power manager of manual power updates.

        Args:
            value: New power value set by user

        Security:
            OWASP A05: Validates coordinator and power manager availability

        Performance:
            Early returns minimize unnecessary coordinator access
        """
        # Access soc_manager through coordinator (not entity attribute)
        if not hasattr(self.coordinator, "soc_manager"):
            _LOGGER.debug(
                "Coordinator has no soc_manager, skipping power manager notification"
            )
            return

        # Check if this is a nominal power entity (early return for performance)
        if self._modbus_item.name != SAX_NOMINAL_POWER:
            return

        # Apply SOC constraints to the power value
        _LOGGER.debug("Applying SOC constraints to manual power update: %sW", value)

        # Access through coordinator property
        constrained_result = await self.coordinator.soc_manager.apply_constraints(value)

        if not constrained_result.allowed:
            _LOGGER.warning(
                "Power update constrained: %sW -> %sW (%s)",
                value,
                constrained_result.constrained_value,
                constrained_result.reason,
            )
            # Update with constrained value
            await self.coordinator.async_write_number_value(
                self._modbus_item, constrained_result.constrained_value
            )
        else:
            _LOGGER.debug("Power update allowed: %sW", value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "entity_type": "modbus",
            "is_write_only": self._is_write_only,
        }

        if self._is_write_only:
            attributes.update(
                {
                    "local_value": self._local_value,
                    "note": "Write-only register - value maintained locally",
                }
            )
        else:
            raw_value = (
                self.coordinator.data.get(self._modbus_item.name)
                if self.coordinator.data
                else None
            )
            attributes["raw_value"] = raw_value

        return attributes

    async def async_added_to_hass(self) -> None:
        """Call entity after it is added to hass."""
        await super().async_added_to_hass()
        # Set up periodic writes for max_charge and max_discharge
        if self._modbus_item.address in REFRESH_REGISTERS:
            last_number_data = await self.async_get_last_number_data()
            if last_number_data:
                # set the state to the last value
                self._local_value = last_number_data.native_value
                self._attr_native_value = last_number_data.native_value
                _LOGGER.debug(
                    "Restored %s from last state: %s",
                    self._modbus_item.name,
                    self._attr_native_value,
                )
            self.async_schedule_update_ha_state()

            self._track_time_remove = async_track_time_interval(
                self.hass,
                self._periodic_write,
                timedelta(minutes=LIMIT_REFRESH_INTERVAL),
            )


class SAXBatteryConfigNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """SAX Battery configuration number entity using SAXItem (virtual entities).

    This class handles ONLY virtual configuration entities (SAXItem) that exist purely
    in coordinator/config state. For hardware-backed Modbus entities, see
    SAXBatteryModbusNumber.

    Architecture:
        - SAXBatteryConfigNumber: Virtual configuration entities (separate class)
        * Examples: min_soc, pilot_power, manual_power
        * Data source: Coordinator memory/config entry (no hardware)
        * Availability: Always available (independent of hardware state)
        * Write operations: Config/state updates only (no hardware writes)
        * Scope: Cluster-wide entities (single instance per installation)



    Availability:
        Config numbers are always available since they don't depend on hardware state.

    Security:
        OWASP A04: Config entities validate input ranges but have no hardware failures
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
    ) -> None:
        """Initialize the config number entity.

        Args:
            coordinator: Master battery coordinator (used for update timing only)
            sax_item: SAX item for system-wide calculations

        Security:
            OWASP A01: Only master coordinator can create config numbers
        """
        super().__init__(coordinator)
        self._sax_item = sax_item

        # Generate unique ID using simple pattern
        clean_name: str = self._sax_item.name.removeprefix("sax_")
        self._attr_unique_id = clean_name

        # Set entity description
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment]

        # Set entity registry enabled state from SAXItem or configuration
        # Special handling for SAX_PILOT_POWER: enabled only if CONF_PILOT_FROM_HA is True
        if sax_item.name == SAX_PILOT_POWER:
            if coordinator.config_entry:
                pilot_from_ha = coordinator.config_entry.data.get(
                    CONF_PILOT_FROM_HA, False
                )
                self._attr_entity_registry_enabled_default = pilot_from_ha
                _LOGGER.debug(
                    "SAX_PILOT_POWER entity enabled_by_default=%s (CONF_PILOT_FROM_HA=%s)",
                    pilot_from_ha,
                    pilot_from_ha,
                )
            else:
                # Fallback: disable by default if no config entry
                self._attr_entity_registry_enabled_default = False
                _LOGGER.warning(
                    "No config entry available, SAX_PILOT_POWER disabled by default"
                )
        else:
            # All other config numbers use SAXItem's enabled_by_default
            self._attr_entity_registry_enabled_default = getattr(
                self._sax_item, "enabled_by_default", True
            )

        # Set entity name
        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            entity_name = str(self.entity_description.name)
            entity_name = entity_name.removeprefix("Sax ")
            self._attr_name = entity_name
        else:
            clean_name = (
                self._attr_unique_id.removeprefix("sax_").replace("_", " ").title()
            )
            self._attr_name = clean_name

        # Initialize with current SOC manager value if this is min_soc
        if sax_item.name == SAX_MIN_SOC and coordinator.soc_manager:
            self._attr_native_value = float(coordinator.soc_manager.min_soc)
        else:
            self._attr_native_value = None

        # Set cluster device info - this creates the "SAX Battery Cluster" device
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            "cluster", self._sax_item.device
        )

    @property
    def battery_count(self) -> int:
        """Get current battery count from config entry.

        Returns:
            Current battery count from configuration

        Performance:
            Direct config access - no caching needed for rarely-changing values
        """
        if not self.coordinator.config_entry:
            _LOGGER.warning("Config entry not available, using default battery count 1")
            return 1

        return get_battery_count(self.coordinator.config_entry)

    @property
    def available(self) -> bool:
        """Return if entity is available.

        Config numbers are available when:
        1. Coordinator last update was successful
        2. We have a valid value from coordinator data or config entry

        Returns:
            True if entity is available, False otherwise
        """
        # ToDo: Check number.sax_cluster_pilot_power which is not calculated
        # Could need special available response

        # Entities depend on coordinator state for calculated values
        return super().available and self.coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # For min_soc, always return current SOC manager value
        if self._sax_item.name == SAX_MIN_SOC and self.coordinator.soc_manager:
            return float(self.coordinator.soc_manager.min_soc)

        return self._attr_native_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for diagnostics.

        Returns:
            Dictionary of diagnostic attributes
        """
        return {
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "entity_type": "cluster_config",
            "calculation_source": "multi_battery_aggregation",
            "sax_item_name": self._sax_item.name,
            "battery_count": self.battery_count,  # Dynamic value from config
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new value with proper validation and persistence."""
        try:
            if self._sax_item.name == SAX_MIN_SOC:
                # Validate SOC manager exists
                if not self.coordinator.soc_manager:
                    raise HomeAssistantError("SOC manager not available")  # noqa: TRY301

                # Validate config entry exists for persistence
                if not self.coordinator.config_entry:
                    raise HomeAssistantError("Config entry not available")  # noqa: TRY301

                # Validate range (0-100%)
                if not isinstance(value, (int, float)) or not (0 <= value <= 100):
                    raise ValueError(f"Minimum SOC must be between 0-100%, got {value}")  # noqa: TRY301

                _LOGGER.debug(
                    "Setting minimum SOC from %s%% to %s%%",
                    self.coordinator.soc_manager.min_soc,
                    value,
                )

                # Update SOC manager
                self.coordinator.soc_manager.min_soc = float(value)

                # Persist to config entry for restart survival
                self.hass.config_entries.async_update_entry(
                    self.coordinator.config_entry,
                    data={
                        **self.coordinator.config_entry.data,
                        CONF_MIN_SOC: int(value),
                    },
                )
                _LOGGER.info("Minimum SOC updated to %s%%", value)

            elif self._sax_item.name == SAX_PILOT_POWER:
                # New: Handle pilot power updates with atomic write to control registers
                await self._handle_pilot_power_update(value)

            else:
                # Generic config value update
                self._attr_native_value = float(value)
                _LOGGER.debug(
                    "Config value %s updated to %s",
                    self._sax_item.name,
                    value,
                )

            # Trigger state update
            self.async_write_ha_state()

        except (ValueError, TypeError) as err:
            _LOGGER.error(
                "Invalid value for %s: %s (%s)",
                self._sax_item.name,
                value,
                err,
            )
            raise HomeAssistantError(f"Invalid value: {err}") from err
        except Exception as err:
            _LOGGER.exception(
                "Failed to set %s to %s",
                self._sax_item.name,
                value,
            )
            raise HomeAssistantError(f"Failed to update: {err}") from err

    async def _handle_pilot_power_update(self, power_value: float) -> None:
        """Handle SAX_PILOT_POWER update by writing to control registers atomically.

        Derives SAX_NOMINAL_POWER and SAX_NOMINAL_FACTOR from pilot power value
        and writes both to registers 41 and 42 in a single atomic transaction.

        Args:
            power_value: Power value in watts (positive=discharge, negative=charge)

        Security:
            OWASP A03: Validates input ranges
            OWASP A05: Applies SOC constraints

        Performance:
            Single atomic Modbus transaction for both registers
        """
        # Validate coordinator and SOC manager availability
        if not self.coordinator.soc_manager:
            raise HomeAssistantError("SOC manager not available")

        # Apply SOC constraints to power value
        _LOGGER.debug("Applying SOC constraints to pilot power: %sW", power_value)
        constrained_result = await self.coordinator.soc_manager.apply_constraints(
            power_value
        )

        if not constrained_result.allowed:
            _LOGGER.warning(
                "Pilot power constrained: %sW -> %sW (%s)",
                power_value,
                constrained_result.constrained_value,
                constrained_result.reason,
            )
            power_value = constrained_result.constrained_value

        # Derive nominal_power (same as pilot power)
        nominal_power = power_value

        # Derive nominal_factor (power factor)
        # Default to 0.95 (9500 in scaled format for 10000 scaling)
        # Or calculate from actual power and apparent power if available
        nominal_factor = await self._calculate_nominal_factor(power_value)

        # Get the ModbusItems for atomic write
        factor_item = next(
            (
                item
                for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
                if item.name == SAX_NOMINAL_FACTOR
            ),
            None,
        )
        power_item = next(
            (
                item
                for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
                if item.name == SAX_NOMINAL_POWER
            ),
            None,
        )

        if not power_item or not factor_item:
            raise HomeAssistantError("Control register items not found")

        # Update corresponding entities if they exist
        self._update_power_entity(SAX_NOMINAL_FACTOR, factor_item, nominal_factor)
        self._update_power_entity(SAX_NOMINAL_POWER, power_item, nominal_power)

        # Write to control registers atomically via coordinator
        success = await self.coordinator.async_write_pilot_control_value(
            power_item=power_item,
            power_factor_item=factor_item,
            power=nominal_power,
            power_factor=nominal_factor,
        )

        if not success:
            raise HomeAssistantError("Failed to write pilot control values")

        # Update local state
        self._attr_native_value = float(power_value)

        _LOGGER.info(
            "Pilot power updated: power=%sW, power_factor=%s",
            nominal_power,
            nominal_factor,
        )

    async def _calculate_nominal_factor(self, power_value: float) -> int:
        """Calculate nominal factor (power factor) from power value.

        Args:
            power_value: Power value in watts

        Returns:
            int: Power factor as scaled integer (0-10000 for 0.0-1.0 range)

        Security:
            OWASP A03: Validates calculation bounds
        """
        # Default power factor: 0.95 (typical for battery systems)
        default_pf = 9500  # 0.95 * 10000

        # Could calculate from apparent power if available:
        # pf = active_power / apparent_power
        # For now, use default value

        if not isinstance(power_value, (int, float)):
            _LOGGER.warning("Invalid power value type, using default PF")  # type: ignore[unreachable]
            return default_pf

        # For zero power, return unity power factor
        if abs(power_value) < 1.0:
            return 10000  # 1.0

        # Return default conservative power factor
        return default_pf

    def _update_power_entity(self, name: str, item: ModbusItem, value: float) -> None:
        """Update the nominal power entity if it exists.

        Args:
            name: name of Modbus item
            item: ModbusItem for diagnosisstic pilot power
            value: New value for number local cache
        """
        if not item:
            return

        # Find the corresponding entity and update its state
        entity_id = self.coordinator.sax_data.get_entity_id_for_item(item, name)
        if entity_id is not None:
            entity = self.hass.states.get(entity_id)
            if entity:
                self.hass.states.async_set(
                    entity_id,
                    str(value),
                    {
                        **entity.attributes,
                        "note": "Updated via pilot power change",
                    },
                )
