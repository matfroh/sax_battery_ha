"""Data provider abstraction for legacy and SunSpec-backed reads."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from custom_components.sax_battery.sunspec_map import (
    SUNSPEC_REGISTER_BLOCKS,
    SunSpecRegisterBlock,
    get_sunspec_block_by_name,
    get_sunspec_block_for_address,
)

from .const_sunspec import get_canonical_sunspec_items_by_name
from .items import ModbusItem
from .sunspec_client import decode_sunspec_block_values, read_sunspec_register_block


class DataProvider(ABC):
    """Base interface used by the coordinator for value reads."""

    @abstractmethod
    async def get_realtime_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values keyed by entity name for the provided items."""

    @abstractmethod
    async def refresh_control_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Refresh control-related values after a successful write when supported."""

    @abstractmethod
    async def get_startup_metadata(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values sourced from the startup metadata block."""

    @abstractmethod
    async def get_battery_sensor_values(
        self, items: list[ModbusItem]
    ) -> dict[str, Any]:
        """Return values sourced from the battery sensor block."""

    @abstractmethod
    async def get_control_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values sourced from the control block."""

    @abstractmethod
    async def get_smart_meter_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values sourced from the smart meter block."""

    @abstractmethod
    async def get_battery_state_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values sourced from the battery state block."""

    @abstractmethod
    def get_diagnostics(self) -> dict[str, Any]:
        """Return provider diagnostics for debugging and field validation."""


class LegacyDataProvider(DataProvider):
    """Read values through the existing Modbus item path."""

    def __init__(self, modbus_api: Any) -> None:
        """Initialize the legacy provider with a Modbus API instance."""
        self._modbus_api = modbus_api

    async def get_realtime_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Read each item directly via its existing async read path."""
        values: dict[str, Any] = {}
        for item in items:
            if self._modbus_api is None:
                continue

            item.modbus_api = self._modbus_api
            value = await item.async_read_value()
            if value is not None:
                values[item.name] = value
        return values

    async def refresh_control_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Legacy mode has no separate control-block refresh path."""
        return {}

    async def get_startup_metadata(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Legacy mode has no block-level metadata path; use standard reads."""
        return await self.get_realtime_values(items)

    async def get_battery_sensor_values(
        self, items: list[ModbusItem]
    ) -> dict[str, Any]:
        """Legacy mode has no block-level sensor path; use standard reads."""
        return await self.get_realtime_values(items)

    async def get_control_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Legacy mode has no block-level control path; use standard reads."""
        return await self.get_realtime_values(items)

    async def get_smart_meter_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Legacy mode has no block-level smart-meter path; use standard reads."""
        return await self.get_realtime_values(items)

    async def get_battery_state_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Legacy mode has no block-level battery-state path; use standard reads."""
        return await self.get_realtime_values(items)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostics for the legacy provider."""
        return {"provider_type": "legacy"}


