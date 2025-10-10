"""SAX Battery integration."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    BATTERY_IDS,
    BATTERY_PHASES,
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_ENABLED,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_BATTERY_PORT,
    CONF_MASTER_BATTERY,
    CONF_PILOT_FROM_HA,
    DEFAULT_PORT,
    DOMAIN,
)
from .coordinator import SAXBatteryCoordinator
from .modbusobject import ModbusAPI
from .models import SAXBatteryData
from .power_manager import PowerManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
]

type SAXBatteryConfigEntry = ConfigEntry[dict[str, SAXBatteryCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: SAXBatteryConfigEntry) -> bool:
    """Set up SAX Battery from a config entry with multi-battery support."""
    try:
        # Initialize SAX Battery Data
        sax_data = SAXBatteryData(hass, entry)

        # Get battery configurations using new constants
        batteries_config = await _get_battery_configurations(entry)
        if not batteries_config:
            raise ConfigEntryNotReady("No valid battery configurations found")  # noqa: TRY301

        # Initialize coordinators for each battery
        coordinators: dict[str, SAXBatteryCoordinator] = {}
        for battery_id, battery_config in batteries_config.items():
            if not battery_config.get(CONF_BATTERY_ENABLED, True):
                _LOGGER.debug("Skipping disabled battery %s", battery_id)
                continue
            coordinator = await _setup_battery_coordinator(
                hass, entry, sax_data, battery_id, battery_config
            )
            coordinators[battery_id] = coordinator

        if not coordinators:
            raise ConfigEntryNotReady("No batteries enabled")  # noqa: TRY301

        # Store coordinators and data BEFORE power manager initialization
        # This prevents KeyError when power manager tries to access hass.data[DOMAIN]
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinators": coordinators,
            "sax_data": sax_data,
            "config": entry.data,
        }

        # Update sax_data with coordinators for cross-battery calculations
        sax_data.coordinators = coordinators

        # Initialize power manager for master battery if enabled
        power_manager_enabled = entry.data.get(CONF_PILOT_FROM_HA, False)
        if power_manager_enabled:
            master_battery_id = sax_data.master_battery_id
            if master_battery_id and master_battery_id in coordinators:
                master_coordinator = coordinators[master_battery_id]
                power_manager = PowerManager(
                    hass=hass,
                    coordinator=master_coordinator,
                    config_entry=entry,
                )

                # Store power manager in integration data (now safe)
                hass.data[DOMAIN][entry.entry_id]["power_manager"] = power_manager

                # Start power manager
                await power_manager.async_start()

                _LOGGER.info(
                    "Power manager initialized for master battery %s",
                    master_battery_id,
                )
            else:
                _LOGGER.warning("Power manager enabled but no master battery found")

        # Log device and entity registry state before platform setup
        await _log_registry_state_before_setup(hass, entry, coordinators, sax_data)

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Log comprehensive setup summary with registry information
        await _log_comprehensive_setup_summary(
            hass, entry, coordinators, dict(entry.data)
        )

        return True  # noqa: TRY300

    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.exception("Failed to setup SAX Battery integration")
        raise ConfigEntryNotReady(f"Unexpected error during setup: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a SAX Battery config entry.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry to unload

    Returns:
        True if unload was successful, False otherwise

    Security:
        OWASP A05: Properly clean up resources to prevent leaks

    Performance:
        Use gather() for parallel connection cleanup of all batteries
    """

    # Check if domain exists in hass.data
    if DOMAIN not in hass.data:
        _LOGGER.debug("Domain %s not in hass.data, nothing to unload", DOMAIN)
        return True

    # Mark integration as unloading to prevent re-initialization
    integration_data = hass.data[DOMAIN].get(entry.entry_id)
    if integration_data:
        integration_data["_unloading"] = True

    # Unload all platforms first
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # OWASP A05: Secure error handling - check if domain exists before accessing
        integration_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

        if integration_data:
            coordinators = integration_data.get("coordinators", {})

            # Stop power manager if it exists
            power_manager = integration_data.get("power_manager")
            if power_manager:
                await power_manager.async_stop()
                _LOGGER.debug("Power manager stopped")

            # Close all Modbus connections in parallel (performance optimization)
            if coordinators:
                close_tasks = [
                    coordinator.modbus_api.close()
                    for coordinator in coordinators.values()
                    if hasattr(coordinator, "modbus_api")
                    and coordinator.modbus_api is not None
                ]

                if close_tasks:
                    results = await asyncio.gather(*close_tasks, return_exceptions=True)
                    failed_closes = sum(
                        1 for result in results if isinstance(result, Exception)
                    )
                    if failed_closes:
                        _LOGGER.warning(
                            "Failed to close %d Modbus connections", failed_closes
                        )

            _LOGGER.info("SAX Battery integration unloaded successfully")

    return unload_ok


