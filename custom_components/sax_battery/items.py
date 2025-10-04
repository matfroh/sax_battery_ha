"""Items module for SAX Battery integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
from typing import Any

from pymodbus.client.mixin import ModbusClientMixin
from pymodbus.exceptions import ModbusException

from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription

# Import from entity_keys instead of const to break circular import
from .entity_keys import (
    SAX_COMBINED_SOC,
    SAX_CUMULATIVE_ENERGY_CONSUMED,
    SAX_CUMULATIVE_ENERGY_PRODUCED,
    SAX_MIN_SOC,
    SAX_PILOT_POWER,
    SAX_SMARTMETER_ENERGY_CONSUMED,
    SAX_SMARTMETER_ENERGY_PRODUCED,
    SAX_SOC,
)
from .enums import DeviceConstants, TypeConstants

_LOGGER = logging.getLogger(__name__)


@dataclass
class BaseItem(ABC):
    """Base class for all SAX Battery data items.

    Supports multiple data sources: Modbus, Web API, calculated values.
    Future extensions can add WebAPIItem, BluetoothItem, etc.
    """

    name: str
    mtype: TypeConstants
    device: DeviceConstants
    translation_key: str = ""
    entitydescription: (
        SensorEntityDescription
        | NumberEntityDescription
        | SwitchEntityDescription
        | None
    ) = None

    # State management
    _state: Any = field(default=None, init=False)
    _is_invalid: bool = field(default=False, init=False)

    @property
    def state(self) -> Any:
        """Get the current state."""
        return self._state

    @state.setter
    def state(self, value: Any) -> None:
        """Set the current state."""
        self._state = value

    @property
    def is_invalid(self) -> bool:
        """Check if the item is invalid."""
        return self._is_invalid

    @is_invalid.setter
    def is_invalid(self, value: bool) -> None:
        """Set the invalid state."""
        self._is_invalid = value

    @abstractmethod
    async def async_read_value(self) -> int | float | bool | None:
        """Read value from data source."""

    @abstractmethod
    async def async_write_value(self, value: float) -> bool:
        """Write value to data source."""


@dataclass
class ModbusItem(BaseItem):
    """Modbus-specific item with physical register communication."""

    address: int = 0
    battery_device_id: int = 1
    data_type: ModbusClientMixin.DATATYPE = ModbusClientMixin.DATATYPE.UINT16
    enabled_by_default: bool = True
    factor: float = 1.0
    offset: int = 0
    _modbus_api: Any = field(default=None, init=False)  # Will be set via set_api()

    @property
    def modbus_api(self) -> Any:
        """Get the ModbusAPI instance."""
        return self._modbus_api

    @modbus_api.setter
    def modbus_api(self, modbus_api: Any) -> None:
        """Set the ModbusAPI instance."""
        self._modbus_api = modbus_api

    async def async_read_value(self) -> int | float | bool | None:
        """Read value from physical modbus register."""
        if self.is_invalid:
            return None

        # Check if this type supports reading using TypeConstants
        if self.mtype == TypeConstants.NUMBER_WO:
            _LOGGER.debug("Skipping read for write-only item %s", self.name)
            return None

        if self._modbus_api is None:
            _LOGGER.error("ModbusAPI not set for item %s", self.name)
            return None

        try:
            result = await self._modbus_api.read_holding_registers(
                count=1, modbus_item=self
            )
            # Ensure we return the correct type
            if isinstance(result, (int, float, bool)):
                return result
            else:  # noqa: RET505
                # Convert other types appropriately
                return float(result) if isinstance(result, (int, float)) else None
        except ModbusException:
            _LOGGER.exception("Failed to read value for %s", self.name)
            return None

    async def async_write_value(self, value: float | bool) -> bool:
        """Write value to physical modbus register."""

        _LOGGER.debug(
            "Writing value %s to item %s (address: %s, data_type: %s)",
            value,
            self.name,
            self.address,
            self.data_type,
        )
        # Check if this type supports writing using TypeConstants
        if self.mtype in (
            TypeConstants.SENSOR,
            TypeConstants.NUMBER_RO,
            TypeConstants.SENSOR_CALC,
        ):
            _LOGGER.warning("Attempted to write to read-only item %s", self.name)
            return False

        if self._modbus_api is None:
            _LOGGER.error("ModbusAPI not set for item %s", self.name)
            return False

        try:
            # Convert value to appropriate type for Modbus writing
            if isinstance(value, bool):
                # For switch entities, use predefined on/off values
                converted_value = (
                    self.get_switch_on_value() if value else self.get_switch_off_value()
                )
            else:  # noqa: PLR5501
                # For number entities, convert float to int as required by UINT16/INT16
                if self.data_type in (
                    ModbusClientMixin.DATATYPE.UINT16,
                    ModbusClientMixin.DATATYPE.INT16,
                    ModbusClientMixin.DATATYPE.UINT32,
                    ModbusClientMixin.DATATYPE.INT32,
                ):
                    # Validate range for data type
                    if self.data_type == ModbusClientMixin.DATATYPE.UINT16:
                        if not 0 <= value <= 65535:
                            _LOGGER.error(
                                "Value %s out of range for UINT16 (0-65535) on %s",
                                value,
                                self.name,
                            )
                            return False
                    elif self.data_type == ModbusClientMixin.DATATYPE.INT16:
                        if not -32768 <= value <= 32767:
                            _LOGGER.error(
                                "Value %s out of range for INT16 (-32768-32767) on %s",
                                value,
                                self.name,
                            )
                            return False

                    # Convert to integer for struct.pack compatibility
                    converted_value = int(round(value))
                else:
                    # Error message for other data types
                    _LOGGER.error(
                        "Wrong data type for write_registers: item %s", self.name
                    )
                    return False

            _LOGGER.debug(
                "Writing value %s (converted: %s) to %s at address %d",
                value,
                converted_value,
                self.name,
                self.address,
            )

            result = await self._modbus_api.write_registers(
                value=converted_value, modbus_item=self
            )

            if result:
                _LOGGER.debug("Successfully wrote value to %s", self.name)
            else:
                _LOGGER.warning("Failed to write value to %s", self.name)

            return bool(result) if result is not None else False

        except (ValueError, TypeError) as exc:
            _LOGGER.error("Invalid value %s for %s: %s", value, self.name, exc)
            return False
        except ModbusException as exc:
            _LOGGER.error("Modbus error writing to %s: %s", self.name, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Unexpected error writing to %s: %s", self.name, exc)
            return False

    def get_switch_on_value(self) -> int:
        """Get the value that represents the switch being 'on'.

        Returns:
            int: Value representing switch on state (default: 2 for SAX Battery)

        Security: Returns safe default value for switch logic
        Performance: Simple attribute access with fallback
        """
        # Security: Use safe default for switch logic - SAX Battery uses 2 for "on"
        return getattr(self, "switch_on_value", 2)

    def get_switch_off_value(self) -> int:
        """Get the value that represents the switch being 'off'.

        Returns:
            int: Value representing switch off state (default: 1 for SAX Battery)

        Security: Returns safe default value for switch logic
        Performance: Simple attribute access with fallback
        """
        # Security: Use safe default for switch logic - SAX Battery uses 1 for "off"
        return getattr(self, "switch_off_value", 1)

    def get_switch_connected_value(self) -> int:
        """Get the value that represents the switch being 'connected'.

        Returns:
            int: Value representing switch connected state (3 for SAX Battery)

        Security: Returns safe default value for switch logic
        Performance: Simple attribute access with fallback
        """
        # SAX Battery uses 3 for "connected" state
        return getattr(self, "switch_connected_value", 3)

    def get_switch_standby_value(self) -> int:
        """Get the value that represents the switch being in 'standby'.

        Returns:
            int: Value representing switch standby state (4 for SAX Battery)

        Security: Returns safe default value for switch logic
        Performance: Simple attribute access with fallback
        """
        # SAX Battery uses 4 for "standby" state
        return getattr(self, "switch_standby_value", 4)

    def is_tri_state_switch(self) -> bool:
        """Check if this switch supports tri-state operation.

        Returns:
            bool: True if switch supports connected state

        Performance: Efficient attribute check
        """
        return getattr(self, "supports_connected_state", True)

    def get_switch_state_name(self, value: int) -> str:
        """Get human-readable name for switch state value.

        Args:
            value: Numeric switch state value

        Returns:
            str: Human-readable state name

        Security: Input validation with safe fallback
        """
        if not isinstance(value, int):
            return "unknown"  # type:ignore [unreachable]

        state_map = {
            self.get_switch_off_value(): "off",
            self.get_switch_on_value(): "on",
            self.get_switch_connected_value(): "connected",
            self.get_switch_standby_value(): "standby",
        }

        return state_map.get(value, "unknown")

    def is_read_only(self) -> bool:
        """Check if this item is read-only.

        Returns:
            bool: True if item is read-only, False if writable

        Performance: Efficient read-only check for optimization
        """
        # Performance: Quick check for read-only items to skip unnecessary reads
        return getattr(self, "read_only", False) or self.mtype in (
            TypeConstants.SENSOR,
            TypeConstants.NUMBER_RO,
            TypeConstants.SENSOR_CALC,
        )


@dataclass
class SAXItem(BaseItem):
    """System-level calculated/aggregated item without physical communication.

    SAXItem represents calculated values across multiple batteries or system-wide
    configuration that doesn't correspond to a single physical register.
    """

    # description: str = ""
    default_value: Any = None
    # is_system_entity: bool = True
    coordinators: dict[str, Any] = field(default_factory=dict, init=False)

    def set_coordinators(self, coordinators: dict[str, Any]) -> None:
        """Set coordinators for multi-battery calculations."""
        self.coordinators = coordinators

    async def async_read_value(self) -> int | float | bool | None:
        """Calculate system-wide value from multiple battery coordinators."""
        return self.calculate_value(self.coordinators)

    async def async_write_value(self, value: float) -> bool:
        """Write system configuration value."""
        # Check if this type supports writing using TypeConstants
        if self.mtype not in (TypeConstants.NUMBER, TypeConstants.NUMBER_WO):
            _LOGGER.warning("Attempted to write to read-only SAX item %s", self.name)
            return False

        # Handle pilot power writes
        if self.name == SAX_PILOT_POWER:
            return await self._write_pilot_power_value(value)

        # System configuration writes are handled through config entry updates
        # This will be implemented based on specific SAX item requirements
        _LOGGER.debug("SAX item write not yet implemented for %s", self.name)
        return False

    def calculate_value(self, coordinators: dict[str, Any]) -> float | int | None:
        """Calculate system-wide value from multiple battery coordinators."""
        try:
            if self.name == SAX_COMBINED_SOC:
                return self._calculate_combined_soc(coordinators)
            if self.name == SAX_CUMULATIVE_ENERGY_PRODUCED:
                return self._calculate_cumulative_energy_produced(coordinators)
            if self.name == SAX_CUMULATIVE_ENERGY_CONSUMED:
                return self._calculate_cumulative_energy_consumed(coordinators)
            if self.name == SAX_PILOT_POWER:
                return self._get_pilot_power_value(coordinators)
            # Default: return None for unknown calculation types
            if self.name != SAX_MIN_SOC:
                _LOGGER.warning("Unknown calculation type for SAXItem: %s", self.name)
            return None  # noqa: TRY300
        except (ValueError, TypeError, KeyError) as exc:
            _LOGGER.error("Error calculating value for %s: %s", self.name, exc)
            return None

    def _get_pilot_power_value(self, coordinators: dict[str, Any]) -> float | None:
        """Get pilot power value from the pilot service."""
        # Get pilot instance from sax_data
        for coordinator in coordinators.values():
            if hasattr(coordinator, "sax_data") and hasattr(
                coordinator.sax_data, "pilot"
            ):
                pilot = coordinator.sax_data.pilot
                return pilot.calculated_power if pilot else 0.0
        return 0.0

    async def _write_pilot_power_value(self, value: float) -> bool:
        """Write pilot power value to the pilot service."""
        try:
            # Get pilot instance from coordinators
            for coordinator in self.coordinators.values():
                if hasattr(coordinator, "sax_data") and hasattr(
                    coordinator.sax_data, "pilot"
                ):
                    pilot = coordinator.sax_data.pilot
                    if pilot:
                        await pilot.set_manual_power(value)
                        return True
            return False  # noqa: TRY300
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to write pilot power value: %s", err)
            return False

    # Calculation functions for SAXItem values
    def _calculate_combined_soc(
        self,
        coordinators: dict[str, Any],
    ) -> float | None:
        """Calculate combined SOC across all batteries."""
        total_soc = 0.0
        count = 0

        for coordinator in coordinators.values():
            if coordinator.data and SAX_SOC in coordinator.data:
                soc_value = coordinator.data[SAX_SOC]
                if soc_value is not None:
                    total_soc += float(soc_value)
                    count += 1

        return total_soc / count if count > 0 else None

    def _calculate_cumulative_energy_produced(
        self,
        coordinators: dict[str, Any],
    ) -> float | None:
        """Calculate cumulative energy produced across all batteries."""
        total_energy = 0.0
        count = 0

        for coordinator in coordinators.values():
            if coordinator.data and SAX_SMARTMETER_ENERGY_PRODUCED in coordinator.data:
                energy_value = coordinator.data[SAX_SMARTMETER_ENERGY_PRODUCED]
                if energy_value is not None:
                    total_energy += float(energy_value)
                    count += 1

        return total_energy if count > 0 else None

    def _calculate_cumulative_energy_consumed(
        self,
        coordinators: dict[str, Any],
    ) -> float | None:
        """Calculate cumulative energy consumed across all batteries."""
        total_energy = 0.0
        count = 0

        for coordinator in coordinators.values():
            if coordinator.data and SAX_SMARTMETER_ENERGY_CONSUMED in coordinator.data:
                energy_value = coordinator.data[SAX_SMARTMETER_ENERGY_CONSUMED]
                if energy_value is not None:
                    total_energy += float(energy_value)
                    count += 1

        return total_energy if count > 0 else None


# Future extension example for Web API items
@dataclass
class WebAPIItem(BaseItem):
    """Web API-based item for SAX Power web application data.

    Future implementation for data not available via Modbus:
    - Detailed battery analytics
    - Historical performance data
    - Advanced configuration options
    - Remote diagnostics
    """

    api_endpoint: str = ""
    api_key: str = ""
    refresh_interval: int = 300  # 5 minutes default
    _web_api_client: Any = field(default=None, init=False)

    def set_api_client(self, web_api_client: Any) -> None:
        """Set the Web API client for this item."""
        self._web_api_client = web_api_client

    async def async_read_value(self) -> int | float | bool | None:
        """Read value from SAX Power Web API."""
        if self.is_invalid:
            return None

        # Future implementation
        _LOGGER.debug("Web API read not yet implemented for %s", self.name)
        return None

    async def async_write_value(self, value: float) -> bool:
        """Write value via SAX Power Web API."""
        # Check if this type supports writing using TypeConstants
        if self.mtype not in (
            TypeConstants.NUMBER,
            TypeConstants.NUMBER_WO,
            TypeConstants.SWITCH,
        ):
            return False

        if self.is_invalid:
            return False

        # Future implementation
        _LOGGER.debug("Web API write not yet implemented for %s", self.name)
        return False
