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
                if hasattr(master_battery._data_manager, "batteries"):
                    battery = master_battery._data_manager.batteries.get(battery_id)

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
        self._attr_name = "SAX Battery Solar Charging"
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
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_ENABLE_SOLAR_CHARGING] = True
        # When solar charging is enabled, manual control must be disabled
        new_data[CONF_MANUAL_CONTROL] = False

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data=new_data,
        )

        # Update pilot mode
        sax_data = self.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        if hasattr(sax_data, "pilot") and sax_data.pilot:
            await sax_data.pilot.set_solar_charging(True)

        self.async_write_ha_state()
        # Trigger update of manual control switch
        self.hass.async_create_task(self.coordinator.async_request_refresh())

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
        self._attr_name = "SAX Battery Manual Control"
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
        new_data = dict(self.coordinator.config_entry.data)
        new_data[CONF_MANUAL_CONTROL] = True
        # When manual control is enabled, solar charging must be disabled
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
        # Trigger update of solar charging switch
        self.hass.async_create_task(self.coordinator.async_request_refresh())

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
            await sax_data.pilot._async_update_pilot()

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
        self._attr_name = f"SAX {battery_id.replace('_', ' ').title()} On/Off"

        # Get registers from the battery's data manager
        if hasattr(battery, "_data_manager") and hasattr(
            battery._data_manager, "modbus_registers"
        ):
            self._registers = battery._data_manager.modbus_registers[battery_id][
                SAX_STATUS
            ]
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
        # Access battery data through coordinator
        if not self.coordinator.data:
            return None

        # Try different status key patterns
        status_keys = [
            f"{self.battery_id}_status",
            f"{self.battery_id}_{SAX_STATUS}",
            SAX_STATUS,
        ]

        for status_key in status_keys:
            if status_key in self.coordinator.data:
                status = self.coordinator.data[status_key]
                if status is not None:
                    # Adjust this logic based on your actual battery status structure
                    if isinstance(status, dict):
                        return bool(status.get("is_charging", False))
                    elif isinstance(status, bool):
                        return status
                    elif isinstance(status, (int, float)):
                        return bool(status)
                    break

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
            SAX_STATUS,
        ]

        for status_key in status_keys:
            if (
                status_key in self.coordinator.data
                and self.coordinator.data[status_key] is not None
            ):
                return True

        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug("Attempting to turn ON battery %s", self.battery_id)

        try:
            if not hasattr(self.battery, "_data_manager"):
                _LOGGER.error(
                    "Battery data manager not available for %s", self.battery_id
                )
                return

            client = self.battery._data_manager.modbus_clients.get(self.battery_id)
            if client is None:
                _LOGGER.error("No Modbus client found for battery %s", self.battery_id)
                return

            if not self._registers:
                _LOGGER.error(
                    "No registers configuration for battery %s", self.battery_id
                )
                return

            slave_id = self._registers.get("slave", 64)
            command_on = self._registers["command_on"]
            address = self._registers["address"]

            _LOGGER.debug(
                "Turning ON battery %s - Writing %s to register %s with slave %s",
                self.battery_id,
                command_on,
                address,
                slave_id,
            )

            # Short delay before command
            await asyncio.sleep(0.1)

            async def _async_write_registers() -> bool:
                """Write registers asynchronously."""
                try:
                    result = client.write_registers(
                        address,
                        [command_on],
                        slave=slave_id,
                    )

                    # Handle async client
                    if asyncio.iscoroutine(result):
                        result = await result

                    return hasattr(result, "function_code") and not (
                        hasattr(result, "isError") and result.isError()
                    )
                except Exception as exc:
                    _LOGGER.debug(
                        "Exception in write_registers: %s", exc, exc_info=True
                    )
                    return False

            success = await _async_write_registers()

            if success:
                _LOGGER.debug("Successfully turned ON battery %s", self.battery_id)
                # Wait for command to take effect
                await asyncio.sleep(3.0)  # Reduced from 180s
                # Update the battery data
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to turn ON battery %s", self.battery_id)

        except Exception as err:
            _LOGGER.error(
                "Failed to turn on battery %s: %s", self.battery_id, err, exc_info=True
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("Attempting to turn OFF battery %s", self.battery_id)

        try:
            if not hasattr(self.battery, "_data_manager"):
                _LOGGER.error(
                    "Battery data manager not available for %s", self.battery_id
                )
                return

            client = self.battery._data_manager.modbus_clients.get(self.battery_id)
            if client is None:
                _LOGGER.error("No Modbus client found for battery %s", self.battery_id)
                return

            if not self._registers:
                _LOGGER.error(
                    "No registers configuration for battery %s", self.battery_id
                )
                return

            slave_id = self._registers.get("slave", 64)
            command_off = self._registers["command_off"]
            address = self._registers["address"]

            _LOGGER.debug(
                "Turning OFF battery %s - Writing %s to register %s with slave %s",
                self.battery_id,
                command_off,
                address,
                slave_id,
            )

            # Short delay before command
            await asyncio.sleep(0.1)

            async def _async_write_registers() -> bool:
                """Write registers asynchronously."""
                try:
                    result = client.write_registers(
                        address,
                        [command_off],
                        slave=slave_id,
                    )

                    # Handle async client
                    if asyncio.iscoroutine(result):
                        result = await result

                    return hasattr(result, "function_code") and not (
                        hasattr(result, "isError") and result.isError()
                    )
                except Exception as exc:
                    _LOGGER.debug(
                        "Exception in write_registers: %s", exc, exc_info=True
                    )
                    return False

            success = await _async_write_registers()

            if success:
                _LOGGER.debug("Successfully turned OFF battery %s", self.battery_id)
                # Wait for command to take effect
                await asyncio.sleep(3.0)  # Reduced from 120s
                # Update the battery data
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to turn OFF battery %s", self.battery_id)

        except Exception as err:
            _LOGGER.error(
                "Failed to turn off battery %s: %s", self.battery_id, err, exc_info=True
            )
