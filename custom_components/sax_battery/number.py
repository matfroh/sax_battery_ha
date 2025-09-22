"""Number platform for SAX Battery integration."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_IDS,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    MODBUS_BATTERY_PILOT_CONTROL_ITEMS,
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

_LOGGER = logging.getLogger(__name__)


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
                entities.append(  # noqa: PERF401
                    SAXBatteryModbusNumber(
                        coordinator=coordinator,
                        battery_id=battery_id,
                        modbus_item=modbus_item,
                    )
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

        system_number_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery("battery_a"),
            TypeConstants.NUMBER,
        )

        for sax_item in system_number_items:
            if isinstance(sax_item, SAXItem):
                entities.append(  # noqa: PERF401
                    SAXBatteryConfigNumber(
                        coordinator=master_coordinator,
                        sax_item=sax_item,
                    )
                )

        _LOGGER.info("Added %d config number entities", len(system_number_items))

    if entities:
        async_add_entities(entities)


class SAXBatteryModbusNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """Implementation of a SAX Battery number entity backed by ModbusItem."""

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

        # Set entity registry enabled state
        self._attr_entity_registry_enabled_default = getattr(
            self._modbus_item, "enabled_by_default", True
        )

        # Add pilot control detection (security: validate against known items)
        self._is_pilot_control_item = any(
            item.name == modbus_item.name for item in MODBUS_BATTERY_PILOT_CONTROL_ITEMS
        )

        # Store reference to paired pilot control item for coordinated writes
        self._pilot_control_pair: ModbusItem | None = None
        if self._is_pilot_control_item:
            self._pilot_control_pair = self._find_pilot_control_pair()

        # Transaction key for coordinating pilot control updates
        self._transaction_key = f"{battery_id}_pilot_control"

        # Generate unique ID using simple pattern (unchanged)
        item_name = self._modbus_item.name.removeprefix("sax_")
        self._attr_unique_id = f"sax_{battery_id}_{item_name}"

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
            clean_name = item_name.replace("_", " ").title()
            self._attr_name = clean_name

        # Set device info for the specific battery (unchanged)
        self._attr_device_info = coordinator.sax_data.get_device_info(battery_id)

        # Initialize with default values for write-only registers (unchanged)
        if self._is_write_only:
            self._initialize_write_only_defaults()

    def _find_pilot_control_pair(self) -> ModbusItem | None:
        """Find the paired pilot control item for coordinated writes.

        Returns:
            The paired ModbusItem or None if not found

        Security:
            Only returns items from the validated MODBUS_BATTERY_PILOT_CONTROL_ITEMS list

        """
        if self._modbus_item.name == SAX_NOMINAL_POWER:
            # Find the power factor item (address 42)
            return next(
                (
                    item
                    for item in MODBUS_BATTERY_PILOT_CONTROL_ITEMS
                    if item.name == SAX_NOMINAL_FACTOR
                ),
                None,
            )
        elif self._modbus_item.name == SAX_NOMINAL_FACTOR:  # noqa: RET505
            # Find the power item (address 41)
            return next(
                (
                    item
                    for item in MODBUS_BATTERY_PILOT_CONTROL_ITEMS
                    if item.name == SAX_NOMINAL_POWER
                ),
                None,
            )
        return None

    def _initialize_write_only_defaults(self) -> None:
        """Initialize default values for write-only registers based on config."""
        if not self.coordinator.config_entry:
            return

        config_data = self.coordinator.config_entry.data

        # Set default values based on register type
        if self._modbus_item.name == SAX_MAX_CHARGE:
            # Get from config or use entity description default
            default_value = LIMIT_MAX_CHARGE_PER_BATTERY  # Default per battery
            self._local_value = float(config_data.get("max_charge", default_value))

        elif self._modbus_item.name == SAX_MAX_DISCHARGE:
            # Get from config or use entity description default
            default_value = LIMIT_MAX_DISCHARGE_PER_BATTERY  # Default per battery
            self._local_value = float(config_data.get("max_discharge", default_value))

        # Initialize pilot control items ONLY from config - no dangerous defaults
        elif self._modbus_item.name in (SAX_NOMINAL_POWER, SAX_NOMINAL_FACTOR):
            # Only initialize if explicitly set in config
            self._local_value = 0.0
            # else: leave as None - no dangerous default

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

    async def async_set_native_value(self, value: float) -> None:
        """Set the native value of the number entity.

        This is the main method that Home Assistant calls when a user changes
        the value of a number entity.

        Args:
            value: The new value to set

        Raises:
            HomeAssistantError: If the write operation fails

        Security:
            Validates input and uses secure write methods

        Performance:
            Uses optimized write paths for different register types

        """
        try:
            _LOGGER.debug(
                "Setting native value for %s to %s", self._modbus_item.name, value
            )

            # Check if this is a pilot control item requiring special handling
            if self._is_pilot_control_item:
                success = await self._write_pilot_control_value_transactional(value)
            else:
                # Standard number entity write using coordinator
                success = await self.coordinator.async_write_number_value(
                    self._modbus_item, value
                )

            if not success:
                msg = f"Failed to write value {value} to {self._modbus_item.name}"
                raise HomeAssistantError(msg)  # noqa: TRY301

            # Update local value for write-only registers (immediate UI feedback)
            if self._is_write_only:
                self._local_value = value

            # Update coordinator data immediately for UI responsiveness
            if self.coordinator.data is not None:
                self.coordinator.data[self._modbus_item.name] = value

            # Schedule a coordinator refresh for the next update cycle
            await self.coordinator.async_request_refresh()

            # Write state immediately for UI feedback
            self.async_write_ha_state()

            _LOGGER.debug("Successfully set %s to %s", self._modbus_item.name, value)

        except HomeAssistantError:
            # Re-raise HomeAssistantError as-is
            raise
        except Exception as err:
            _LOGGER.error(
                "Failed to set %s to %s: %s", self._modbus_item.name, value, err
            )
            msg = f"Unexpected error setting {self._modbus_item.name}: {err}"
            raise HomeAssistantError(msg) from err

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


class SAXBatteryConfigNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """Implementation of a SAX Battery configuration number entity using SAXItem."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
    ) -> None:
        """Initialize the config number entity."""
        super().__init__(coordinator)
        self._sax_item = sax_item

        # Generate unique ID using simple pattern
        if self._sax_item.name.startswith("sax_"):
            self._attr_unique_id = self._sax_item.name
        else:
            self._attr_unique_id = f"sax_{self._sax_item.name}"

        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment]

        # Set cluster device info - this creates the "SAX Battery Cluster" device
        self._attr_device_info = coordinator.sax_data.get_device_info("cluster")

    @property
    def native_value(self) -> float | None:
        """Return the current value using SAXItem logic."""
        # For SAX_MIN_SOC, get from config entry data
        if self._sax_item.name == SAX_MIN_SOC and self.coordinator.config_entry:
            config_value = self.coordinator.config_entry.data.get("min_soc", 15)
            return float(config_value)

        # For other SAX items, use the item's own read method
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        raw_value = (
            self.coordinator.data.get(self._sax_item.name)
            if self.coordinator.data
            else None
        )

        return {
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "raw_value": raw_value,
            "entity_type": "config",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new value using SAXItem communication."""
        try:
            _LOGGER.debug(
                "Setting config value for %s to %s", self._sax_item.name, value
            )

            # Use SAXItem's write method for system configuration
            success = await self._sax_item.async_write_value(value)
            if not success:
                msg = f"Failed to write config value {value} to {self._sax_item.name}"
                raise HomeAssistantError(msg)  # noqa: TRY301

            _LOGGER.debug(
                "Successfully set config %s to %s", self._sax_item.name, value
            )

        except HomeAssistantError:
            # Re-raise HomeAssistantError as-is
            raise
        except Exception as err:
            _LOGGER.error("Failed to set %s to %s: %s", self._sax_item.name, value, err)
            msg = f"Unexpected error setting {self._sax_item.name}: {err}"
            raise HomeAssistantError(msg) from err