class SunSpecDataProvider(DataProvider):
    """Read values through a SunSpec-aware path using the detected device ID."""

    def __init__(self, modbus_api: Any, detected_device_id: int) -> None:
        """Initialize the SunSpec provider with a Modbus API and device ID."""
        self._modbus_api = modbus_api
        self._detected_device_id = detected_device_id
        self._block_cache: dict[str, list[int]] = {}
        self._block_status: dict[str, dict[str, Any]] = {
            block.name: {
                "required": block.required,
                "start_address": block.start_address,
                "end_address": block.end_address,
                "register_count": block.register_count,
                "cached_register_count": 0,
                "last_refresh_success": None,
                "last_refresh_time": None,
                "last_error": None,
            }
            for block in SUNSPEC_REGISTER_BLOCKS
        }
        self._sunspec_items_by_name = get_canonical_sunspec_items_by_name()

    async def get_realtime_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Read values using documented SunSpec register blocks only."""
        values: dict[str, Any] = {}

        if self._modbus_api is None:
            return values

        values.update(await self.get_startup_metadata(items))
        values.update(await self.get_battery_sensor_values(items))
        values.update(await self.get_control_values(items))
        values.update(await self.get_smart_meter_values(items))
        values.update(await self.get_battery_state_values(items))

        return values

    async def refresh_control_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Refresh the documented SunSpec control block after successful writes."""
        control_block = get_sunspec_block_by_name("battery_controls")
        if control_block is None:
            return {}

        mapped_items = [
            item
            for item in items
            if (sunspec_item := self._resolve_sunspec_item(item)) is not None
            and get_sunspec_block_for_address(sunspec_item.address) == control_block
        ]

        if not mapped_items:
            await self._read_sunspec_block(control_block)
            return {}

        return await self.get_control_values(mapped_items)

    async def get_startup_metadata(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values from block 40000-40014."""
        return await self._get_values_for_block("device_metadata", items)

    async def get_battery_sensor_values(
        self, items: list[ModbusItem]
    ) -> dict[str, Any]:
        """Return values from block 40015-40046."""
        return await self._get_values_for_block("battery_sensor_data", items)

    async def get_control_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values from block 40047-40053."""
        return await self._get_values_for_block("battery_controls", items)

    async def get_smart_meter_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values from block 40054-40094."""
        return await self._get_values_for_block("smartmeter_data", items)

    async def get_battery_state_values(self, items: list[ModbusItem]) -> dict[str, Any]:
        """Return values from block 40095-40114."""
        return await self._get_values_for_block("battery_states", items)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return SunSpec provider diagnostics including block refresh status."""
        required_blocks_failed = sorted(
            block_name
            for block_name, status in self._block_status.items()
            if bool(status.get("required"))
            and status.get("last_refresh_success") is False
        )
        optional_blocks_failed = sorted(
            block_name
            for block_name, status in self._block_status.items()
            if not bool(status.get("required"))
            and status.get("last_refresh_success") is False
        )

        return {
            "provider_type": "sunspec",
            "detected_device_id": self._detected_device_id,
            "cached_blocks": sorted(self._block_cache),
            "blocks": self._block_status,
            "required_blocks_failed": required_blocks_failed,
            "optional_blocks_failed": optional_blocks_failed,
            "session_degraded": bool(required_blocks_failed),
            "smartmeter_unavailable": "smartmeter_data" in optional_blocks_failed,
        }

    def _resolve_sunspec_item(self, item: ModbusItem) -> ModbusItem | None:
        """Resolve a legacy item name to its SunSpec-backed register definition."""
        mapped_item = self._sunspec_items_by_name.get(item.name)
        if mapped_item is not None:
            return mapped_item

        if 40000 <= item.address <= 40114:
            return item

        return None

    async def _get_values_for_block(
        self,
        block_name: str,
        items: list[ModbusItem],
    ) -> dict[str, Any]:
        """Read and decode values for items mapped to one SunSpec block."""
        block = get_sunspec_block_by_name(block_name)
        if block is None or self._modbus_api is None:
            return {}

        item_pairs: list[tuple[ModbusItem, ModbusItem]] = []
        for item in items:
            if item.mtype.value == "number_wo":
                continue

            sunspec_item = self._resolve_sunspec_item(item)
            if sunspec_item is None:
                continue

            if get_sunspec_block_for_address(sunspec_item.address) == block:
                item_pairs.append((item, sunspec_item))

        if not item_pairs:
            return {}

        block_values = await self._read_sunspec_block(block)
        if block_values is None:
            return {}

        return decode_sunspec_block_values(
            self._modbus_api,
            block=block,
            block_values=block_values,
            item_pairs=item_pairs,
        )

    async def _read_sunspec_block(
        self, block: SunSpecRegisterBlock
    ) -> list[int] | None:
        """Read and cache one documented SunSpec register block."""
        status = self._block_status[block.name]
        block_values = await read_sunspec_register_block(
            self._modbus_api,
            start_address=block.start_address,
            register_count=block.register_count,
            device_id=self._detected_device_id,
        )

        if block_values is None:
            status["last_refresh_success"] = False
            status["last_error"] = "read_failed"
            return None

        self._block_cache[block.name] = block_values
        status["cached_register_count"] = len(block_values)
        status["last_refresh_success"] = True
        status["last_refresh_time"] = datetime.now().isoformat()
        status["last_error"] = None

        return block_values
