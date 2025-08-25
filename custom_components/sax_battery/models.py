"""Simplified models using existing const.py definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    MODBUS_SMARTMETER_BASIC_ITEMS,
    MODBUS_SMARTMETER_PHASE_ITEMS,
    PILOT_ITEMS,
    SAX_CURRENT_L1,
    SAX_POWER,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SOC,
    SAX_VOLTAGE_L1,
)
from .items import ModbusItem, SAXItem
from .modbusobject import ModbusAPI
from .utils import create_register_access_config, get_battery_realtime_items


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

    def update_data(self, new_data: dict[str, Any]) -> None:
        """Update multiple data values."""
        self._data.update(new_data)

    @abstractmethod
    def get_device_info(self) -> DeviceInfo:
        """Get device info for Home Assistant."""

    @abstractmethod
    def get_modbus_items(self) -> list[ModbusItem]:
        """Get modbus items for this model."""

    @abstractmethod
    def get_sax_items(self) -> list[SAXItem]:
        """Get SAX items for this model."""


@dataclass
class BatteryModel(BaseModel):
    """Battery model using predefined items from const.py."""

    host: str = ""
    port: int = 502
    is_master: bool = False
    config_data: dict[str, Any] = field(default_factory=dict)

    def get_device_info(self) -> DeviceInfo:
        """Get device info for battery."""
        return DeviceInfo(
            identifiers={("sax_battery", self.device_id)},
            name=self.name,
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )

    def get_modbus_items(self) -> list[ModbusItem]:
        """Get modbus items based on battery role."""
        # Create access config to determine appropriate entity types
        access_config = create_register_access_config(self.config_data, self.is_master)

        # All batteries get realtime and static items
        items = list(get_battery_realtime_items(access_config))
        items.extend(MODBUS_BATTERY_STATIC_ITEMS)
        items.extend(MODBUS_BATTERY_SWITCH_ITEMS)

        # Master battery also gets smart meter items
        if self.is_master:
            items.extend(MODBUS_BATTERY_SMARTMETER_ITEMS)

        return items

    def get_sax_items(self) -> list[SAXItem]:
        """Get SAX items for battery."""
        items = []

        # Only master battery gets aggregated and pilot items
        if self.is_master:
            items.extend(AGGREGATED_ITEMS)
            items.extend(PILOT_ITEMS)

        return items

    # Convenience properties for common battery values
    @property
    def soc(self) -> float | None:
        """Get battery state of charge."""
        value = self.get_value(SAX_SOC)
        return float(value) if value is not None else None

    @property
    def power(self) -> float | None:
        """Get battery power."""
        value = self.get_value(SAX_POWER)
        return float(value) if value is not None else None

    @property
    def voltage_l1(self) -> float | None:
        """Get L1 voltage."""
        value = self.get_value(SAX_VOLTAGE_L1)
        return float(value) if value is not None else None

    @property
    def current_l1(self) -> float | None:
        """Get L1 current."""
        value = self.get_value(SAX_CURRENT_L1)
        return float(value) if value is not None else None


@dataclass
class SmartMeterModel(BaseModel):
    """Smart meter model for aggregated grid data."""

    def get_device_info(self) -> DeviceInfo:
        """Get device info for smart meter."""
        return DeviceInfo(
            identifiers={("sax_battery", f"{self.device_id}_smartmeter")},
            name=f"{self.name} Smart Meter",
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model="Smart Meter",
            via_device=("sax_battery", self.device_id),
        )

    def get_modbus_items(self) -> list[ModbusItem]:
        """Smart meter data comes through battery modbus items."""
        return []  # Data is polled through master battery

    def get_sax_items(self) -> list[SAXItem]:
        """Get SAX items for smart meter."""
        return []  # No calculated items specific to smart meter

    def get_smart_meter_items(self) -> list[ModbusItem]:
        """Get smart meter modbus items."""
        return list(MODBUS_SMARTMETER_BASIC_ITEMS) + list(MODBUS_SMARTMETER_PHASE_ITEMS)

    @property
    def total_power(self) -> float | None:
        """Get total power from smart meter."""
        value = self.get_value(SAX_SMARTMETER_TOTAL_POWER)
        return float(value) if value is not None else None


class SAXBatteryData:
    """Main data structure for SAX Battery integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize SAX Battery data."""
        self.hass = hass
        self.entry = entry
        self.batteries: dict[str, BatteryModel] = {}
        self.smart_meter_data: SmartMeterModel | None = None
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

    async def async_initialize(self) -> None:
        """Initialize the SAX Battery data."""
        # Initialize modbus connections and data structures

    def is_battery_connected(self, battery_id: str) -> bool:
        """Check if a battery is connected."""
        return battery_id in self.batteries

    def should_poll_smart_meter(self, battery_id: str) -> bool:
        """Check if this battery should poll smart meter data."""
        battery = self.batteries.get(battery_id)
        return battery.is_master if battery else False

    def get_modbus_items_for_battery(self, battery_id: str) -> list[ModbusItem]:
        """Get modbus items for a specific battery."""
        battery = self.batteries.get(battery_id)
        return battery.get_modbus_items() if battery else []

    def get_sax_items_for_battery(self, battery_id: str) -> list[SAXItem]:
        """Get SAX items for a specific battery."""
        battery = self.batteries.get(battery_id)
        return battery.get_sax_items() if battery else []

    def get_smart_meter_items(self) -> list[ModbusItem]:
        """Get smart meter modbus items."""
        return list(MODBUS_SMARTMETER_BASIC_ITEMS) + list(MODBUS_SMARTMETER_PHASE_ITEMS)

    def get_modbus_api(self) -> ModbusAPI | None:
        """Get the modbus API instance."""
        return self.modbus_api

    def get_device_info(self, battery_id: str) -> DeviceInfo:
        """Get device info for a specific battery."""
        battery = self.batteries.get(battery_id)
        if battery:
            return battery.get_device_info()

        # Fallback device info
        return DeviceInfo(
            identifiers={("sax_battery", battery_id)},
            name=f"SAX Battery {battery_id}",
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model=DEFAULT_DEVICE_INFO.model,
            sw_version=DEFAULT_DEVICE_INFO.sw_version,
        )
