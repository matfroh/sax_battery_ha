"""Test configuration and fixtures for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest

from custom_components.sax_battery.const import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ModbusItem
from custom_components.sax_battery.models import SAXBatteryData
from homeassistant.config_entries import ConfigEntry

# Collect pytest plugins for Home Assistant testing
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    return enable_custom_integrations


@pytest.fixture
def mock_entry():
    """Return a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_address": 1,
        "name": "SAX Battery",
    }
    entry.options = {}
    entry.entry_id = "test_entry_id"
    entry.title = "SAX Battery"
    return entry


@pytest.fixture(name="mock_config_entry")
def mock_config_entry_fixture():
    """Mock config entry for tests."""
    mock_config_entry = MagicMock()
    mock_config_entry.data = {
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "battery_count": 1,
    }
    return mock_config_entry


@pytest.fixture(name="mock_sax_battery_data")
def mock_sax_battery_data_fixture(mock_config_entry):
    """Mock SAXBatteryData for modbus tests."""
    # Create actual SAXBatteryData instance with mocked entry
    return SAXBatteryData(config_entry=mock_config_entry)


@pytest.fixture(name="mock_modbus_item")
def mock_modbus_item_fixture():
    """Mock ModbusItem for tests."""
    return ModbusItem(
        name="test_item",
        address=100,
        mtype=TypeConstants.SENSOR,
        mformat=FormatConstants.TEMPERATURE,
        translation_key="test_key",
        device=DeviceConstants.SYS,
    )


@pytest.fixture(autouse=True)
def mock_modbus_client():
    """Mock AsyncModbusTcpClient to prevent event loop issues."""
    with patch(
        "custom_components.sax_battery.modbusobject.AsyncModbusTcpClient"
    ) as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock all the properties and methods we need
        type(mock_client).connected = PropertyMock(return_value=False)
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = Mock()
        mock_client.read_input_registers = AsyncMock()
        mock_client.read_holding_registers = AsyncMock()
        mock_client.write_register = AsyncMock()

        yield mock_client


@pytest.fixture
def mock_setup_entry():
    """Mock async_setup_entry."""
    with patch(
        "custom_components.sax_battery.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup
