"""Global fixtures for SAX Battery integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# Only import what's absolutely necessary for tests
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture
def mock_sax_battery_data():
    """Create mock SAX battery data."""
    mock_data = MagicMock()
    mock_data.master_battery_id = "battery_a"
    mock_data.coordinators = {}
    mock_data.batteries = {}
    mock_data.smart_meter_data = MagicMock()

    # Mock methods
    mock_data.get_device_info = MagicMock(
        return_value={
            "identifiers": {("sax_battery", "test_battery")},
            "name": "Test SAX Battery",
            "manufacturer": "SAX-power",
            "model": "Test Model",
        }
    )

    mock_data.should_poll_smart_meter = MagicMock(return_value=False)
    mock_data.get_sax_items_for_battery = MagicMock(return_value=[])
    mock_data.get_modbus_items_for_battery = MagicMock(return_value=[])

    return mock_data


@pytest.fixture
def mock_coordinator():
    """Create mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {"test_item": 42}
    coordinator.last_update_success = True
    coordinator.last_update_success_time = 1234567890.0
    coordinator.api_items = []
    coordinator.sax_data = MagicMock()

    # Mock async methods
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_write_switch_value = AsyncMock(return_value=True)
    coordinator.async_write_numeric_value = AsyncMock(return_value=True)
    coordinator.async_write_int_value = AsyncMock(return_value=True)
    coordinator.update_sax_item_state = MagicMock()

    return coordinator


@pytest.fixture
def mock_modbus_item():
    """Create mock modbus item."""
    item = MagicMock()
    item.name = "test_item"
    item.address = 100
    item.mtype = MagicMock()
    item.unit = "V"
    item.icon = "mdi:battery"
    item.min_value = 0.0
    item.max_value = 100.0
    item.step = 1.0
    return item


@pytest.fixture
def mock_config_entry():
    """Create mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "batteries": {
            "battery_a": {"name": "Battery A", "slave_id": 1},
            "battery_b": {"name": "Battery B", "slave_id": 2},
        },
    }
    entry.options = {}
    return entry
