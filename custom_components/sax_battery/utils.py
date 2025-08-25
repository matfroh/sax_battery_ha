"""Utility functions for SAX Battery integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory

from .const import (
    CONF_BATTERY_COUNT,
    CONF_LIMIT_POWER,
    CONF_PILOT_FROM_HA,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    MAX_SUPPORTED_BATTERIES,
    MODBUS_BATTERY_PILOT_ITEMS,
    MODBUS_BATTERY_REALTIME_ITEMS,
    WRITE_ONLY_REGISTERS,
)
from .items import ModbusItem, SAXItem


def format_battery_display_name(battery_id: str) -> str:
    """Format battery ID into a human-readable display name.

    Args:
        battery_id: The battery identifier (e.g., "battery_a", "battery_b")

    Returns:
        Formatted display name (e.g., "Battery A", "Battery B")

    Examples:
        >>> format_battery_display_name("battery_a")
        "Battery A"
        >>> format_battery_display_name("battery_b")
        "Battery B"
        >>> format_battery_display_name("custom_battery_c")
        "Custom Battery C"

    """
    # Remove common prefixes and convert to title case
    display_name = battery_id.replace("battery_", "Battery ").title()

    # Handle edge cases where battery_id doesn't follow expected pattern
    if not display_name.startswith("Battery"):
        # If it doesn't start with "Battery", format it nicely
        display_name = display_name.replace("_", " ").title()

    return display_name


def determine_entity_category(
    modbus_item: ModbusItem | SAXItem,
) -> EntityCategory | None:
    """Determine entity category based on modbus item.

    Args:
        modbus_item: Modbus item

    Returns:
        Entity category or None

    """
    # Check entitydescription for entity_category first
    if hasattr(modbus_item, "entitydescription") and modbus_item.entitydescription:
        if (
            hasattr(modbus_item.entitydescription, "entity_category")
            and modbus_item.entitydescription.entity_category
        ):
            return modbus_item.entitydescription.entity_category

    diagnostic_keywords = ["debug", "diagnostic", "status", "error", "version"]
    config_keywords = ["config", "setting", "limit", "max_", "pilot_", "enable_"]

    item_name_lower = modbus_item.name.lower()

    if any(keyword in item_name_lower for keyword in diagnostic_keywords):
        return EntityCategory.DIAGNOSTIC

    if any(keyword in item_name_lower for keyword in config_keywords):
        return EntityCategory.CONFIG

    return None


def should_include_entity(
    modbus_item: ModbusItem,
    config_entry: ConfigEntry,
    battery_id: str,
) -> bool:
    """Determine if entity should be included based on configuration.

    Args:
        modbus_item: Modbus item
        config_entry: Config entry
        battery_id: Battery identifier

    Returns:
        True if entity should be included

    """
    # Filter out write-only registers that cannot be read
    if hasattr(modbus_item, "address") and modbus_item.address in WRITE_ONLY_REGISTERS:
        return False

    # Check device type compatibility
    device_type = getattr(modbus_item, "device", None)
    if device_type:
        config_device = config_entry.data.get("device_type")
        if config_device and device_type != config_device:
            return False

    # Check master-only items
    master_only = getattr(modbus_item, "master_only", False)
    if master_only:
        # Check if this battery is configured as master
        master_battery_id: str = config_entry.data.get("master_battery", "battery_a")
        is_master: bool = battery_id == master_battery_id

        # Also check batteries configuration if available
        batteries_config = config_entry.data.get("batteries", {})
        if batteries_config and battery_id in batteries_config:
            battery_config = batteries_config[battery_id]
            is_master = battery_config.get("role") == "master"

        return is_master

    # Check required features
    required_features = getattr(modbus_item, "required_features", None)
    if required_features:
        available_features = config_entry.data.get("features", [])
        return all(feature in available_features for feature in required_features)

    return True


def calculate_system_max_charge(battery_count: int) -> int:
    """Calculate maximum charge power for the entire system.

    Args:
        battery_count: Number of batteries in the system (1-3)

    Returns:
        Maximum charge power in watts for the system

    """
    if battery_count < 1 or battery_count > MAX_SUPPORTED_BATTERIES:
        msg = f"Battery count must be between 1 and {MAX_SUPPORTED_BATTERIES}, got {battery_count}"
        raise ValueError(msg)

    return battery_count * LIMIT_MAX_CHARGE_PER_BATTERY


def calculate_system_max_discharge(battery_count: int) -> int:
    """Calculate maximum discharge power for the entire system.

    Args:
        battery_count: Number of batteries in the system (1-3)

    Returns:
        Maximum discharge power in watts for the system

    """
    if battery_count < 1 or battery_count > MAX_SUPPORTED_BATTERIES:
        msg = f"Battery count must be between 1 and {MAX_SUPPORTED_BATTERIES}, got {battery_count}"
        raise ValueError(msg)

    return battery_count * LIMIT_MAX_DISCHARGE_PER_BATTERY


# def get_battery_limits_for_count(battery_count: int) -> tuple[int, int]:
#     """Get both charge and discharge limits for a given battery count.

