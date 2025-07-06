"""Data models for SAX Battery integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .coordinator import SAXBatteryCoordinator


class BatteryRole(Enum):
    """Battery role in the system."""

    MASTER = "master"
    SLAVE = "slave"


class CommunicationInterface(Enum):
    """Communication interface types."""

    MODBUS_TCP = "modbus_tcp"  # Ethernet port for individual battery communication
    MODBUS_RTU = "modbus_rtu"  # RS485 port for smart meter communication


@dataclass
class SmartMeterData:
    """Smart meter data structure for grid measurements."""

    # Total grid measurements
    total_power: float | None = None
    grid_frequency: float | None = None

    # Phase-specific measurements
    voltage_l1: float | None = None
    voltage_l2: float | None = None
    voltage_l3: float | None = None

    current_l1: float | None = None
    current_l2: float | None = None
    current_l3: float | None = None

    active_power_l1: float | None = None
    active_power_l2: float | None = None
    active_power_l3: float | None = None

    # Grid connection status
    import_power: float | None = None
    export_power: float | None = None

    # Last update timestamp
    last_update: float | None = None


@dataclass
class BatteryConfig:
    """Configuration for a single battery unit."""

    battery_id: str
    role: BatteryRole

    # Modbus TCP connection (individual battery)
    tcp_host: str
    tcp_port: int = 502
    tcp_slave_id: int = 64

    # RS485 connection info (smart meter communication)
    rtu_slave_id: int = 40

    # Battery-specific settings
    max_charge_power: int | None = None
    max_discharge_power: int | None = None


@dataclass
class SAXBatterySystem:
    """Complete SAX battery system data structure."""

    entry: ConfigEntry
    coordinator: SAXBatteryCoordinator | None = None
    device_id: str | None = None

    # System configuration
    master_battery_id: str | None = None
    battery_configs: dict[str, BatteryConfig] = field(default_factory=dict)

    # Communication interfaces
    modbus_api: Any = None  # ModbusAPI instance
    smart_meter_data: SmartMeterData = field(default_factory=SmartMeterData)

    # Runtime data
    batteries: dict[str, Any] = field(default_factory=dict)  # Battery instances
    pilot: Any | None = None

    # Power management
    system_power_limits: dict[str, int] = field(default_factory=dict)
    phase_balancing_enabled: bool = True

    def get_master_battery(self) -> Any | None:
        """Get the master battery instance."""
        if self.master_battery_id:
            return self.batteries.get(self.master_battery_id)
        return None

    def get_slave_batteries(self) -> list[Any]:
        """Get all slave battery instances."""
        slaves = []
        for battery_id, battery in self.batteries.items():
            if battery_id != self.master_battery_id:
                slaves.append(battery)
        return slaves

    def should_poll_smart_meter(self, battery_id: str) -> bool:
        """Check if a battery should poll smart meter data."""
        # Only master battery polls smart meter data
        return battery_id == self.master_battery_id

    def get_polling_interval_for_battery(
        self, battery_id: str, data_type: str = "battery"
    ) -> int:
        """Get appropriate polling interval for specific data type."""
        if data_type == "battery_realtime":
            return 10  # BATTERY_POLL_INTERVAL - SOC, Power, Status
        if data_type == "battery_static":
            return 300  # BATTERY_STATIC_POLL_INTERVAL - Capacity, Cycles, Temperature, Energy counters
        if data_type == "smartmeter_basic":
            return (
                10 if self.should_poll_smart_meter(battery_id) else 0
            )  # SMARTMETER_POLL_INTERVAL
        if data_type == "smartmeter_phase":
            return (
                60 if self.should_poll_smart_meter(battery_id) else 0
            )  # SMARTMETER_PHASE_POLL_INTERVAL
        return 10  # Default to realtime interval

    def get_modbus_items_for_battery(self, battery_id: str) -> list[Any]:
        """Get appropriate modbus items for a specific battery."""
        # Import here to avoid circular imports
        if self.should_poll_smart_meter(battery_id):
            # Master battery polls all items (battery + smart meter)
            # Return union of MODBUS_BATTERY_ITEMS + MODBUS_SMARTMETER_ITEMS
            return []  # Will be populated by coordinator based on MODBUS_ALL_ITEMS
        # Slave batteries only poll their own battery data
        return []  # Will be populated by coordinator based on MODBUS_BATTERY_ITEMS

    def get_total_system_power(self) -> float:
        """Calculate total system power across all batteries."""
        total = 0.0
        for battery in self.batteries.values():
            if hasattr(battery, "data") and "sax_power" in battery.data:
                power = battery.data.get("sax_power", 0)
                if power is not None and isinstance(power, (int, float)):
                    total += float(power)
        return total

    def get_average_soc(self) -> float | None:
        """Calculate average SOC across all batteries."""
        soc_values: list[float] = []
        for battery in self.batteries.values():
            if hasattr(battery, "data") and "sax_soc" in battery.data:
                soc = battery.data.get("sax_soc")
                if soc is not None and isinstance(soc, (int, float)):
                    soc_values.append(float(soc))

        if soc_values:
            return sum(soc_values) / len(soc_values)
        return None


# Legacy compatibility alias
SAXBatteryData = SAXBatterySystem