async def _log_registry_state_before_setup(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinators: dict[str, SAXBatteryCoordinator],
    sax_data: SAXBatteryData,
) -> None:
    """Log device and entity registry state before platform setup.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        coordinators: Dictionary of coordinators
        sax_data: SAX Battery data manager

    Security: Only logs non-sensitive registry information
    Performance: Efficient registry queries with proper filtering
    """
    try:
        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)

        # Check for existing SAX Battery devices
        existing_devices = [
            device
            for device in device_registry.devices.values()
            if any(identifier[0] == "sax_battery" for identifier in device.identifiers)
        ]

        # Check for existing SAX Battery entities
        existing_entities = [
            entity
            for entity in entity_registry.entities.values()
            if entity.platform == DOMAIN
        ]

        _LOGGER.debug(
            "Registry state before setup: %d existing SAX Battery devices, %d existing entities",
            len(existing_devices),
            len(existing_entities),
        )

        # Log device details
        for device in existing_devices:
            device_name = next(
                (
                    identifier[1]
                    for identifier in device.identifiers
                    if identifier[0] == "sax_battery"
                ),
                "unknown",
            )
            _LOGGER.debug(
                "Existing device: %s (id=%s, name=%s, disabled=%s)",
                device_name,
                device.id,
                device.name,
                device.disabled,
            )

        # Log entity summary by platform
        entity_summary: dict[str, int] = {}
        for entity in existing_entities:
            platform = entity.domain
            entity_summary[platform] = entity_summary.get(platform, 0) + 1

        for platform, count in entity_summary.items():
            _LOGGER.debug("Existing %s entities: %d", platform, count)

    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Error logging registry state: %s", err)


