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
    DEFAULT_DEVICE_INFO,
    MODBUS_BATTERY_SMARTMETER_ITEMS,
    MODBUS_BATTERY_STATIC_ITEMS,
    MODBUS_BATTERY_SWITCH_ITEMS,
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

    # def update_data(self, new_data: dict[str, Any]) -> None:
    #     """Update multiple data values."""
    #     self._data.update(new_data)

    # @abstractmethod
    # def get_device_info(self) -> DeviceInfo:
    #     """Get device info for Home Assistant."""

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
        items.extend(MODBUS_BATTERY_STATIC_ITEMS)
        items.extend(MODBUS_BATTERY_SWITCH_ITEMS)

        # Master battery also gets consolidated smart meter items
        if self.is_master:
            # MODBUS_BATTERY_SMARTMETER_ITEMS already includes all smart meter data
            # Including basic items, phase items, and battery-accessible smart meter data
            items.extend(MODBUS_BATTERY_SMARTMETER_ITEMS)
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

        # Initialize batteries from config entry
        self._initialize_batteries()

    def _initialize_batteries(self) -> None:
        """Initialize battery models from config entry."""
        battery_count = self.entry.data.get("battery_count", 1)
        master_battery_id = self.entry.data.get("master_battery", "battery_a")

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
            # Cluster device info for aggregated entities
            return DeviceInfo(
                identifiers={("sax_battery", "sax_battery_cluster")},
                name="SAX Battery Cluster",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model="Battery Cluster",
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
            )
        if device == DeviceConstants.SM:
            # Smartmeter device info for aggregated entities
            return DeviceInfo(
                identifiers={("sax_battery", "sax_smartmeter")},
                name="SAX Smart Meter",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model="Smart Meter",
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
            )

        if device == DeviceConstants.BESS:
            # Battery device info for aggregated entities
            return DeviceInfo(
                identifiers={("sax_battery", battery_id)},
                name=f"SAX Battery {battery_id.removeprefix('battery_').upper()}",
                manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
                model=DEFAULT_DEVICE_INFO.model,
                sw_version=DEFAULT_DEVICE_INFO.sw_version,
            )

        _LOGGER.error("Unknown device type: %s, %s", battery_id, device)  # type: ignore [unreachable]
        raise ValueError(f"Unknown device type: {device}")
