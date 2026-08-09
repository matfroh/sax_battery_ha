"""Tests for the coordinator data provider abstraction."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.sax_battery.data_provider import (
    LegacyDataProvider,
    SunSpecDataProvider,
)
from custom_components.sax_battery.entity_keys import (
    SAX_CAPACITY,
    SAX_SMARTMETER_AC_CURRENT_SUM,
    SAX_SMARTMETER_CURRENT_L1,
    SAX_SMARTMETER_ENERGY_CONSUMED,
    SAX_SMARTMETER_ENERGY_PRODUCED,
    SAX_SMARTMETER_SWITCHING_STATE,
    SAX_SMARTMETER_TOTAL_POWER,
    SAX_SOC,
    SAX_SUNSPEC_POWER_SETPOINT,
    SAX_TEMPERATURE,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem


class _FakeModbusAPI:
    """Minimal fake Modbus API for provider tests."""

    def __init__(self, values: dict[str, int | float | None] | None = None) -> None:
        self._values = values or {}
        self.calls: list[tuple[str, int | None]] = []
        self.block_calls: list[tuple[int, int, int]] = []

    async def read_holding_registers(
        self,
        count: int,
        modbus_item: ModbusItem,
        device_id: int | None = None,
    ) -> int | float | None:
        self.calls.append((modbus_item.name, device_id))
        return self._values.get(modbus_item.name)

    async def read_register_block(
        self,
        address: int,
        count: int,
        device_id: int,
    ) -> list[int] | None:
        self.block_calls.append((address, count, device_id))
        registers = [0] * count
        if address == 40000:
            registers[0] = 75
        if address == 40015:
            registers[0] = 830
            registers[1] = 215
        if address == 40047:
            registers[2] = 777
        if address == 40095:
            registers[1] = 123
            registers[2] = 456
            registers[4] = 3
            registers[5] = 321
            registers[15] = 789
        return registers

    def decode_register_block_value(
        self,
        registers: list[int],
        modbus_item: ModbusItem,
    ) -> int | float | None:
        if not registers:
            return None
        value: int | float = registers[0]
        if modbus_item.factor != 1.0:
            value *= modbus_item.factor
        return value


class _FlakyBlockModbusAPI(_FakeModbusAPI):
    """Fake Modbus API that fails the first read for selected block starts."""

    def __init__(self, fail_first_addresses: set[int]) -> None:
        super().__init__()
        self._fail_first_addresses = fail_first_addresses
        self._attempts: dict[int, int] = {}

    async def read_register_block(
        self,
        address: int,
        count: int,
        device_id: int,
    ) -> list[int] | None:
        self._attempts[address] = self._attempts.get(address, 0) + 1
        if address in self._fail_first_addresses and self._attempts[address] == 1:
            self.block_calls.append((address, count, device_id))
            return None

        return await super().read_register_block(address, count, device_id)


class _AlwaysFailBlockModbusAPI(_FakeModbusAPI):
    """Fake Modbus API that always fails selected block starts."""

    def __init__(self, failed_addresses: set[int]) -> None:
        super().__init__()
        self._failed_addresses = failed_addresses

    async def read_register_block(
        self,
        address: int,
        count: int,
        device_id: int,
    ) -> list[int] | None:
        self.block_calls.append((address, count, device_id))
        if address in self._failed_addresses:
            return None
        return await super().read_register_block(address, count, device_id)


def test_legacy_provider_reads_values_without_overrides() -> None:
    """Legacy provider should read items using the default Modbus device ID."""
    api = _FakeModbusAPI({"sax_soc": 55, "sax_power": -1200})
    provider = LegacyDataProvider(modbus_api=api)
    item_soc = ModbusItem(
        name="sax_soc",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item_soc.modbus_api = api
    item_power = ModbusItem(
        name="sax_power",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item_power.modbus_api = api

    result = asyncio.run(provider.get_realtime_values([item_soc, item_power]))

    assert result == {"sax_soc": 55, "sax_power": -1200}
    assert api.calls == [("sax_soc", None), ("sax_power", None)]


def test_sunspec_provider_uses_detected_device_id() -> None:
    """SunSpec provider should override the device ID for SunSpec reads."""
    api = _FakeModbusAPI({"sax_soc": 75})
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SOC,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_realtime_values([item]))

    assert result == {SAX_SOC: 75}
    assert api.block_calls == [(40000, 15, 100)]
    assert api.calls == []


def test_sunspec_provider_reads_documented_block_once_for_multiple_items() -> None:
    """SunSpec provider should use one documented block read for items in one block."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item_capacity = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item_capacity.modbus_api = api
    item_temperature = ModbusItem(
        name=SAX_TEMPERATURE,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item_temperature.modbus_api = api

    result = asyncio.run(
        provider.get_realtime_values([item_capacity, item_temperature])
    )

    assert result == {SAX_CAPACITY: 830, SAX_TEMPERATURE: 215}
    assert api.block_calls == [(40015, 32, 100)]
    assert api.calls == []


def test_sunspec_provider_refreshes_control_block_after_write() -> None:
    """SunSpec provider should target the documented control block refresh path."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SUNSPEC_POWER_SETPOINT,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
    )
    item.modbus_api = api

    result = asyncio.run(provider.refresh_control_values([item]))

    assert result[SAX_SUNSPEC_POWER_SETPOINT] == pytest.approx(7.77)
    assert api.block_calls == [(40047, 7, 100)]


def test_sunspec_provider_exposes_block_refresh_diagnostics() -> None:
    """SunSpec provider should report per-block refresh metadata."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SOC,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item.modbus_api = api

    asyncio.run(provider.get_realtime_values([item]))
    diagnostics = provider.get_diagnostics()

    assert diagnostics["provider_type"] == "sunspec"
    assert diagnostics["detected_device_id"] == 100
    assert diagnostics["cached_blocks"] == ["device_metadata"]
    assert diagnostics["blocks"]["device_metadata"]["last_refresh_success"] is True
    assert diagnostics["blocks"]["device_metadata"]["cached_register_count"] == 15
    assert diagnostics["blocks"]["device_metadata"]["last_refresh_time"] is not None


def test_sunspec_provider_reads_state_block_once_for_multiple_items() -> None:
    """SunSpec provider should use one state-block read for documented 40095+ items."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item_energy_produced = ModbusItem(
        name=SAX_SMARTMETER_ENERGY_PRODUCED,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item_energy_produced.modbus_api = api
    item_energy_consumed = ModbusItem(
        name=SAX_SMARTMETER_ENERGY_CONSUMED,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item_energy_consumed.modbus_api = api
    item_switching_state = ModbusItem(
        name=SAX_SMARTMETER_SWITCHING_STATE,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item_switching_state.modbus_api = api
    item_current_l1 = ModbusItem(
        name=SAX_SMARTMETER_CURRENT_L1,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item_current_l1.modbus_api = api
    item_total_power = ModbusItem(
        name=SAX_SMARTMETER_TOTAL_POWER,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item_total_power.modbus_api = api

    result = asyncio.run(
        provider.get_realtime_values(
            [
                item_energy_produced,
                item_energy_consumed,
                item_switching_state,
                item_current_l1,
                item_total_power,
            ]
        )
    )

    assert result == {
        SAX_SMARTMETER_ENERGY_PRODUCED: 1230.0,
        SAX_SMARTMETER_ENERGY_CONSUMED: 4560.0,
        SAX_SMARTMETER_SWITCHING_STATE: 3,
        SAX_SMARTMETER_CURRENT_L1: 32.1,
        SAX_SMARTMETER_TOTAL_POWER: 789,
    }
    assert api.block_calls == [(40095, 20, 100)]


def test_sunspec_provider_get_startup_metadata_uses_metadata_block() -> None:
    """Startup metadata reads should use block 40000-40014 only."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SOC,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_startup_metadata([item]))

    assert result == {SAX_SOC: 75}
    assert api.block_calls == [(40000, 15, 100)]


def test_sunspec_provider_get_battery_sensor_values_uses_sensor_block() -> None:
    """Battery sensor reads should use block 40015-40046 only."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item_capacity = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item_capacity.modbus_api = api
    item_temperature = ModbusItem(
        name=SAX_TEMPERATURE,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item_temperature.modbus_api = api

    result = asyncio.run(
        provider.get_battery_sensor_values([item_capacity, item_temperature])
    )

    assert result == {SAX_CAPACITY: 830, SAX_TEMPERATURE: 215}
    assert api.block_calls == [(40015, 32, 100)]


def test_sunspec_provider_get_control_values_uses_control_block() -> None:
    """Control reads should use block 40047-40053 only."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SUNSPEC_POWER_SETPOINT,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_control_values([item]))

    assert result[SAX_SUNSPEC_POWER_SETPOINT] == pytest.approx(7.77)
    assert api.block_calls == [(40047, 7, 100)]


def test_sunspec_provider_get_smart_meter_values_uses_meter_block() -> None:
    """Smart-meter reads should use block 40054-40094 only."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SMARTMETER_AC_CURRENT_SUM,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_smart_meter_values([item]))

    assert result == {SAX_SMARTMETER_AC_CURRENT_SUM: 0}
    assert api.block_calls == [(40054, 41, 100)]


def test_sunspec_provider_realtime_does_not_fallback_to_single_register_reads() -> None:
    """SunSpec realtime reads should not use direct per-register fallback reads."""
    api = _FakeModbusAPI({"legacy_unmapped": 999})
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name="legacy_unmapped",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
        address=999,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_realtime_values([item]))

    assert result == {}
    assert api.calls == []
    assert api.block_calls == []


def test_sunspec_provider_retries_transient_block_read_failures() -> None:
    """SunSpec provider should recover when a documented block read fails once."""
    api = _FlakyBlockModbusAPI({40015})
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item_capacity = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item_capacity.modbus_api = api

    result = asyncio.run(provider.get_battery_sensor_values([item_capacity]))

    assert result == {SAX_CAPACITY: 830}
    assert api.block_calls == [(40015, 32, 100), (40015, 32, 100)]


def test_sunspec_provider_diagnostics_marks_optional_block_unavailable() -> None:
    """Optional smart-meter block failures should not mark session degraded."""
    api = _AlwaysFailBlockModbusAPI({40054})
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SMARTMETER_AC_CURRENT_SUM,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_smart_meter_values([item]))
    diagnostics = provider.get_diagnostics()

    assert result == {}
    assert diagnostics["session_degraded"] is False
    assert diagnostics["smartmeter_unavailable"] is True
    assert diagnostics["optional_blocks_failed"] == ["smartmeter_data"]
    assert diagnostics["required_blocks_failed"] == []


def test_sunspec_provider_diagnostics_marks_required_block_degraded() -> None:
    """Required block failures should mark session degraded."""
    api = _AlwaysFailBlockModbusAPI({40015})
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_CAPACITY,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_battery_sensor_values([item]))
    diagnostics = provider.get_diagnostics()

    assert result == {}
    assert diagnostics["session_degraded"] is True
    assert diagnostics["required_blocks_failed"] == ["battery_sensor_data"]


def test_sunspec_provider_get_battery_state_values_uses_state_block() -> None:
    """Battery-state reads should use block 40095-40114 only."""
    api = _FakeModbusAPI()
    provider = SunSpecDataProvider(modbus_api=api, detected_device_id=100)
    item = ModbusItem(
        name=SAX_SMARTMETER_TOTAL_POWER,
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SM,
    )
    item.modbus_api = api

    result = asyncio.run(provider.get_battery_state_values([item]))

    assert result == {SAX_SMARTMETER_TOTAL_POWER: 789}
    assert api.block_calls == [(40095, 20, 100)]
