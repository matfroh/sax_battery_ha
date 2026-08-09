"""Diagnostics support for SAX Battery integration.

Provides centralized access to integration health, performance metrics,
and troubleshooting data via the Home Assistant diagnostics platform.

Security:
    OWASP A02: Redacts sensitive network configuration (host IPs)
    OWASP A05: Exposes only aggregated metrics, no credentials or tokens
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_BATTERIES, CONF_BATTERY_HOST, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Keys to redact from config entry data (OWASP A02)
TO_REDACT = {
    CONF_BATTERY_HOST,
    "battery_a_host",
    "battery_b_host",
    "battery_c_host",
}

# Keys to redact from nested battery configurations
BATTERY_KEYS_TO_REDACT = {
    CONF_BATTERY_HOST,
    "host",
}


def _redact_battery_config(data: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive data from nested battery configurations.

    Args:
        data: Raw config entry data

    Returns:
        Data with nested battery host IPs redacted

    Security:
        OWASP A02: Ensures nested structures are also redacted
    """
    redacted = dict(async_redact_data(data, TO_REDACT))

    # Redact hosts inside nested batteries dict
    if CONF_BATTERIES in redacted and isinstance(redacted[CONF_BATTERIES], dict):
        redacted_batteries = {}
        for battery_id, battery_config in redacted[CONF_BATTERIES].items():
            if isinstance(battery_config, dict):
                redacted_batteries[battery_id] = dict(
                    async_redact_data(battery_config, BATTERY_KEYS_TO_REDACT)
                )
            else:
                redacted_batteries[battery_id] = battery_config
        redacted[CONF_BATTERIES] = redacted_batteries

    return redacted


def _get_coordinator_diagnostics(coordinator: Any) -> dict[str, Any]:
    """Collect diagnostics from a single coordinator.

    Args:
        coordinator: SAXBatteryCoordinator instance

    Returns:
        Dictionary with coordinator health and performance data

    Security:
        OWASP A05: Handles missing attributes gracefully
    """
    protocol_mode = getattr(coordinator, "protocol_mode", None)
    protocol_mode_value: str | None = None
    if isinstance(protocol_mode, str):
        protocol_mode_value = protocol_mode
    else:
        mode_value = getattr(protocol_mode, "value", None)
        if isinstance(mode_value, str):
            protocol_mode_value = mode_value

    diag: dict[str, Any] = {
        "battery_id": getattr(coordinator, "battery_id", "unknown"),
        "is_master": getattr(coordinator, "is_master", False),
        "last_update_success": getattr(coordinator, "last_update_success", None),
        "update_interval": str(getattr(coordinator, "update_interval", None)),
        "protocol_mode": protocol_mode_value,
        "detected_device_id": getattr(
            coordinator,
            "detected_device_id",
            getattr(coordinator, "detected_device_id", None),
        ),
        "protocol_detection_path": getattr(
            coordinator,
            "protocol_detection_path",
            None,
        ),
        "protocol_detection_reason": getattr(
            coordinator,
            "protocol_detection_reason",
            None,
        ),
    }

    # Last update time
    last_time = getattr(coordinator, "last_update_success_time", None)
    if isinstance(last_time, datetime):
        diag["last_update_success_time"] = last_time.isoformat()
    elif last_time is not None:
        diag["last_update_success_time"] = str(last_time)
    else:
        diag["last_update_success_time"] = None

    # Update counters
    diag["total_updates"] = getattr(coordinator, "_total_updates", 0)
    diag["failed_updates"] = getattr(coordinator, "_failed_updates", 0)

    # Circuit breaker diagnostics
    circuit_breaker = getattr(coordinator, "_circuit_breaker", None)
    if circuit_breaker and hasattr(circuit_breaker, "get_diagnostics"):
        diag["circuit_breaker"] = circuit_breaker.get_diagnostics()

    # Cycle time statistics from CoordinatorStatistics
    statistics = getattr(coordinator, "_statistics", None)
    if statistics and hasattr(statistics, "cycle_time_statistics"):
        diag["cycle_time_statistics"] = statistics.cycle_time_statistics

    # ModbusAPI diagnostics
    modbus_api = getattr(coordinator, "modbus_api", None)
    if modbus_api and hasattr(modbus_api, "get_diagnostics"):
        diag["modbus"] = modbus_api.get_diagnostics()

    # SOC manager diagnostics
    soc_manager = getattr(coordinator, "soc_manager", None)
    if soc_manager and hasattr(soc_manager, "get_diagnostics"):
        diag["soc_manager"] = soc_manager.get_diagnostics()

    data_provider = getattr(coordinator, "data_provider", None)
    if data_provider and hasattr(data_provider, "get_diagnostics"):
        diag["data_provider"] = data_provider.get_diagnostics()

    sunspec_control_refresh = getattr(
        coordinator,
        "_sunspec_control_refresh_diag",
        None,
    )
    if isinstance(sunspec_control_refresh, dict):
        diag["sunspec_control_refresh"] = dict(sunspec_control_refresh)

    return diag


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Collects data from all integration components:
    - Config entry data (redacted)
    - Per-battery coordinator health and performance
    - Circuit breaker state per battery
    - ModbusAPI connection status per battery
    - SOC manager state (master only)
    - Power manager state (if enabled)

    Args:
        hass: Home Assistant instance
        entry: Config entry to diagnose

    Returns:
        Dictionary with complete integration diagnostics

    Security:
        OWASP A02: All sensitive data (host IPs) is redacted
        OWASP A05: Structured error handling per component
    """
    diagnostics: dict[str, Any] = {}

    # 1. Redacted config entry data
    diagnostics["entry_data"] = _redact_battery_config(dict(entry.data))

    # 2. Integration metadata
    diagnostics["integration_info"] = {
        "domain": DOMAIN,
        "entry_id": entry.entry_id,
    }

    # 3. Get integration data from hass.data
    integration_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not integration_data:
        diagnostics["error"] = "Integration data not found in hass.data"
        return diagnostics

    # 4. Per-battery coordinator diagnostics
    coordinators = integration_data.get("coordinators", {})
    batteries_diag: dict[str, Any] = {}

    for battery_id, coordinator in coordinators.items():
        try:
            batteries_diag[battery_id] = _get_coordinator_diagnostics(coordinator)
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Failed to collect diagnostics for battery %s",
                battery_id,
            )
            batteries_diag[battery_id] = {"error": "Failed to collect diagnostics"}

    diagnostics["batteries"] = batteries_diag

    diagnostics["protocol_detection"] = integration_data.get("protocol_detection")

    # 5. Power manager diagnostics (if enabled)
    power_manager = integration_data.get("power_manager")
    if power_manager and hasattr(power_manager, "get_diagnostics"):
        try:
            diagnostics["power_manager"] = power_manager.get_diagnostics()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to collect power manager diagnostics")
            diagnostics["power_manager"] = {
                "error": "Failed to collect diagnostics",
            }
    else:
        diagnostics["power_manager"] = None

    return diagnostics