async def _log_comprehensive_setup_summary(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinators: dict[str, SAXBatteryCoordinator],
    config_data: dict[str, Any],
) -> None:
    """Log comprehensive setup summary with device and entity registry information.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        coordinators: Dictionary of initialized coordinators
        config_data: Configuration data from entry

    Security: OWASP A05 - No sensitive data in logs
    Performance: Efficient registry queries and data aggregation
    """
    try:
        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)

        battery_count = len(coordinators)

        # Find master batteries
        master_batteries = [
            battery_id
            for battery_id, coordinator in coordinators.items()
            if coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False)
        ]

        # Get battery phase mappings
        phase_mappings = [
            f"{battery_id}→{coordinator.battery_config.get(CONF_BATTERY_PHASE, 'L1')}"
            for battery_id, coordinator in coordinators.items()
        ]

        # Get feature flags
        pilot_from_ha = config_data.get("pilot_from_ha", False)
        limit_power = config_data.get("limit_power", False)
        enable_solar = config_data.get("enable_solar_charging", False)

        # Query device registry for SAX Battery devices
        sax_devices = [
            device
            for device in device_registry.devices.values()
            if any(identifier[0] == "sax_battery" for identifier in device.identifiers)
        ]

        # Query entity registry for SAX Battery entities
        sax_entities = [
            entity
            for entity in entity_registry.entities.values()
            if entity.platform == DOMAIN
        ]

        # Categorize devices by type
        device_summary = {"battery": 0, "smartmeter": 0, "cluster": 0, "unknown": 0}
        for device in sax_devices:
            device_identifier = next(
                (
                    identifier[1]
                    for identifier in device.identifiers
                    if identifier[0] == "sax_battery"
                ),
                "unknown",
            )

            if device_identifier.startswith("battery_"):
                device_summary["battery"] += 1
            elif device_identifier == "sax_smartmeter":
                device_summary["smartmeter"] += 1
            elif device_identifier == "sax_battery_cluster":
                device_summary["cluster"] += 1
            else:
                device_summary["unknown"] += 1

        # Categorize entities by platform and enabled state
        entity_summary = {}
        for entity in sax_entities:
            platform = entity.domain
            if platform not in entity_summary:
                entity_summary[platform] = {"enabled": 0, "disabled": 0, "total": 0}

            if entity.disabled:
                entity_summary[platform]["disabled"] += 1
            else:
                entity_summary[platform]["enabled"] += 1
            entity_summary[platform]["total"] += 1

        # Log main setup summary
        _LOGGER.info(
            "SAX Battery setup complete - %d batteries [%s], master: %s, "
            "devices: %d battery + %d smartmeter + %d cluster, "
            "features: pilot=%s, limits=%s, solar=%s",
            battery_count,
            ", ".join(phase_mappings),
            master_batteries[0] if master_batteries else "none",
            device_summary["battery"],
            device_summary["smartmeter"],
            device_summary["cluster"],
            pilot_from_ha,
            limit_power,
            enable_solar,
        )

        # Log detailed entity summary by platform
        for platform, stats in entity_summary.items():
            _LOGGER.info(
                "SAX Battery %s entities: %d enabled, %d disabled (%d total)",
                platform,
                stats["enabled"],
                stats["disabled"],
                stats["total"],
            )

        # Log device details with unique IDs
        _LOGGER.debug("SAX Battery devices registered:")
        for device in sax_devices:
            device_identifier = next(
                (
                    identifier[1]
                    for identifier in device.identifiers
                    if identifier[0] == "sax_battery"
                ),
                "unknown",
            )
            _LOGGER.debug(
                "  Device: %s (name=%s, id=%s, disabled=%s, manufacturer=%s)",
                device_identifier,
                device.name,
                device.id,
                device.disabled,
                device.manufacturer,
            )

        # Log detailed entity information for each platform
        for platform in ["sensor", "number", "switch"]:
            platform_entities = [e for e in sax_entities if e.domain == platform]
            if platform_entities:
                enabled_entities = [e for e in platform_entities if not e.disabled]
                disabled_entities = [e for e in platform_entities if e.disabled]

                _LOGGER.debug(
                    "SAX Battery %s entities (%d enabled, %d disabled):",
                    platform,
                    len(enabled_entities),
                    len(disabled_entities),
                )

                # Log enabled entities
                for entity in enabled_entities:
                    _LOGGER.debug(
                        "  ✓ %s: %s (unique_id=%s, device_id=%s)",
                        platform,
                        entity.entity_id,
                        entity.unique_id,
                        entity.device_id,
                    )

                # Log disabled entities (limited to avoid spam)
                if disabled_entities:
                    shown_disabled = disabled_entities[:5]  # Limit to first 5
                    for entity in shown_disabled:
                        _LOGGER.debug(
                            "  ✗ %s: %s (unique_id=%s, disabled_by=%s)",
                            platform,
                            entity.entity_id,
                            entity.unique_id,
                            entity.disabled_by,
                        )

                    if len(disabled_entities) > 5:
                        _LOGGER.debug(
                            "  ... and %d more disabled %s entities",
                            len(disabled_entities) - 5,
                            platform,
                        )

        # Log coordinator-specific information
        _LOGGER.debug("Battery coordinator details:")
        for battery_id, coordinator in coordinators.items():
            # Get entity counts for this battery
            battery_entities = [
                e for e in sax_entities if e.unique_id and battery_id in e.unique_id
            ]
            enabled_count = sum(1 for e in battery_entities if not e.disabled)

            _LOGGER.debug(
                "  %s: phase=%s, master=%s, entities=%d enabled/%d total, update_interval=%s",
                battery_id,
                coordinator.battery_config.get(CONF_BATTERY_PHASE, "L1"),
                coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False),
                enabled_count,
                len(battery_entities),
                coordinator.update_interval,
            )

    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Error logging comprehensive setup summary: %s", err)
        # Fallback to basic summary
        _log_setup_summary(coordinators, config_data)