#     Args:
#         battery_count: Number of batteries in the system (1-3)

#     Returns:
#         Tuple of (max_charge, max_discharge) in watts

#     """
#     return (
#         calculate_system_max_charge(battery_count),
#         calculate_system_max_discharge(battery_count),
#     )


def create_register_access_config(
    config_data: dict[str, Any], is_master: bool = False
) -> RegisterAccessConfig:
    """Create register access configuration.

    Args:
        config_data: Configuration data from config entry
        is_master: Whether this is the master battery

    Returns:
        RegisterAccessConfig with dynamic limits based on battery count

    """
    battery_count = config_data.get(CONF_BATTERY_COUNT, 1)

    return RegisterAccessConfig(
        pilot_from_ha=config_data.get(CONF_PILOT_FROM_HA, False),
        limit_power=config_data.get(CONF_LIMIT_POWER, False),
        is_master_battery=is_master,
        battery_count=battery_count,
    )


def get_writable_registers(
    config_data: dict[str, Any], is_master: bool = False
) -> set[int]:
    """Get set of registers that are writable based on current configuration."""
    access_config = create_register_access_config(config_data, is_master)
    return access_config.get_writable_registers()


@dataclass(frozen=True)
class RegisterAccessConfig:
    """Configuration for register access control."""

    pilot_from_ha: bool = False
    limit_power: bool = False
    is_master_battery: bool = False
    battery_count: int = 1

    # def can_write_register(self, address: int) -> bool:
    #     """Check if a register can be written to."""
    #     # Pilot registers (41, 42) require pilot_from_ha
    #     if address in {41, 42}:
    #         return self.pilot_from_ha and self.is_master_battery

    #     # Power limit registers (43, 44) require limit_power
    #     if address in {43, 44}:
    #         return self.limit_power

    #     # Other registers are generally writable
    #     return True

    # def get_system_max_charge(self) -> int:
    #     """Get system maximum charge power."""
    #     return calculate_system_max_charge(self.battery_count)

    # def get_system_max_discharge(self) -> int:
    #     """Get system maximum discharge power."""
    #     return calculate_system_max_discharge(self.battery_count)

    def get_writable_registers(self) -> set[int]:
        """Get set of writable register addresses."""
        writable = set()

        if self.pilot_from_ha and self.is_master_battery:
            writable.update({41, 42})

        if self.limit_power:
            writable.update({43, 44})

        return writable


# Entity descriptions for read-only versions
def get_battery_realtime_items(access_config: RegisterAccessConfig) -> list[ModbusItem]:
    """Get battery realtime items based on access configuration."""
    items = MODBUS_BATTERY_REALTIME_ITEMS

    # Add writable items based on configuration
    if access_config.pilot_from_ha:
        items.extend(MODBUS_BATTERY_PILOT_ITEMS)

    return items
