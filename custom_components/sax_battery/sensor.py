"""Sensor platform for SAX Battery integration."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MASTER_BATTERY,  # Import from local const.py, not homeassistant.const
    DOMAIN,
    # Add any other constants you need from const.py
)
from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SAX Battery sensors."""
    coordinator: SAXBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Debug: Show the full config entry data
    _LOGGER.info(
        "Config entry data: %s",
        {k: v for k, v in entry.data.items() if "password" not in k.lower()},
    )

    # Get master battery from config entry data (stored during config flow)
    master_battery_id = entry.data.get(CONF_MASTER_BATTERY)

    _LOGGER.info("Master battery from config: %s", master_battery_id)

    # Fallback logic if not found in config
    if not master_battery_id and hasattr(coordinator.hub, "batteries"):
        available_batteries = list(coordinator.hub.batteries.keys())
        master_battery_id = available_batteries[0] if available_batteries else None
        _LOGGER.warning(
            "No master battery in config, using fallback: %s from available: %s",
            master_battery_id,
            available_batteries,
        )

    _LOGGER.info(
        "Final master battery selection: %s, Available batteries: %s",
        master_battery_id,
        list(coordinator.hub.batteries.keys())
        if hasattr(coordinator.hub, "batteries") and coordinator.hub.batteries
        else "None",
    )

    entities: list[SensorEntity] = []

    # Create combined sensors first (these aggregate data from all batteries)
    entities.extend(
        [
            SAXBatteryCombinedSensor(coordinator, "combined_soc", "Combined SOC"),
            SAXBatteryCombinedSensor(coordinator, "combined_power", "Combined Power"),
        ]
    )

    # Keep track of created sensors to avoid duplicates
    created_sensors: set[str] = set()

    # Create sensors for all data keys from the coordinator
    if coordinator.data:
        for key in coordinator.data:
            # Skip combined keys as they're handled above
            if key.startswith("combined_"):
                continue

            # Handle battery-specific sensors (battery_a_, battery_b_, etc.)
            if key.startswith("battery_"):
                for battery_prefix in ["battery_a_", "battery_b_", "battery_c_"]:
                    if key.startswith(battery_prefix):
                        battery_letter = battery_prefix.split("_")[1].upper()
                        battery_name = f"Battery {battery_letter}"

                        # Create unique sensor key to track duplicates
                        sensor_key = f"battery_{battery_letter.lower()}_{key.replace(battery_prefix, '')}"

                        if sensor_key not in created_sensors:
                            entities.append(
                                SAXBatterySensor(
                                    coordinator, key, battery_name=battery_name
                                )
                            )
                            created_sensors.add(sensor_key)
                        break
            else:
                # Handle non-battery-specific keys
                # Only create if this isn't duplicating a battery-specific sensor
                sensor_base_key = key

                # Check if this sensor would duplicate a battery-specific one
                is_duplicate = False
                for battery_id in ["battery_a", "battery_b", "battery_c"]:
                    battery_specific_key = f"{battery_id}_{sensor_base_key}"
                    if battery_specific_key in coordinator.data:
                        is_duplicate = True
                        break

                # Only create the non-prefixed sensor if it's not a duplicate
                if not is_duplicate and key not in created_sensors:
                    entities.append(SAXBatterySensor(coordinator, key))
                    created_sensors.add(key)

    # Add cumulative energy sensors with the configured master battery
    if master_battery_id:
        entities.extend(
            [
                SAXBatteryCumulativeEnergyProducedSensor(
                    coordinator, master_battery_id
                ),
                SAXBatteryCumulativeEnergyConsumedSensor(
                    coordinator, master_battery_id
                ),
            ]
        )

        _LOGGER.debug(
            "Added cumulative sensors using master battery: %s", master_battery_id
        )
    else:
        _LOGGER.warning("No master battery configured, skipping cumulative sensors")

    async_add_entities(entities)


