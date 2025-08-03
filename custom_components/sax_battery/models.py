"""Simplified models using existing const.py definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    AGGREGATED_ITEMS,
    DEFAULT_DEVICE_INFO,
    MODBUS_BATTERY_ITEMS,
    MODBUS_SMARTMETER_ITEMS,
    PILOT_ITEMS,
    SAX_CURRENT_L1,
    SAX_POWER,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SOC,
    SAX_VOLTAGE_L1,
)
from .items import ModbusItem, SAXItem
from .modbusobject import ModbusAPI


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

    slave_id: int = 1
    host: str = ""
    port: int = 502
    is_master: bool = False

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
        if self.is_master:
            # Master battery gets all items including smart meter data
            return MODBUS_BATTERY_ITEMS + MODBUS_SMARTMETER_ITEMS
        else:  # noqa: RET505
            # Slave batteries only get battery-specific items
            return MODBUS_BATTERY_ITEMS

    def get_sax_items(self) -> list[SAXItem]:
        """Get SAX items for battery."""
        items = []

        if self.is_master:
            # Master battery gets aggregated and pilot items
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

    @property
    def total_power(self) -> float | None:
        """Get total power from smart meter."""
        value = self.get_value(SAX_SMARTMETER_TOTAL_POWER)
        return float(value) if value is not None else None


@dataclass
class SystemModel(BaseModel):
    """System-wide model for aggregated data."""

    batteries: dict[str, BatteryModel] = field(default_factory=dict)
    smart_meter: SmartMeterModel | None = None

    def get_device_info(self) -> DeviceInfo:
        """Get device info for system."""
        return DeviceInfo(
            identifiers={("sax_battery", "system")},
            name="SAX Battery System",
            manufacturer=DEFAULT_DEVICE_INFO.manufacturer,
            model="Battery System",
        )

    def get_modbus_items(self) -> list[ModbusItem]:
        """System doesn't have direct modbus items."""
        return []

    def get_sax_items(self) -> list[SAXItem]:
        """Get system-wide calculated items."""
        return AGGREGATED_ITEMS + PILOT_ITEMS

    def add_battery(self, battery: BatteryModel) -> None:
        """Add a battery to the system."""
        self.batteries[battery.device_id] = battery

    def get_master_battery(self) -> BatteryModel | None:
        """Get the master battery."""
        return next((b for b in self.batteries.values() if b.is_master), None)

    def get_slave_batteries(self) -> list[BatteryModel]:
        """Get all slave batteries."""
        return [b for b in self.batteries.values() if not b.is_master]

    @property
    def total_power(self) -> float | None:
        """Get total power from all batteries."""
        powers = [b.power for b in self.batteries.values() if b.power is not None]
        return sum(powers) if powers else None

    @property
    def average_soc(self) -> float | None:
        """Get average SOC from all batteries."""
        socs = [b.soc for b in self.batteries.values() if b.soc is not None]
        return sum(socs) / len(socs) if socs else None


@dataclass
class SAXBatteryData:
    """Main data structure for SAX Battery integration."""

    batteries: dict[str, BatteryModel] = field(default_factory=dict)
    smart_meter_data: SmartMeterModel | None = None
    coordinators: dict[str, Any] = field(default_factory=dict)
    modbus_api: ModbusAPI | None = None
    master_battery_id: str | None = None

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
        return MODBUS_SMARTMETER_ITEMS

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
