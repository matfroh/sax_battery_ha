"""Legacy power manager for SAX Battery integration.

Coordinator-centric power management using SAX_POWER_SETPOINT (register 41)
and SAX_POWER_SETPOINT_FACTOR (register 42) via coordinator.async_write_power_control_value()
for atomic Modbus writes.

Security:
    OWASP A05: Validates all sensor inputs and power values
    OWASP A01: Only master battery can create power manager

Performance:
    Uses coordinator update cycle for periodic power adjustments
    Direct coordinator writes instead of HA service calls

SunSpec mode does not use this manager. Its Model 123 control registers provide
device-side manual setpoint and Smart Meter zero-balancing modes directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_BALANCED_LOADING,
    CONF_ENABLE_GRID_CHARGING,
    CONF_ENABLE_PV_CHARGING,
    CONF_GRID_POWER_MODE,
    CONF_MIN_SOC,
    CONF_POWER_SENSOR,
    CONF_SM_CONNECTED,
    DEFAULT_GRID_POWER_MODE,
    DEFAULT_MIN_SOC,
    DOMAIN,
    GRID_CHARGING_MODE,
    GRID_POWER_MODE_CHARGE,
    GRID_POWER_MODE_DISCHARGE,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    POWER_SETPOINT_DEADBAND_W,
    POWER_SETPOINT_REFRESH_SECONDS,
    PV_CHARGING_MODE,
    SAX_AC_POWER_TOTAL,
    SAX_CHARGE_FROM_PV_SWITCH,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_MAX_SOC_CHARGING,
    SAX_POWER_SETPOINT,
    SAX_POWER_SM,
)
from .coordinator import BATTERY_POLL_INTERVAL, SAXBatteryCoordinator
from .items import ModbusItem
from .power_control_strategy import SunSpecPowerControlStrategy
from .protocol_mode import ProtocolMode

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PowerManagerState:
    """Power manager state tracking.

    Performance: Uses slots for memory efficiency
    """

    mode: str
    target_power: float
    last_update: datetime
    pv_charging_enabled: bool = False
    grid_charging_enabled: bool = False
    grid_power_mode: str = DEFAULT_GRID_POWER_MODE
    # State persistence for mode transitions
    previous_pv_state: bool = False  # Store PV state before grid charging
    previous_grid_state: bool = False  # noqa: DC06 # Store grid state before PV charging


class PowerManager:
    """Legacy-only coordinator-centric power manager for SAX Battery systems.

    This class is irrelevant to SunSpec mode and is not started for it. SunSpec
    Model 123 uses readable control registers and performs Smart Meter balancing
    in the battery rather than this software loop.

    Uses coordinator.async_write_power_control_value() for atomic Modbus writes
    to SAX_POWER_SETPOINT (register 41) and SAX_POWER_SETPOINT_FACTOR (register 42).

    Write flow:
        PowerManager.update_power_setpoint()
        -> coordinator.async_write_power_control_value(power_item, power, factor)
        -> modbus_api.write_power_setpoint(value, power_factor, modbus_item)
        -> register 41 (power) + register 42 (factor) atomic write
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SAXBatteryCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize power manager.

        Args:
            hass: Home Assistant instance
            coordinator: Master battery coordinator
            config_entry: Configuration entry

        Security:
            OWASP A01: Validates coordinator is for master battery
        """
        self.hass = hass
        self.coordinator = coordinator
        self.config_entry = config_entry
        self.battery_count = len(coordinator.sax_data.coordinators)

        # UI display limits (cluster-wide totals for entity native_max_value).
        # These are for UI sliders/boxes only and must NEVER be written to registers.
        # The master distributes register values WITHOUT modification to ALL batteries,
        # so register writes must use per-battery limits (LIMIT_MAX_*_PER_BATTERY).
        self.ui_max_discharge_power = (
            self.battery_count * LIMIT_MAX_DISCHARGE_PER_BATTERY
        )
        self.ui_max_charge_power = self.battery_count * LIMIT_MAX_CHARGE_PER_BATTERY

        # State tracking
        self._state = PowerManagerState(
            mode=PV_CHARGING_MODE,
            target_power=0.0,
            last_update=datetime.now(),
        )

        # Tracking for event listeners
        self._remove_interval_update: Callable[[], None] | None = None
        self._remove_config_update: Callable[[], None] | None = None
        self._running = False
        self._last_power_write_monotonic: float | None = None
        self._power_write_lock = asyncio.Lock()
        self._stop_complete = asyncio.Event()
        self._stop_complete.set()
        self._power_generation = 0
        self._update_generation: ContextVar[int | None] = ContextVar(
            "power_update_generation", default=None
        )

        # Configuration values
        self._update_config_values()

    def _get_switch_state(self, switch_name: str) -> bool:
        """Get current state of a switch entity.

        Args:
            switch_name: Entity key (e.g., SAX_CHARGE_FROM_PV_SWITCH)

        Returns:
            True if switch is on, False otherwise

        Security:
            OWASP A05: Validates entity availability before reading state
        """
        try:
            switch_item = self.coordinator.sax_data.get_item_by_name(switch_name)
            if not switch_item:
                _LOGGER.debug("Switch item %s not found", switch_name)
                return False

            entity_id = self.coordinator.sax_data.get_entity_id_for_item(
                switch_item,
                battery_id=None,  # Cluster-wide entity
            )

            if not entity_id:
                _LOGGER.debug("Entity ID not found for %s", switch_name)
                return False

            state = self.hass.states.get(entity_id)
            if not state or state.state in ("unknown", "unavailable"):
                _LOGGER.debug("Switch %s state unavailable", entity_id)
                return False

            return state.state == "on"  # noqa: TRY300

        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Could not get switch state for %s: %s", switch_name, err)
            return False

    def _update_config_values(self) -> None:
        """Update configuration values from entry data.

        Uses coordinator cycle for polling instead of custom interval.
        CONF_POWER_SENSOR represents the power sensor for balanced charging.
        Reads SAX_CHARGE_FROM_PV_SWITCH entity state for runtime control.
        """
        self.pv_power_sensor = self.config_entry.data.get(CONF_POWER_SENSOR)

        # Smart meter and balanced loading configuration
        self.sm_connected = self.config_entry.data.get(CONF_SM_CONNECTED, True)
        self.balanced_loading = self.config_entry.data.get(CONF_BALANCED_LOADING, False)

        # The switch entity is unavailable during config reloads, so once running
        # the manager's own state is authoritative.
        pv_enabled = (
            self._state.pv_charging_enabled
            if self._running
            else bool(
                self.config_entry.data.get(
                    CONF_ENABLE_PV_CHARGING,
                    self._get_switch_state(SAX_CHARGE_FROM_PV_SWITCH),
                )
            )
        )
        grid_enabled = bool(
            self.config_entry.data.get(CONF_ENABLE_GRID_CHARGING, False)
        )

        # Security: Enforce mutual exclusion at startup
        if pv_enabled and grid_enabled:
            _LOGGER.warning(
                "Both PV charging and grid control are enabled - "
                "defaulting to PV charging mode"
            )
            pv_enabled = True
            grid_enabled = False

        self._state.pv_charging_enabled = pv_enabled
        self._state.grid_charging_enabled = grid_enabled

        grid_power_mode = self.config_entry.data.get(
            CONF_GRID_POWER_MODE, DEFAULT_GRID_POWER_MODE
        )
        self._state.grid_power_mode = (
            grid_power_mode
            if grid_power_mode in (GRID_POWER_MODE_CHARGE, GRID_POWER_MODE_DISCHARGE)
            else DEFAULT_GRID_POWER_MODE
        )
        _LOGGER.info(
            "Power manager config updated: PV=%s, grid=%s, pv_sensor=%s, "
            "sm_connected=%s, balanced_loading=%s",
            pv_enabled,
            grid_enabled,
            self.pv_power_sensor,
            self.sm_connected,
            self.balanced_loading,
        )

    async def async_start(self) -> None:
        """Start the power manager service.

        Uses coordinator's update_interval.
        Security: Only starts if not already running
        """
        if self._running:
            _LOGGER.warning("Power manager already running")
            return

        self._running = True

        # Set up periodic updates using coordinator's update interval
        # Use 60 seconds as fallback if coordinator interval is not set
        update_interval: timedelta = (
            self.coordinator.update_interval
            if self.coordinator.update_interval is not None
            else timedelta(seconds=60)
        )

        self._remove_interval_update = async_track_time_interval(
            self.hass,
            self._async_update_power,
            update_interval,
        )

        # Add listener for config entry updates
        self._remove_config_update = self.config_entry.add_update_listener(
            self._async_config_updated
        )

        # Do initial update
        await self._async_update_power(None)

        _LOGGER.info(
            "Power manager started with coordinator cycle (%ss)",
            update_interval.total_seconds(),
        )

    async def async_stop(self) -> None:
        """Stop the power manager service.

        Security: Proper resource cleanup (OWASP A05)
        """
        if not self._running:
            return

        if self._remove_interval_update is not None:
            self._remove_interval_update()
            self._remove_interval_update = None

        if self._remove_config_update is not None:
            self._remove_config_update()
            self._remove_config_update = None

        self._running = False
        _LOGGER.info("Power manager stopped")

    async def _async_config_updated(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Handle config entry updates.

        Args:
            hass: Home Assistant instance
            entry: Updated config entry
        """
        self.config_entry = entry
        self._update_config_values()
        await self._async_update_power(None)
        _LOGGER.info("Power manager configuration updated")

    async def _async_update_power(self, now: Any = None) -> None:
        """Run a power update associated with the current control generation."""
        if not self._stop_complete.is_set():
            return
        token = self._update_generation.set(self._power_generation)
        try:
            await self._async_update_power_for_mode(now)
        finally:
            self._update_generation.reset(token)

    async def _async_update_power_for_mode(self, now: Any = None) -> None:
        """Update power via coordinator based on current mode.

        Power source selection:
        - sm_connected=True: Use SAX_POWER_SM from coordinator
        - sm_connected=False, balanced_loading=True: Check PV threshold,
          use balanced loading if sufficient PV, otherwise charge from grid
        - sm_connected=False, balanced_loading=False: Standard PV/grid modes

        Args:
            now: Current time (from time interval trigger)

        Security:
            OWASP A05: Validates sensor states before processing
        """
        try:
            # Check current mode (priority order: grid > pv)
            if self._state.grid_charging_enabled:
                await self._update_grid_load_mode()
                return

            if self._is_sunspec:
                # The battery balances itself (Model 123 Mode 0) in PV mode
                return

            if self._state.pv_charging_enabled:
                # Smart meter connected: use SAX smart meter data directly
                if self.sm_connected:
                    _LOGGER.debug(
                        "Smart meter connected: using SAX smart meter for power balancing"
                    )
                    await self._update_sm_balanced_power()
                    return

                # SM not connected but balanced loading enabled:
                # Use grid power sign to decide mode
                # Negative grid power = production/export to grid (surplus available, typically solar PV)
                # Positive grid power = consumption/import from grid (no surplus)
                if self.balanced_loading:
                    grid_power = await self._get_grid_power()
                    if grid_power is not None and grid_power < 0:
                        _LOGGER.debug(
                            "Balanced loading: grid production %.0fW (surplus available, "
                            "typically solar PV), using PV charging mode",
                            grid_power,
                        )
                        await self._update_pv_charging_power()
                    else:
                        grid_display = (
                            f"{grid_power:.0f}" if grid_power is not None else "N/A"
                        )
                        _LOGGER.debug(
                            "Balanced loading: grid consumption %sW (no surplus), "
                            "standby",
                            grid_display,
                        )
                        await self._update_grid_balance_mode()
                    return

                # Standard PV charging (no SM, no balanced loading)
                await self._update_pv_charging_power()
            else:
                _LOGGER.debug("No active power management mode")

        except (OSError, ValueError, TypeError) as err:
            _LOGGER.error("Error updating power: %s", err)

    @property
    def _is_sunspec(self) -> bool:
        """Return whether the master coordinator uses SunSpec Model 123 controls."""
        return (
            getattr(self.coordinator, "protocol_mode", ProtocolMode.LEGACY)
            == ProtocolMode.SUNSPEC
        )

    async def _update_grid_load_mode(self) -> None:
        """Charge from or discharge to the grid at the configured power limit.

        Charging uses number.sax_bms_max_charge until the max SOC for charging is
        reached; discharging uses number.sax_bms_max_discharge until the minimum
        SOC is reached. At either SOC limit grid mode is switched off and the
        battery falls back to balanced operation.
        """
        combined_soc = (
            self.coordinator.data.get(SAX_COMBINED_SOC)
            if self.coordinator.data
            else None
        )
        if combined_soc is None:
            _LOGGER.warning("Combined SOC not available, skipping grid power update")
            return

        if self._state.grid_power_mode == GRID_POWER_MODE_DISCHARGE:
            if combined_soc <= await self._get_min_soc_limit():
                await self._async_stop_grid_mode(
                    f"SOC {combined_soc:.1f}% reached minimum SOC"
                )
                return
            target_power = await self._get_max_discharge_limit()
        else:
            if combined_soc >= await self._get_max_soc_charging_limit():
                await self._async_stop_grid_mode(
                    f"SOC {combined_soc:.1f}% reached maximum charging SOC"
                )
                return
            target_power = -await self._get_max_charge_limit()

        self._state.mode = GRID_CHARGING_MODE
        await self._async_write_power(target_power)

    async def _async_write_power(
        self, per_battery_power: float, *, force: bool = False
    ) -> bool:
        """Write a per-battery power target using the active protocol."""
        if not self._is_sunspec:
            return await self.update_power_setpoint(per_battery_power, force=force)

        # Model 123 setpoint is relative to the cluster reference power
        await SunSpecPowerControlStrategy(self.coordinator).async_set_power(
            per_battery_power * max(self.battery_count, 1)
        )
        self._state.target_power = per_battery_power
        self._state.last_update = datetime.now()
        return True

    async def _async_stop_grid_mode(self, reason: str) -> None:
        """Leave grid mode because a limit was reached and fall back to balancing."""
        _LOGGER.info("Grid power mode stopped: %s", reason)
        await self.set_grid_control_mode(False)
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                CONF_ENABLE_GRID_CHARGING: False,
                CONF_ENABLE_PV_CHARGING: self._state.pv_charging_enabled,
            },
        )

    async def _async_apply_balanced_fallback(self) -> None:
        """Hand control back to balanced operation after grid mode."""
        if self._is_sunspec:
            await SunSpecPowerControlStrategy(
                self.coordinator
            ).async_set_mode_zero_balance()
        elif self._state.pv_charging_enabled:
            await self._async_update_power(None)
        else:
            await self.update_power_setpoint(0.0)

    async def _update_pv_charging_power(self) -> None:
        """Update setpoint for PV charging mode.

        Uses the formula: New Setpoint = Current Battery Power + Grid Power
        (grid power is positive for import, negative for export; setpoint and
        battery power are positive for discharge). Export therefore charges.
        This ensures grid power goes to zero by adjusting battery charge/discharge.

        Security:
            OWASP A05: Validates PV sensor state and battery power availability

        Performance:
            Direct state machine access with entity registry lookup
        """
        if not self.pv_power_sensor:
            _LOGGER.warning("PV power sensor not configured")
            return

        # Grid power from CONF_POWER_SENSOR: positive = import, negative = export
        pv_state = self.hass.states.get(self.pv_power_sensor)
        if pv_state is None:
            _LOGGER.warning("PV power sensor %s not found", self.pv_power_sensor)
            return

        if pv_state.state in (None, "unknown", "unavailable"):
            _LOGGER.warning(
                "PV power sensor %s state is %s",
                self.pv_power_sensor,
                pv_state.state,
            )
            return

        try:
            pv_power = float(pv_state.state)
        except (ValueError, TypeError) as err:
            _LOGGER.error(
                "Could not convert PV power '%s' to float: %s",
                pv_state.state,
                err,
            )
            return

        # Get current battery power from Home Assistant state machine
        current_battery_power = await self._get_battery_power()

        if current_battery_power is None:
            _LOGGER.warning("Battery power not available, skipping pv charging update")
            return

        # Export (negative grid) lowers the setpoint below the current discharge,
        # which charges the battery
        target_power = current_battery_power + pv_power

        _LOGGER.debug(
            "PV charging calculation: pv=%sW, current_battery=%sW, raw_target=%sW",
            pv_power,
            current_battery_power,
            target_power,
        )

        # Pre-clamp to per-battery hardware limits before constraint enforcement.
        # CRITICAL: The master distributes register values unchanged to all batteries,
        # so the value must never exceed per-battery hardware limits.
        target_power = max(
            -LIMIT_MAX_CHARGE_PER_BATTERY,  # Max charge per battery (negative)
            min(
                LIMIT_MAX_DISCHARGE_PER_BATTERY, target_power
            ),  # Max discharge per battery
        )

        _LOGGER.debug("After power limits: target=%sW", target_power)

        _LOGGER.info(
            "PV charging update: pv=%sW, battery=%sW",
            pv_power,
            current_battery_power,
        )

        # Update setpoint via coordinator
        await self.update_power_setpoint(target_power)

    async def _update_grid_balance_mode(self) -> None:
        """Update setpoint to balance grid power.

        Uses grid power sensor to calculate battery power needed
        to achieve zero grid import/export.

        Formula:
            target_setpoint = current_battery_power + grid_power

        Grid power sign convention:
            - Negative grid_power = production/export to grid (surplus available,
              typically from solar photovoltaic)
            - Positive grid_power = consumption/import from grid (no surplus)

        Security:
            OWASP A05: Validates sensor availability and data freshness

        Performance:
            Single entity state lookup, O(1) calculation
        """
        if self.sm_connected:
            await self._update_sm_balanced_power()
            return

        # Get external grid power sensor from config
        power_sensor_id = self.config_entry.data.get(CONF_POWER_SENSOR)
        if not power_sensor_id:
            _LOGGER.warning("Grid power sensor not configured")
            return

        # Get current grid power
        grid_state = self.hass.states.get(power_sensor_id)
        if not grid_state or grid_state.state in ("unknown", "unavailable"):
            _LOGGER.warning("Grid power sensor unavailable: %s", power_sensor_id)
            return

        try:
            grid_power = float(grid_state.state)
        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid grid power value: %s", err)
            return

        # Get current battery power from state machine
        current_battery_power = await self._get_battery_power()

        if current_battery_power is None:
            _LOGGER.warning("Battery power not available, skipping grid balance update")
            return

        # Battery power and setpoint are both positive for discharge; grid is positive for import.
        target_power = current_battery_power + grid_power

        _LOGGER.debug(
            "Grid balance: grid_power=%.0fW, battery_power=%.0fW, target=%.0fW",
            grid_power,
            current_battery_power,
            target_power,
        )

        # Apply constraints and update hardware via coordinator
        await self.update_power_setpoint(target_power)

    async def _get_grid_power(self) -> float | None:
        """Get current grid power from CONF_POWER_SENSOR.

        Returns:
            float | None: Current grid power in watts or None if unavailable.
                Negative = production/export to grid (surplus available,
                typically from solar photovoltaic).
                Positive = consumption/import from grid (no surplus).

        Security:
            OWASP A05: Validates sensor availability before access
        """
        if not self.pv_power_sensor:
            return None

        state = self.hass.states.get(self.pv_power_sensor)
        if not state or state.state in (None, "unknown", "unavailable"):
            return None

        try:
            return float(state.state)
        except ValueError, TypeError:
            return None

    async def _update_sm_balanced_power(self) -> None:
        """Update setpoint using SAX smart meter data.

        Uses SAX_POWER_SM (sensor.sax_bess_a_power_smartmeter, register 48) from
        coordinator data for balanced loading when an ADW200/ADL400 is connected.
        The battery reports it positive for import from the grid.

        Formula:
            target_battery_power = current_battery_power + sm_power

        Battery power and setpoint are positive for discharge, the smart-meter
        value is positive for import.

        Security:
            OWASP A05: Validates coordinator data availability
        """
        sm_power = self.coordinator.data.get(SAX_POWER_SM)
        if sm_power is None:
            _LOGGER.warning("Smart meter power not available from coordinator")
            return

        try:
            sm_power_value = float(sm_power)
        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid smart meter power value: %s", err)
            return

        current_battery_power = await self._get_battery_power()
        if current_battery_power is None:
            _LOGGER.warning("Battery power not available, skipping SM balanced update")
            return

        target_power = current_battery_power + sm_power_value

        # Pre-clamp to per-battery hardware limits
        target_power = max(
            -LIMIT_MAX_CHARGE_PER_BATTERY,
            min(LIMIT_MAX_DISCHARGE_PER_BATTERY, target_power),
        )

        _LOGGER.debug(
            "SM balanced: sm_power=%.0fW, battery=%.0fW, target=%.0fW",
            sm_power_value,
            current_battery_power,
            target_power,
        )

        await self.update_power_setpoint(target_power)

    async def _get_battery_power(self) -> float | None:
        """Get current battery power (SAX_AC_POWER_TOTAL) from state machine.

        Uses coordinator.sax_data.get_item_by_name() for item lookup.

        Returns:
            float | None: Current battery power in watts or None if unavailable

        Security:
            OWASP A05: Validates entity availability before access

        Performance:
            Direct state machine access via coordinator.sax_data
        """
        try:
            if not hasattr(self.coordinator, "sax_data"):
                _LOGGER.error("Coordinator missing sax_data attribute")
                return None

            power_ac_item = self.coordinator.sax_data.get_item_by_name(
                SAX_AC_POWER_TOTAL
            )

            if power_ac_item is None:
                _LOGGER.debug(
                    "Could not find item for %s via sax_data", SAX_AC_POWER_TOTAL
                )
                return None

            # SAX_AC_POWER_TOTAL is a cluster-wide entity (battery_id=None)
            power_entity_id = self.coordinator.sax_data.get_entity_id_for_item(
                power_ac_item,
                battery_id=None,
            )

            if power_entity_id is None:
                return None

            state = self.hass.states.get(power_entity_id)
            if state and state.state not in ("unknown", "unavailable", None):
                try:
                    power_value = float(state.state)
                    _LOGGER.debug(
                        "Battery power %s: %.1fW",
                        power_entity_id,
                        power_value,
                    )
                    return power_value  # noqa: TRY300
                except (ValueError, TypeError) as err:
                    _LOGGER.debug("Could not convert battery power value: %s", err)

        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.error("Error getting battery power: %s", err)

        return None

    async def _get_min_soc_limit(self) -> float:
        """Get minimum SOC limit from config.

        Returns:
            Minimum SOC percentage (0-100)

        Security:
            OWASP A05: Validates config entry availability
        """
        if not self.config_entry:
            return DEFAULT_MIN_SOC

        return float(self.config_entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC))

    async def _get_max_soc_charging_limit(self) -> float:
        """Get maximum SOC charging limit from entity.

        Uses coordinator.sax_data.get_item_by_name() for item lookup.

        Returns:
            Maximum SOC percentage (0-100)

        Security:
            OWASP A05: Validates entity availability with fallback
        """
        try:
            max_soc_item = self.coordinator.sax_data.get_item_by_name(
                SAX_MAX_SOC_CHARGING
            )

            if not max_soc_item:
                return 90.0  # Default fallback

            max_soc_entity_id = self.coordinator.sax_data.get_entity_id_for_item(
                max_soc_item,
                battery_id=None,  # Cluster-wide entity
            )

            if max_soc_entity_id:
                state = self.hass.states.get(max_soc_entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    return float(state.state)

        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Could not get max SOC charging limit: %s", err)

        return 90.0  # Default fallback

    def _read_entity_power_value(
        self,
        entity_key: str,
        hw_limit: float,
    ) -> float:
        """Read a power limit value from an entity state (sync).

        Reads the entity's current state and clamps it to the absolute
        per-battery hardware limit as a safety guard.

        Args:
            entity_key: Entity key name (e.g., SAX_MAX_CHARGE)
            hw_limit: Absolute hardware limit (LIMIT_MAX_*_PER_BATTERY)

        Returns:
            Power limit in watts, guaranteed <= hw_limit

        Security:
            OWASP A05: Validates entity availability, clamps to hardware limit
        """
        try:
            item = self.coordinator.sax_data.get_item_by_name(entity_key)
            if not item:
                return hw_limit

            unique_id = self.coordinator.sax_data.get_unique_id_for_item(
                item,
                battery_id=self.coordinator.battery_id,
            )
            if not unique_id:
                return hw_limit

            entity_id = er.async_get(self.hass).async_get_entity_id(
                "number", DOMAIN, unique_id
            )

            if entity_id:
                state = self.hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable"):
                    value = float(state.state)
                    # SAFETY: Clamp to absolute hardware limit regardless
                    # of what the entity reports
                    return min(value, hw_limit)

        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("Could not get power limit for %s: %s", entity_key, err)

        return hw_limit

    async def _get_max_charge_limit(self) -> float:
        """Get user-configured maximum charge power limit.

        Reads SAX_MAX_CHARGE entity (user-configurable in BMS config dialog)
        and clamps to absolute hardware limit.

        Returns:
            Maximum charge power in watts (per battery),
            guaranteed <= LIMIT_MAX_CHARGE_PER_BATTERY

        Security:
            OWASP A05: Validates entity availability with hardware safety clamp
        """
        return self._read_entity_power_value(
            SAX_MAX_CHARGE, LIMIT_MAX_CHARGE_PER_BATTERY
        )

    async def _get_max_discharge_limit(self) -> float:
        """Get user-configured maximum discharge power limit.

        Reads SAX_MAX_DISCHARGE entity (user-configurable in BMS config dialog)
        and clamps to absolute hardware limit.

        Returns:
            Maximum discharge power in watts (per battery),
            guaranteed <= LIMIT_MAX_DISCHARGE_PER_BATTERY

        Security:
            OWASP A05: Validates entity availability with hardware safety clamp
        """
        return self._read_entity_power_value(
            SAX_MAX_DISCHARGE, LIMIT_MAX_DISCHARGE_PER_BATTERY
        )

    async def apply_power_constraints(
        self,
        target_power: float,
        combined_soc: float,
    ) -> float:
        """Apply all power constraints in correct order.

        CRITICAL SAFETY: The master battery distributes the register value
        WITHOUT modification to ALL batteries. The returned value is the
        per-battery power that will be written to the master register and
        applied identically to every battery in the cluster.

        Args:
            target_power: Desired per-battery power (positive=discharge, negative=charge)
            combined_soc: Current cluster SOC percentage

        Returns:
            Constrained per-battery power value, guaranteed to be within
            [-LIMIT_MAX_CHARGE_PER_BATTERY, LIMIT_MAX_DISCHARGE_PER_BATTERY]

        Security:
            OWASP A05: Hardware protection via constraint enforcement

        Performance:
            O(1) constraint checks, no loops

        Note:
            Constraint enforcement order:
            1. SOC-based discharge protection (MIN_SOC)
            2. SOC-based charge limit (MAX_SOC_CHARGING)
            3. Hardware charge limit (MAX_CHARGE entity or LIMIT_MAX_CHARGE_PER_BATTERY)
            4. Hardware discharge limit (MAX_DISCHARGE entity or LIMIT_MAX_DISCHARGE_PER_BATTERY)
            5. Absolute hardware safety clamp (final guarantee)
        """
        battery_power = target_power

        # Get constraint limits from entities (fall back to per-battery HW limits)
        min_soc = await self._get_min_soc_limit()
        max_soc_charging = await self._get_max_soc_charging_limit()
        max_charge = await self._get_max_charge_limit()
        max_discharge = await self._get_max_discharge_limit()

        _LOGGER.debug(
            "Constraint limits: min_soc=%.1f%%, max_soc=%.1f%%, "
            "max_charge=%.0fW, max_discharge=%.0fW",
            min_soc,
            max_soc_charging,
            max_charge,
            max_discharge,
        )

        # Step 1: SOC-based discharge protection
        if combined_soc <= min_soc and battery_power > 0:
            _LOGGER.info(
                "Discharge blocked: SOC %.1f%% <= min %.1f%%",
                combined_soc,
                min_soc,
            )
            return 0.0

        # Step 2: SOC-based charge limit
        if combined_soc >= max_soc_charging and battery_power < 0:
            _LOGGER.info(
                "Charge blocked: SOC %.1f%% >= max %.1f%%",
                combined_soc,
                max_soc_charging,
            )
            return 0.0

        # Step 3: Hardware charge limit (charging = negative power)
        if battery_power < 0:
            original_power = battery_power
            battery_power = max(battery_power, -max_charge)
            if battery_power != original_power:
                _LOGGER.debug(
                    "Charge power limited: %.0fW -> %.0fW",
                    original_power,
                    battery_power,
                )

        # Step 4: Hardware discharge limit (discharging = positive power)
        if battery_power > 0:
            original_power = battery_power
            battery_power = min(battery_power, max_discharge)
            if battery_power != original_power:
                _LOGGER.debug(
                    "Discharge power limited: %.0fW -> %.0fW",
                    original_power,
                    battery_power,
                )

        # Step 5: ABSOLUTE HARDWARE SAFETY CLAMP
        # Final guarantee: regardless of entity values or calculation errors,
        # NEVER exceed per-battery hardware limits. The master distributes
        # this value unchanged to every battery in the cluster.
        battery_power = max(
            -LIMIT_MAX_CHARGE_PER_BATTERY,
            min(LIMIT_MAX_DISCHARGE_PER_BATTERY, battery_power),
        )

        return battery_power  # noqa: RET504

    async def update_power_setpoint(self, power: float, *, force: bool = False) -> bool:
        """Serialize regular writes and discard stale mode calculations."""
        if force:
            return await self._async_update_power_setpoint(power, force=True)

        generation = self._update_generation.get()
        async with self._power_write_lock:
            if generation is not None and generation != self._power_generation:
                return False
            return await self._async_update_power_setpoint(power)

    async def _async_update_power_setpoint(
        self, power: float, *, force: bool = False
    ) -> bool:
        """Update setpoint via coordinator atomic write.

        Uses coordinator.async_write_power_control_value() to write both
        SAX_POWER_SETPOINT (register 41) and SAX_POWER_SETPOINT_FACTOR (register 42)
        atomically via a direct coordinator write.

        Write sequence:
            1. Get SAX_POWER_SETPOINT ModbusItem via coordinator.sax_data
            2. Apply SOC and hardware constraints
            3. Call coordinator.async_write_power_control_value(item, power, factor)
            4. modbus_api.write_power_setpoint() writes both registers

        Args:
            power: Per-battery power value in watts (positive = discharge, negative = charge)
                   CRITICAL: This value is written to the master register and distributed
                   WITHOUT modification to ALL batteries. Must never exceed per-battery
                   hardware limits (LIMIT_MAX_CHARGE/DISCHARGE_PER_BATTERY).

        Security:
            OWASP A05: Validates power limits, SOC constraints, and item availability
        Performance:
            Coordinator-centric write avoids HA service call overhead
        """
        # Security: Validate power value type
        if not isinstance(power, (int, float)):
            _LOGGER.error("Invalid power value type: %s", type(power))  # type:ignore[unreachable] # noqa: DC12
            return False

        # Get current combined SOC for constraint enforcement
        combined_soc = self.coordinator.data.get(SAX_COMBINED_SOC)
        if combined_soc is None and power != 0:
            _LOGGER.warning("Combined SOC not available, cannot apply constraints")
            return False

        # Apply all power constraints (SOC protection, hardware limits)
        # Returns per-battery value already clamped to hardware limits
        constrained_power = (
            await self.apply_power_constraints(
                target_power=power,
                combined_soc=combined_soc,
            )
            if combined_soc is not None
            else 0.0
        )

        # CRITICAL SAFETY: Final absolute per-battery hardware clamp before register write.
        # The master distributes this value unchanged to ALL batteries.
        # This is a defense-in-depth guard against any upstream calculation error.
        constrained_power = max(
            -LIMIT_MAX_CHARGE_PER_BATTERY,
            min(LIMIT_MAX_DISCHARGE_PER_BATTERY, constrained_power),
        )

        if constrained_power != power:
            _LOGGER.info(
                "Power constrained: %.0fW -> %.0fW (SOC: %.1f%%)",
                power,
                constrained_power,
                combined_soc,
            )

        last_written_power: float | None = None
        last_written_values = getattr(
            self.coordinator, "last_written_power_control", None
        )
        if isinstance(last_written_values, dict):
            written_power = last_written_values.get(SAX_POWER_SETPOINT)
            if isinstance(written_power, (int, float)):
                last_written_power = float(written_power)

        if not force and combined_soc is not None and last_written_power is not None:
            same_direction = (
                last_written_power == 0
                or constrained_power == 0
                or (last_written_power > 0) == (constrained_power > 0)
            )
            within_deadband = (
                abs(constrained_power - last_written_power) < POWER_SETPOINT_DEADBAND_W
            )
            zero_already_written = constrained_power == 0 and last_written_power == 0
            if (
                within_deadband
                and same_direction
                and (constrained_power != 0 or zero_already_written)
                and constrained_power in (power, last_written_power)
            ):
                last_allowed_power = await self.apply_power_constraints(
                    target_power=last_written_power,
                    combined_soc=combined_soc,
                )
                if (
                    last_allowed_power == last_written_power
                    and self._last_power_write_monotonic is not None
                    and time.monotonic() - self._last_power_write_monotonic
                    < POWER_SETPOINT_REFRESH_SECONDS
                ):
                    return True

        # Get SAX_POWER_SETPOINT ModbusItem from coordinator's sax_data
        power_item = self.coordinator.sax_data.get_item_by_name(SAX_POWER_SETPOINT)
        if not isinstance(power_item, ModbusItem):
            _LOGGER.error("SAX_POWER_SETPOINT not found or not a ModbusItem")
            return False

        # Power factor: 1000 = 1.0 (full power capacity)
        power_factor = 1000

        # Coordinator-centric atomic write with timeout protection
        try:
            async with asyncio.timeout(5.0):
                success = await self.coordinator.async_write_power_control_value(
                    power_item=power_item,
                    power=int(constrained_power),
                    power_factor=power_factor,
                )

            if success:
                self._last_power_write_monotonic = time.monotonic()
                self._state.target_power = constrained_power
                self._state.last_update = datetime.now()
                _LOGGER.info(
                    "Power setpoint updated to %sW via coordinator",
                    constrained_power,
                )
            else:
                _LOGGER.error("Failed to write setpoint via coordinator")
            return success  # noqa: TRY300

        except TimeoutError:
            _LOGGER.error(
                "Timeout writing power value %sW via coordinator",
                constrained_power,
            )
        except (OSError, ValueError) as err:
            _LOGGER.error("Failed to update setpoint: %s", err)
        return False

    async def set_pv_charging_mode(self, enabled: bool) -> None:
        """Enable or disable PV charging mode.

        Args:
            enabled: True to enable PV charging mode

        Security:
            OWASP A01: Power manager state synchronized with switch state
        """
        if enabled:
            await self._stop_complete.wait()
        self._state.pv_charging_enabled = enabled
        self._state.mode = PV_CHARGING_MODE if enabled else GRID_CHARGING_MODE

        # Update grid charging state (mutual exclusion)
        if enabled:
            self._state.grid_charging_enabled = False

        if self.config_entry.data.get(CONF_ENABLE_PV_CHARGING, False) != enabled:
            new_data = {
                **self.config_entry.data,
                CONF_ENABLE_PV_CHARGING: enabled,
            }
            if enabled:
                new_data[CONF_ENABLE_GRID_CHARGING] = False
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

        _LOGGER.info(
            "PV charging mode %s (grid_charging=%s)",
            "enabled" if enabled else "disabled",
            self._state.grid_charging_enabled,
        )

        if enabled:
            if self._is_sunspec:
                await SunSpecPowerControlStrategy(
                    self.coordinator
                ).async_set_mode_zero_balance()
            await self._async_update_power(None)
        else:
            await self._async_stop_power()

    async def _async_stop_power(self) -> None:
        """Send zero and allow a Legacy coordinator interval for settling."""
        if self._is_sunspec:
            await self._async_write_power(0.0, force=True)
            return
        self._stop_complete.clear()
        self._power_generation += 1
        try:
            async with self._power_write_lock:
                if not await self._async_write_power(0.0, force=True):
                    raise HomeAssistantError("Failed to send zero power setpoint")
                interval = self.coordinator.update_interval
                await asyncio.sleep(
                    interval.total_seconds() if interval else BATTERY_POLL_INTERVAL
                )
        finally:
            self._stop_complete.set()

    async def set_grid_control_mode(
        self,
        enabled: bool,
        power: float = 0.0,
        *,
        restore_pv: bool = True,
        fallback_to_balance: bool = True,
    ) -> None:
        """Enable or disable grid charging mode.

        Args:
            enabled: True to enable grid charging mode
            power: Initial charge power (optional, uses SAX_MAX_CHARGE if 0)

        Security:
            OWASP A01: Power manager state synchronized with switch state

        """
        if enabled:
            await self._stop_complete.wait()

        # Store previous PV state before enabling grid charging
        if enabled:
            if not self._state.grid_charging_enabled:
                self._state.previous_pv_state = self._state.pv_charging_enabled
            self._state.pv_charging_enabled = False  # Mutual exclusion
        elif restore_pv and self._state.previous_pv_state:
            # Restore previous PV state when disabling grid charging
            _LOGGER.info("Restoring PV charging mode after grid charging disabled")
            self._state.pv_charging_enabled = self._state.previous_pv_state
            self._state.previous_pv_state = False
        elif not restore_pv:
            self._state.previous_pv_state = False

        self._state.grid_charging_enabled = enabled
        self._state.mode = (
            GRID_CHARGING_MODE
            if enabled
            else (PV_CHARGING_MODE if self._state.pv_charging_enabled else "standby")
        )

        _LOGGER.info(
            "Grid charging mode %s (PV charging will be %s)",
            "enabled" if enabled else "disabled",
            "restored"
            if not enabled and self._state.pv_charging_enabled
            else "disabled",
        )

        if enabled:
            # Apply grid charging power if specified
            if power != 0.0:
                await self.update_power_setpoint(power)
            else:
                await self._async_update_power(None)
        elif fallback_to_balance:
            await self._async_apply_balanced_fallback()
        else:
            await self._async_stop_power()

    @property
    def get_pv_charging_enabled(self) -> bool:
        """Check if PV charging mode is enabled."""
        return self._state.pv_charging_enabled

    @property
    def get_grid_charging_enabled(self) -> bool:
        """Check if grid charging mode is enabled."""
        return self._state.grid_charging_enabled

    def get_diagnostics(self) -> dict[str, object]:
        """Return diagnostic information for troubleshooting.

        Includes user-configured limits (from BMS config dialog entities)
        and absolute hardware safety limits.

        Returns:
            Dictionary with power manager state and configuration

        Security:
            OWASP A05: Does not expose sensitive configuration data
        """
        update_interval: timedelta = (
            self.coordinator.update_interval
            if self.coordinator.update_interval is not None
            else timedelta(seconds=60)
        )

        # Read user-configured limits from entity states (sync).
        # These are the effective limits used for power control,
        # always <= the absolute hardware limits.
        user_max_charge = self._read_entity_power_value(
            SAX_MAX_CHARGE, LIMIT_MAX_CHARGE_PER_BATTERY
        )
        user_max_discharge = self._read_entity_power_value(
            SAX_MAX_DISCHARGE, LIMIT_MAX_DISCHARGE_PER_BATTERY
        )

        return {
            "running": self._running,
            "mode": self._state.mode,
            "target_power": self._state.target_power,
            "pv_charging_enabled": self._state.pv_charging_enabled,
            "grid_charging_enabled": self._state.grid_charging_enabled,
            "last_update": self._state.last_update.isoformat(),
            "battery_count": self.battery_count,
            "ui_max_discharge_power": self.ui_max_discharge_power,
            "ui_max_charge_power": self.ui_max_charge_power,
            # Effective user-configured limits (from BMS config dialog)
            "configured_max_charge": user_max_charge,
            "configured_max_discharge": user_max_discharge,
            # Absolute hardware safety limits (never exceeded)
            "hw_limit_charge_per_battery": LIMIT_MAX_CHARGE_PER_BATTERY,
            "hw_limit_discharge_per_battery": LIMIT_MAX_DISCHARGE_PER_BATTERY,
            "update_interval_seconds": update_interval.total_seconds(),
        }