class SAXBatteryCombinedSensor(CoordinatorEntity, SensorEntity):
    """Combined sensor that aggregates data from all batteries."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the combined sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type

        # Match old naming convention exactly
        match sensor_type:
            case "combined_soc":
                self._attr_name = "Sax Battery Combined SOC"
                self._attr_device_class = SensorDeviceClass.BATTERY
                self._attr_native_unit_of_measurement = PERCENTAGE
                self._attr_state_class = SensorStateClass.MEASUREMENT
            case "combined_power":
                self._attr_name = "Sax Battery Combined Power"
                self._attr_device_class = SensorDeviceClass.POWER
                self._attr_native_unit_of_measurement = UnitOfPower.WATT
                self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_unique_id = f"{DOMAIN}_{sensor_type}"

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    @property
    def native_value(self) -> float | None:
        """Return the combined value."""
        if not self.coordinator.data:
            return None

        return self.coordinator.data.get(self._sensor_type)

    async def async_update(self) -> None:
        """Update the sensor by recalculating combined values."""
        # Force coordinator update first
        await self.coordinator.async_request_refresh()

        # Calculate combined values similar to old implementation
        match self._sensor_type:
            case "combined_power":
                await self._calculate_combined_power()
            case "combined_soc":
                await self._calculate_combined_soc()

    async def _calculate_combined_power(self) -> None:
        """Calculate combined power from all batteries."""
        total_power = 0.0

        # Sum power from all configured batteries
        for battery_id in self.coordinator.batteries:
            power_key = f"{battery_id}_power"
            if (
                self.coordinator.data
                and power_key in self.coordinator.data
                and self.coordinator.data[power_key] is not None
            ):
                total_power += self.coordinator.data[power_key]

        # Store in coordinator data for consistency
        if not self.coordinator.data:
            self.coordinator.data = {}
        self.coordinator.data["combined_power"] = round(total_power, 1)

        # Also store in combined_data for backward compatibility
        if not hasattr(self.coordinator, "combined_data"):
            self.coordinator.combined_data = {}
        self.coordinator.combined_data["sax_battery_combined_power"] = round(
            total_power, 1
        )

        self._attr_native_value = round(total_power, 1)

    async def _calculate_combined_soc(self) -> None:
        """Calculate average SOC from all batteries."""
        total_soc = 0.0
        valid_batteries = 0

        # Calculate average SOC from all configured batteries
        for battery_id in self.coordinator.batteries:
            soc_key = f"{battery_id}_soc"
            if (
                self.coordinator.data
                and soc_key in self.coordinator.data
                and self.coordinator.data[soc_key] is not None
            ):
                total_soc += self.coordinator.data[soc_key]
                valid_batteries += 1

        # Calculate average if we have valid data
        if valid_batteries > 0:
            combined_soc = round(total_soc / valid_batteries, 1)

            # Store in coordinator data
            if not self.coordinator.data:
                self.coordinator.data = {}
            self.coordinator.data["combined_soc"] = combined_soc

            # Also store in combined_data for backward compatibility (matching old const)
            if not hasattr(self.coordinator, "combined_data"):
                self.coordinator.combined_data = {}
            self.coordinator.combined_data["sax_battery_combined_soc"] = combined_soc

            self._attr_native_value = combined_soc
        else:
            # No valid SOC data
            if self.coordinator.data:
                self.coordinator.data["combined_soc"] = None
            if hasattr(self.coordinator, "combined_data"):
                self.coordinator.combined_data["sax_battery_combined_soc"] = None
            self._attr_native_value = None


class SAXBatteryCumulativeEnergyProducedSensor(CoordinatorEntity, SensorEntity):
    """SAX Battery Cumulative Energy Produced sensor - accumulates charging energy."""

    def __init__(
        self, coordinator: SAXBatteryCoordinator, master_battery_id: str | None
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._master_battery_id = master_battery_id
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_name = "Sax Battery Cumulative Energy Produced"
        self._attr_unique_id = f"{DOMAIN}_cumulative_energy_produced"
        self._last_update_time: datetime | None = None
        self._cumulative_value = 0.0

        # Log initialization details
        _LOGGER.info(
            "Cumulative Energy Produced sensor initialized with master battery: %s",
            self._master_battery_id,
        )

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def native_value(self) -> float:
        """Return the native value of the sensor."""
        # Update cumulative value when requested
        self._update_cumulative_value()
        return self._cumulative_value

    def _update_cumulative_value(self) -> None:
        """Update the cumulative value if enough time has passed."""
        current_time = datetime.now()

        # Only update the cumulative value once per hour
        should_update = (
            self._last_update_time is None
            or (current_time - self._last_update_time).total_seconds() >= 3600
        )

        if should_update:
            _LOGGER.debug(
                "Cumulative Energy Produced: Time condition met, checking data"
            )

            # Get the current energy produced value from master battery
            if self.coordinator.data and self._master_battery_id:
                # Look for the master battery's energy produced sensor data
                master_key = f"{self._master_battery_id}_energy_produced"
                current_value = self.coordinator.data.get(master_key)

                # Debug: Show what master battery we're using and what keys are available
                available_keys = (
                    list(self.coordinator.data.keys()) if self.coordinator.data else []
                )
                energy_produced_keys = [
                    k for k in available_keys if "energy_produced" in k
                ]

                _LOGGER.info(
                    "Cumulative Energy Produced: Master battery ID: %s, "
                    "Looking for key: '%s', Found value: %s, "
                    "Available energy_produced keys: %s, "
                    "All available keys: %s",
                    self._master_battery_id,
                    master_key,
                    current_value,
                    energy_produced_keys,
                    available_keys[:10],  # Show first 10 keys to avoid log spam
                )

                if current_value is not None and current_value > 0:
                    # Update the cumulative value (accumulate charging energy)
                    old_cumulative = self._cumulative_value
                    self._cumulative_value += current_value
                    # Update the last update time
                    self._last_update_time = current_time

                    _LOGGER.info(
                        "Cumulative Energy Produced: Master battery %s - Added %s kWh to cumulative total. "
                        "Old: %s kWh, New: %s kWh",
                        self._master_battery_id,
                        current_value,
                        old_cumulative,
                        self._cumulative_value,
                    )
                else:
                    _LOGGER.debug(
                        "Cumulative Energy Produced: Current value is None or <= 0: %s",
                        current_value,
                    )
            else:
                _LOGGER.debug(
                    "Cumulative Energy Produced: No coordinator data or master battery ID. "
                    "Data exists: %s, Master ID: %s",
                    self.coordinator.data is not None,
                    self._master_battery_id,
                )
        else:
            time_diff = (current_time - self._last_update_time).total_seconds()
            _LOGGER.debug(
                "Cumulative Energy Produced: Too soon to update. Time since last update: %s seconds",
                time_diff,
            )


class SAXBatteryCumulativeEnergyConsumedSensor(CoordinatorEntity, SensorEntity):
    """SAX Battery Cumulative Energy Consumed sensor - accumulates discharging energy."""

    def __init__(
        self, coordinator: SAXBatteryCoordinator, master_battery_id: str | None
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._master_battery_id = master_battery_id
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_name = "Sax Battery Cumulative Energy Consumed"
        self._attr_unique_id = f"{DOMAIN}_cumulative_energy_consumed"
        self._last_update_time: datetime | None = None
        self._cumulative_value = 0.0

        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    @property
    def native_value(self) -> float:
        """Return the native value of the sensor."""
        # Update cumulative value when requested
        self._update_cumulative_value()
        return self._cumulative_value

    def _update_cumulative_value(self) -> None:
        """Update the cumulative value if enough time has passed."""
        current_time = datetime.now()

        _LOGGER.debug(
            "Cumulative Energy Consumed: Checking update conditions. "
            "Last update: %s, Current time: %s, Master battery: %s",
            self._last_update_time,
            current_time,
            self._master_battery_id,
        )

        # Only update the cumulative value once per hour
        should_update = (
            self._last_update_time is None
            or (current_time - self._last_update_time).total_seconds() >= 3600
        )

        if should_update:
            _LOGGER.debug(
                "Cumulative Energy Consumed: Time condition met, checking data"
            )

            # Get the current energy consumed value from master battery
            if self.coordinator.data and self._master_battery_id:
                # Look for the master battery's energy consumed sensor data
                master_key = f"{self._master_battery_id}_energy_consumed"
                current_value = self.coordinator.data.get(master_key)

                _LOGGER.debug(
                    "Cumulative Energy Consumed: Looking for key '%s', found value: %s (type: %s)",
                    master_key,
                    current_value,
                    type(current_value).__name__
                    if current_value is not None
                    else "None",
                )

                # Debug: Show all available keys
                available_keys = (
                    list(self.coordinator.data.keys()) if self.coordinator.data else []
                )
                energy_keys = [k for k in available_keys if "energy" in k.lower()]
                _LOGGER.debug(
                    "Available energy-related keys in coordinator data: %s",
                    energy_keys,
                )

                if current_value is not None and current_value > 0:
                    # Update the cumulative value (accumulate discharging energy)
                    old_cumulative = self._cumulative_value
                    self._cumulative_value += current_value
                    # Update the last update time
                    self._last_update_time = current_time

                    _LOGGER.info(
                        "Cumulative Energy Consumed: Added %s kWh to cumulative total. "
                        "Old: %s kWh, New: %s kWh",
                        current_value,
                        old_cumulative,
                        self._cumulative_value,
                    )
                else:
                    _LOGGER.debug(
                        "Cumulative Energy Consumed: Current value is None or <= 0: %s",
                        current_value,
                    )
            else:
                _LOGGER.debug(
                    "Cumulative Energy Consumed: No coordinator data or master battery ID. "
                    "Data exists: %s, Master ID: %s",
                    self.coordinator.data is not None,
                    self._master_battery_id,
                )
        else:
            time_diff = (current_time - self._last_update_time).total_seconds()
            _LOGGER.debug(
                "Cumulative Energy Consumed: Too soon to update. Time since last update: %s seconds",
                time_diff,
            )


class SAXBatterySensor(CoordinatorEntity, SensorEntity):
    """SAX Battery sensor using coordinator."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        data_key: str,
        battery_name: str | None = None,
    ) -> None:
        """Initialize the SAX Battery sensor."""
        super().__init__(coordinator)
        self._data_key = data_key
        self._battery_name = battery_name

        # Use battery-specific name if provided
        if battery_name:
            # Remove battery prefix (battery_a_, battery_b_, etc.) from data key
            sensor_key = data_key
            for prefix in ["battery_a_", "battery_b_", "battery_c_"]:
                if data_key.startswith(prefix):
                    sensor_key = data_key.replace(prefix, "")
                    break

            sensor_base_name = self._get_sensor_name(sensor_key)
            # Create entity name in format: SAX Battery A Sensor Name
            battery_letter = battery_name.split()[-1].upper()
            self._attr_name = f"Sax Battery {battery_letter} {sensor_base_name}"
            # Update unique_id to match the naming pattern you want: sax_battery_a_sensor_key
            self._attr_unique_id = (
                f"{DOMAIN}_battery_{battery_letter.lower()}_{sensor_key}"
            )
        else:
            self._attr_name = self._get_sensor_name(data_key)
            self._attr_unique_id = f"{DOMAIN}_{data_key}"

        self._attr_device_class, self._attr_native_unit_of_measurement = (
            self._get_device_class_and_unit(data_key)
        )
        self._attr_state_class = self._get_state_class(data_key)

        # Add device info - use coordinator device_id for consistency
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    def _get_sensor_name(self, key: str) -> str:
        """Get human-readable sensor name."""
        name_mapping = {
            "soc": "SOC",
            "power": "Power",
            "smartmeter": "Smart Meter",
            "capacity": "Capacity",
            "cycles": "Cycles",
            "temp": "Temperature",
            "energy_produced": "Energy Produced",
            "energy_consumed": "Energy Consumed",
            "voltage_l1": "Voltage L1",
            "voltage_l2": "Voltage L2",
            "voltage_l3": "Voltage L3",
            "current_l1": "Current L1",
            "current_l2": "Current L2",
            "current_l3": "Current L3",
            "grid_frequency": "Grid Frequency",
            "active_power_l1": "Active Power L1",
            "active_power_l2": "Active Power L2",
            "active_power_l3": "Active Power L3",
            "apparent_power": "Apparent Power",
            "reactive_power": "Reactive Power",
            "power_factor": "Power Factor",
            "phase_currents_sum": "Phase Currents Sum",
            "ac_power_total": "AC Power Total",
            "storage_status": "Storage Status",
            "smartmeter_voltage_l1": "Smart Meter Voltage L1",
            "smartmeter_voltage_l2": "Smart Meter Voltage L2",
            "smartmeter_voltage_l3": "Smart Meter Voltage L3",
            "smartmeter_current_l1": "Smart Meter Current L1",
            "smartmeter_current_l2": "Smart Meter Current L2",
            "smartmeter_current_l3": "Smart Meter Current L3",
            "smartmeter_total_power": "Smart Meter Total Power",
        }
        return name_mapping.get(key, key.replace("_", " ").title())

    def _get_device_class_and_unit(
        self, key: str
    ) -> tuple[SensorDeviceClass | None, str | None]:
        """Get device class and unit for sensor."""
        # Remove battery prefix for lookup
        lookup_key = key
        for prefix in ["battery_a_", "battery_b_", "battery_c_"]:
            if key.startswith(prefix):
                lookup_key = key.replace(prefix, "")
                break

        mapping = {
            "soc": (SensorDeviceClass.BATTERY, PERCENTAGE),
            "power": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "capacity": (SensorDeviceClass.ENERGY, UnitOfEnergy.WATT_HOUR),
            "temp": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
            "energy_produced": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR),
            "energy_consumed": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR),
            "voltage_l1": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "voltage_l2": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "voltage_l3": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
            "current_l1": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "current_l2": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "current_l3": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
            "grid_frequency": (SensorDeviceClass.FREQUENCY, UnitOfFrequency.HERTZ),
            "active_power_l1": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "active_power_l2": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "active_power_l3": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "apparent_power": (SensorDeviceClass.APPARENT_POWER, "VA"),
            "reactive_power": (
                SensorDeviceClass.REACTIVE_POWER,
                "var",
            ),  # Fixed: was "VAR"
            "power_factor": (SensorDeviceClass.POWER_FACTOR, PERCENTAGE),
            "phase_currents_sum": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "ac_power_total": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "smartmeter_voltage_l1": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "smartmeter_voltage_l2": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "smartmeter_voltage_l3": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "smartmeter_current_l1": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "smartmeter_current_l2": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "smartmeter_current_l3": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "smartmeter_total_power": (SensorDeviceClass.POWER, UnitOfPower.WATT),
        }
        return mapping.get(lookup_key, (None, None))

    def _get_state_class(self, key: str) -> SensorStateClass | None:
        """Get state class for sensor."""
        # Remove battery prefix for lookup
        lookup_key = key
        for prefix in ["battery_a_", "battery_b_", "battery_c_"]:
            if key.startswith(prefix):
                lookup_key = key.replace(prefix, "")
                break

        if lookup_key in ["energy_produced", "energy_consumed", "cycles"]:
            return SensorStateClass.TOTAL_INCREASING
        if lookup_key == "capacity":  # Capacity should be TOTAL, not MEASUREMENT
            return SensorStateClass.TOTAL
        if lookup_key in [
            "soc",
            "power",
            "temp",
            "voltage_l1",
            "voltage_l2",
            "voltage_l3",
            "current_l1",
            "current_l2",
            "current_l3",
            "grid_frequency",
            "active_power_l1",
            "active_power_l2",
            "active_power_l3",
            "apparent_power",
            "reactive_power",
            "power_factor",  # Added missing power_factor
            "phase_currents_sum",
            "ac_power_total",
            "smartmeter_voltage_l1",
            "smartmeter_voltage_l2",
            "smartmeter_voltage_l3",
            "smartmeter_current_l1",
            "smartmeter_current_l2",
            "smartmeter_current_l3",
            "smartmeter_total_power",
        ]:
            return SensorStateClass.MEASUREMENT
        return None

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._data_key in (
            self.coordinator.data or {}
        )
