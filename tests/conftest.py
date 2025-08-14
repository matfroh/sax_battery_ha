"""Global fixtures for SAX Battery integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.modbusobject import ModbusAPI

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture
def mock_modbus_api():
    """Create mock ModbusAPI."""
    api = MagicMock(spec=ModbusAPI)
    api.battery_id = "battery_a"
    api._host = "192.168.1.100"
    api._port = 502
    api._connected = True

    api.connect = AsyncMock(return_value=True)
    api.close = MagicMock(return_value=True)
    api.write_holding_register = AsyncMock(return_value=True)
    api.read_holding_registers = AsyncMock(return_value=[100])
    api.read_input_registers = AsyncMock(return_value=[100])

    # Mock the modbus client
    mock_client = MagicMock()
    mock_client.connected = True
    mock_client.write_register = AsyncMock(
        return_value=MagicMock(isError=MagicMock(return_value=False))
    )
    api.get_device.return_value = mock_client

    return api


@pytest.fixture
def mock_sax_data():
    """Create mock SAX battery data."""
    data = MagicMock()
    data.master_battery_id = "battery_a"
    data.coordinators = {}
    data.batteries = {"battery_a": MagicMock()}
    data.batteries["battery_a"].data = {"test_value": 42}
    data.smart_meter_data = MagicMock()
    data.smart_meter_data.data = {"smartmeter_total_power": 2500.0}

    # Mock methods
    data.get_device_info = MagicMock(
        return_value={
            "identifiers": {("sax_battery", "test_battery")},
            "name": "Test SAX Battery",
            "manufacturer": "SAX-power",
            "model": "Test Model",
        }
    )

    data.should_poll_smart_meter = MagicMock(return_value=False)
    data.get_modbus_items_for_battery = MagicMock(return_value=[])
    data.get_sax_items_for_battery = MagicMock(return_value=[])
    data.get_smart_meter_items = MagicMock(return_value=[])

    return data


@pytest.fixture
def mock_coordinator():
    """Create mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {"test_value": 42}
    coordinator.last_update_success = True
    coordinator.last_update_success_time = 1234567890.0
    coordinator.battery_id = "battery_a"
    coordinator._first_update_done = False

    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    coordinator._async_update_data = AsyncMock(return_value={"test_value": 42})

    return coordinator


@pytest.fixture
def mock_modbus_item():
    """Create mock ModbusItem."""
    item = ModbusItem(
        name="test_item",
        address=100,
        battery_slave_id=1,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,  # Fixed: Use SYS instead of BATTERY
        divider=10,
    )
    return item  # noqa: RET504


@pytest.fixture
def mock_config_entry():
    """Create mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "battery_b_host": "192.168.1.101",
        "battery_b_port": 502,
        "batteries": {
            "battery_a": {"name": "Battery A", "slave_id": 1},
            "battery_b": {"name": "Battery B", "slave_id": 2},
        },
    }
    entry.options = {}
    return entry
