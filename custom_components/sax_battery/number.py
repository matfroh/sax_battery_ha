"""Number platform for SAX Battery integration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.components.sensor import ATTR_LAST_RESET
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_IDS,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_CONTROL_POWER,
    CONF_ENABLE_GRID_CHARGING,
    CONF_LIMIT_POWER,
    CONF_MIN_SOC,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    LIMIT_REFRESH_INTERVAL,
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
    REFRESH_REGISTERS,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MAX_SOC_CHARGING,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
    WRITE_ONLY_REGISTERS,
)
from .coordinator import SAXBatteryCoordinator
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import TypeConstants
from .items import ModbusItem, SAXItem
from .utils import get_battery_count

_LOGGER = logging.getLogger(__name__)

# custom_components/sax_battery/number.py
PARALLEL_UPDATES = 0  # Coordinator-based, no limit needed


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery number entities from a config entry.

    Creates two types of number entities:
    1. Cluster-wide config numbers (SAXItem → SAXBatteryConfigNumber)
       - Examples: min_soc
       - Single instance per installation
       - Always available (no hardware dependency)

    2. Per-battery hardware numbers (ModbusItem → SAXBatteryModbusNumber)
       - Examples: max_discharge, max_charge, nominal_power
       - One per battery (bess_a, bess_b, bess_c)
       - Availability depends on Modbus connection

    Security:
        OWASP A05: Validates battery_id and coordinator availability
    """
    integration_data = hass.data[DOMAIN][entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    # Use union type to allow both entity types
    entities: list[SAXBatteryConfigNumber | SAXBatteryModbusNumber] = []
    entity_details: list[dict[str, Any]] = []

    # ============================================================================
    # STEP 1: Create per-battery hardware numbers (ModbusItem → SAXBatteryModbusNumber)
    # ============================================================================
    # These entities are battery-specific and depend on Modbus hardware
    # Examples: sax_max_discharge, sax_max_charge, sax_nominal_power

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
            entry,
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

                # Access name attributes directly
                entity_name = getattr(entity, "_attr_name", None) or (
                    entity.entity_description.name
                    if hasattr(entity, "entity_description")
                    and entity.entity_description
                    else modbus_item.name
                )

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
                        "item_type": "ModbusItem",
                        "write_only": getattr(entity, "_is_write_only", False),
                    }
                )

        _LOGGER.info(
            "Added %d modbus number entities for %s",
            len(number_items),
            battery_id,
        )

    # ============================================================================
    # STEP 2: Create cluster-wide config numbers (SAXItem → SAXBatteryConfigNumber)
    # ============================================================================
    # These entities are system-wide (not per-battery) and always available
    # Examples: sax_min_soc, sax_max_soc_charging

    # Find master coordinator
    master_coordinators = {
        battery_id: coordinator
        for battery_id, coordinator in coordinators.items()
        if coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False)
    }

    if master_coordinators:
        master_coordinator = next(iter(master_coordinators.values()))

        # Use get_sax_items_for_battery() method, not sax_items property
        system_number_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery("bess_a"),  # Correct source
            TypeConstants.NUMBER,
        )

        for sax_item in system_number_items:
            if isinstance(sax_item, SAXItem):
                entity = SAXBatteryConfigNumber(
                    coordinator=master_coordinator,
                    sax_item=sax_item,
                )
                entities.append(entity)

                # Access name attributes directly (not name property)
                entity_name = getattr(entity, "_attr_name", None) or (
                    entity.entity_description.name
                    if hasattr(entity, "entity_description")
                    and entity.entity_description
                    else sax_item.name
                )

                entity_details.append(
                    {
                        "type": "config",
                        "battery_id": "cluster",
                        "unique_id": entity.unique_id,
                        "name": entity_name,
                        "enabled_by_default": True,
                        "item_type": "SAXItem",
                        "sax_item_name": sax_item.name,
                    }
                )

        _LOGGER.info(
            "Added %d config number entities",
            len(system_number_items),
        )

    # ============================================================================
    # STEP 3: Add all entities to Home Assistant
    # ============================================================================

    if entities:
        async_add_entities(entities)

        # Detailed entity logging using direct name access
        _LOGGER.debug("SAX Battery number entities created:")
        for detail in entity_details:
            if detail["type"] == "modbus":
                _LOGGER.debug(
                    "  ✓ %s: %s (battery=%s, unique_id=%s, addr=%s, enabled=%s, write_only=%s)",
                    detail["type"],
                    detail["name"],
                    detail["battery_id"],
                    detail["unique_id"],
                    detail["address"],
                    detail["enabled_by_default"],
                    detail["write_only"],
                )
            else:
                _LOGGER.debug(
                    "  ✓ %s: %s (battery=%s, unique_id=%s, enabled=%s)",
                    detail["type"],
                    detail["name"],
                    detail["battery_id"],
                    detail["unique_id"],
                    detail["enabled_by_default"],
                )
    else:
        _LOGGER.warning("No number entities created - check configuration")


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
            * Scope: Per-battery entities (bess_a, bess_b, bess_c)

    Write-Only Register Behavior:
        Certain Modbus registers (addresses 41-44) are write-only in SAX battery
        hardware and cannot be read back. For these registers:
        - Values are stored locally in `_local_value` cache
        - `native_value` returns cached value instead of coordinator data
        - UI updates are immediate via `async_write_ha_state()`
        - Values persist across Home Assistant restarts via local cache
        - Registers 41-44: nominal_power, nominal_factor, max_discharge, max_charge

    Power Control Registers (41, 42):
        These registers are written atomically by power_manager or coordinator:
        - SAX_NOMINAL_POWER and SAX_NOMINAL_FACTOR are DIAGNOSTIC entities
        - Users cannot write directly via UI (entity_category=DIAGNOSTIC)
        - Coordinator handles atomic writes via async_write_power_control_value()
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
    _unrecorded_attributes = frozenset({ATTR_LAST_RESET})

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
        self._local_value: int | None = None
        self._is_write_only = (
            hasattr(modbus_item, "address")
            and modbus_item.address in WRITE_ONLY_REGISTERS
        )

        # Track periodic write timer
        self._track_time_remove: Callable[[], None] | None = None

        # Generate unique ID using simple pattern
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=modbus_item,
            battery_id=battery_id,  # For per-battery entities
        )

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
        cached_value: int | None = None
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
            self.native_max_value = int(default_value)

            # Priority: cached > config > default
            if cached_value is not None:
                self._local_value = cached_value
                _LOGGER.debug(
                    "Restored cached value for %s: %sW",
                    self._modbus_item.name,
                    cached_value,
                )
            else:
                self._local_value = int(config_data.get("max_charge", default_value))

        elif self._modbus_item.name == SAX_MAX_DISCHARGE:
            default_value = LIMIT_MAX_DISCHARGE_PER_BATTERY * battery_count
            self.native_max_value = int(default_value)

            # Priority: cached > config > default
            if cached_value is not None:
                self._local_value = cached_value
                _LOGGER.debug(
                    "Restored cached value for %s: %sW",
                    self._modbus_item.name,
                    cached_value,
                )
            else:
                self._local_value = int(config_data.get("max_discharge", default_value))

        # Initialize power control items ONLY from cached/config - no dangerous defaults
        elif self._modbus_item.name in (SAX_NOMINAL_POWER, SAX_NOMINAL_FACTOR):
            # Use cached value if available, otherwise 0
            if cached_value is not None:
                self._local_value = cached_value
                _LOGGER.debug(
                    "Restored cached value for power control %s: %s",
                    self._modbus_item.name,
                    cached_value,
                )
            else:
                self._local_value = 0

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if entity should be enabled when first added to the registry.

        Security:
            OWASP A01: Access control based on configuration flags
        """
        # For write-only registers, only enable if feature is configured
        if (
            isinstance(self._modbus_item, ModbusItem)
            and hasattr(self._modbus_item, "address")
            and self._modbus_item.address in WRITE_ONLY_REGISTERS
        ):
            _LOGGER.debug(
                "Write-only register %s (address %d) entity_registry_enabled_default check",
                self._modbus_item.name,
                self._modbus_item.address,
            )

            config_entry = self.coordinator.config_entry
            if config_entry is None:
                return True

            # Check if the corresponding feature is enabled
            if self._modbus_item.name in [SAX_MAX_DISCHARGE, SAX_MAX_CHARGE]:
                # Power limit registers (43-44): check CONF_LIMIT_POWER
                limit_power_enabled = bool(
                    config_entry.data.get(CONF_LIMIT_POWER, False)
                )
                _LOGGER.debug(
                    "Power limit register %s enabled by config: %s",
                    self._modbus_item.name,
                    limit_power_enabled,
                )
                return limit_power_enabled

            if self._modbus_item.name in [SAX_NOMINAL_POWER, SAX_NOMINAL_FACTOR]:
                # power registers (41-42): check CONF_CONTROL_POWER
                control_power_enabled = bool(
                    config_entry.data.get(CONF_CONTROL_POWER, False)
                )
                _LOGGER.debug(
                    "Control power register %s enabled by config: %s",
                    self._modbus_item.name,
                    control_power_enabled,
                )
                return control_power_enabled

        return True

    def _get_battery_count(self) -> int:
        """Get the number of configured batteries.

        Returns:
            Number of batteries configured in the config entry.
            Defaults to 1 if not configured.

        Security:
            OWASP A05: Validates config entry exists before access
        """
        config_entry = self.coordinator.config_entry
        if config_entry is not None:
            return int(config_entry.data.get(CONF_BATTERY_COUNT, 1))
        return 1

    def _is_grid_charging_enabled(self) -> bool:
        """Check if grid charging is enabled in config.

        Returns:
            True if grid charging is enabled, False otherwise.

        Security:
            OWASP A05: Validates config entry exists before access
        """
        config_entry = self.coordinator.config_entry
        if config_entry is not None:
            return bool(config_entry.data.get(CONF_ENABLE_GRID_CHARGING, False))
        return False

    @property
    def native_value(self) -> int | None:
        """Return the current value.

        For write-only registers (41-44), returns cached local value.
        For readable registers, returns value from coordinator data.

        Returns:
            int | None: Current register value or None if unavailable

        Security:
            OWASP A05: Validates data source before access

        Performance:
            Single coordinator data lookup for non-write-only registers
        """
        # Write-only registers: Return cached value
        if self._is_write_only:
            return self._local_value

        # Readable registers: Return from coordinator data
        if not self.coordinator.data:
            return None

        value = self.coordinator.data.get(self._modbus_item.name)

        # Ensure integer type for UINT16/INT16 registers
        if value is not None and isinstance(value, (int, float)):
            return int(value)

        return None

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

    async def async_set_native_value(self, value: float) -> None:
        """Set new value via coordinator write queue for number entity with comprehensive validation and side effects.

        This is the main method that Home Assistant calls when a user changes the value
        of a number entity through the UI or via service calls. It handles:

        1. **Input Validation**: Validates value against min/max bounds
        2. **SOC Constraint Enforcement**: For power-related registers (SAX_NOMINAL_POWER,
        SAX_MAX_DISCHARGE), applies battery protection constraints via SOC manager
        3. **Direct Modbus Write**: All registers use direct Modbus write via coordinator
        (power control registers 41, 42 are typically written via coordinator's atomic
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
            For registers 41-44 (power control and power limits), the value is stored
            locally in `_local_value` and returned by `native_value` property since
            these registers cannot be read back from SAX battery hardware.

        Power Control Coordination:
            SAX_NOMINAL_POWER (register 41) and SAX_NOMINAL_FACTOR (register 42) are
            typically written atomically via coordinator's `async_write_power_control_value()`
            method by power_manager or SAXBatteryConfigNumber. Direct writes to individual
            registers still work but may not maintain coordination.

            These entities have `entity_category=DIAGNOSTIC` which makes them read-only
            in the UI, preventing user-initiated writes. Updates come from:
            - Power manager's automatic control loop
            - SAX_NOMINAL_POWER config number entity (derives and writes both atomically)

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

            # Power control (address 41 - SAX_NOMINAL_POWER)
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

        # Convert to int immediately for validation
        int_value = int(round(value))

        # Validate min/max bounds
        if self.native_min_value is not None and int_value < self.native_min_value:
            msg = f"Value {int_value} below minimum {self.native_min_value}"
            raise HomeAssistantError(msg)

        if self.native_max_value is not None and int_value > self.native_max_value:
            msg = f"Value {int_value} above maximum {self.native_max_value}"
            raise HomeAssistantError(msg)

        original_value = int_value

        # SOC constraint enforcement for power-related registers
        if (
            hasattr(self.coordinator, "soc_manager")
            and self.coordinator.soc_manager is not None
            and self._modbus_item.name == SAX_MAX_DISCHARGE
        ):
            # Get current SOC from coordinator data
            current_soc = (
                self.coordinator.data.get(SAX_COMBINED_SOC)
                if self.coordinator.data
                else None
            )

            if (
                current_soc is not None
                and current_soc < self.coordinator.soc_manager.min_soc
            ):
                # SOC below minimum - constrain discharge power to 0W
                _LOGGER.warning(
                    "%s: SOC %.1f%% below minimum %.1f%% - constraining discharge power from %sW to 0W",
                    self.entity_id,
                    current_soc,
                    self.coordinator.soc_manager.min_soc,
                    int_value,
                )
                int_value = 0

        # Update local cache and UI BEFORE hardware write
        # This ensures UI shows the new value immediately, even if write is queued
        if self._is_write_only:
            self._local_value = int_value
            self.async_write_ha_state()  # Update UI immediately

        # Write to hardware via coordinator write queue
        try:
            # Pilot control registers require atomic write with proper parameters
            if self._modbus_item.name in (SAX_NOMINAL_POWER, SAX_NOMINAL_FACTOR):
                await self._write_power_control_register(
                    self._modbus_item.name, int_value
                )
            else:
                # Standard register write via coordinator (uses write queue)
                await self.coordinator.async_write_number_value(
                    self._modbus_item,
                    int_value,
                )

            _LOGGER.debug(
                "Successfully wrote %s=%s to %s (original=%s)",
                self._modbus_item.name,
                int_value,
                self._battery_id,
                original_value,
            )

            # Notify power manager if this is a limit change
            if self._modbus_item.name in (SAX_MAX_DISCHARGE, SAX_MAX_CHARGE):
                await self._notify_power_manager_update(int_value)

        except Exception as err:
            # Restore original local cache value on write failure
            if self._is_write_only:
                self._local_value = original_value
                self.async_write_ha_state()

            msg = f"Failed to write {self._modbus_item.name}: {err}"
            _LOGGER.error(msg)
            raise HomeAssistantError(msg) from err

    async def _write_power_control_register(
        self,
        item_name: str,
        value: int,
    ) -> bool:
        """Write to power control registers (SAX_NOMINAL_POWER, SAX_NOMINAL_FACTOR).

        Pilot control registers (addresses 41, 42) require atomic writes to prevent
        race conditions. This method coordinates writes through the coordinator's
        write queue to ensure proper sequencing.

        Architecture:
            - SAX_NOMINAL_FACTOR updates are cached locally only (no hardware write)
            - SAX_NOMINAL_POWER triggers actual Modbus write with current factor value
            - Assumes SAX_NOMINAL_FACTOR is always updated before SAX_NOMINAL_POWER
            - Coordinator's async_write_power_control_value() handles atomic write

        Args:
            item_name: Name of the power control register (SAX_NOMINAL_POWER or SAX_NOMINAL_FACTOR)
            value: Value to write (W for power, 0-100% for factor)

        Returns:
            bool: True if write successful or cached, False on error

        Security:
            OWASP A05: Validates coordinator availability before hardware writes
            OWASP A01: Ensures only master coordinator can write power registers

        Performance:
            Avoids redundant writes by caching factor values
            Batches power+factor writes through coordinator queue
        """
        if item_name not in [SAX_NOMINAL_POWER, SAX_NOMINAL_FACTOR]:
            _LOGGER.error(
                "Invalid power control register: %s (expected %s or %s)",
                item_name,
                SAX_NOMINAL_POWER,
                SAX_NOMINAL_FACTOR,
            )
            return False

        # SAX_NOMINAL_FACTOR: Cache locally, no hardware write
        if item_name == SAX_NOMINAL_FACTOR:
            self._local_value = value
            _LOGGER.debug(
                "%s: Cached nominal factor %.1f%% (no hardware write)",
                self.entity_id,
                value,
            )
            return True

        # SAX_NOMINAL_POWER: Trigger hardware write with coordinator
        if item_name == SAX_NOMINAL_POWER:
            # Get current factor value (should be updated before this call)
            factor_entity = self._get_factor_entity()
            if not factor_entity:
                _LOGGER.warning(
                    "%s: Could not find SAX_NOMINAL_FACTOR entity, using default 100%%",
                    self.entity_id,
                )
                factor_value = 100
            else:
                factor_value = factor_entity.native_value or 100

            _LOGGER.debug(
                "%s: Writing power control: power=%.1fW, factor=%.1f%%",
                self.entity_id,
                value,
                factor_value,
            )

            # Delegate to coordinator's atomic write method
            try:
                result = await self.coordinator.async_write_power_control_value(
                    self._modbus_item,
                    value,
                    factor_value,
                )

                if result:
                    # Update local cache on successful write
                    self._local_value = value
                    _LOGGER.info(
                        "%s: Pilot control write successful: power=%.1fW, factor=%.1f%%",
                        self.entity_id,
                        value,
                        factor_value,
                    )
                else:
                    _LOGGER.error(
                        "%s: Pilot control write failed: power=%.1fW, factor=%.1f%%",
                        self.entity_id,
                        value,
                        factor_value,
                    )

                return result  # noqa: TRY300

            except Exception as exc:
                _LOGGER.error(  # noqa: G201
                    "%s: Exception during power control write: %s",
                    self.entity_id,
                    exc,
                    exc_info=True,
                )
                return False

        return False

    def _get_factor_entity(self) -> SAXBatteryModbusNumber | None:
        """Get the SAX_NOMINAL_FACTOR entity for reading current factor value.

        Returns:
            SAXBatteryModbusNumber | None: Factor entity if found, None otherwise

        Performance:
            Uses entity registry lookup to avoid scanning all entities
        """

        ent_reg = er.async_get(self.hass)

        if not self.coordinator.config_entry:
            _LOGGER.error("Coordinator has no config entry")
            return None

        # Find SAX_NOMINAL_FACTOR ModbusItem from MODBUS_BATTERY_POWER_LIMIT_ITEMS list
        factor_item: ModbusItem = next(
            (
                item
                for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
                if item.name == SAX_NOMINAL_FACTOR
            ),
        )

        factor_unique_id = self.coordinator.sax_data.get_unique_id_for_item(
            factor_item,
            SAX_NOMINAL_FACTOR,
        )

        if not factor_unique_id:
            _LOGGER.warning("Could not generate unique_id for SAX_NOMINAL_FACTOR")
            return None

        # Lookup entity_id from registry
        factor_entity_id = ent_reg.async_get_entity_id(
            "number",
            DOMAIN,
            factor_unique_id,
        )

        if not factor_entity_id:
            _LOGGER.warning(
                "Could not find entity_id for SAX_NOMINAL_FACTOR (unique_id: %s)",
                factor_unique_id,
            )
            return None

        # Get entity instance from platform
        platform = entity_platform.async_get_current_platform()
        factor_entity = platform.entities.get(factor_entity_id)

        if not factor_entity or not isinstance(factor_entity, SAXBatteryModbusNumber):
            _LOGGER.warning(
                "Factor entity %s not found or wrong type",
                factor_entity_id,
            )
            return None

        return factor_entity

    async def _notify_power_manager_update(self, value: float) -> None:
        """Notify power manager of control power updates.

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
        _LOGGER.debug("Applying SOC constraints to control power update: %sW", value)

        # Access through coordinator property
        await self.coordinator.async_write_number_value(self._modbus_item, int(value))

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
        """Call entity after it is added to hass.

        For power limit registers (41-42), sets up periodic hardware refresh
        to maintain values after battery power cycles or firmware resets.

        Security:
            OWASP A05: Validates register address before enabling periodic writes

        Performance:
            Only refreshes registers that need it (41-42), not all write-only (43-44)
        """
        await super().async_added_to_hass()

        # Only set up periodic refresh for power limit registers
        # Pilot control registers (43-44) are managed by power manager
        if self._modbus_item.address in REFRESH_REGISTERS:
            # Restore cached value from previous state
            last_number_data = await self.async_get_last_number_data()
            if last_number_data:
                self._local_value = (
                    int(last_number_data.native_value)
                    if last_number_data.native_value is not None
                    else 0
                )
                _LOGGER.debug(
                    "Restored %s from last state: %dW",
                    self._modbus_item.name,
                    self._local_value,
                )

            # Update UI state immediately
            self.async_write_ha_state()

            # Set up periodic hardware refresh
            self._track_time_remove = async_track_time_interval(
                self.hass,
                self._periodic_write,
                timedelta(minutes=LIMIT_REFRESH_INTERVAL),
            )

            _LOGGER.info(
                "Enabled periodic refresh for %s every %d minutes",
                self._modbus_item.name,
                LIMIT_REFRESH_INTERVAL,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed.

        Performance:
            Cancels periodic write timer to prevent memory leaks
        """
        await super().async_will_remove_from_hass()
        await self._stop_periodic_refresh()

    async def _stop_periodic_refresh(self) -> None:
        """Stop periodic refresh timer.

        Performance:
            Prevents memory leaks by properly cleaning up timers
        """
        if self._track_time_remove is not None:
            self._track_time_remove()
            self._track_time_remove = None
            _LOGGER.debug(
                "Cancelled periodic refresh for %s",
                self._modbus_item.name,
            )

    def _handle_entity_disabled(self) -> None:
        """Handle entity being disabled via entity registry.

        Called when entity is disabled to clean up periodic refresh.

        Security:
            OWASP A05: Proper resource cleanup when access is revoked
        """
        # Check if entity is disabled and stop periodic refresh
        if self.entity_registry_enabled_default is False:
            # Schedule async cleanup on next event loop iteration
            self.hass.async_create_task(self._stop_periodic_refresh())
            _LOGGER.info(
                "Entity %s disabled, stopping periodic refresh",
                self.entity_id,
            )

    async def _periodic_write(self, now: datetime | None = None) -> None:
        """Periodically write cached value to hardware.

        This method refreshes power limit registers (41-42) to maintain values
        after battery power cycles, firmware updates, or unexpected resets.

        Args:
            now: Current time (provided by async_track_time_interval)

        Security:
            OWASP A05: Validates cached value and coordinator state

        Performance:
            Non-blocking write via coordinator queue
            Early return if no cached value or coordinator unavailable
        """
        # Validate cached value exists
        if self._local_value is None:
            _LOGGER.debug(
                "Skipping periodic refresh for %s: no cached value",
                self._modbus_item.name,
            )
            return

        # Validate coordinator availability
        if not self.coordinator.last_update_success:
            _LOGGER.debug(
                "Skipping periodic refresh for %s: coordinator unavailable",
                self._modbus_item.name,
            )
            return

        try:
            _LOGGER.debug(
                "Periodic refresh: writing %s=%dW to hardware",
                self._modbus_item.name,
                self._local_value,
            )

            # Write cached value via coordinator queue
            await self.coordinator.async_write_number_value(
                self._modbus_item,
                self._local_value,
            )

            _LOGGER.info(
                "Periodic refresh successful for %s: %dW",
                self._modbus_item.name,
                self._local_value,
            )

        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Periodic refresh failed for %s: %s",
                self._modbus_item.name,
                err,
            )
            # Don't raise - allow next periodic attempt


class SAXBatteryConfigNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """SAX Battery configuration number entity using SAXItem (virtual entities).

    This class handles ONLY virtual configuration entities (SAXItem) that exist purely
    in coordinator/config state. For hardware-backed Modbus entities, see
    SAXBatteryModbusNumber.

    Architecture:
        - SAXBatteryConfigNumber: Virtual configuration entities (separate class)
        * Examples: min_soc, max_soc_charging
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
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=sax_item,
            battery_id=None,  # For per-battery entities
        )

        # Set entity description
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment]

        # Set entity registry enabled state from SAXItem or configuration
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

            # Initialize with current SOC manager value if this is min_soc
            if sax_item.name == SAX_MIN_SOC and coordinator.soc_manager:
                self._attr_native_value = float(coordinator.soc_manager.min_soc)
            elif sax_item.name == SAX_MAX_SOC_CHARGING and coordinator.soc_manager:
                self._attr_native_value = float(
                    coordinator.soc_manager.max_soc_charging
                )
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
        # Entities depend on coordinator state for calculated values
        return super().available and self.coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # For min_soc, always return current SOC manager value
        if self._sax_item.name == SAX_MIN_SOC and self.coordinator.soc_manager:
            return float(self.coordinator.soc_manager.min_soc)
        if self._sax_item.name == SAX_MAX_SOC_CHARGING and self.coordinator.soc_manager:
            return float(self.coordinator.soc_manager.max_soc_charging)

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
                self.coordinator.soc_manager.min_soc = int(value)

                # Persist to config entry for restart survival
                self.hass.config_entries.async_update_entry(
                    self.coordinator.config_entry,
                    data={
                        **self.coordinator.config_entry.data,
                        CONF_MIN_SOC: int(value),
                    },
                )
                _LOGGER.info("Minimum SOC updated to %s%%", value)

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

    async def _handle_control_power_update(self, power_value: int) -> None:
        """Handle CONF_CONTROL_POWER update by writing to control registers atomically.

        Derives SAX_NOMINAL_POWER and SAX_NOMINAL_FACTOR from control power value
        and writes both to registers 41 and 42 in a single atomic transaction.

        Args:
            power_value: Power value in watts (positive=discharge, negative=charge)

        Security:
            OWASP A03: Validates input ranges

        Performance:
            Single atomic Modbus transaction for both registers
        """
        # Validate coordinator and SOC manager availability
        if not self.coordinator.soc_manager:
            raise HomeAssistantError("SOC manager not available")

        # Derive nominal_power (same as  xxx power)
        nominal_power: int = power_value

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
        success = await self.coordinator.async_write_power_control_value(
            power_item=power_item,
            power=nominal_power,
            power_factor=nominal_factor,
        )

        if not success:
            raise HomeAssistantError("Failed to write power control values")

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
        if abs(power_value) < 1:
            return 10000  # 1.0

        # Return default conservative power factor
        return default_pf

    def _update_power_entity(self, name: str, item: ModbusItem, value: int) -> None:
        """Update the nominal power entity if it exists.

        Args:
            name: name of Modbus item
            item: ModbusItem for diagnostic nominal power
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
                        "note": "Updated via nominal power change",
                    },
                )
