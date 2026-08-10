"""Utility functions for SAX Battery integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_BATTERY_COUNT,
    CONF_CONTROL_POWER,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
    MODBUS_BATTERY_POWER_LIMIT_ITEMS,
    MODBUS_BATTERY_REALTIME_ITEMS,
    WRITE_ONLY_REGISTERS,
)
from .items import ModbusItem, SAXItem

_LOGGER = logging.getLogger(__name__)


def get_battery_count(config_entry: ConfigEntry) -> int:
    """Get the number of batteries from configuration entry."""
    return int(config_entry.data.get(CONF_BATTERY_COUNT, 1))


def should_include_entity(
    item: ModbusItem | SAXItem,
    config_entry: ConfigEntry,
    battery_id: str,
) -> bool:
    """Determine if entity should be included based on configuration.

    Note: For write-only registers (41-44), this function determines if the entity
    should be created at all. The entity's enabled state is controlled separately
    via _attr_entity_registry_enabled_default in the entity class.

    Security:
        OWASP A01: Only master battery can have write-only register entities

    Returns:
        True if entity should be created, False otherwise
    """
    # Always include write-only registers for master battery
    # Entity enabled state is controlled via entity_registry_enabled_default
    if (
        isinstance(item, ModbusItem)
        and hasattr(item, "address")
        and item.address in WRITE_ONLY_REGISTERS
    ):
        # Get master battery ID from configuration
        master_battery_id = config_entry.data.get(CONF_MASTER_BATTERY, "bess_a")
        is_master: bool = battery_id == master_battery_id

        # Only master battery gets write-only register entities
        # Entity will be disabled by default if feature is not enabled
        return is_master

    # For ModbusItem, check additional constraints (general case)
    if isinstance(item, ModbusItem):
        device_type = getattr(item, "device", None)
        if device_type:
            config_device = config_entry.data.get("device_type")
            if config_device and device_type != config_device:
                return False

        master_only = getattr(item, "master_only", False)
        if master_only:
            battery_configs = config_entry.data.get("batteries", {})
            battery_config = battery_configs.get(battery_id, {})
            return bool(battery_config.get("role") == "master")

        required_features = getattr(item, "required_features", None)
        if required_features:
            available_features = config_entry.data.get("features", [])
            return bool(
                all(feature in available_features for feature in required_features)
            )

    # Default: include the entity
    return True


def create_register_access_config(
    config_data: dict[str, Any], is_master: bool = False
) -> RegisterAccessConfig:
    """Create register access configuration.

    Args:
        config_data: Configuration data from config entry
        is_master: Whether this is the master battery

    Returns:
        RegisterAccessConfig with dynamic limits based on battery count

    Security:
        Validates configuration parameters and applies secure defaults

    """
    battery_count = config_data.get(CONF_BATTERY_COUNT, 1)

    # Security: Validate battery count is within reasonable limits
    if not isinstance(battery_count, int) or battery_count < 1 or battery_count > 10:
        _LOGGER.warning("Invalid battery count %s, using default of 1", battery_count)
        battery_count = 1

    return RegisterAccessConfig(
        control_power=bool(config_data.get(CONF_CONTROL_POWER, False)),
        limit_power=bool(config_data.get(CONF_LIMIT_POWER, False)),
        is_master_battery=bool(is_master),
        battery_count=battery_count,
    )


def get_writable_registers(
    config_data: dict[str, Any], is_master: bool = False
) -> set[int]:
    """Get set of registers that are writable based on current configuration.

    Args:
        config_data: Configuration data from config entry
        is_master: Whether this is the master battery

    Returns:
        Set of writable register addresses

    Security:
        Only returns registers that are explicitly authorized by configuration

    """
    access_config = create_register_access_config(config_data, is_master)
    return access_config.get_writable_registers()


@dataclass(frozen=True)
class RegisterAccessConfig:
    """Configuration for register access control.

    Security:
        Immutable configuration prevents tampering after creation
    """

    control_power: bool = False
    limit_power: bool = False
    is_master_battery: bool = False
    battery_count: int = 1

    def get_writable_registers(self) -> set[int]:
        """Get set of writable register addresses.

        Returns:
            Set of register addresses that are writable based on configuration

        Security:
            Uses explicit allow-list pattern - only authorized registers are returned

        """
        writable: set[int] = set()

        # Pilot control registers require both control_power AND master battery
        if self.control_power and self.is_master_battery:
            writable.update({41, 42})

        # Power limit registers require both limit_power AND master battery
        if self.limit_power and self.is_master_battery:
            writable.update({43, 44})

        return writable


def get_battery_realtime_items(access_config: RegisterAccessConfig) -> list[ModbusItem]:
    """Get battery realtime items based on access configuration.

    Always includes ALL items (including write-only registers).
    Entity visibility is controlled via entity_registry_enabled_default instead.

    Args:
        access_config: Register access configuration

    Returns:
        List of ModbusItem objects for realtime data including ALL control items

    Security:
        OWASP A01: Only master batteries receive write-only control items
        Entity enabled state controls visibility, not creation

    Performance:
        Creates all entities once, avoids conditional logic during setup
    """
    items = list(MODBUS_BATTERY_REALTIME_ITEMS)  # Make a copy

    # Always add control items for master battery
    # Entity enabled state is controlled via entity_registry_enabled_default
    if access_config.is_master_battery:
        # Add pilot control items (registers 41, 42)
        items.extend(MODBUS_BATTERY_POWER_CONTROL_ITEMS)

        # Add power limit items (registers 43, 44)
        items.extend(MODBUS_BATTERY_POWER_LIMIT_ITEMS)

        _LOGGER.debug(
            "Master battery: Added %d pilot control items and %d power limit items",
            len(MODBUS_BATTERY_POWER_CONTROL_ITEMS),
            len(MODBUS_BATTERY_POWER_LIMIT_ITEMS),
        )

    return items