async def _get_battery_configurations(entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    """Get battery configurations using new constants consistently.

    Args:
        entry: Config entry containing battery configuration data

    Returns:
        dict: Validated battery configurations indexed by battery_id

    Security:
        Validates all configuration data to prevent injection and misconfiguration

    """
    batteries_config: dict[str, dict[str, Any]] = {}

    # Check for new nested battery configuration format
    if CONF_BATTERIES in entry.data:
        # Use new constants consistently
        for battery_id, config in entry.data[CONF_BATTERIES].items():
            batteries_config[battery_id] = {
                CONF_BATTERY_HOST: config.get("host", config.get(CONF_BATTERY_HOST)),
                CONF_BATTERY_PORT: config.get(
                    "port", config.get(CONF_BATTERY_PORT, DEFAULT_PORT)
                ),
                CONF_BATTERY_ENABLED: config.get(
                    "enabled", config.get(CONF_BATTERY_ENABLED, True)
                ),
                CONF_BATTERY_PHASE: config.get(
                    "phase",
                    config.get(
                        CONF_BATTERY_PHASE, BATTERY_PHASES.get(battery_id, "L1")
                    ),
                ),
                CONF_BATTERY_IS_MASTER: config.get(
                    "is_master", config.get(CONF_BATTERY_IS_MASTER, False)
                ),
            }
        _LOGGER.debug("Using nested battery configuration format")
    else:
        # Legacy conversion using new constants
        battery_count = entry.data.get(CONF_BATTERY_COUNT, 1)
        master_battery = entry.data.get(CONF_MASTER_BATTERY, "battery_a")

        for i in range(1, int(battery_count) + 1):
            battery_id = BATTERY_IDS[i - 1]  # Use consistent battery IDs

            host = entry.data.get(f"{battery_id}_host")
            port = entry.data.get(f"{battery_id}_port", DEFAULT_PORT)

            if host:
                batteries_config[battery_id] = {
                    CONF_BATTERY_HOST: host.strip(),
                    CONF_BATTERY_PORT: int(port),
                    CONF_BATTERY_ENABLED: True,
                    CONF_BATTERY_PHASE: BATTERY_PHASES[battery_id],
                    CONF_BATTERY_IS_MASTER: (battery_id == master_battery),
                }

    return {k: v for k, v in batteries_config.items() if _validate_battery_config(k, v)}


async def _setup_battery_coordinator(
    hass: HomeAssistant,
    entry: ConfigEntry,
    sax_data: SAXBatteryData,
    battery_id: str,
    battery_config: dict[str, Any],
) -> SAXBatteryCoordinator:
    """Set up coordinator using new constants.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        sax_data: SAX Battery data manager
        battery_id: Battery identifier (battery_a, battery_b, battery_c)
        battery_config: Battery-specific configuration

    Returns:
        SAXBatteryCoordinator: Initialized coordinator

    Raises:
        ConfigEntryNotReady: If connection or initialization fails

    Security:
        Validates all network configuration before attempting connections

    """
    host = battery_config[CONF_BATTERY_HOST]
    port = battery_config[CONF_BATTERY_PORT]
    is_master = battery_config.get(CONF_BATTERY_IS_MASTER, False)
    phase = battery_config.get(CONF_BATTERY_PHASE, "L1")

    # OWASP A05: Security Misconfiguration - Validate network parameters
    if not isinstance(host, str) or not host.strip():
        raise ConfigEntryNotReady(f"Invalid host configuration for {battery_id}")

    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ConfigEntryNotReady(f"Invalid port configuration for {battery_id}")

    _LOGGER.debug(
        "Setting up battery %s (%s, %s) at %s:%s",
        battery_id,
        "master" if is_master else "slave",
        phase,
        host,
        port,
    )

    # Initialize Modbus API
    modbus_api = ModbusAPI(host=host, port=port, battery_id=battery_id)

    # Test connection
    if not await modbus_api.connect():
        raise ConfigEntryNotReady(f"Could not connect to {battery_id} at {host}:{port}")

    # Create coordinator
    coordinator = SAXBatteryCoordinator(
        hass=hass,
        battery_id=battery_id,
        sax_data=sax_data,
        modbus_api=modbus_api,
        config_entry=entry,
        battery_config=battery_config,
    )

    # Initial data fetch
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        # Ensure connection is closed on failure
        await modbus_api.close()
        raise ConfigEntryNotReady(
            f"Initial data fetch failed for {battery_id}: {err}"
        ) from err

    return coordinator


def _validate_battery_config(battery_id: str, battery_config: dict[str, Any]) -> bool:
    """Validate battery configuration for security and consistency.

    Args:
        battery_id: Battery identifier to validate
        battery_config: Configuration dictionary to validate

    Returns:
        bool: True if configuration is valid

    Security:
        OWASP A03: Injection prevention through input validation
        OWASP A05: Security misconfiguration prevention

    """
    # Validate battery ID is in allowed list
    if battery_id not in BATTERY_IDS:
        _LOGGER.error(
            "Invalid battery ID %s, must be one of %s", battery_id, BATTERY_IDS
        )
        return False

    # Validate required configuration keys exist
    required_keys = [CONF_BATTERY_HOST, CONF_BATTERY_PORT]
    for key in required_keys:
        if key not in battery_config:
            _LOGGER.error(
                "Missing required configuration key %s for battery %s", key, battery_id
            )
            return False

    # Validate host format (basic IP/hostname validation)
    host = battery_config.get(CONF_BATTERY_HOST)
    if not isinstance(host, str) or not host.strip():
        _LOGGER.error("Invalid host format for battery %s: %s", battery_id, host)
        return False

    # OWASP A03: Input validation to prevent injection attacks
    if not _validate_host(host=host.strip()):
        _LOGGER.error(
            "Host format validation failed for battery %s: %s", battery_id, host
        )
        return False

    # Validate port range with type safety
    port = battery_config.get(CONF_BATTERY_PORT)
    if port is None:
        _LOGGER.error("Missing port configuration for battery %s", battery_id)
        return False

    try:
        # OWASP A03: Input validation - ensure port is convertible to int
        if isinstance(port, (str, int, float)):
            port_int = int(port)
        else:
            _LOGGER.error(
                "Invalid port type %s for battery %s: %s",
                type(port).__name__,
                battery_id,
                port,
            )
            return False

        if not (1 <= port_int <= 65535):
            _LOGGER.error(
                "Port %s out of valid range [1-65535] for battery %s",
                port_int,
                battery_id,
            )
            return False
    except (ValueError, TypeError, OverflowError) as err:
        _LOGGER.error(
            "Invalid port format for battery %s: %s (%s)", battery_id, port, err
        )
        return False

    # Validate phase assignment
    phase = battery_config.get(CONF_BATTERY_PHASE, "L1")
    valid_phases = ["L1", "L2", "L3"]
    if phase not in valid_phases:
        _LOGGER.error(
            "Invalid phase %s for battery %s, must be one of %s",
            phase,
            battery_id,
            valid_phases,
        )
        return False

    # Validate boolean fields
    for bool_key in [CONF_BATTERY_ENABLED, CONF_BATTERY_IS_MASTER]:
        if bool_key in battery_config and not isinstance(
            battery_config[bool_key], bool
        ):
            _LOGGER.error(
                "Configuration key %s must be boolean for battery %s",
                bool_key,
                battery_id,
            )
            return False

    return True


def _validate_host(host: str) -> bool:
    """Validate host format for security.

    Args:
        host: Hostname or IP address to validate

    Returns:
        bool: True if host format is valid

    Security:
        Prevents malformed hosts that could cause issues in network operations

    """
    if not host or len(host) > 253:
        return False

    # Validate IPv4 address with proper octet range checking
    ipv4_parts = host.split(".")
    if len(ipv4_parts) == 4:
        try:
            # Security: Validate each octet is in valid range 0-255
            for part in ipv4_parts:
                # Ensure part is not empty and contains only digits
                if not part or not part.isdigit():
                    # Not a valid IPv4, try hostname validation below
                    break
                octet = int(part)
                if not (0 <= octet <= 255):
                    return False
            else:
                # All parts validated successfully as IPv4
                return True
        except (ValueError, TypeError):
            # Not a valid IPv4, check if hostname
            pass
    elif len(ipv4_parts) != 1 and ipv4_parts[1].isdigit():
        return False

    # Allow hostnames and IPv4 addresses only (no IPv6 for simplicity)
    host_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$|^((([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9]))$"

    return bool(re.match(host_pattern, host))


def _log_setup_summary(
    coordinators: dict[str, SAXBatteryCoordinator], config_data: dict[str, Any]
) -> None:
    """Log successful setup summary without exposing sensitive information.

    Args:
        coordinators: Dictionary of initialized coordinators
        config_data: Configuration data from entry

    Security:
        OWASP A05: Security misconfiguration - No sensitive data in logs
        Only logs non-sensitive configuration summary

    """
    battery_count = len(coordinators)

    # Find master batteries (should be only one, but handle multiple for robustness)
    master_batteries = [
        battery_id
        for battery_id, coordinator in coordinators.items()
        if coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False)
    ]

    # Get battery phase mappings for summary
    phase_mappings = [
        f"{battery_id}→{coordinator.battery_config.get(CONF_BATTERY_PHASE, 'L1')}"
        for battery_id, coordinator in coordinators.items()
    ]

    # Get feature flags (non-sensitive configuration)
    pilot_from_ha = config_data.get("pilot_from_ha", False)
    limit_power = config_data.get("limit_power", False)
    enable_solar = config_data.get("enable_solar_charging", False)

    _LOGGER.info(
        "SAX Battery integration setup complete - %d batteries configured [%s], "
        "master: %s, features: pilot_control=%s, power_limits=%s, solar_charging=%s",
        battery_count,
        ", ".join(phase_mappings),
        master_batteries[0] if master_batteries else "none",
        pilot_from_ha,
        limit_power,
        enable_solar,
    )

    # Additional debug info for troubleshooting (no sensitive data)
    _LOGGER.debug(
        "Battery coordinator summary: %s",
        {
            battery_id: {
                "phase": coordinator.battery_config.get(CONF_BATTERY_PHASE, "L1"),
                "is_master": coordinator.battery_config.get(
                    CONF_BATTERY_IS_MASTER, False
                ),
                "enabled": coordinator.battery_config.get(CONF_BATTERY_ENABLED, True),
            }
            for battery_id, coordinator in coordinators.items()
        },
    )
