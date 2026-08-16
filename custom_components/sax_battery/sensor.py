"""SAX Battery sensor platform."""

from __future__ import annotations

from datetime import datetime
import logging
import time
from typing import Any, Literal

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import txid_error_tracker
from .const import (
    AGGREGATED_ITEMS,
    ATTR_ATTRIBUTION,
    ATTRIBUTION,
    BATTERY_IDS,
    BMS_UNAVAILABILITY_RATE,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_PROTOCOL_MODE,
    COORDINATOR_CIRCUIT_BREAKER,
    COORDINATOR_CYCLE_TIME,
    COORDINATOR_ERROR_RATE,
    DIAGNOSTIC_ITEMS,
    DOMAIN,
    PROTOCOL_MODE_LEGACY,
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CHARGED,
    SAX_CUMULATIVE_ENERGY_DISCHARGED,
    SAX_SOC,
    TXID_ERROR_RATE,
)
from .coordinator import (
    CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    SAXBatteryCoordinator,
)
from .energy_integration import EnergyIntegrator
from .entity_keys import (
    SAX_ENERGY_CHARGED_DAILY,
    SAX_ENERGY_CHARGED_MONTHLY,
    SAX_ENERGY_DISCHARGED_DAILY,
    SAX_ENERGY_DISCHARGED_MONTHLY,
    SAX_POWER,
)
from .entity_utils import filter_items_by_type, filter_sax_items_by_type
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem, SAXItem

_LOGGER = logging.getLogger(__name__)

# Coordinator-based sensors don't need update serialization
PARALLEL_UPDATES = 0

# Service name for resetting all energy sensors
SERVICE_RESET_ENERGY_SENSORS = "reset_energy_sensors"

