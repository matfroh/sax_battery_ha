"""Number platform for SAX Battery integration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.components.number import NumberEntity
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
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    LIMIT_REFRESH_INTERVAL,
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
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


class SAXBatteryModbusNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
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

         - **SAXBatteryConfigNumber**: Virtual configuration entities (separate class)
             * Examples: min_soc, pilot_power, manual_power
             * Data source: Coordinator memory/config entry (no hardware)
             * Availability: Always available (independent of hardware state)
             * Write operations: Config/state updates only (no hardware writes)
             * Scope: Cluster-wide entities (single instance per installation)

     Write-Only Register Behavior:
         Certain Modbus registers (addresses 41-44) are write-only in SAX battery
         hardware and cannot be read back. For these registers:
         - Values are stored locally in `_local_value` cache
         - `native_value` returns cached value instead of coordinator data
         - UI updates are immediate via `async_write_ha_state()`
         - Values persist across Home Assistant restarts via local cache
         - Registers 41-44: nominal_power, nominal_factor, max_discharge, max_charge

     Pilot Control Coordination:
         Registers 41 (nominal_power) and 42 (nominal_factor) require atomic
         transaction coordination to ensure both values are written together.
         This coordination is critical for the pilot service that controls
         battery charging based on photovoltaic production:

         - Both values must be written in single Modbus transaction
         - If one value is updated, transaction waits for paired value update
         - Transaction timeout: 2.0 seconds
         - Expired transactions are cleaned up automatically
         - Ensures battery receives consistent power/power_factor pair

     Battery Hierarchy and Multi-Battery Systems:
         - Each battery (A, B, C) has its own coordinator and Modbus connection
         - Each battery creates its own set of hardware number entities
         - Master battery (typically A) coordinates power limits across all batteries
         - Slave batteries (B, C) receive coordinated power limits from master
         - Entity unique IDs are per-battery: `{battery_id}_{register_name}`
         - SOC constraints are enforced per-battery via battery's coordinator

     Unique ID Pattern:
         - Format: `{register_name}` without battery_id prefix
         - Examples: "max_discharge", "max_charge", "nominal_power"
         - Device info separates entities by battery (battery_a, battery_b, battery_c)
         - Ensures uniqueness across multi-battery installations
         - Stable across restarts and reconfigurations

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
         - Transaction validation ensures atomic pilot control updates

     Performance:
         - Single atomic Modbus transaction for pilot control register pairs
         - Local cache eliminates repeated reads for write-only registers
         - Batch coordinator updates minimize network overhead
         - Early returns in validation minimize unnecessary processing
         - Transaction cleanup prevents memory leaks from stale operations

    """

    _attr_has_entity_name = True
    # Class-level transaction tracking for pilot control coordination
    _pilot_control_transaction: dict[str, dict[str, Any]] = {}
    _transaction_timeout = 2.0  # seconds

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
    ) -> None:
        """Initialize the modbus number entity with pilot control detection."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id

        # Preserve existing _local_value functionality for write-only registers
        self._local_value: float | None = None
        self._is_write_only = (
            hasattr(modbus_item, "address")
            and modbus_item.address in WRITE_ONLY_REGISTERS
        )

        # Set entity registry enabled state based on configuration
        # This controls whether the entity is enabled by default in the UI
        if coordinator.config_entry:
            self._attr_entity_registry_enabled_default = (
                should_enable_entity_by_default(modbus_item, coordinator.config_entry)
            )
        else:
            # Fallback to item's enabled_by_default attribute
            self._attr_entity_registry_enabled_default = getattr(
                self._modbus_item, "enabled_by_default", True
            )

        # Add pilot control detection (security: validate against known items)
        self._is_pilot_control_item = any(
            item.name == modbus_item.name for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
        )

        # Store reference to paired pilot control item for coordinated writes
        self._pilot_control_pair: ModbusItem | None = None
        if self._is_pilot_control_item:
            self._pilot_control_pair = self._find_pilot_control_pair()

        # Transaction key for coordinating pilot control updates
        self._transaction_key = f"{battery_id}_pilot_control"

        # Generate unique ID using simple pattern (unchanged)
        clean_name: str = self._modbus_item.name.removeprefix("sax_")
        self._attr_unique_id = clean_name

        # Set entity description from modbus item if available (unchanged)
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment]

        # Set entity name (unchanged)
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

        # Set device info for the specific battery (unchanged)
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            battery_id, self._modbus_item.device
        )

        # Initialize with default values for write-only registers (unchanged)
        if self._is_write_only:
            self._initialize_write_only_defaults()

    def _find_pilot_control_pair(self) -> ModbusItem | None:
        """Find the paired pilot control item for coordinated writes.

        Returns:
            The paired ModbusItem or None if not found

        Security:
            Only returns items from the validated MODBUS_BATTERY_POWER_CONTROL_ITEMS list

        """
        if self._modbus_item.name == SAX_NOMINAL_POWER:
            # Find the power factor item (address 42)
            return next(
                (
                    item
                    for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
                    if item.name == SAX_NOMINAL_FACTOR
                ),
                None,
            )
        elif self._modbus_item.name == SAX_NOMINAL_FACTOR:  # noqa: RET505
            # Find the power item (address 41)
            return next(
                (
                    item
                    for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
                    if item.name == SAX_NOMINAL_POWER
                ),
                None,
            )
        return None

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
            self._attr_native_max_value = float(default_value)

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
            self._attr_native_max_value = float(default_value)

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
        """Return the current value (unchanged)."""
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
        """Return if entity is available (unchanged)."""
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
            await self.async_set_native_value(self._local_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value for number entity with comprehensive validation and side effects.

        This is the main method that Home Assistant calls when a user changes the value
        of a number entity through the UI or via service calls. It handles:

        1. **Input Validation**: Validates value against min/max bounds
        2. **SOC Constraint Enforcement**: For power-related registers (SAX_NOMINAL_POWER,
           SAX_MAX_DISCHARGE), applies battery protection constraints via SOC manager
        3. **Write Path Selection**:
           - Pilot control items: Uses atomic transactional write for coordinated updates
           - Standard items: Direct Modbus write via coordinator
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

        Pilot Control Transaction Coordination:
            For SAX_NOMINAL_POWER (addr 41) and SAX_NOMINAL_FACTOR (addr 42), writes
            are coordinated as atomic transactions to ensure both values are updated
            together, which is required for the pilot service that reads photovoltaic
            production and updates battery loading parameters.

        SOC Constraint Behavior:
            When SOC drops below min_soc threshold:
            - User's requested power value is replaced with constrained value (typically 0W)
            - Local cache is updated with constrained value for UI synchronization
            - No error is raised (silent constraint application)
            - Hardware write is enforced by SOC manager's check_and_enforce_discharge_limit()

        Security:
            OWASP A03: Input validation with explicit range checks
            OWASP A05: Enforces battery protection constraints via SOC manager
            OWASP A01: Validates coordinator and SOC manager availability

        Performance:
            - Uses optimized write paths for different register types (NUMBER_WO, NUMBER)
            - Single state update after successful write (no intermediate updates)
            - Early returns in constraint checking minimize coordinator overhead
            - Atomic transaction coordination prevents redundant Modbus operations

        Example:
            # Standard write (readable register)
            await entity.async_set_native_value(3000.0)  # Direct Modbus write

            # Write-only register (address 43 - SAX_MAX_DISCHARGE)
            await entity.async_set_native_value(4000.0)  # Writes to hardware + updates local cache

            # Pilot control (address 41 - SAX_NOMINAL_POWER)
            await entity.async_set_native_value(2500.0)  # Atomic transaction with power_factor

            # SOC constrained write
            # When SOC < min_soc, user's 3000W request becomes 0W constraint
            await entity.async_set_native_value(3000.0)  # Actually writes 0W to hardware

        Side Effects:
            - Updates `_local_value` for write-only registers
            - Triggers `async_write_ha_state()` for UI update
            - Notifies power manager of power changes
            - Triggers coordinator refresh
            - May initiate pilot control transaction
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

            # Handle pilot control items with transaction coordination
            if self._is_pilot_control_item:
                success = await self._write_pilot_control_value_transactional(value)
            else:
                # Direct modbus write
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
        """Return extra state attributes with transaction info."""
        attributes = {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "entity_type": "modbus",
            "is_write_only": self._is_write_only,
            "is_pilot_control": self._is_pilot_control_item,
        }

        if self._is_write_only:
            attributes.update(
                {
                    "local_value": self._local_value,
                    "note": "Write-only register - value maintained locally",
                }
            )

            # Add pilot control specific info
            if self._is_pilot_control_item:
                transaction_pending = (
                    self._transaction_key in self._pilot_control_transaction
                )
                attributes.update(
                    {
                        "pilot_control_note": (
                            "Pilot control register - atomic transaction with paired register"
                        ),
                        "transaction_pending": transaction_pending,
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

    async def _write_pilot_control_value_transactional(self, value: float) -> bool:
        """Write pilot control value using atomic transaction coordination.

        This method ensures that power and power factor are always updated together
        as a single atomic operation, which is crucial for the pilot service that
        reads photovoltaic production and updates battery loading parameters.

        Args:
            value: Value to write to this register

        Returns:
            bool: True if successful

        Security:
            Validates input values and uses transaction-safe operations

        Performance:
            Single atomic Modbus transaction for both registers

        """
        if not self._pilot_control_pair:
            _LOGGER.error("No pilot control pair found for %s", self._modbus_item.name)
            return False

        current_time = time.time()

        # Clean up expired transactions (performance optimization)
        self._cleanup_expired_transactions(current_time)

        try:
            # Get or create transaction for this battery's pilot control
            transaction = self._pilot_control_transaction.setdefault(
                self._transaction_key,
                {
                    "power": None,
                    "power_factor": None,
                    "timestamp": current_time,
                    "pending_writes": set(),
                },
            )

            # Update transaction timestamp
            transaction["timestamp"] = current_time

            # Store the value in the transaction based on register type
            if self._modbus_item.name == SAX_NOMINAL_POWER:
                transaction["power"] = value
                transaction["pending_writes"].add("power")
                _LOGGER.debug(
                    "Transaction: Power value %s W staged for atomic write", value
                )

            elif self._modbus_item.name == SAX_NOMINAL_FACTOR:
                # Validate power factor range before staging
                if not self._validate_power_factor_range(value):
                    _LOGGER.error(
                        "Transaction aborted: Invalid power factor value %s", value
                    )
                    self._pilot_control_transaction.pop(self._transaction_key, None)
                    return False

                transaction["power_factor"] = value
                transaction["pending_writes"].add("power_factor")
                _LOGGER.debug(
                    "Transaction: Power factor value %s staged for atomic write", value
                )

            # Check if we have both values or can get the missing one
            power_value = transaction["power"]
            power_factor_value = transaction["power_factor"]

            # Get missing values from current state
            if power_value is None:
                power_value = await self._get_current_pilot_control_value(
                    SAX_NOMINAL_POWER
                )
                if power_value is None:
                    _LOGGER.debug(
                        "Transaction deferred: Missing power value for atomic write"
                    )
                    return True  # Transaction staged, waiting for paired value
                transaction["power"] = power_value

            if power_factor_value is None:
                power_factor_value = await self._get_current_pilot_control_value(
                    SAX_NOMINAL_FACTOR
                )
                if power_factor_value is None:
                    _LOGGER.debug(
                        "Transaction deferred: Missing power factor value for atomic write"
                    )
                    return True  # Transaction staged, waiting for paired value
                transaction["power_factor"] = power_factor_value

            # Security: Validate all values before atomic write
            if not isinstance(power_value, (int, float)) or power_value < 0:
                _LOGGER.error(
                    "Transaction aborted: Invalid power value %s", power_value
                )
                self._pilot_control_transaction.pop(self._transaction_key, None)
                return False

            if not self._validate_power_factor_range(power_factor_value):
                _LOGGER.error(
                    "Transaction aborted: Invalid power factor value %s",
                    power_factor_value,
                )
                self._pilot_control_transaction.pop(self._transaction_key, None)
                return False

            # Determine scaling for power factor conversion
            pf_display_factor = 10000.0 if power_factor_value > 1000 else 1000.0
            pf_normalized = power_factor_value / pf_display_factor

            _LOGGER.debug(
                "Transaction: Executing atomic pilot control write - power=%s W, power_factor=%s (scaled=%s)",
                power_value,
                power_factor_value,
                pf_normalized,
            )

            # Execute atomic write using coordinator's specialized method
            success = await self.coordinator.async_write_pilot_control_value(
                power_item=(
                    self._modbus_item
                    if self._modbus_item.name == SAX_NOMINAL_POWER
                    else self._pilot_control_pair
                ),
                power_factor_item=(
                    self._modbus_item
                    if self._modbus_item.name == SAX_NOMINAL_FACTOR
                    else self._pilot_control_pair
                ),
                power=power_value,
                power_factor=pf_normalized,
            )

            if success:
                # Update local state for both values (performance: immediate UI feedback)
                if self._is_write_only:
                    self._local_value = value

                _LOGGER.debug(
                    "Transaction completed successfully: power=%s W, power_factor=%s",
                    power_value,
                    power_factor_value,
                )
            else:
                _LOGGER.error(
                    "Transaction failed: Could not write pilot control values atomically"
                )

            # Clean up completed transaction
            self._pilot_control_transaction.pop(self._transaction_key, None)
            return success  # noqa: TRY300

        except (ValueError, TypeError) as err:
            _LOGGER.error("Transaction error - value conversion failed: %s", err)
            self._pilot_control_transaction.pop(self._transaction_key, None)
            return False
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Transaction error - unexpected failure: %s", err)
            self._pilot_control_transaction.pop(self._transaction_key, None)
            return False

    def _validate_power_factor_range(self, value: float) -> bool:
        """Validate power factor value is within acceptable range.

        Args:
            value: Power factor value to validate

        Returns:
            bool: True if value is valid

        Security:
            Prevents invalid power factor values from being written

        """
        try:
            # Determine scaling based on the input value
            if value > 1000:
                max_pf = 10000  # 10000 scaling (9500 = 0.95)
                display_pf = value / 10000.0
            else:
                max_pf = 1000  # 1000 scaling (950 = 0.95)
                display_pf = value / 1000.0

            if not (0 <= value <= max_pf):
                _LOGGER.error(
                    "Power factor %s outside valid range [0, %s]", value, max_pf
                )
                return False

            if not (0.0 <= display_pf <= 1.0):
                _LOGGER.error(
                    "Power factor %s converts to %s, outside physical range [0.0, 1.0]",
                    value,
                    display_pf,
                )
                return False

            return True  # noqa: TRY300

        except (ValueError, TypeError) as err:
            _LOGGER.error("Power factor validation error: %s", err)
            return False

    async def _get_current_pilot_control_value(
        self, register_name: str
    ) -> float | None:
        """Get current value for pilot control register from available sources.

        Args:
            register_name: Name of the register (SAX_NOMINAL_POWER or SAX_NOMINAL_FACTOR)

        Returns:
            Current value or None if not available

        Security:
            Only uses trusted data sources (coordinator data, local state)

        """
        # Try coordinator data first (performance: cached values)
        if self.coordinator.data:
            value = self.coordinator.data.get(register_name)
            if value is not None:
                return float(value)

        # Try local state if this is the register we're handling
        if self._modbus_item.name == register_name and self._local_value is not None:
            return self._local_value

        # For write-only registers, we cannot read current values
        _LOGGER.debug(
            "Current value for %s not available - WO register cannot be read",
            register_name,
        )
        return None

    @classmethod
    def _cleanup_expired_transactions(cls, current_time: float) -> None:
        """Clean up expired transactions to prevent memory leaks.

        Args:
            current_time: Current timestamp for comparison

        Performance:
            Prevents unbounded memory growth from stale transactions

        """
        expired_keys = [
            key
            for key, transaction in cls._pilot_control_transaction.items()
            if current_time - transaction["timestamp"] > cls._transaction_timeout
        ]

        for key in expired_keys:
            _LOGGER.debug("Cleaning up expired pilot control transaction: %s", key)
            cls._pilot_control_transaction.pop(key, None)

    async def async_added_to_hass(self) -> None:
        """Call entity after it is added to hass (unchanged)."""
        await super().async_added_to_hass()

        # For write-only registers, restore value from config if available
        if self._is_write_only and self._local_value is None:
            self._initialize_write_only_defaults()

        # Set up periodic writes
        if self._modbus_item.name in [SAX_MAX_CHARGE, SAX_MAX_DISCHARGE]:
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
        - SAXItem: Virtual entities (min_soc, pilot_power, etc.)
        - ModbusItem: Hardware entities (handled by SAXBatteryModbusNumber)

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
        # Could need special avalable response

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
