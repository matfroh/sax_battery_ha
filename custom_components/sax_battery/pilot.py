"""SAX Battery pilot functionality."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from pymodbus import ModbusException

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    SAX_COMBINED_SOC,
)
from .coordinator import SAXBatteryCoordinator
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

    entities: list[NumberEntity] = []

    # Create pilot entities only for master battery
    master_battery_id = sax_data.master_battery_id
    if master_battery_id and master_battery_id in coordinators:
        coordinator = sax_data.coordinators[master_battery_id]
        pilot = SAXBatteryPilot(hass, sax_data, coordinator)

        # Store pilot instance in sax_data for access by other components
        # Add pilot attribute to SAXBatteryData model
        setattr(sax_data, "pilot", pilot)

        # Add power control entity if pilot from HA is enabled
        if config_entry.data.get(CONF_PILOT_FROM_HA, False):
            entities.append(
                SAXBatteryPilotPowerEntity(pilot, coordinator, master_battery_id)
            )

        # Start automatic pilot service if enabled
        if config_entry.data.get(CONF_PILOT_FROM_HA, False):
            await pilot.async_start()

    if entities:
        async_add_entities(entities, update_before_add=True)


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
        self.max_discharge_power = self.battery_count * 3600
        self.max_charge_power = self.battery_count * 4500

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
        """Send power command to battery using write_nominal_power."""
        try:
            _LOGGER.debug(
                "Sending power command: power=%s, power_factor=%s", power, power_factor
            )

            # Get the nominal power setpoint item (address 41)
            power_item = self._get_modbus_item("sax_nominal_power_setpoint")

            if not power_item:
                _LOGGER.error(
                    "Could not find nominal power setpoint item for battery %s",
                    self.coordinator.battery_id,
                )
                return

            # Use write_nominal_power which handles both power and power_factor
            # Convert power_factor to int as expected by write_nominal_power
            success = await self.coordinator.modbus_api.write_nominal_power(
                value=power, power_factor=int(power_factor), modbus_item=power_item
            )

            if not success:
                _LOGGER.error("Failed to write nominal power command")
                return

            _LOGGER.debug("Nominal power command sent successfully")

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
        """Set the maximum charge power limit."""
        try:
            _LOGGER.debug("Setting charge power limit to %s W", power_limit)

            # Find the charge power limit item
            charge_items = [
                item
                for item in self.sax_data.get_modbus_items_for_battery(
                    self.coordinator.battery_id
                )
                if item.name == "sax_max_charge_power"
            ]

            if not charge_items:
                _LOGGER.error("Could not find charge power limit item")
                return False

            charge_item = charge_items[0]
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
        """Set the maximum discharge power limit."""
        try:
            _LOGGER.debug("Setting discharge power limit to %s W", power_limit)

            # Find the discharge power limit item
            discharge_items = [
                item
                for item in self.sax_data.get_modbus_items_for_battery(
                    self.coordinator.battery_id
                )
                if item.name == "sax_max_discharge_power"
            ]

            if not discharge_items:
                _LOGGER.error("Could not find discharge power limit item")
                return False

            discharge_item = discharge_items[0]
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

    def _get_modbus_item(self, item_name: str) -> Any | None:
        """Get modbus item by name for backwards compatibility."""
        # Get modbus items for master battery
        api_items = self.sax_data.get_modbus_items_for_battery(
            self.coordinator.battery_id
        )

        for item in api_items:
            if hasattr(item, "name") and item.name == item_name:
                return item

        return None

    def get_solar_charging_enabled(self) -> bool:
        """Get solar charging state."""
        return bool(self.entry.data.get(CONF_ENABLE_SOLAR_CHARGING, True))

    def get_manual_control_enabled(self) -> bool:
        """Get manual control state."""
        return bool(self.entry.data.get(CONF_MANUAL_CONTROL, True))


class SAXBatteryPilotPowerEntity(
    CoordinatorEntity[SAXBatteryCoordinator], NumberEntity
):
    """Entity showing current calculated pilot power."""

    def __init__(
        self,
        pilot: SAXBatteryPilot,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._pilot = pilot
        self._battery_id = battery_id

        # Generate unique ID
        self._attr_unique_id = f"sax_{battery_id}_pilot_power"
        self._attr_name = (
            f"Sax {battery_id.replace('battery_', 'Battery ').title()} Pilot Power"
        )

        # Set number entity properties
        self._attr_native_min_value = -self._pilot.max_discharge_power
        self._attr_native_max_value = self._pilot.max_charge_power
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_mode = NumberMode.BOX
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> Any:
        """Return device info."""
        return self.coordinator.sax_data.get_device_info(self._battery_id)

    @property
    def native_value(self) -> float | None:
        """Return the current calculated power."""
        return (
            float(self._pilot.calculated_power)
            if self._pilot.calculated_power is not None
            else None
        )

    @property
    def icon(self) -> str | None:
        """Return the icon to use for the entity."""
        if self._pilot.calculated_power > 0:
            return "mdi:battery-charging"
        if self._pilot.calculated_power < 0:
            return "mdi:battery-minus"
        return "mdi:battery"

    async def async_set_native_value(self, value: float) -> None:
        """Handle manual override of calculated power."""
        await self._pilot.set_manual_power(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if not self.coordinator.last_update_success:
            return None

        return {
            "battery_id": self._battery_id,
            "solar_charging_enabled": self._pilot.get_solar_charging_enabled(),
            "manual_control_enabled": self._pilot.get_manual_control_enabled(),
            "max_charge_power": self._pilot.max_charge_power,
            "max_discharge_power": self._pilot.max_discharge_power,
            "last_updated": self.coordinator.last_update_success_time,
        }
