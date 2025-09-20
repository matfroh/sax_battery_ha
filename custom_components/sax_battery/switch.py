"""Switch platform for SAX Battery integration."""

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_SOLAR_CHARGING, CONF_MANUAL_CONTROL, DOMAIN, SAX_STATUS
from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SAX Battery switches."""
    coordinator: SAXBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SAXBatterySolarChargingSwitch(coordinator),
        SAXBatteryManualControlSwitch(coordinator),
    ]

    # Add individual battery on/off switches
    # Access battery objects directly from coordinator's battery attributes
    for battery_id in coordinator.batteries:
        # Try different ways to access the battery object
        battery = None

        # Method 1: Try as direct attribute (most likely)
        if hasattr(coordinator, battery_id):
            battery = getattr(coordinator, battery_id)

        # Method 2: Try from a batteries collection/dict
        if battery is None and hasattr(coordinator, "battery_objects"):
            battery = coordinator.battery_objects.get(battery_id)

        # Method 3: Try accessing from master battery's data manager
        if battery is None and hasattr(coordinator, "master_battery"):
            master_battery = coordinator.master_battery
            if hasattr(master_battery, "_data_manager"):
                # Check if the battery objects are stored in the data manager
                if hasattr(master_battery._data_manager, "batteries"):  # noqa: SLF001
                    battery = master_battery._data_manager.batteries.get(battery_id)  # noqa: SLF001

        if battery is not None:
            entities.append(SAXBatteryOnOffSwitch(battery_id, battery, coordinator))
        else:
            _LOGGER.warning("Battery object not found for ID: %s", battery_id)
            # Add debug info to help understand the coordinator structure
            _LOGGER.debug(
                "Coordinator attributes: %s",
                [attr for attr in dir(coordinator) if not attr.startswith("_")],
            )
            if hasattr(coordinator, "master_battery"):
                _LOGGER.debug(
                    "Master battery attributes: %s",
                    [
                        attr
                        for attr in dir(coordinator.master_battery)
                        if not attr.startswith("_")
                    ],
                )

    async_add_entities(entities)


class SAXBatterySolarChargingSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable solar charging."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_name = "Sax Battery Solar Charging"
        self._attr_unique_id = f"{DOMAIN}_solar_charging"
        self._attr_icon = "mdi:solar-power"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.coordinator.config_entry.data.get(CONF_ENABLE_SOLAR_CHARGING, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (enable solar charging)."""
        await self._update_mode_switches(solar_charging=True, manual_control=False)

    async def _update_mode_switches(
        self, solar_charging: bool, manual_control: bool
    ) -> None:
        """Update both mode switches atomically."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_ENABLE_SOLAR_CHARGING] = solar_charging
        new_data[CONF_MANUAL_CONTROL] = manual_control

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Update pilot mode
        sax_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            await sax_data.pilot.set_solar_charging(solar_charging)

        # Force immediate state updates
        self.async_schedule_update_ha_state(force_refresh=True)

        # Trigger coordinator refresh
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (disable solar charging)."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_ENABLE_SOLAR_CHARGING] = False

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Update pilot mode
        sax_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            await sax_data.pilot.set_solar_charging(False)

        self.async_write_ha_state()


class SAXBatteryManualControlSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable manual control mode."""

    def __init__(self, coordinator: SAXBatteryCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_name = "Sax Battery Manual Control"
        self._attr_unique_id = f"{DOMAIN}_manual_control"
        self._attr_icon = "mdi:hand-back-right"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.coordinator.config_entry.data.get(CONF_MANUAL_CONTROL, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (enable manual control)."""
        await self._update_mode_switches(solar_charging=False, manual_control=True)

    async def _update_mode_switches(
        self, solar_charging: bool, manual_control: bool
    ) -> None:
        """Update both mode switches atomically."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_ENABLE_SOLAR_CHARGING] = solar_charging
        new_data[CONF_MANUAL_CONTROL] = manual_control

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Update pilot mode
        sax_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            await sax_data.pilot.set_solar_charging(solar_charging)

        # Force immediate state updates
        self.async_schedule_update_ha_state(force_refresh=True)

        # Trigger coordinator refresh
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (disable manual control)."""
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_MANUAL_CONTROL] = False

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Force pilot back to automatic mode
        sax_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            await sax_data.pilot._async_update_pilot()  # noqa: SLF001

        self.async_write_ha_state()


class SAXBatteryOnOffSwitch(CoordinatorEntity, SwitchEntity):
    """SAX Battery On/Off switch."""

    def __init__(
        self, battery_id: str, battery: Any, coordinator: SAXBatteryCoordinator
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.battery_id = battery_id
        self.battery = battery
        self._attr_unique_id = f"{DOMAIN}_{battery_id}_switch"
        self._attr_name = f"Sax {battery_id.replace('_', ' ').title()} On/Off"

        # Get registers from coordinator's modbus_registers
        if battery_id in coordinator.modbus_registers:
            self._registers = coordinator.modbus_registers[battery_id].get(
                SAX_STATUS, {}
            )
        else:
            _LOGGER.error("Cannot access modbus registers for battery %s", battery_id)
            self._registers = {}

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        if not self.coordinator.data:
            return None

        # Try different status key patterns based on your data structure
        status_keys = [
            f"{self.battery_id}_status",
            f"{self.battery_id}_{SAX_STATUS}",
            f"{self.battery_id}_sax_status",
            SAX_STATUS,
        ]

        for status_key in status_keys:
            if status_key in self.coordinator.data:
                status_value = self.coordinator.data[status_key]
                if status_value is None:
                    continue

                # Log the actual status value for debugging
                _LOGGER.debug(
                    "Battery %s status key '%s' has value: %s (type: %s)",
                    self.battery_id,
                    status_key,
                    status_value,
                    type(status_value),
                )

                # Match against configured on/off states from registers
                if self._registers:
                    state_on = self._registers.get("state_on", 3)
                    state_off = self._registers.get("state_off", 1)

                    if isinstance(status_value, (int, float)):
                        is_on = int(status_value) == state_on
                        _LOGGER.debug(
                            "Battery %s status %s compared to on=%s, off=%s -> is_on=%s",
                            self.battery_id,
                            status_value,
                            state_on,
                            state_off,
                            is_on,
                        )
                        return is_on
                    if isinstance(status_value, dict):
                        # If status is a dict, look for relevant keys
                        if "state" in status_value:
                            return int(status_value["state"]) == state_on
                        if "status" in status_value:
                            return int(status_value["status"]) == state_on
                        if "is_on" in status_value:
                            return bool(status_value["is_on"])
                    elif isinstance(status_value, bool):
                        return status_value

                # Fallback logic if no register config
                if isinstance(status_value, (int, float)):
                    # Assume non-zero means on (adjust based on your battery behavior)
                    return status_value != 0
                if isinstance(status_value, bool):
                    return status_value

        _LOGGER.debug("No valid status found for battery %s", self.battery_id)
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.data:
            return False

        # Check if any status key exists and has non-None value
        status_keys = [
            f"{self.battery_id}_status",
            f"{self.battery_id}_{SAX_STATUS}",
            f"{self.battery_id}_sax_status",
            SAX_STATUS,
        ]

        return any(
            status_key in self.coordinator.data
            and self.coordinator.data[status_key] is not None
            for status_key in status_keys
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug("Attempting to turn ON battery %s", self.battery_id)

        if not self._registers:
            _LOGGER.error("No registers configuration for battery %s", self.battery_id)
            return

        try:
            slave_id = self._registers.get("slave", 64)
            command_on = self._registers.get("command_on", 2)
            address = self._registers.get("address", 45)
            expected_state = self._registers.get("state_on", 3)

            _LOGGER.debug(
                "Turning ON battery %s - Writing %s to register %s with device_id %s",
                self.battery_id,
                command_on,
                address,
                slave_id,
            )

            success = await self.coordinator.async_write_modbus_registers(
                self.battery_id,
                address,
                [command_on],
                device_id=slave_id,
            )

            if success:
                _LOGGER.debug(
                    "Successfully sent ON command to battery %s", self.battery_id
                )
                _LOGGER.info(
                    "Battery %s startup initiated - waiting up to 3 minutes",
                    self.battery_id,
                )

                # Wait for actual status change with 3-minute timeout
                await self._wait_for_status_change(expected_state, timeout=180)

            else:
                _LOGGER.error(
                    "Failed to send ON command to battery %s", self.battery_id
                )

        except Exception as err:
            _LOGGER.error(  # noqa: G201
                "Failed to turn on battery %s: %s", self.battery_id, err, exc_info=True
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("Attempting to turn OFF battery %s", self.battery_id)

        if not self._registers:
            _LOGGER.error("No registers configuration for battery %s", self.battery_id)
            return

        try:
            slave_id = self._registers.get("slave", 64)
            command_off = self._registers.get("command_off", 1)
            address = self._registers.get("address", 45)
            expected_state = self._registers.get("state_off", 1)

            _LOGGER.debug(
                "Turning OFF battery %s - Writing %s to register %s with device_id %s",
                self.battery_id,
                command_off,
                address,
                slave_id,
            )

            success = await self.coordinator.async_write_modbus_registers(
                self.battery_id,
                address,
                [command_off],
                device_id=slave_id,
            )

            if success:
                _LOGGER.debug(
                    "Successfully sent OFF command to battery %s", self.battery_id
                )
                _LOGGER.info(
                    "Battery %s shutdown initiated - waiting up to 3 minutes",
                    self.battery_id,
                )

                # Wait for actual status change with 3-minute timeout
                await self._wait_for_status_change(expected_state, timeout=180)

            else:
                _LOGGER.error(
                    "Failed to send OFF command to battery %s", self.battery_id
                )

        except Exception as err:
            _LOGGER.error(  # noqa: G201
                "Failed to turn off battery %s: %s", self.battery_id, err, exc_info=True
            )

    async def _wait_for_status_change(
        self, expected_state: int, timeout: int = 180
    ) -> None:
        """Wait for battery status to change to expected state."""
        start_time = asyncio.get_event_loop().time()
        check_interval = 10  # Check every 10 seconds to reduce coordinator load
        last_log_time = start_time
        log_interval = 30  # Log progress every 30 seconds

        while (elapsed := asyncio.get_event_loop().time() - start_time) < timeout:
            # Refresh coordinator data
            await self.coordinator.async_request_refresh()
            await asyncio.sleep(2)  # Give coordinator time to update

            # Check current status
            current_status = self._get_current_status()

            if current_status is not None and int(current_status) == expected_state:
                _LOGGER.info(
                    "Battery %s status changed to %s after %d seconds",
                    self.battery_id,
                    expected_state,
                    int(elapsed),
                )
                # Force entity state update
                self.async_write_ha_state()
                return

            # Log progress every 30 seconds
            if elapsed - last_log_time >= log_interval:
                _LOGGER.debug(
                    "Battery %s status is %s, waiting for %s (elapsed: %ds/%ds)",
                    self.battery_id,
                    current_status,
                    expected_state,
                    int(elapsed),
                    timeout,
                )
                last_log_time = elapsed

            # Wait before next check
            await asyncio.sleep(check_interval)

        # Timeout reached
        final_status = self._get_current_status()
        _LOGGER.warning(
            "Timeout after %d seconds waiting for battery %s status change - Expected: %s, Current: %s",
            timeout,
            self.battery_id,
            expected_state,
            final_status,
        )
        # Force final entity state update even on timeout
        self.async_write_ha_state()

    def _get_current_status(self) -> int | None:
        """Get current battery status value."""
        if not self.coordinator.data:
            return None

        status_keys = [
            f"{self.battery_id}_status",
            f"{self.battery_id}_{SAX_STATUS}",
            f"{self.battery_id}_sax_status",
            SAX_STATUS,
        ]

        for status_key in status_keys:
            if status_key in self.coordinator.data:
                status_value = self.coordinator.data[status_key]
                if status_value is not None:
                    if isinstance(status_value, (int, float)):
                        return int(status_value)
                    if isinstance(status_value, dict):
                        if "state" in status_value:
                            return int(status_value["state"])
                        if "status" in status_value:
                            return int(status_value["status"])
        return None
