"""SAX Battery pilot functionality."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from pymodbus import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    CONF_PRIORITY_DEVICES,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
)
from .coordinator import SAXBatteryCoordinator
from .items import ModbusItem
from .models import SAXBatteryData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery pilot entities."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    # Create pilot entities only for master battery
    master_battery_id = sax_data.master_battery_id
    if master_battery_id and master_battery_id in coordinators:
        coordinator = sax_data.coordinators[master_battery_id]
        pilot = SAXBatteryPilot(hass, sax_data, coordinator)

        # Store pilot instance in sax_data for access by other components
        setattr(sax_data, "pilot", pilot)

        # Start automatic pilot service if enabled
        if config_entry.data.get(CONF_PILOT_FROM_HA, False):
            await pilot.async_start()

    # Note: Pilot power entity will be created by the number platform
    # using SAXBatteryConfigNumber with the sax_pilot_power SAXItem


class SAXBatteryPilot:
    """SAX Battery pilot controller for master battery coordination."""

    def __init__(
        self,
        hass: HomeAssistant,
        sax_data: SAXBatteryData,
        coordinator: SAXBatteryCoordinator,
    ) -> None:
        """Initialize the pilot controller."""
        self.hass = hass
        self.sax_data = sax_data
        self.coordinator = coordinator
        self.entry = sax_data.entry
        self.battery_count = len(sax_data.coordinators)

        # Configuration values
        self._update_config_values()
        self.power_sensor_entity_id = self.entry.data.get(CONF_POWER_SENSOR)
        self.pf_sensor_entity_id = self.entry.data.get(CONF_PF_SENSOR)
        self.priority_devices = self.entry.data.get(CONF_PRIORITY_DEVICES, [])
        self.min_soc = self.entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self.update_interval = self.entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )

        # Calculated values
        self.calculated_power = 0.0
        self.max_discharge_power = self.battery_count * LIMIT_MAX_CHARGE_PER_BATTERY
        self.max_charge_power = self.battery_count * LIMIT_MAX_DISCHARGE_PER_BATTERY

        # Track state
        self._remove_interval_update: Callable[[], None] | None = None
        self._remove_config_update: Callable[[], None] | None = None
        self._running = False

    def _update_config_values(self) -> None:
        """Update configuration values from entry data."""
        self.power_sensor_entity_id = self.entry.data.get(CONF_POWER_SENSOR)
        self.pf_sensor_entity_id = self.entry.data.get(CONF_PF_SENSOR)
        self.priority_devices = self.entry.data.get(CONF_PRIORITY_DEVICES, [])
        self.min_soc = self.entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self.update_interval = self.entry.data.get(
            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
        )
        _LOGGER.debug(
            "Updated config values - min_soc: %s%%, update_interval: %ss",
            self.min_soc,
            self.update_interval,
        )

    async def async_start(self) -> None:
        """Start the pilot service."""
        if self._running:
            return

        self._running = True
        self._remove_interval_update = async_track_time_interval(
            self.hass, self._async_update_pilot, timedelta(seconds=self.update_interval)
        )

        # Add listener for config entry updates
        self._remove_config_update = self.entry.add_update_listener(
            self._async_config_updated
        )

        # Do initial calculation
        await self._async_update_pilot(None)

        _LOGGER.info(
            "SAX Battery pilot started with %ss interval", self.update_interval
        )

    async def _async_config_updated(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Handle config entry updates."""
        self.entry = entry
        self._update_config_values()
        # Apply new configuration immediately
        await self._async_update_pilot(None)
        _LOGGER.info("SAX Battery pilot configuration updated")

    async def async_stop(self) -> None:
        """Stop the pilot service."""
        if not self._running:
            return

        if self._remove_interval_update is not None:
            self._remove_interval_update()
            self._remove_interval_update = None

        if self._remove_config_update is not None:
            self._remove_config_update()
            self._remove_config_update = None

        self._running = False
        _LOGGER.info("SAX Battery pilot stopped")

    async def _async_update_pilot(self, now: Any = None) -> None:
        """Update the pilot calculations and send to battery."""
        try:
            # Check if in manual mode
            if self.entry.data.get(CONF_MANUAL_CONTROL, False):
                # Skip automatic calculations in manual mode
                _LOGGER.debug(
                    "Manual control mode active - Current power setting: %sW",
                    self.calculated_power,
                )

                # Check SOC constraints for the current manual power setting
                _LOGGER.debug(
                    "Checking SOC constraints for manual power: %sW",
                    self.calculated_power,
                )
                constrained_power = await self._apply_soc_constraints(
                    self.calculated_power
                )
                if constrained_power != self.calculated_power:
                    _LOGGER.info(
                        "Manual power needs adjustment from %sW to %sW due to SOC constraints",
                        self.calculated_power,
                        constrained_power,
                    )
                    # Update the power setting if constraints changed it
                    await self.send_power_command(constrained_power, 1.0)
                    self.calculated_power = constrained_power
                    _LOGGER.info(
                        "Manual power adjusted to %sW due to SOC constraints",
                        constrained_power,
                    )
                else:
                    _LOGGER.debug(
                        "No SOC constraint adjustments needed for manual power %sW",
                        self.calculated_power,
                    )
                return

            # Get current power sensor state
            if self.power_sensor_entity_id is None:
                _LOGGER.warning("Power sensor entity ID is not configured")
                return

            power_state = self.hass.states.get(self.power_sensor_entity_id)
            if power_state is None:
                _LOGGER.warning(
                    "Power sensor %s not found", self.power_sensor_entity_id
                )
                return

            if power_state.state in (None, "unknown", "unavailable"):
                _LOGGER.warning(
                    "Power sensor %s state is %s",
                    self.power_sensor_entity_id,
                    power_state.state,
                )
                return

            try:
                total_power = float(power_state.state)
            except (ValueError, TypeError) as err:
                _LOGGER.error(
                    "Could not convert power sensor state '%s' to float: %s",
                    power_state.state,
                    err,
                )
                return

            # Get current PF value
            if self.pf_sensor_entity_id is None:
                _LOGGER.warning("PF sensor entity ID is not configured")
                return

            pf_state = self.hass.states.get(self.pf_sensor_entity_id)
            if pf_state is None:
                _LOGGER.warning("PF sensor %s not found", self.pf_sensor_entity_id)
                return

            if pf_state.state in (None, "unknown", "unavailable"):
                _LOGGER.warning(
                    "PF sensor %s state is %s", self.pf_sensor_entity_id, pf_state.state
                )
                return

            try:
                power_factor = float(pf_state.state)
            except (ValueError, TypeError) as err:
                _LOGGER.error(
                    "Could not convert PF sensor state '%s' to float: %s",
                    pf_state.state,
                    err,
                )
                return

            # Get priority device power consumption
            priority_power = 0.0
            for device_id in self.priority_devices:
                device_state = self.hass.states.get(device_id)
                if device_state is not None:
                    try:
                        priority_power += float(device_state.state)
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Could not convert state of %s to number", device_id
                        )

            # Get current battery power
            battery_power_state = self.hass.states.get(
                "sensor.sax_battery_combined_power"
            )
            battery_power = 0.0
            if battery_power_state is not None:
                try:
                    if battery_power_state.state not in (
                        None,
                        "unknown",
                        "unavailable",
                    ):
                        battery_power = float(battery_power_state.state)
                    else:
                        _LOGGER.debug(
                            "Battery power state is %s", battery_power_state.state
                        )
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Could not convert battery power '%s' to number: %s",
                        battery_power_state.state,
                        err,
                    )

            # Get current SOC for logging
            master_soc = await self._get_combined_soc()
            _LOGGER.debug("Current master SOC: %s%%", master_soc)

            # Calculate target power
            _LOGGER.debug(
                "Starting calculation with total_power=%s, priority_power=%s, battery_power=%s",
                total_power,
                priority_power,
                battery_power,
            )

            if priority_power > 50:
                _LOGGER.debug(
                    "Condition met: priority_power > 50 (%s > 50)", priority_power
                )
                net_power = 0.0
                _LOGGER.debug("Set net_power = 0")
            else:
                _LOGGER.debug(
                    "Condition met: priority_power <= 50 (%s <= 50)", priority_power
                )
                net_power = total_power - battery_power
                _LOGGER.debug(
                    "Calculated net_power = %s - %s = %s",
                    total_power,
                    battery_power,
                    net_power,
                )

            _LOGGER.debug("Final net_power value: %s", net_power)

            target_power = -net_power
            _LOGGER.debug("Final target_power value: %s", target_power)

            # Apply limits
            target_power = max(
                -self.max_discharge_power, min(self.max_charge_power, target_power)
            )

            # Apply SOC constraints
            _LOGGER.debug("Pre-constraint target power: %sW", target_power)
            target_power = await self._apply_soc_constraints(target_power)
            _LOGGER.debug("Post-constraint target power: %sW", target_power)

            # Update calculated power
            self.calculated_power = target_power

            # Send to battery if solar charging is enabled
            if self.get_solar_charging_enabled():
                await self.send_power_command(target_power, power_factor)

            _LOGGER.debug(
                "Updated battery pilot: target power = %sW, PF = %s",
                target_power,
                power_factor,
            )

        except (OSError, ValueError, TypeError) as err:
            _LOGGER.error("Error in battery pilot update: %s", err)

    async def _get_combined_soc(self) -> float:
        """Get combined SOC from coordinator data."""
        if not self.coordinator.data:
            return 0.0

        soc_value = self.coordinator.data.get(SAX_COMBINED_SOC, 0)
        try:
            return float(soc_value)
        except (ValueError, TypeError):
            return 0.0

    async def _apply_soc_constraints(self, power_value: float) -> float:
        """Apply SOC constraints to a power value."""
        # Get current battery SOC
        master_soc = await self._get_combined_soc()

        # Log the input values
        _LOGGER.debug(
            "Applying SOC constraints - Current SOC: %s%%, Min SOC: %s%%, Power: %sW",
            master_soc,
            self.min_soc,
            power_value,
        )

        # Apply constraints
        original_value = power_value

        # Don't discharge below min SOC
        if master_soc < self.min_soc and power_value > 0:
            power_value = 0
            _LOGGER.debug(
                "Battery SOC at minimum (%s%%), preventing discharge", master_soc
            )

        # Don't charge above 100%
        if master_soc >= 100 and power_value < 0:
            power_value = 0
            _LOGGER.debug("Battery SOC at maximum (100%), preventing charge")

        # Log if any change was made
        if original_value != power_value:
            _LOGGER.info(
                "SOC constraint applied: changed power from %sW to %sW",
                original_value,
                power_value,
            )
        else:
            _LOGGER.debug(
                "SOC constraint check: no change needed to power value %sW", power_value
            )

        return power_value

    async def send_power_command(self, power: float, power_factor: float) -> None:
        """Send power command to battery using coordinator's write method."""
        try:
            _LOGGER.debug(
                "Sending power command: power=%s, power_factor=%s", power, power_factor
            )

            # Find the nominal power item using updated constant
            power_item = self._get_modbus_item_by_name(SAX_NOMINAL_POWER)
            power_factor_item = self._get_modbus_item_by_name(SAX_NOMINAL_FACTOR)

            if not power_item:
                _LOGGER.error(
                    "Could not find nominal power item for battery %s",
                    self.coordinator.battery_id,
                )
                return
            if not power_factor_item:
                _LOGGER.error(
                    "Could not find nominal power factor item for battery %s",
                    self.coordinator.battery_id,
                )
                return

            # Use coordinator's write_nominal_power which handles power and power_factor
            success = await self.coordinator.async_write_pilot_control_value(
                power_item, power_factor_item, power, int(power_factor)
            )

            if success:
                _LOGGER.debug("Nominal power command sent successfully")
            else:
                _LOGGER.error("Failed to write nominal power command")

        except ModbusException as e:
            _LOGGER.error("Modbus error sending power command: %s", e)
        except OSError as e:
            _LOGGER.error("Network error sending power command: %s", e)
        except (ValueError, TypeError) as e:
            _LOGGER.error("Data error sending power command: %s", e)

    async def set_manual_power(self, power_value: float) -> None:
        """Set a manual power value."""
        # Apply SOC constraints
        power_value = await self._apply_soc_constraints(power_value)

        # Send the power command with a default power factor of 1.0
        await self.send_power_command(power_value, 1.0)
        self.calculated_power = power_value
        _LOGGER.info("Manual power set to %sW", power_value)

    async def set_charge_power_limit(self, power_limit: int) -> bool:
        """Set the maximum charge power limit using coordinator."""
        try:
            _LOGGER.debug("Setting charge power limit to %s W", power_limit)

            # Find the charge power limit item using updated constant
            charge_item = self._get_modbus_item_by_name(SAX_MAX_CHARGE)

            if not charge_item:
                _LOGGER.error("Could not find charge power limit item")
                return False

            # Use coordinator's write method
            success = await self.coordinator.async_write_number_value(
                charge_item, float(power_limit)
            )

            if success:
                _LOGGER.debug("Charge power limit set successfully")
            else:
                _LOGGER.error("Failed to set charge power limit")

            return success  # noqa: TRY300

        except ModbusException as e:
            _LOGGER.error("Modbus error setting charge power limit: %s", e)
            return False
        except OSError as e:
            _LOGGER.error("Network error setting charge power limit: %s", e)
            return False
        except (ValueError, TypeError) as e:
            _LOGGER.error("Data error setting charge power limit: %s", e)
            return False

    async def set_discharge_power_limit(self, power_limit: int) -> bool:
        """Set the maximum discharge power limit using coordinator."""
        try:
            _LOGGER.debug("Setting discharge power limit to %s W", power_limit)

            # Find the discharge power limit item using updated constant
            discharge_item = self._get_modbus_item_by_name(SAX_MAX_DISCHARGE)

            if not discharge_item:
                _LOGGER.error("Could not find discharge power limit item")
                return False

            # Use coordinator's write method
            success = await self.coordinator.async_write_number_value(
                discharge_item, float(power_limit)
            )

            if success:
                _LOGGER.debug("Discharge power limit set successfully")
            else:
                _LOGGER.error("Failed to set discharge power limit")

            return success  # noqa: TRY300

        except ModbusException as e:
            _LOGGER.error("Modbus error setting discharge power limit: %s", e)
            return False
        except OSError as e:
            _LOGGER.error("Network error setting discharge power limit: %s", e)
            return False
        except (ValueError, TypeError) as e:
            _LOGGER.error("Data error setting discharge power limit: %s", e)
            return False

    def _get_modbus_item_by_name(self, item_name: str) -> ModbusItem | None:
        """Get modbus item by name using sax_data."""
        # Get modbus items for master battery
        modbus_items = self.sax_data.get_modbus_items_for_battery(
            self.coordinator.battery_id
        )

        # Filter by name and type
        matching_items = [
            item
            for item in modbus_items
            if hasattr(item, "name") and item.name == item_name
        ]

        if matching_items:
            return matching_items[0]

        _LOGGER.warning("Could not find modbus item with name: %s", item_name)
        return None

    def get_solar_charging_enabled(self) -> bool:
        """Get solar charging state."""
        return bool(self.entry.data.get(CONF_ENABLE_SOLAR_CHARGING, True))

    def get_manual_control_enabled(self) -> bool:
        """Get manual control state."""
        return bool(self.entry.data.get(CONF_MANUAL_CONTROL, True))
