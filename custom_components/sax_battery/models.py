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
    DEFAULT_DEVICE_INFO,
    DOMAIN,
    MODBUS_BATTERY_BMS_ITEMS,
    MODBUS_BATTERY_SMARTMETER_ITEMS,
    MODBUS_BATTERY_SWITCH_ITEMS,
    MODBUS_BATTERY_UNDOCUMENTED_ITEMS,
    PILOT_ITEMS,
)
from .enums import DeviceConstants
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
            # MODBUS_BATTERY_SMARTMETER_ITEMS already includes all smart meter data
            # Including basic items, phase items, and battery-accessible smart meter data
            items.extend(MODBUS_BATTERY_BMS_ITEMS)
            items.extend(MODBUS_BATTERY_SMARTMETER_ITEMS)
            items.extend(MODBUS_BATTERY_UNDOCUMENTED_ITEMS)
            switch_item: ModbusItem = MODBUS_BATTERY_SWITCH_ITEMS[0]
            switch_item.device = DeviceConstants.SYS
            items.append(switch_item)  # Add system-level switch for master battery
            _LOGGER.debug(
                "Added %d smart meter items to master battery",
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
        else:
            # Legacy configuration format
            battery_count = self.entry.data.get(CONF_BATTERY_COUNT, 1)
            master_battery_id = self.entry.data.get(CONF_MASTER_BATTERY, "battery_a")

            for i in range(1, int(battery_count) + 1):
                battery_id = f"battery_{chr(96 + i)}"  # battery_a, battery_b, battery_c
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

    def should_poll_smart_meter(self, battery_id: str) -> bool:
        """Check if this battery should poll smart meter data.

        Args:
            battery_id: Battery identifier to check

        Returns:
            bool: True only if this is the master battery

        Security: Ensures only master battery polls smart meter data
        Performance: Prevents multiple polling of same smart meter registers
        """
        battery = self.batteries.get(battery_id)
        is_master = battery.is_master if battery else False

        if is_master:
            _LOGGER.debug(
                "Battery %s is master - will poll smart meter data", battery_id
            )
        else:
            _LOGGER.debug(
                "Battery %s is slave - skipping smart meter polling", battery_id
            )

        return is_master

    def get_modbus_items_for_battery(self, battery_id: str) -> list[ModbusItem]:
        """Get modbus items for a specific battery."""
        battery = self.batteries.get(battery_id)
        return battery.get_modbus_items() if battery else []

    def get_sax_items_for_battery(self, battery_id: str) -> list[SAXItem]:
        """Get SAX items for a specific battery."""
        battery = self.batteries.get(battery_id)
        return battery.get_sax_items() if battery else []

    def get_smart_meter_items(self) -> list[ModbusItem]:
        """Get smart meter modbus items.

        Returns:
            Empty list - smart meter items are handled through master battery

        Security: Prevents duplicate entity registration
        Performance: Eliminates redundant polling of same registers
        """
        # Smart meter items are already included in MODBUS_BATTERY_SMARTMETER_ITEMS
        # for the master battery. Returning empty list prevents duplicates.
        _LOGGER.debug(
            "Smart meter items handled through master battery - preventing duplicates"
        )
        return []

    def get_device_info(self, battery_id: str, device: DeviceConstants) -> DeviceInfo:
        """Get device info for a specific battery."""
        if device == DeviceConstants.SYS:
            # Cluster device info for aggregated and control entities
            return DeviceInfo(
                identifiers={(DOMAIN, "cluster")},
                name="SAX Cluster",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model=DEFAULT_DEVICE_INFO.model,
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
                translation_key="dev_bms",
            )

        if device == DeviceConstants.SM:
            # Smartmeter device info for all devices
            return DeviceInfo(
                identifiers={(DOMAIN, "sax_smartmeter")},
                name="SAX Smart Meter",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model=DEFAULT_DEVICE_INFO.model,
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
                translation_key="dev_sm",
            )

        if device == DeviceConstants.BESS:
            # Battery device info for specific battery
            return DeviceInfo(
                identifiers={(DOMAIN, battery_id)},
                name=f"SAX Battery {battery_id.removeprefix('battery_').upper()}",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model=DEFAULT_DEVICE_INFO.model,
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
                translation_key="dev_bess",
                translation_placeholders={
                    "battery_id": battery_id.removeprefix("battery_").upper()
                },
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
            sax_data.get_unique_id_for_item(max_discharge_item, battery_id="battery_a")
            # Returns: "sax_cluster_max_discharge"

            # Per-battery sensor (BESS device)
            sax_data.get_unique_id_for_item(temperature_item, battery_id="battery_a")
            # Returns: "sax_battery_a_temperature"

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
                unique_id = f"sax_cluster_{clean_item_name}"
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
