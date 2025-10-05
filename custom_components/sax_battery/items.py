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
    """Base class for all SAX Battery data items."""

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
    _modbus_api: Any = field(default=None, init=False)

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

        if self.mtype == TypeConstants.NUMBER_WO:
            _LOGGER.debug("Skipping read for write-only item %s", self.name)
            return None

        if self._modbus_api is None:
            _LOGGER.error("ModbusAPI not set for item %s", self.name)
            return None

        try:
            result: int | float | None = await self._modbus_api.read_holding_registers(
                count=1, modbus_item=self
            )
            # Return result directly - type conversion handled by ModbusAPI
            return result  # noqa: TRY300
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
            converted_value = self._convert_write_value(value)
            if converted_value is None:
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

    def _convert_write_value(self, value: float | bool) -> int | None:
        """Convert value for Modbus writing with validation.

        Args:
            value: Value to convert (float or bool)

        Returns:
            Converted integer value or None if conversion fails

        Security: Validates data type ranges to prevent overflow
        Performance: Efficient type checking and conversion
        """
        if isinstance(value, bool):
            return self.get_switch_on_value() if value else self.get_switch_off_value()

        # Validate numeric types
        if self.data_type == ModbusClientMixin.DATATYPE.UINT16:
            if not 0 <= value <= 65535:
                _LOGGER.error(
                    "Value %s out of range for UINT16 (0-65535) on %s",
                    value,
                    self.name,
                )
                return None
        elif self.data_type == ModbusClientMixin.DATATYPE.INT16:
            if not -32768 <= value <= 32767:
                _LOGGER.error(
                    "Value %s out of range for INT16 (-32768-32767) on %s",
                    value,
                    self.name,
                )
                return None
        elif self.data_type in (
            ModbusClientMixin.DATATYPE.UINT32,
            ModbusClientMixin.DATATYPE.INT32,
        ):
            # UINT32/INT32 support for future expansion
            pass
        else:
            _LOGGER.error(
                "Unsupported data type for write: %s on %s", self.data_type, self.name
            )
            return None

        return int(round(value))

    def get_switch_on_value(self) -> int:
        """Get the value that represents the switch being 'on'."""
        return getattr(self, "switch_on_value", 2)

    def get_switch_off_value(self) -> int:
        """Get the value that represents the switch being 'off'."""
        return getattr(self, "switch_off_value", 1)

    def get_switch_connected_value(self) -> int:
        """Get the value that represents the switch being 'connected'."""
        return getattr(self, "switch_connected_value", 3)

    def get_switch_standby_value(self) -> int:
        """Get the value that represents the switch being in 'standby'."""
        return getattr(self, "switch_standby_value", 4)

    def is_tri_state_switch(self) -> bool:
        """Check if this switch supports tri-state operation."""
        return getattr(self, "supports_connected_state", True)

    def get_switch_state_name(self, value: int) -> str:
        """Get human-readable name for switch state value."""
        if not isinstance(value, int):
            return "unknown"  # type:ignore[unreachable]

        state_map = {
            self.get_switch_off_value(): "off",
            self.get_switch_on_value(): "on",
            self.get_switch_connected_value(): "connected",
            self.get_switch_standby_value(): "standby",
        }

        return state_map.get(value, "unknown")

    def is_read_only(self) -> bool:
        """Check if this item is read-only."""
        return getattr(self, "read_only", False) or self.mtype in (
            TypeConstants.SENSOR,
            TypeConstants.NUMBER_RO,
            TypeConstants.SENSOR_CALC,
        )


@dataclass
class SAXItem(BaseItem):
    """System-level calculated/aggregated item without physical communication."""

    default_value: Any = None
    coordinators: dict[str, Any] = field(default_factory=dict, init=False)

    def set_coordinators(self, coordinators: dict[str, Any]) -> None:
        """Set coordinators for multi-battery calculations."""
        self.coordinators = coordinators

    async def async_read_value(self) -> int | float | bool | None:
        """Calculate system-wide value from multiple battery coordinators."""
        return self.calculate_value(self.coordinators)

    async def async_write_value(self, value: float) -> bool:
        """Write system configuration value."""
        if self.mtype not in (TypeConstants.NUMBER, TypeConstants.NUMBER_WO):
            _LOGGER.warning("Attempted to write to read-only SAX item %s", self.name)
            return False

        if self.name == SAX_PILOT_POWER:
            return await self._write_pilot_power_value(value)

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

            if self.name != SAX_MIN_SOC:
                _LOGGER.warning("Unknown calculation type for SAXItem: %s", self.name)
            return None  # noqa: TRY300
        except (ValueError, TypeError, KeyError) as exc:
            _LOGGER.error("Error calculating value for %s: %s", self.name, exc)
            return None

    def _get_pilot_power_value(self, coordinators: dict[str, Any]) -> float | None:
        """Get pilot power value from the pilot service."""
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
            for coordinator in self.coordinators.values():
                if hasattr(coordinator, "sax_data") and hasattr(
                    coordinator.sax_data, "pilot"
                ):
                    pilot = coordinator.sax_data.pilot
                    if pilot:
                        await pilot.set_manual_power(value)
                        return True
            _LOGGER.error("No pilot service found in coordinators")
            return False  # noqa: TRY300
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to write pilot power value: %s", err)
            return False

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


@dataclass
class WebAPIItem(BaseItem):
    """Web API-based item for SAX Power web application data."""

    api_endpoint: str = ""
    api_key: str = ""
    refresh_interval: int = 300
    _web_api_client: Any = field(default=None, init=False)

    def set_api_client(self, web_api_client: Any) -> None:
        """Set the Web API client for this item."""
        self._web_api_client = web_api_client

    async def async_read_value(self) -> int | float | bool | None:
        """Read value from SAX Power Web API."""
        if self.is_invalid:
            return None

        _LOGGER.debug("Web API read not yet implemented for %s", self.name)
        return None

    async def async_write_value(self, value: float) -> bool:
        """Write value via SAX Power Web API."""
        if self.mtype not in (
            TypeConstants.NUMBER,
            TypeConstants.NUMBER_WO,
            TypeConstants.SWITCH,
        ):
            return False

        if self.is_invalid:
            return False

        _LOGGER.debug("Web API write not yet implemented for %s", self.name)
        return False
