"""Simplified models using existing const.py definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    AGGREGATED_ITEMS,
    BATTERY_IDS,
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PORT,
    CONF_MASTER_BATTERY,
    CONF_SM_CONNECTED,
    DEFAULT_DEVICE_INFO,
    DOMAIN,
    MODBUS_BATTERY_BMS_ITEMS,
    MODBUS_BATTERY_SMARTMETER_ITEMS,
    MODBUS_BATTERY_SWITCH_ITEMS,
    PILOT_ITEMS,
)
from .enums import DeviceConstants, TypeConstants
from .items import ModbusItem, SAXItem
from .modbusobject import ModbusAPI
from .utils import create_register_access_config, get_battery_realtime_items

_LOGGER = logging.getLogger(__name__)


@dataclass
class BaseModel(ABC):
    """Base model with common functionality."""

    device_id: str
    name: str
    _data: dict[str, Any] = field(default_factory=dict, init=False)

    @property
    def data(self) -> dict[str, Any]:
        """Get the current data."""
        return self._data

    def get_value(self, key: str) -> Any:
        """Get value for a specific key."""
        return self._data.get(key)

    def set_value(self, key: str, value: Any) -> None:
        """Set value for a specific key."""
        self._data[key] = value

    @abstractmethod
    def get_modbus_items(self) -> list[ModbusItem]:
        """Get modbus items for this model."""

    @abstractmethod
    def get_sax_items(self) -> list[SAXItem]:
        """Get SAX items for this model."""


@dataclass
class BatteryModel(BaseModel):
    """Battery model using predefined items from const.py."""

    # slave_id: int = 1
    host: str = ""
    port: int = 502
    is_master: bool = False
    config_data: dict[str, Any] = field(default_factory=dict)

    # def get_device_info(self) -> DeviceInfo:
    #     """Get device info for battery."""
    #     return DeviceInfo(
    #         identifiers={("sax_battery", self.device_id)},
    #         name=self.name,
    #         manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
    #         model=DEFAULT_DEVICE_INFO.model,
    #         sw_version=DEFAULT_DEVICE_INFO.sw_version,
    #     )

    def get_modbus_items(self) -> list[ModbusItem]:
        """Get modbus items based on battery role.

        Returns:
            list[ModbusItem]: Appropriate items for this battery's role

        Security: Role-based access control for different battery types
        Performance: Optimized item lists based on battery function
        """
        # Create access config to determine appropriate entity types
        access_config = create_register_access_config(self.config_data, self.is_master)

        # All batteries get realtime and static items
        items = list(get_battery_realtime_items(access_config))
        if not self.is_master:
            items.extend(MODBUS_BATTERY_SWITCH_ITEMS)

        # Master battery also gets consolidated smart meter items
        if self.is_master:
            items.extend(MODBUS_BATTERY_BMS_ITEMS)
            # Only include smart meter items when SM is connected via RS485
            sm_connected = self.config_data.get(CONF_SM_CONNECTED, True)
            if sm_connected:
                items.extend(MODBUS_BATTERY_SMARTMETER_ITEMS)
            switch_item: ModbusItem = MODBUS_BATTERY_SWITCH_ITEMS[0]
            switch_item.device = DeviceConstants.SYS
            items.append(switch_item)  # Add system-level switch for master battery
            if sm_connected:
                _LOGGER.debug(
                    "Added %d smart meter items to master battery",
                    len(MODBUS_BATTERY_SMARTMETER_ITEMS),
                )
            else:
                _LOGGER.debug(
                    "Smart meter not connected - skipping %d SM items",
                    len(MODBUS_BATTERY_SMARTMETER_ITEMS),
                )

        return items

    def get_sax_items(self) -> list[SAXItem]:
        """Get SAX items for battery."""
        items = []

        # Only master battery gets aggregated and pilot items
        if self.is_master:
            items.extend(AGGREGATED_ITEMS)
            items.extend(PILOT_ITEMS)

        return items


class SAXBatteryData:
    """Main data structure for SAX Battery integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize SAX Battery data."""
        self.hass = hass
        self.entry = entry
        self.batteries: dict[str, BatteryModel] = {}
        self.coordinators: dict[str, Any] = {}
        self.modbus_api: ModbusAPI | None = None
        self.master_battery_id: str | None = None
        self._is_unloading = False
        self._battery_count = 0

        # Initialize batteries from config entry
        self._initialize_batteries()

    def _initialize_batteries(self) -> None:
        """Initialize battery models from config entry."""
        # Skip initialization if unloading
        integration_data = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {})
        if integration_data.get("_unloading", False) or self._is_unloading:
            _LOGGER.debug("Skipping battery initialization during unload")
            return

        # Check for new nested battery configuration format
        if CONF_BATTERIES in self.entry.data:
            batteries_config = self.entry.data[CONF_BATTERIES]

            for battery_id, battery_config in batteries_config.items():
                # Security: Validate battery_id is in allowed list
                if battery_id not in BATTERY_IDS:
                    _LOGGER.warning("Invalid battery ID %s, skipping", battery_id)
                    continue

                host = battery_config.get(CONF_BATTERY_HOST, "")
                port = battery_config.get(CONF_BATTERY_PORT, 502)
                is_master = battery_config.get(CONF_BATTERY_IS_MASTER, False)

                if is_master:
                    self.master_battery_id = battery_id

                battery = BatteryModel(
                    device_id=battery_id,
                    name=f"SAX Battery {battery_id.split('_')[1].upper()}",
                    host=host,
                    port=port,
                    is_master=is_master,
                    config_data=dict(self.entry.data),
                )

                self.batteries[battery_id] = battery
            self._battery_count = len(self.batteries)
        else:
            # Legacy configuration format
            battery_count = self.entry.data.get(CONF_BATTERY_COUNT, 1)
            master_battery_id = self.entry.data.get(CONF_MASTER_BATTERY, "bess_a")

            for i in range(1, int(battery_count) + 1):
                battery_id = f"bess_{chr(96 + i)}"  # bess_a, bess_b, bess_c
                host = self.entry.data.get(f"{battery_id}_host", "")
                port = self.entry.data.get(f"{battery_id}_port", 502)
                is_master = battery_id == master_battery_id

                if is_master:
                    self.master_battery_id = battery_id

                battery = BatteryModel(
                    device_id=battery_id,
                    name=f"SAX Battery {battery_id.split('_')[1].upper()}",
                    host=host,
                    port=port,
                    is_master=is_master,
                    config_data=dict(self.entry.data),
                )

                self.batteries[battery_id] = battery
            self._battery_count = battery_count

    @property
    def get_battery_count(self) -> int:
        """Get the number of configured batteries."""
        return self._battery_count

    def get_modbus_items_for_battery(self, battery_id: str) -> list[ModbusItem]:
        """Get modbus items for a specific battery."""
        battery = self.batteries.get(battery_id)
        return battery.get_modbus_items() if battery else []

    def get_sax_items_for_battery(self, battery_id: str) -> list[SAXItem]:
        """Get SAX items for a specific battery."""
        battery = self.batteries.get(battery_id)
        return battery.get_sax_items() if battery else []

    def get_device_info(self, battery_id: str, device: DeviceConstants) -> DeviceInfo:
        """Get device info for a specific battery."""
        if device == DeviceConstants.SYS:
            # Cluster device info for aggregated and control entities
            return DeviceInfo(
                identifiers={(DOMAIN, "cluster")},
                name="SAX BMS",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model=DEFAULT_DEVICE_INFO.model,
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
            )

        if device == DeviceConstants.SM:
            # Smartmeter device info for all devices
            return DeviceInfo(
                identifiers={(DOMAIN, "sax_smartmeter")},
                name="SAX SM",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model=DEFAULT_DEVICE_INFO.model,
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
            )

        if device == DeviceConstants.BESS:
            # Battery device info for specific battery
            return DeviceInfo(
                identifiers={(DOMAIN, battery_id)},
                name=f"SAX BESS {battery_id.removeprefix('bess_').upper()}",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model=DEFAULT_DEVICE_INFO.model,
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
            )

        _LOGGER.error("Unknown device type: %s, %s", battery_id, device)  # type: ignore [unreachable]
        raise ValueError(f"Unknown device type: {device}")

    def get_unique_id_for_item(
        self,
        item: ModbusItem | SAXItem,
        battery_id: str | None = None,
    ) -> str | None:
        """Generate unique ID for an entity item using device info.

        Uses SAXBatteryData.get_device_info() for consistent device naming
        instead of duplicating device name logic.

        Args:
            item: ModbusItem or SAXItem instance
            battery_id: Battery ID for the battery that handles this entity.
                       - For WO registers: master battery ID (hardware communication)
                       - For per-battery sensors: specific battery ID
                       - For virtual entities: None (no hardware)

        Returns:
            Unique ID string or None if generation fails

        Examples:
            # WO register entity - uses master battery for Modbus but cluster device
            sax_data.get_unique_id_for_item(max_discharge_item, battery_id="bess_a")
            # Returns: "sax_cluster_max_discharge"

            # Per-battery sensor (BESS device)
            sax_data.get_unique_id_for_item(temperature_item, battery_id="bess_a")
            # Returns: "sax_bess_a_temperature"

            # Virtual entity (SYS device, no hardware)
            sax_data.get_unique_id_for_item(min_soc_item, battery_id=None)
            # Returns: "sax_cluster_min_soc"

        Security:
            OWASP A01: Proper entity identification prevents unauthorized access
            OWASP A03: Input validation prevents injection attacks

        Performance:
            Uses existing device info cache - no registry lookups
        """
        try:
            # Validate item name is not empty
            if not item.name or not item.name.strip():
                _LOGGER.warning("Cannot generate unique_id: item name is empty")
                return None

            # Normalize item name (remove "sax_" prefix if present, convert to lowercase)
            clean_item_name = item.name.removeprefix("sax_").lower()

            # Get device type from item definition
            device = item.device

            # Generate unique_id based on device type and battery_id
            if battery_id is None:
                # Virtual/calculated entity (no hardware backing)
                # Examples: min_soc, combined_soc, cumulative_energy
                # Always uses cluster device regardless of item.device
                unique_id = f"sax_bms_{clean_item_name}"
                _LOGGER.debug(
                    "Generated cluster unique_id '%s' for virtual item '%s'",
                    unique_id,
                    item.name,
                )
            else:
                # Hardware-backed or coordinator-managed entity
                # Get device info based on item's device type
                device_info: DeviceInfo | None = self.get_device_info(
                    battery_id, device
                )
                if device_info is None:
                    _LOGGER.warning(
                        "Cannot generate unique_id: no device info for battery_id=%s, device=%s",
                        battery_id,
                        device.value,
                    )
                    return None

                # Validate device name exists and is not None
                device_name_raw = device_info.get("name")
                if not device_name_raw:
                    _LOGGER.warning(
                        "Cannot generate unique_id: device info has no name for battery_id=%s, device=%s",
                        battery_id,
                        device.value,
                    )
                    return None

                device_name_clean = (
                    device_name_raw.lower().replace(" ", "_").removeprefix("sax_")
                )
                unique_id = f"sax_{device_name_clean}_{clean_item_name}"
                _LOGGER.debug(
                    "Generated unique_id '%s' for item '%s' (battery_id=%s, device=%s)",
                    unique_id,
                    item.name,
                    battery_id,
                    device.value,
                )

            return unique_id  # noqa: TRY300

        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Error generating unique_id for item %s (battery_id=%s): %s",
                item.name,
                battery_id,
                err,
            )
            return None

    def get_entity_id_for_item(
        self,
        item: ModbusItem | SAXItem,
        battery_id: str | None = None,
    ) -> str | None:
        """Generate entity ID for a ModbusItem or SAXItem using device info.

        This method converts an item into its corresponding Home Assistant entity ID
        by combining the unique_id generation logic with platform-specific prefixes
        (number., sensor., switch.).

        The entity ID format follows Home Assistant's naming convention:
        - Hardware entities: "{platform}.sax_{device}_{item_name}"
        - Virtual entities: "{platform}.sax_cluster_{item_name}"

        Args:
            item: ModbusItem or SAXItem instance to generate entity ID for
            battery_id: Optional battery ID for hardware-backed entities
                - For hardware entities (BESS device): specific battery ID (e.g., "bess_a")
                - For smart meter entities (SM device): master battery ID
                - For virtual entities (SYS device): None (uses cluster device)

        Returns:
            str | None: Full entity ID with platform prefix, or None if generation fails

        Examples:
            # Hardware number entity (BESS device)
            >>> item = ModbusItem(name="sax_temperature", mtype=TypeConstants.NUMBER, device=DeviceConstants.BESS)
            >>> sax_data.get_entity_id_for_item(item, battery_id="bess_a")
            "number.sax_bess_a_temperature"

            # Virtual sensor entity (SYS device)
            >>> item = SAXItem(name="sax_combined_soc", mtype=TypeConstants.SENSOR_CALC, device=DeviceConstants.SYS)
            >>> sax_data.get_entity_id_for_item(item, battery_id=None)
            "sensor.sax_cluster_combined_soc"

            # Smart meter sensor (SM device)
            >>> item = ModbusItem(name="sax_grid_power", mtype=TypeConstants.SENSOR, device=DeviceConstants.SM)
            >>> sax_data.get_entity_id_for_item(item, battery_id="bess_a")
            "sensor.sax_smart_meter_grid_power"

            # Control switch (SYS device)
            >>> item = SAXItem(name="sax_solar_charging", mtype=TypeConstants.SWITCH, device=DeviceConstants.SYS)
            >>> sax_data.get_entity_id_for_item(item, battery_id=None)
            "switch.sax_cluster_solar_charging"

        Supported Entity Types:
            - NUMBER/NUMBER_RO/NUMBER_WO: Maps to "number." platform
            - SENSOR/SENSOR_CALC: Maps to "sensor." platform
            - SWITCH: Maps to "switch." platform

        Security:
            OWASP A01: Proper entity identification prevents unauthorized access
            OWASP A03: Input validation via get_unique_id_for_item prevents injection
            OWASP A05: Consistent entity ID generation prevents misconfiguration

        Performance:
            Single delegation to get_unique_id_for_item - minimal overhead
            No registry lookups - uses cached device info
            Early return on unique_id generation failure

        Error Handling:
            - Returns None if unique_id generation fails
            - Returns None for unknown item types
            - Logs warnings for invalid inputs

        Dependencies:
            Relies on get_unique_id_for_item() for unique ID generation
            Uses item.mtype to determine platform prefix

        Related Methods:
            - get_unique_id_for_item(): Generates base unique ID without platform prefix
            - get_device_info(): Provides device naming for entity ID construction
        """
        # Generate base unique_id (without platform prefix)
        unique_id = self.get_unique_id_for_item(item, battery_id)
        if unique_id is None:
            _LOGGER.debug(
                "Cannot generate entity_id: unique_id generation failed for item '%s'",
                item.name,
            )
            return None

        # Map item type to Home Assistant platform prefix
        if item.mtype in [
            TypeConstants.NUMBER_WO,
            TypeConstants.NUMBER_RO,
            TypeConstants.NUMBER,
        ]:
            entity_id = f"number.{unique_id}"
        elif item.mtype in [TypeConstants.SENSOR, TypeConstants.SENSOR_CALC]:
            entity_id = f"sensor.{unique_id}"
        elif item.mtype == TypeConstants.SWITCH:
            entity_id = f"switch.{unique_id}"
        else:
            _LOGGER.warning(
                "Unknown item type '%s' for item '%s', cannot generate entity_id",
                item.mtype,
                item.name,
            )
            return None

        _LOGGER.debug(
            "Generated entity_id '%s' for item '%s' (battery_id=%s, type=%s)",
            entity_id,
            item.name,
            battery_id,
            item.mtype,
        )

        return entity_id

    def get_item_by_name(self, name: str) -> ModbusItem | SAXItem | None:
        """Get ModbusItem or SAXItem by name across all batteries.

        Args:
            name: Item name to search for (e.g., "sax_nominal_power", "sax_soc")

        Returns:
            ModbusItem or SAXItem if found, None otherwise

        Security:
            OWASP A03: Input validation prevents injection attacks
            OWASP A01: Proper item lookup prevents unauthorized access

        Performance:
            Searches master battery first (most likely to have item)
            Early return on first match to minimize iterations
        """
        # Security: Validate input
        if not name or not isinstance(name, str):
            _LOGGER.warning("Invalid item name: %s", name)
            return None

        # Normalize name (ensure "sax_" prefix for consistency)
        search_name = name if name.startswith("sax_") else f"sax_{name}"

        # Performance: Search master battery first (has most items)
        if self.master_battery_id:
            # Search ModbusItems
            for modbusItem in self.get_modbus_items_for_battery(self.master_battery_id):
                if modbusItem.name == search_name:
                    _LOGGER.debug(
                        "Found ModbusItem '%s' in master battery '%s'",
                        search_name,
                        self.master_battery_id,
                    )
                    return modbusItem

            # Search SAXItems (only master battery has these)
            for saxItem in self.get_sax_items_for_battery(self.master_battery_id):
                if saxItem.name == search_name:
                    _LOGGER.debug(
                        "Found SAXItem '%s' in master battery '%s'",
                        search_name,
                        self.master_battery_id,
                    )
                    return saxItem

        # Search remaining slave batteries
        for battery_id, battery in self.batteries.items():
            if battery_id == self.master_battery_id:
                continue  # Already searched master

            # Search ModbusItems
            for item in battery.get_modbus_items():
                if item.name == search_name:
                    _LOGGER.debug(
                        "Found ModbusItem '%s' in battery '%s'",
                        search_name,
                        battery_id,
                    )
                    return item

        # Item not found
        _LOGGER.debug("Item '%s' not found in any battery", search_name)
        return None