# Period energy items handled by SAXBatteryPeriodEnergySensor, not SAXBatteryCalculatedSensor
_PERIOD_ENERGY_ITEM_NAMES: frozenset[str] = frozenset(
    {
        SAX_ENERGY_DISCHARGED_DAILY,
        SAX_ENERGY_CHARGED_DAILY,
        SAX_ENERGY_DISCHARGED_MONTHLY,
        SAX_ENERGY_CHARGED_MONTHLY,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAX Battery sensor platform with multi-battery support."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = integration_data["coordinators"]
    sax_data = integration_data["sax_data"]

    entities: list[SensorEntity] = []

    # Create sensors for each battery using new constants
    for battery_id, coordinator in coordinators.items():
        # Validate battery_id is in allowed list
        if battery_id not in BATTERY_IDS:
            _LOGGER.warning("Invalid battery ID %s, skipping", battery_id)
            continue

        # Get battery-specific configuration
        battery_config = coordinator.battery_config
        is_master = battery_config.get(CONF_BATTERY_IS_MASTER, False)
        phase = battery_config.get(CONF_BATTERY_PHASE, "L1")

        _LOGGER.debug(
            "Setting up sensors for %s battery %s (%s)",
            "master" if is_master else "slave",
            battery_id,
            phase,
        )

        # Filter sensor items for this battery
        sensor_items = filter_items_by_type(
            sax_data.get_modbus_items_for_battery(battery_id),
            TypeConstants.SENSOR,
            config_entry,
            battery_id,
        )

        for modbus_item in sensor_items:
            if isinstance(modbus_item, ModbusItem):
                entities.append(  # noqa: PERF401
                    SAXBatteryModbusSensor(
                        coordinator=coordinator,
                        battery_id=battery_id,
                        modbus_item=modbus_item,
                    )
                )

        # 2. Create diagnostic sensors (coordinator statistics)
        # Only create for master battery to avoid duplicates
        if is_master:
            entities.extend(
                SAXBatteryCoordinatorCycleSensor(
                    coordinator=coordinator,
                    sax_item=diag_item,
                )
                for diag_item in DIAGNOSTIC_ITEMS
                if isinstance(diag_item, SAXItem)
            )

            _LOGGER.debug(
                "Added %d diagnostic sensors for master battery %s",
                len(DIAGNOSTIC_ITEMS),
                battery_id,
            )

        _LOGGER.info(
            "Added %d modbus sensor entities for %s", len(sensor_items), battery_id
        )

    # Create system-wide calculated sensors only once (using master battery coordinator)
    # Find master coordinator - check both the coordinator's battery_config AND sax_data
    master_coordinator = None
    for battery_id, coordinator in coordinators.items():
        # Check coordinator's battery_config first
        is_master = coordinator.battery_config.get(CONF_BATTERY_IS_MASTER, False)

        # If not found in coordinator, check sax_data as fallback
        if not is_master and battery_id in sax_data.batteries:
            battery_model = sax_data.batteries[battery_id]
            is_master = battery_model.is_master

        if is_master:
            master_coordinator = coordinator
            _LOGGER.debug(
                "Found master battery coordinator: %s (is_master=%s)",
                battery_id,
                is_master,
            )
            break

    if master_coordinator:
        # Get calculated sensor items
        sax_items = filter_sax_items_by_type(
            sax_data.get_sax_items_for_battery(sax_data.master_battery_id or "bess_a"),
            TypeConstants.SENSOR,
        )

        # Create calculated sensors (exclude period energy items handled separately)
        for sax_item in sax_items:
            if sax_item.name in _PERIOD_ENERGY_ITEM_NAMES:
                continue
            sax_item.set_coordinators(coordinators)
            entities.append(
                SAXBatteryCalculatedSensor(
                    master_coordinator,
                    sax_item,
                    coordinators,
                )
            )

        _LOGGER.debug(
            "Created %d calculated sensors using master coordinator", len(sax_items)
        )

        # Create period-derived energy sensors (daily and monthly)
        # Source items for subscriptions (look up by name in AGGREGATED_ITEMS)
        source_discharged = next(
            i for i in AGGREGATED_ITEMS if i.name == SAX_CUMULATIVE_ENERGY_DISCHARGED
        )
        source_charged = next(
            i for i in AGGREGATED_ITEMS if i.name == SAX_CUMULATIVE_ENERGY_CHARGED
        )
        _period_specs: list[tuple[str, SAXItem, Literal["daily", "monthly"]]] = [
            (SAX_ENERGY_DISCHARGED_DAILY, source_discharged, "daily"),
            (SAX_ENERGY_CHARGED_DAILY, source_charged, "daily"),
            (SAX_ENERGY_DISCHARGED_MONTHLY, source_discharged, "monthly"),
            (SAX_ENERGY_CHARGED_MONTHLY, source_charged, "monthly"),
        ]
        for item_name, source_item, period in _period_specs:
            period_sax_item = next(i for i in AGGREGATED_ITEMS if i.name == item_name)
            entities.append(
                SAXBatteryPeriodEnergySensor(
                    master_coordinator,
                    period_sax_item,
                    source_item,
                    period,
                )
            )

        _LOGGER.debug("Created 4 period energy sensors (daily/monthly)")
    else:
        _LOGGER.warning(
            "No master battery found for cumulative energy calculation. "
            "Available batteries: %s, battery configs: %s",
            list(coordinators.keys()),
            {
                bid: coord.battery_config.get(CONF_BATTERY_IS_MASTER, "not set")
                for bid, coord in coordinators.items()
            },
        )

    if entities:
        async_add_entities(entities)
        _LOGGER.info(
            "Set up %d sensor entities across %d batteries",
            len(entities),
            len(coordinators),
        )

    # Collect energy sensor references for the reset service
    period_sensors: list[SAXBatteryPeriodEnergySensor] = [
        e for e in entities if isinstance(e, SAXBatteryPeriodEnergySensor)
    ]
    cumulative_sensors: list[SAXBatteryCalculatedSensor] = [
        e
        for e in entities
        if isinstance(e, SAXBatteryCalculatedSensor)
        and e._sax_item.name  # noqa: SLF001
        in (SAX_CUMULATIVE_ENERGY_DISCHARGED, SAX_CUMULATIVE_ENERGY_CHARGED)
    ]

    async def _handle_reset_energy_sensors(
        _call: object,
    ) -> None:
        """Handle sax_battery.reset_energy_sensors service call."""
        _LOGGER.info(
            "Resetting %d cumulative and %d period energy sensors",
            len(cumulative_sensors),
            len(period_sensors),
        )
        for cum_sensor in cumulative_sensors:
            await cum_sensor.async_reset_energy()
        for period_sensor in period_sensors:
            await period_sensor.async_reset_period()

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_ENERGY_SENSORS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_ENERGY_SENSORS,
            _handle_reset_energy_sensors,
        )
        config_entry.async_on_unload(
            lambda: hass.services.async_remove(DOMAIN, SERVICE_RESET_ENERGY_SENSORS)
        )
        _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_RESET_ENERGY_SENSORS)


