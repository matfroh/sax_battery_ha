"""Utility functions for SAX Battery integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import (
    CONF_BATTERY_COUNT,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_PILOT_FROM_HA,
    DOMAIN,
    MANUAL_CONTROL_SWITCH,
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
    MODBUS_BATTERY_POWER_LIMIT_ITEMS,
    MODBUS_BATTERY_REALTIME_ITEMS,
    SOLAR_CHARGING_SWITCH,
    WRITE_ONLY_REGISTERS,
)
from .items import ModbusItem, SAXItem

_LOGGER = logging.getLogger(__name__)


def get_unique_id_for_item(
    hass: HomeAssistant,
    config_entry_id: str,
    item_name: str,
) -> str | None:
    """Generate unique ID for an entity from device name and item name.

    This function constructs entity unique IDs following the pattern:
    {device_name_normalized}_{item_name_without_sax_prefix}

    Args:
        hass: Home Assistant instance for device registry access
        config_entry_id: Config entry ID to find associated device
        item_name: Item name (e.g., "sax_max_discharge")

    Returns:
        Unique ID string (e.g., "sax_cluster_max_discharge") or None if device not found

    Security:
        OWASP A05: Validates inputs to prevent injection attacks

    Performance:
        Single device registry lookup, efficient string operations

    Example:
        >>> get_unique_id_for_item(hass, entry_id, "sax_max_discharge")
        "sax_cluster_max_discharge"
    """
    # Validate input
    if not item_name:
        _LOGGER.error("Item name cannot be empty")
        return None

    # Get device registry
    dev_reg = dr.async_get(hass)

    # Find device associated with this config entry
    # Look for device with matching config_entry_id in the SAX Battery domain
    device = None
    for dev in dev_reg.devices.values():
        if config_entry_id in dev.config_entries and any(
            domain == DOMAIN for domain, _ in dev.identifiers
        ):
            device = dev
            break

    if not device:
        _LOGGER.error(
            "Could not find device for config entry %s in device registry",
            config_entry_id,
        )
        return None

    # Extract device name and normalize it
    # Convert to lowercase and replace spaces with underscores
    device_name_normalized: str = "unknown_device"
    if isinstance(device.name, str):
        device_name_normalized = device.name.lower().replace(" ", "_")
    else:
        _LOGGER.warning(
            "Device name is not a string: %s. Using 'unknown_device' as fallback.",
            device.name,
        )

    # Remove "sax_" prefix from item name if present
    item_name_part: str = item_name.removeprefix("sax_").lower()

    # Construct unique ID
    unique_id = f"{device_name_normalized}_{item_name_part}"

    _LOGGER.debug(
        "Generated unique_id '%s' from device '%s' and item '%s'",
        unique_id,
        device.name,
        item_name,
    )

    return unique_id


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
        master_battery_id = config_entry.data.get(CONF_MASTER_BATTERY, "battery_a")
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


def should_enable_entity_by_default(
    item: ModbusItem | SAXItem,
    config_entry: ConfigEntry,
) -> bool:
    """Determine if entity should be enabled by default in entity registry.

    This controls the entity's visibility in the UI. Entities that are disabled
    by default can still be enabled manually by users through the UI.

    Args:
        item: ModbusItem or SAXItem to check
        config_entry: Configuration entry with feature flags

    Returns:
        True if entity should be enabled by default, False otherwise

    Security:
        OWASP A05: Feature-gated entities are disabled until explicitly enabled

    Performance:
        Simple boolean checks with efficient set lookups
    """

    enable_power_control: bool = config_entry.data.get(CONF_PILOT_FROM_HA, False)
    enable_power_limits: bool = config_entry.data.get(CONF_LIMIT_POWER, False)

    # Handle SAXItem control switches - enabled when pilot mode is active
    if isinstance(item, SAXItem):
        if item.name in (SOLAR_CHARGING_SWITCH, MANUAL_CONTROL_SWITCH):
            _LOGGER.debug(
                "Checking SAXItem control switch %s, pilot_from_ha=%s",
                item.name,
                enable_power_control,
            )
            return enable_power_control

        # For other SAXItems, respect the item's enabled_by_default attribute
        return getattr(item, "enabled_by_default", True)

    # Handle ModbusItem write-only registers
    if (
        isinstance(item, ModbusItem)
        and hasattr(item, "address")
        and item.address in WRITE_ONLY_REGISTERS
    ):
        # Build set of pilot control register addresses for efficient lookup
        pilot_control_addresses = {
            item.address for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
        }

        # Build set of power limit register addresses for efficient lookup
        power_limit_addresses = {
            item.address for item in MODBUS_BATTERY_POWER_LIMIT_ITEMS
        }

        # Pilot control registers require pilot_from_ha feature flag
        if item.address in pilot_control_addresses:
            _LOGGER.info(
                "Checking pilot control register %d, pilot_from_ha=%s",
                item.address,
                enable_power_control,
            )
            return enable_power_control

        # Power limit registers require limit_power feature flag
        if item.address in power_limit_addresses:
            _LOGGER.info(
                "Checking power limit register %d, limit_power=%s",
                item.address,
                enable_power_limits,
            )
            return enable_power_limits

    # For all other entities, respect the item's enabled_by_default attribute
    return getattr(item, "enabled_by_default", True)


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
        pilot_from_ha=bool(config_data.get(CONF_PILOT_FROM_HA, False)),
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

    pilot_from_ha: bool = False
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

        # Pilot control registers require both pilot_from_ha AND master battery
        if self.pilot_from_ha and self.is_master_battery:
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
