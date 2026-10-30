"""Tests for the PowerControlStrategy abstraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.const_sunspec import (
    SAX_SUNSPEC_CONTROL_MODE,
    SAX_SUNSPEC_POWER_SETPOINT,
    SAX_SUNSPEC_REFERENCE_POWER,
    SAX_SUNSPEC_SETPOINT_TIMEOUT,
)
from custom_components.sax_battery.entity_keys import (
    SAX_POWER_SETPOINT,
    SAX_POWER_SETPOINT_FACTOR,
)
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.power_control_strategy import (
    LegacyPowerControlStrategy,
    SunSpecPowerControlStrategy,
)


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """Create a mock coordinator for strategy testing."""
    coord = MagicMock()
    coord.sax_data = MagicMock()
    coord.sax_data.coordinators = {"bess_a": MagicMock(), "bess_b": MagicMock()}
    coord.data = {
        SAX_POWER_SETPOINT: 0,
        SAX_POWER_SETPOINT_FACTOR: 100,
        SAX_SUNSPEC_REFERENCE_POWER: 9200,
    }
    coord.async_write_power_control_value = AsyncMock(return_value=True)
    coord.async_write_number_value = AsyncMock(return_value=True)
    return coord


async def test_legacy_power_control_strategy(mock_coordinator: MagicMock) -> None:
    """Test Legacy strategy sets power via atomic write."""
    power_item = ModbusItem(
        name=SAX_POWER_SETPOINT,
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.SYS,
    )
    factor_item = ModbusItem(
        name=SAX_POWER_SETPOINT_FACTOR,
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.SYS,
    )
    mock_coordinator.sax_data.get_item_by_name = lambda name: {
        SAX_POWER_SETPOINT: power_item,
        SAX_POWER_SETPOINT_FACTOR: factor_item,
    }.get(name)

    strategy = LegacyPowerControlStrategy(mock_coordinator)
    assert strategy.get_max_power_rating() == 9200.0

    res = await strategy.async_set_power(3000.0)
    assert res is True
    mock_coordinator.async_write_power_control_value.assert_called_once_with(
        power_item, 3000, 100
    )


async def test_sunspec_power_control_strategy(mock_coordinator: MagicMock) -> None:
    """Test SunSpec strategy converts watts to percentage and writes registers."""
    setpoint_item = ModbusItem(
        name=SAX_SUNSPEC_POWER_SETPOINT,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,
    )
    timeout_item = ModbusItem(
        name=SAX_SUNSPEC_SETPOINT_TIMEOUT,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,
    )
    mode_item = ModbusItem(
        name=SAX_SUNSPEC_CONTROL_MODE,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,
    )
    mock_coordinator.sax_data.get_item_by_name = lambda name: {
        SAX_SUNSPEC_POWER_SETPOINT: setpoint_item,
        SAX_SUNSPEC_SETPOINT_TIMEOUT: timeout_item,
        SAX_SUNSPEC_CONTROL_MODE: mode_item,
    }.get(name)

    strategy = SunSpecPowerControlStrategy(mock_coordinator)
    assert strategy.get_max_power_rating() == 9200.0

    # 4600W on a 9200W reference is 50%
    res = await strategy.async_set_power(4600.0, timeout_s=60)
    assert res is True
    assert mock_coordinator.async_write_number_value.call_count == 3

    # Test zero balance mode
    mock_coordinator.async_write_number_value.reset_mock()
    res_zb = await strategy.async_set_mode_zero_balance()
    assert res_zb is True
    mock_coordinator.async_write_number_value.assert_called_once_with(mode_item, 0)