class SAXBatteryModbusSensor(CoordinatorEntity[SAXBatteryCoordinator], SensorEntity):
    """Implementation of a SAX Battery modbus sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        battery_id: str,
        modbus_item: ModbusItem,
    ) -> None:
        """Initialize the modbus sensor."""
        super().__init__(coordinator)
        self._modbus_item = modbus_item
        self._battery_id = battery_id

        # Generate unique ID using get_unique_id_for_item
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=modbus_item,
            battery_id=battery_id,  # For per-battery entities
        )

        # Set entity description from modbus item if available
        if self._modbus_item.entitydescription is not None:
            self.entity_description = self._modbus_item.entitydescription  # type: ignore[assignment]

        # Set entity registry enabled state from ModbusItem
        # CONF_PROTOCOL_MODE == legacy shall not enable modbus_item with battery_device_id==100

        if coordinator.config_entry is None or coordinator.config_entry.data is None:
            _LOGGER.warning(
                "Coordinator config_entry.data is None for battery %s; "
                "defaulting entity registry enabled state to False",
                battery_id,
            )
            self._attr_entity_registry_enabled_default = False
        else:
            config_data = coordinator.config_entry.data
            if (
                config_data.get(CONF_PROTOCOL_MODE) == PROTOCOL_MODE_LEGACY
                and self._battery_id == "100"
            ):
                self._attr_entity_registry_enabled_default = False
            else:
                self._attr_entity_registry_enabled_default = getattr(
                    self._modbus_item, "enabled_by_default", True
                )

        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            # Remove "Sax " prefix from entity description name
            self.entity_description.key.removeprefix("Smartmeter ")  # beautify the key
            entity_name = str(self.entity_description.name)
            entity_name = entity_name.removeprefix("Sax ")
            self._attr_name = entity_name

<<<<<<< HEAD
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
            # SunSpec interface (slave 100) - derived, scale-corrected values
            "sunspec_pv_power": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "sunspec_max_power_reference": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "sunspec_grid_frequency": (
                SensorDeviceClass.FREQUENCY,
                UnitOfFrequency.HERTZ,
            ),
            "sunspec_grid_power_sum": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "sunspec_grid_power_l1": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "sunspec_grid_power_l2": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "sunspec_grid_power_l3": (SensorDeviceClass.POWER, UnitOfPower.WATT),
            "sunspec_grid_current_sum": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "sunspec_grid_current_l1": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "sunspec_grid_current_l2": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "sunspec_grid_current_l3": (
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
            ),
            "sunspec_grid_voltage_ln_avg": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "sunspec_grid_voltage_l1": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "sunspec_grid_voltage_l2": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "sunspec_grid_voltage_l3": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "sunspec_grid_voltage_ll_avg": (
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
            ),
            "sunspec_grid_apparent_power_sum": (
                SensorDeviceClass.APPARENT_POWER,
                "VA",
            ),
            "sunspec_grid_reactive_power_sum": (
                SensorDeviceClass.REACTIVE_POWER,
                "var",
            ),
            "sunspec_grid_power_factor_sum": (
                SensorDeviceClass.POWER_FACTOR,
                None,
            ),
            "sunspec_grid_power_factor_l1": (
                SensorDeviceClass.POWER_FACTOR,
                None,
            ),
            "sunspec_grid_power_factor_l2": (
                SensorDeviceClass.POWER_FACTOR,
                None,
            ),
            "sunspec_grid_power_factor_l3": (
                SensorDeviceClass.POWER_FACTOR,
                None,
            ),
            "sunspec_capacity": (SensorDeviceClass.ENERGY, UnitOfEnergy.WATT_HOUR),
            "sunspec_available_charge_power": (
                SensorDeviceClass.POWER,
                UnitOfPower.WATT,
            ),
            "sunspec_available_discharge_power": (
                SensorDeviceClass.POWER,
                UnitOfPower.WATT,
            ),
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
        if lookup_key in (
            "capacity",
            "sunspec_capacity",
        ):  # Capacity should be TOTAL, not MEASUREMENT
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
            "sunspec_pv_power",
            "sunspec_max_power_reference",
            "sunspec_grid_frequency",
            "sunspec_grid_power_sum",
            "sunspec_grid_power_l1",
            "sunspec_grid_power_l2",
            "sunspec_grid_power_l3",
            "sunspec_grid_current_sum",
            "sunspec_grid_current_l1",
            "sunspec_grid_current_l2",
            "sunspec_grid_current_l3",
            "sunspec_grid_voltage_ln_avg",
            "sunspec_grid_voltage_l1",
            "sunspec_grid_voltage_l2",
            "sunspec_grid_voltage_l3",
            "sunspec_grid_voltage_ll_avg",
            "sunspec_grid_apparent_power_sum",
            "sunspec_grid_reactive_power_sum",
            "sunspec_grid_power_factor_sum",
            "sunspec_grid_power_factor_l1",
            "sunspec_grid_power_factor_l2",
            "sunspec_grid_power_factor_l3",
            "sunspec_available_charge_power",
            "sunspec_available_discharge_power",
        ]:
            return SensorStateClass.MEASUREMENT
        return None
=======
        # Set device info
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            battery_id, self._modbus_item.device
        )
>>>>>>> 4670f53 (use coordinator pattern for sax-power battery control)

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._modbus_item.name)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        return {
            "battery_id": self._battery_id,
            "modbus_address": getattr(self._modbus_item, "address", None),
            "last_update": getattr(self.coordinator, "last_update_success_time", None),
            "raw_value": self.coordinator.data.get(self._modbus_item.name)
            if self.coordinator.data
            else None,
        }


class SAXBatteryCalculatedSensor(
    CoordinatorEntity[SAXBatteryCoordinator], RestoreSensor
):
    """SAX Battery calculated sensor entity with system-wide aggregation."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({ATTR_ATTRIBUTION})

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
        coordinators: dict[str, SAXBatteryCoordinator],
    ) -> None:
        """Initialize the calculated sensor entity.

        Args:
            coordinators: Dictionary of battery_id -> coordinator for aggregation
            sax_item: SAXItem containing entity configuration
            coordinator: Coordinator for the master battery

        Security:
            OWASP A05: Validates coordinators and item configuration
        """
        super().__init__(coordinator)
        self._sax_item = sax_item
        self._coordinators = coordinators

        # Set coordinators on the SAX item for calculations
        self._sax_item.set_coordinators(coordinators)

        # Generate unique ID using class name pattern
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=sax_item,
            battery_id=None,  # For per-battery entities
        )

        # Set entity description from sax item if available
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment]

        if (
            hasattr(self, "entity_description")
            and self.entity_description
            and hasattr(self.entity_description, "name")
            and isinstance(self.entity_description.name, str)
        ):
            self._attr_name = self.entity_description.name.removeprefix("Sax ")

        # Per-battery energy integrators for trapezoidal integration
        # Positive SAX_POWER = charging -> energy charged into battery
        # Negative SAX_POWER = discharging -> energy discharged from battery (absolute value)
        self._discharged_integrators: dict[str, EnergyIntegrator] = {
            battery_id: EnergyIntegrator() for battery_id in coordinators
        }
        self._charged_integrators: dict[str, EnergyIntegrator] = {
            battery_id: EnergyIntegrator() for battery_id in coordinators
        }

        # Set system device info
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            "cluster", DeviceConstants.SYS
        )

    @property
    def native_value(self) -> float | None:
        """Return the calculated sensor value.

        Performance:
            O(n) iteration over coordinators - efficient for small battery counts

        Security:
            OWASP A05: Validates coordinator data availability
        """
        if self._sax_item.name == SAX_COMBINED_SOC:
            return self._calculate_combined_soc()
        if self._sax_item.name in (
            SAX_CUMULATIVE_ENERGY_DISCHARGED,
            SAX_CUMULATIVE_ENERGY_CHARGED,
        ):
            self._integrate_all_batteries()
            if self._sax_item.name == SAX_CUMULATIVE_ENERGY_DISCHARGED:
                return self._get_total_discharged()
            return self._get_total_charged()

        _LOGGER.warning("Unknown calculation type for sensor: %s", self._sax_item.name)
        return None

    def _calculate_combined_soc(self) -> float | None:
        """Calculate combined SOC from all batteries."""
        total_soc = 0.0
        battery_count = 0

        for coordinator in self._coordinators.values():
            if not coordinator.data:
                continue

            soc_value = coordinator.data.get(SAX_SOC)
            if soc_value is not None:
                try:
                    total_soc += float(soc_value)
                    battery_count += 1
                except ValueError, TypeError:
                    _LOGGER.debug(
                        "Invalid SOC value for battery %s: %s",
                        coordinator.battery_id,
                        soc_value,
                    )

        if battery_count == 0:
            return None

        return round(total_soc / battery_count, 1)

    def _integrate_all_batteries(self) -> None:
        """Feed current power readings from all batteries into integrators.

        For each battery, reads SAX_POWER (signed watts):
        - Positive SAX_POWER = discharging -> energy discharged from battery
        - Negative SAX_POWER = charging -> energy charged into battery (absolute value)

        Uses trapezoidal integration for high-resolution energy tracking,
        matching the accuracy of HA's built-in Riemann sum integration.

        Performance:
            O(n) where n = number of batteries (typically 1-3)
        """
        now = time.monotonic()

        for battery_id, coordinator in self._coordinators.items():
            if not coordinator.data:
                continue

            power_value = coordinator.data.get(SAX_POWER)
            if power_value is None:
                continue

            try:
                power_w = float(power_value)
            except ValueError, TypeError:
                _LOGGER.debug(
                    "Invalid power value for battery %s: %s",
                    battery_id,
                    power_value,
                )
                continue

            # Positive SAX_POWER = discharging = energy discharged from battery
            discharged_power = max(power_w, 0.0)
            self._discharged_integrators[battery_id].add_sample(discharged_power, now)

            # Negative SAX_POWER = charging = energy charged into battery (take abs)
            charged_power = abs(min(power_w, 0.0))
            self._charged_integrators[battery_id].add_sample(charged_power, now)

    def _get_total_discharged(self) -> float:
        """Return total energy discharged from all batteries in Wh."""
        return round(
            sum(
                integrator.accumulated_wh
                for integrator in self._discharged_integrators.values()
            ),
            2,
        )

    def _get_total_charged(self) -> float:
        """Return total energy charged into all batteries in Wh."""
        return round(
            sum(
                integrator.accumulated_wh
                for integrator in self._charged_integrators.values()
            ),
            2,
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass.

        Security:
            OWASP A05: Validates restored state before use
        """
        await super().async_added_to_hass()

        # Restore previous state for TOTAL_INCREASING sensors
        if self._sax_item.name in (
            SAX_CUMULATIVE_ENERGY_DISCHARGED,
            SAX_CUMULATIVE_ENERGY_CHARGED,
        ):
            await self._restore_cumulative_state()

    async def _restore_cumulative_state(self) -> None:
        """Restore cumulative energy state from last known value.

        Distributes the restored value evenly across all battery integrators
        so the total matches the previous state.

        Security:
            OWASP A05: Validates restored state
        """
        last_state = await self.async_get_last_state()

        if not last_state or last_state.state in (
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ):
            _LOGGER.debug("No previous state to restore for %s", self._sax_item.name)
            return

        try:
            restored_value = float(last_state.state)

            if self._sax_item.name == SAX_CUMULATIVE_ENERGY_DISCHARGED:
                integrators = self._discharged_integrators
            elif self._sax_item.name == SAX_CUMULATIVE_ENERGY_CHARGED:
                integrators = self._charged_integrators
            else:
                return

            # Distribute restored value evenly across battery integrators
            if integrators:
                per_battery = restored_value / len(integrators)
                for integrator in integrators.values():
                    integrator.restore(per_battery)

            _LOGGER.info(
                "Restored %s: %s Wh across %d batteries",
                self._sax_item.name,
                restored_value,
                len(integrators),
            )

        except (ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Failed to restore state for %s: %s",
                self._sax_item.name,
                exc,
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes.

        Returns:
            Dictionary of extra attributes for diagnostics
        """
        attrs: dict[str, Any] = {ATTR_ATTRIBUTION: ATTRIBUTION}

        # Add per-battery breakdown for energy sensors
        if self._sax_item.name == SAX_CUMULATIVE_ENERGY_DISCHARGED:
            attrs["per_battery"] = {
                bid: integrator.accumulated_wh
                for bid, integrator in self._discharged_integrators.items()
            }
        elif self._sax_item.name == SAX_CUMULATIVE_ENERGY_CHARGED:
            attrs["per_battery"] = {
                bid: integrator.accumulated_wh
                for bid, integrator in self._charged_integrators.items()
            }

        return attrs

    async def async_reset_energy(self) -> None:
        """Reset the energy integrators to zero and update state."""
        if self._sax_item.name == SAX_CUMULATIVE_ENERGY_DISCHARGED:
            for integrator in self._discharged_integrators.values():
                integrator.reset()
            _LOGGER.info("Reset cumulative discharged energy integrators")
        elif self._sax_item.name == SAX_CUMULATIVE_ENERGY_CHARGED:
            for integrator in self._charged_integrators.values():
                integrator.reset()
            _LOGGER.info("Reset cumulative charged energy integrators")
        self.async_write_ha_state()


class SAXBatteryCoordinatorCycleSensor(
    CoordinatorEntity[SAXBatteryCoordinator], SensorEntity
):
    """Sensor for coordinator cycle time monitoring."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sax_item = sax_item
        self._coordinators = coordinator

        if sax_item.entitydescription is not None:
            self.entity_description = sax_item.entitydescription  # type: ignore[assignment]

        # Generate unique ID using get_unique_id_for_item
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=sax_item,
            battery_id=coordinator.battery_id,  # Per-battery diagnostic
        )

        # Set device info for proper grouping
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            coordinator.battery_id, sax_item.device
        )

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value."""
        stats = self.coordinator.cycle_time_statistics

        # Proper key matching
        if self.entity_description.key == COORDINATOR_CYCLE_TIME:
            last_cycle = stats.get("last")
            return float(last_cycle) if last_cycle is not None else None

        if self.entity_description.key == COORDINATOR_ERROR_RATE:
            errors_per_hour = stats.get("errors_per_hour", 0.0)
            return float(errors_per_hour) if errors_per_hour is not None else 0.0

        if self.entity_description.key == COORDINATOR_CIRCUIT_BREAKER:
            circuit_breaker_open = stats.get("circuit_breaker_open", 0.0)
            return "OPEN" if circuit_breaker_open else "CLOSED"

        if self.entity_description.key == BMS_UNAVAILABILITY_RATE:
            unavailability_per_hour = stats.get("bms_unavailability_per_hour", 0.0)
            return (
                float(unavailability_per_hour)
                if unavailability_per_hour is not None
                else 0.0
            )

        if self.entity_description.key == TXID_ERROR_RATE:
            txid_errors = stats.get("txid_errors_per_hour", 0.0)
            return float(txid_errors) if txid_errors is not None else 0.0

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        stats = self.coordinator.cycle_time_statistics

        if self.entity_description.key == COORDINATOR_CYCLE_TIME:
            return {
                "average": round(stats.get("average", 0.0), 3),
                "min": round(stats.get("min", 0.0), 3),
                "max": round(stats.get("max", 0.0), 3),
                "stddev": round(stats.get("stddev", 0.0), 3),
                "total_updates": self.coordinator._total_updates,  # noqa: SLF001
                "failed_updates": self.coordinator._failed_updates,  # noqa: SLF001
                "consecutive_failures": self.coordinator._circuit_breaker.consecutive_failures,  # noqa: SLF001
            }

        if self.entity_description.key == COORDINATOR_ERROR_RATE:
            # Reuse cached stats from cycle_time_statistics (Issue #43)
            # Avoids redundant error_history iteration
            return {
                "modbus_errors": stats.get("modbus_errors", 0),
                "network_errors": stats.get("network_errors", 0),
                "timeout_errors": stats.get("timeout_errors", 0),
                "total_errors_last_hour": int(stats.get("errors_per_hour", 0)),
                "failed_registers": stats.get("failed_registers", {}),
                "last_error_time": stats.get("last_error_time"),
            }

        if self.entity_description.key == COORDINATOR_CIRCUIT_BREAKER:
            return {
                "consecutive_failures": self.coordinator._circuit_breaker.consecutive_failures,  # noqa: SLF001
                "failure_threshold": CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                "cooldown_seconds": CIRCUIT_BREAKER_COOLDOWN_SECONDS,
            }

        if self.entity_description.key == BMS_UNAVAILABILITY_RATE:
            return {
                "total_unavailability_last_hour": int(
                    stats.get("bms_unavailability_per_hour", 0)
                ),
                "last_error_time": stats.get("last_error_time"),
            }

        if self.entity_description.key == TXID_ERROR_RATE:
            return {
                "total_errors_last_hour": int(stats.get("txid_errors_per_hour", 0)),
                "total_errors_since_startup": txid_error_tracker.get_total_errors(),
            }

        return {}


class SAXBatteryPeriodEnergySensor(
    CoordinatorEntity[SAXBatteryCoordinator], RestoreSensor
):
    """Energy sensor tracking discharge or charge energy for a day or month.

    Derives its value from the corresponding cumulative (TOTAL_INCREASING) sensor
    by maintaining a period-start baseline:

        native_value = current_total - period_start_baseline

    Resets at midnight for "daily" and on the 1st of each month at midnight for
    "monthly".  The ``last_reset`` property enables HA long-term statistics and
    bar-chart cards.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _unrecorded_attributes = frozenset({ATTR_ATTRIBUTION})

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
        source_item: SAXItem,
        period: Literal["daily", "monthly"],
    ) -> None:
        """Initialize the period energy sensor.

        Args:
            coordinator: Master battery coordinator (used for device info).
            sax_item: SAXItem describing this entity (key, description, etc.).
            source_item: SAXItem of the cumulative sensor to subscribe to.
            period: "daily" resets at midnight; "monthly" resets on the 1st.

        Security:
            OWASP A05: Validates source item before subscription.
        """
        super().__init__(coordinator)
        self._sax_item = sax_item
        self._source_item = source_item
        self._period: Literal["daily", "monthly"] = period

        # Period tracking state
        self._period_start_wh: float = 0.0
        self._current_period_wh: float = 0.0
        self._last_reset: datetime | None = None
        self._source_entity_id: str | None = None
        self._pending_reset: bool = False
        self._initialized: bool = False  # True once baseline has been set

        # Generate unique ID (cluster-wide, no battery_id)
        self._attr_unique_id = coordinator.sax_data.get_unique_id_for_item(
            item=sax_item,
            battery_id=None,
        )

        if sax_item.entitydescription is not None:
            self.entity_description = sax_item.entitydescription  # type: ignore[assignment]

        # System-level device (cluster device)
        self._attr_device_info: DeviceInfo = coordinator.sax_data.get_device_info(
            "cluster", DeviceConstants.SYS
        )

    # ------------------------------------------------------------------
    # HA entity properties
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> float | None:
        """Return accumulated energy for the current period in Wh."""
        return round(self._current_period_wh, 1)

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of the current period for HA statistics."""
        return self._last_reset

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic extra state attributes."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "period": self._period,
            "period_start_wh": round(self._period_start_wh, 2),
            "last_reset": self._last_reset.isoformat() if self._last_reset else None,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restore state, subscribe to source sensor, register time callbacks.

        Security:
            OWASP A05: Validates restored state before use.
        """
        await super().async_added_to_hass()

        await self._restore_period_state()
        self._source_entity_id = self._resolve_source_entity_id()

        if self._source_entity_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._source_entity_id],
                    self._handle_source_update,
                )
            )
        else:
            _LOGGER.warning(
                "Period sensor %s could not find source entity %s; "
                "values will remain 0 until source becomes available",
                self._sax_item.name,
                self._source_item.name,
            )

        # Daily reset: fire at every midnight
        # Monthly reset: fire at every midnight, check day==1 in callback
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._async_reset_period,
                hour=0,
                minute=0,
                second=0,
            )
        )

    # ------------------------------------------------------------------
    # State restore
    # ------------------------------------------------------------------

    async def _restore_period_state(self) -> None:
        """Restore period baseline and value from the last known HA state."""
        last_state = await self.async_get_last_state()

        if not last_state or last_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            _LOGGER.debug(
                "No previous state for %s; starting fresh", self._sax_item.name
            )
            self._last_reset = dt_util.now()
            return

        try:
            self._current_period_wh = float(last_state.state)
        except ValueError, TypeError:
            self._current_period_wh = 0.0

        attrs = last_state.attributes
        try:
            self._period_start_wh = float(attrs.get("period_start_wh", 0.0))
        except ValueError, TypeError:
            self._period_start_wh = 0.0

        last_reset_str = attrs.get("last_reset")
        if last_reset_str:
            try:
                self._last_reset = dt_util.parse_datetime(last_reset_str)
            except ValueError, TypeError:
                self._last_reset = dt_util.now()
        else:
            self._last_reset = dt_util.now()

        # If we crossed a period boundary while HA was offline, defer reset
        now = dt_util.now()
        if self._last_reset and self._is_new_period(now, self._last_reset):
            _LOGGER.debug(
                "Period boundary crossed while offline for %s; "
                "will reset on next source update",
                self._sax_item.name,
            )
            self._pending_reset = True

        self._initialized = True
        _LOGGER.info(
            "Restored %s: %.1f Wh (baseline %.2f Wh, last reset %s)",
            self._sax_item.name,
            self._current_period_wh,
            self._period_start_wh,
            self._last_reset,
        )

    # ------------------------------------------------------------------
    # Source entity resolution
    # ------------------------------------------------------------------

    def _resolve_source_entity_id(self) -> str | None:
        """Look up the source cumulative sensor's entity_id via the entity registry.

        Security:
            OWASP A05: Validates unique_id before registry lookup.
        """
        source_unique_id = self.coordinator.sax_data.get_unique_id_for_item(
            item=self._source_item,
            battery_id=None,
        )
        if not source_unique_id:
            _LOGGER.warning(
                "Cannot resolve unique_id for source item %s", self._source_item.name
            )
            return None

        ent_reg = er.async_get(self.hass)
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, source_unique_id)
        if entity_id:
            _LOGGER.debug(
                "%s resolved source entity: %s", self._sax_item.name, entity_id
            )
        else:
            _LOGGER.warning(
                "Source entity for %s (unique_id=%s) not found in registry",
                self._source_item.name,
                source_unique_id,
            )
        return entity_id

    # ------------------------------------------------------------------
    # Event / time callbacks
    # ------------------------------------------------------------------

    @callback
    def _handle_source_update(self, event: Event[EventStateChangedData]) -> None:
        """React to state changes of the source cumulative sensor.

        Security:
            OWASP A03: Validates state value before float conversion.
        """
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return

        try:
            current_total = float(new_state.state)
        except ValueError, TypeError:
            return

        if not self._initialized:
            # First valid source update — capture current cumulative as baseline
            self._period_start_wh = current_total
            self._last_reset = dt_util.now()
            self._current_period_wh = 0.0
            self._initialized = True
            self._pending_reset = False
            _LOGGER.info(
                "%s: initialized with baseline %.2f Wh",
                self._sax_item.name,
                self._period_start_wh,
            )
        elif self._pending_reset:
            self._period_start_wh = current_total
            self._last_reset = dt_util.now()
            self._current_period_wh = 0.0
            self._pending_reset = False
            _LOGGER.info(
                "Deferred period reset applied for %s: new baseline %.2f Wh",
                self._sax_item.name,
                self._period_start_wh,
            )
        else:
            self._current_period_wh = max(0.0, current_total - self._period_start_wh)

        self.async_write_ha_state()

    @callback
    def _async_reset_period(self, now: datetime) -> None:
        """Reset the period baseline at the start of a new day or month.

        For "daily" sensors this fires at every midnight.
        For "monthly" sensors this fires at every midnight but only resets
        when ``now.day == 1`` (first of the month).
        """
        if self._period == "monthly" and now.day != 1:
            return

        source_state = (
            self.hass.states.get(self._source_entity_id)
            if self._source_entity_id
            else None
        )

        if source_state and source_state.state not in (
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ):
            try:
                self._period_start_wh = float(source_state.state)
                self._last_reset = now
                self._current_period_wh = 0.0
                _LOGGER.info(
                    "Period reset for %s: new baseline %.2f Wh at %s",
                    self._sax_item.name,
                    self._period_start_wh,
                    now,
                )
            except ValueError, TypeError:
                self._pending_reset = True
        else:
            # Defer reset to next valid source update
            self._pending_reset = True
            _LOGGER.debug(
                "Source unavailable at period reset for %s; deferring",
                self._sax_item.name,
            )

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_new_period(self, now: datetime, last_reset: datetime) -> bool:
        """Return True if ``now`` is in a later period than ``last_reset``."""
        if self._period == "daily":
            return now.date() > last_reset.date()
        # monthly
        return (now.year, now.month) > (last_reset.year, last_reset.month)

    async def async_reset_period(self) -> None:
        """Force a period reset: clear baseline so next source update sets it."""
        self._initialized = False
        self._period_start_wh = 0.0
        self._current_period_wh = 0.0
        self._pending_reset = False
        self._last_reset = dt_util.now()
        _LOGGER.info(
            "Reset period sensor %s; will re-baseline on next source update",
            self._sax_item.name,
        )
        self.async_write_ha_state()
