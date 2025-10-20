"""Global fixtures for SAX Battery integration tests."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_BATTERY_COUNT,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_GRID_POWER_SENSOR,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    CONF_PRIORITY_DEVICES,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DESCRIPTION_SAX_COMBINED_SOC,
    DESCRIPTION_SAX_MAX_CHARGE,
    DESCRIPTION_SAX_MIN_SOC,
    DESCRIPTION_SAX_NOMINAL_POWER,
    DESCRIPTION_SAX_STATUS_SWITCH,
    DOMAIN,
    PILOT_ITEMS,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
    SAX_STATUS,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.modbusobject import ModbusAPI
from custom_components.sax_battery.models import BatteryModel, SAXBatteryData
from custom_components.sax_battery.soc_manager import SOCManager
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)

pytest_plugins = "pytest_homeassistant_custom_component"


# Base Mock Objects
@pytest.fixture
def mock_hass_base():
    """Create base mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock(return_value=True)
    hass.data = {}
    hass.loop_thread_id = 1
    return hass


@pytest.fixture
def mock_config_entry_base():
    """Create base mock config entry."""
    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.data = {"min_soc": 15, "max_charge": 4000.0, "max_discharge": 3000.0}
    config_entry.options = {}
    return config_entry


# Coordinator Fixtures
@pytest.fixture
def mock_coordinator_modbus_base(mock_hass_base, mock_config_entry_base):
    """Create base mock coordinator for modbus number tests."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.data = {"sax_temperature": 25.5}
    coordinator.battery_id = "battery_a"
    coordinator.hass = mock_hass_base
    coordinator.sax_data = MagicMock()
    coordinator.sax_data.get_device_info.return_value = {"name": "Test Battery"}
    coordinator.config_entry = mock_config_entry_base
    coordinator.battery_config = {"is_master": True, "phase": "L1"}
    coordinator.modbus_api = MagicMock()
    coordinator.modbus_api.write_holding_registers = AsyncMock(return_value=True)
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    coordinator.async_request_refresh = AsyncMock(return_value=None)
    coordinator.last_update_success = True
    coordinator.last_update_success_time = MagicMock()
    return coordinator


@pytest.fixture
def mock_coordinator_config_base(mock_hass_base, mock_config_entry_base):
    """Create base mock coordinator for config number tests."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.data = {SAX_MIN_SOC: 20.0}
    coordinator.battery_id = "battery_a"
    coordinator.hass = mock_hass_base
    coordinator.sax_data = MagicMock()
    coordinator.sax_data.get_device_info.return_value = {"name": "Test Battery"}
    coordinator.config_entry = mock_config_entry_base
    coordinator.battery_config = {"is_master": True, "phase": "L1"}
    coordinator.async_write_sax_value = AsyncMock(return_value=True)
    coordinator.last_update_success = True
    coordinator.last_update_success_time = MagicMock()

    # Add soc_manager mock for min_soc initialization
    coordinator.soc_manager = MagicMock()
    coordinator.soc_manager.min_soc = 10.0  # Default minimum SOC

    return coordinator


@pytest.fixture
def mock_hass_number():
    """Create mock Home Assistant instance for number tests."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock(return_value=True)
    hass.data = {}
    return hass


@pytest.fixture
def mock_coordinator_config_number_unique(mock_hass_number):
    """Create mock coordinator with SOC data for config number tests."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.battery_id = "battery_a"
    coordinator.hass = mock_hass_number
    coordinator.sax_data = MagicMock()
    coordinator.sax_data.get_device_info.return_value = {
        "identifiers": {("sax_battery", "cluster")},
        "name": "SAX Cluster",
    }
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.entry_id = "test_entry"
    coordinator.config_entry.data = {CONF_MIN_SOC: 10, CONF_BATTERY_COUNT: 1}
    coordinator.battery_config = {"is_master": True, "phase": "L1"}
    coordinator.last_update_success = True
    coordinator.last_update_success_time = MagicMock()

    # Add soc_manager mock - THIS IS THE AUTHORITATIVE VALUE
    coordinator.soc_manager = MagicMock()
    coordinator.soc_manager.min_soc = 10.0

    # Remove coordinator.data - it's not used for min_soc
    # The native_value property reads from soc_manager.min_soc

    return coordinator


@pytest.fixture
def mock_coordinator_pilot_control_base(mock_hass_base, mock_config_entry_base):
    """Create base mock coordinator for pilot control tests."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.data = {}
    coordinator.battery_id = "battery_a"
    coordinator.hass = mock_hass_base
    coordinator.sax_data = MagicMock()
    coordinator.sax_data.get_device_info.return_value = {"name": "Test Battery"}
    coordinator.config_entry = mock_config_entry_base
    coordinator.battery_config = {"is_master": True, "phase": "L1"}
    coordinator.async_write_pilot_control_value = AsyncMock(return_value=True)
    coordinator.last_update_success = True
    coordinator.last_update_success_time = MagicMock()
    return coordinator


# ModbusItem Fixtures
@pytest.fixture
def modbus_item_max_charge_base():
    """Create power number ModbusItem for testing."""
    return ModbusItem(
        address=44,
        name=SAX_MAX_CHARGE,
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.SYS,
        entitydescription=DESCRIPTION_SAX_MAX_CHARGE,
    )


@pytest.fixture
def modbus_item_percentage_base():
    """Create percentage number ModbusItem for testing."""
    return ModbusItem(
        address=101,
        name=SAX_MIN_SOC,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,
        entitydescription=DESCRIPTION_SAX_MIN_SOC,
    )


@pytest.fixture
def modbus_item_pilot_power_base():
    """Create pilot control power ModbusItem for testing."""
    return ModbusItem(
        address=41,
        name=SAX_NOMINAL_POWER,
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.BESS,
        entitydescription=NumberEntityDescription(
            key="nominal_power",
            name="Nominal Power",
            native_min_value=0,
            native_max_value=5000,
            native_step=100,
            native_unit_of_measurement="W",
        ),
    )


@pytest.fixture
def soc_manager(mock_coordinator) -> SOCManager:
    """Create real SOCManager instance for integration testing.

    This fixture provides a real SOCManager with mocked coordinator for tests
    that need to verify actual SOCManager behavior (not just interface compliance).

    Performance:
        Reusable fixture reduces test setup overhead

    Security:
        OWASP A05: Validates actual constraint enforcement logic

    Returns:
        Real SOCManager instance with mocked dependencies
    """
    # Ensure hass.services.async_call is AsyncMock (awaitable)
    mock_coordinator.hass.services.async_call = AsyncMock(return_value=None)

    # Ensure config_entry exists
    if not hasattr(mock_coordinator, "config_entry"):
        mock_coordinator.config_entry = MagicMock()
        mock_coordinator.config_entry.entry_id = "test_entry_123"

    # Create real SOCManager instance (not a mock)
    manager = SOCManager(
        coordinator=mock_coordinator,
        min_soc=20.0,
        enabled=True,
    )

    return manager  # noqa: RET504


@pytest.fixture
def mock_soc_manager() -> SOCManager:
    """Create a properly configured SOCManager for testing.

    Returns real SOCManager instance with mocked dependencies.
    Security:
        OWASP A05: Validates manager has required attributes for testing
    """
    # Create mock coordinator with required attributes
    mock_coordinator = MagicMock()
    mock_coordinator.data = {}

    # Create mock Home Assistant instance
    mock_hass = MagicMock()
    # FIX: Use AsyncMock for async_call since it's awaitable
    mock_hass.services.async_call = AsyncMock(return_value=None)

    # Mock entity registry for entity ID lookups
    mock_entity_registry = MagicMock()
    mock_entity_registry.async_get_entity_id = MagicMock(
        return_value="number.test_entity"
    )
    mock_hass.data = {"entity_registry": mock_entity_registry}

    mock_coordinator.hass = mock_hass

    # Create mock config_entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry_123"
    mock_coordinator.config_entry = mock_entry

    # Create mock SAXBatteryData with get_unique_id_for_item
    mock_sax_data = MagicMock()
    mock_sax_data.get_unique_id_for_item = MagicMock(return_value=None)
    mock_coordinator.sax_data = mock_sax_data

    # Create mock battery_id
    mock_coordinator.battery_id = "battery_a"

    # Create REAL SOCManager instance with mocked dependencies
    manager = SOCManager(
        coordinator=mock_coordinator,
        min_soc=20.0,
        enabled=True,
    )

    return manager  # noqa: RET504


@pytest.fixture
def mock_coordinator_master(
    mock_sax_data, mock_modbus_api, mock_config_entry, mock_soc_manager
):
    """Create mock master battery coordinator for power manager tests.

    Performance:
        Reusable fixture reduces test setup overhead

    Security:
        OWASP A01: Validates master battery role
    """
    coordinator = MagicMock(spec=SAXBatteryCoordinator)

    # Basic coordinator properties
    coordinator.hass = MagicMock()
    coordinator.hass.data = {DOMAIN: {}}
    coordinator.hass.states = MagicMock()
    coordinator.hass.services = MagicMock()
    coordinator.hass.services.async_call = AsyncMock()

    coordinator.data = {
        "sax_soc": 75.0,
        "sax_power": 2000.0,
        "sax_max_charge": 4500.0,
        "sax_max_discharge": 3600.0,
        "sax_combined_soc": 75.0,
    }

    coordinator.battery_id = "battery_a"
    coordinator.last_update_success = True
    coordinator.last_update_success_time = 1234567890.0

    # Battery configuration
    coordinator.battery_config = {
        "is_master": True,
        "phase": "L1",
        "enabled": True,
    }

    # Config entry
    coordinator.config_entry = mock_config_entry

    # SAX data with single battery
    coordinator.sax_data = mock_sax_data
    coordinator.sax_data.coordinators = {"battery_a": coordinator}
    coordinator.sax_data.master_battery_id = "battery_a"

    # Modbus API
    coordinator.modbus_api = mock_modbus_api

    # SOC manager
    coordinator.soc_manager = mock_soc_manager

    # Async methods
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    coordinator.async_set_updated_data = MagicMock()
    coordinator._async_update_data = AsyncMock(return_value=coordinator.data)

    return coordinator


@pytest.fixture
def mock_coordinator_slave(
    mock_sax_data, mock_modbus_api, mock_config_entry, mock_soc_manager
):
    """Create mock slave battery coordinator for multi-battery tests.

    Performance:
        Efficient mock for testing multi-battery scenarios
    """
    coordinator = MagicMock(spec=SAXBatteryCoordinator)

    # Basic coordinator properties
    coordinator.hass = MagicMock()
    coordinator.hass.data = {DOMAIN: {}}

    coordinator.data = {
        "sax_soc": 70.0,
        "sax_power": 1500.0,
        "sax_max_charge": 4500.0,
        "sax_max_discharge": 3600.0,
    }

    coordinator.battery_id = "battery_b"
    coordinator.last_update_success = True
    coordinator.last_update_success_time = 1234567890.0

    # Battery configuration (slave)
    coordinator.battery_config = {
        "is_master": False,
        "phase": "L2",
        "enabled": True,
    }

    # Config entry
    coordinator.config_entry = mock_config_entry

    # SAX data
    coordinator.sax_data = mock_sax_data

    # Modbus API
    coordinator.modbus_api = mock_modbus_api

    # SOC manager
    coordinator.soc_manager = mock_soc_manager

    # Async methods
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    coordinator.async_set_updated_data = MagicMock()
    coordinator._async_update_data = AsyncMock(return_value=coordinator.data)

    return coordinator


@pytest.fixture
def mock_multi_battery_coordinators(mock_coordinator_master, mock_coordinator_slave):
    """Create dictionary of mock coordinators for multi-battery testing.

    Performance:
        Efficient fixture composition pattern
    """
    # Add third battery
    mock_coordinator_c = MagicMock(spec=SAXBatteryCoordinator)
    mock_coordinator_c.battery_id = "battery_c"
    mock_coordinator_c.battery_config = {
        "is_master": False,
        "phase": "L3",
        "enabled": True,
    }
    mock_coordinator_c.data = {
        "sax_soc": 72.0,
        "sax_power": 1800.0,
    }

    coordinators = {
        "battery_a": mock_coordinator_master,
        "battery_b": mock_coordinator_slave,
        "battery_c": mock_coordinator_c,
    }

    # Update master's sax_data to include all coordinators
    mock_coordinator_master.sax_data.coordinators = coordinators

    return coordinators


@pytest.fixture
def temperature_modbus_item_sensor():
    """Create temperature sensor ModbusItem for testing.

    Performance:
        Reusable fixture for sensor tests
    """
    return ModbusItem(
        address=200,
        name="sax_temperature",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.BESS,
        entitydescription=SensorEntityDescription(
            key="temperature",
            name="Temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
    )


@pytest.fixture
def modbus_item_pilot_factor_base():
    """Create pilot control power factor ModbusItem for testing."""
    return ModbusItem(
        address=42,
        name=SAX_NOMINAL_FACTOR,
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.BESS,
        entitydescription=NumberEntityDescription(
            key="nominal_factor",
            name="Nominal Power Factor",
            native_min_value=0,
            native_max_value=1000,
            native_step=1,
        ),
    )


# SAXItem Fixtures
@pytest.fixture
def sax_item_min_soc_base() -> SAXItem:
    """Create a test SAX item for min SOC using real const.py data."""
    # Extract the real SAX item from PILOT_ITEMS
    min_soc_item = next(
        (item for item in PILOT_ITEMS if item.name == SAX_MIN_SOC), None
    )

    if min_soc_item is None:
        # Fallback creation if not found in PILOT_ITEMS
        min_soc_item = SAXItem(
            name=SAX_MIN_SOC,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_MIN_SOC,
        )

    # Mock the async_write_value method for testing
    min_soc_item.async_write_value = AsyncMock(return_value=True)  # type: ignore[method-assign]

    return min_soc_item


# Core fixtures
@pytest.fixture
def mock_smart_meter_data():
    """Create mock smart meter data."""
    smart_meter = MagicMock()
    smart_meter.set_value = MagicMock()
    smart_meter.data = {"smartmeter_total_power": 2500.0}
    return smart_meter


@pytest.fixture
def mock_sax_data_sm(mock_smart_meter_data):
    """Create mock SAX battery data."""
    data = MagicMock()
    data.master_battery_id = "battery_a"
    data.coordinators = {}
    data.batteries = {"battery_a": MagicMock()}
    data.batteries["battery_a"].data = {"test_value": 42}
    data.smart_meter_data = mock_smart_meter_data

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
    data.is_battery_connected = MagicMock(return_value=True)

    return data


@pytest.fixture
def mock_sax_data():
    """Create mock SAX battery data.

    Performance:
        Comprehensive mock for all test scenarios
    """
    sax_data = MagicMock(spec=SAXBatteryData)

    # Add batteries dictionary with proper battery models
    sax_data.batteries = {
        "battery_a": BatteryModel(
            device_id="battery_a",
            name="SAX Battery A",
            host="192.168.1.100",
            port=502,
            is_master=True,
            config_data={},
        ),
        "battery_b": BatteryModel(
            device_id="battery_b",
            name="SAX Battery B",
            host="192.168.1.101",
            port=502,
            is_master=False,
            config_data={},
        ),
        "battery_c": BatteryModel(
            device_id="battery_c",
            name="SAX Battery C",
            host="192.168.1.102",
            port=502,
            is_master=False,
            config_data={},
        ),
    }

    sax_data.coordinators = {}
    sax_data.master_battery_id = "battery_a"

    # Mock methods
    sax_data.get_modbus_items_for_battery = MagicMock(return_value=[])
    sax_data.get_sax_items_for_battery = MagicMock(return_value=[])
    sax_data.get_device_info = MagicMock(
        return_value={
            "identifiers": {("sax_battery", "battery_a")},
            "name": "SAX Battery A",
            "manufacturer": "SAX Power",
            "model": "Battery 7.5kWh",
        }
    )

    return sax_data


@pytest.fixture
def mock_modbus_api():
    """Create mock ModbusAPI for testing."""
    api = MagicMock(spec=ModbusAPI)

    # Mock the core ModbusAPI methods
    api.connect = AsyncMock(return_value=True)
    api.close = MagicMock(return_value=True)
    api.read_holding_registers = AsyncMock(return_value=1500)
    api.write_registers = AsyncMock(return_value=True)

    # Mock the internal modbus client
    mock_client = MagicMock()
    mock_client.connected = True
    api._modbus_client = mock_client

    return api


@pytest.fixture
def mock_coordinator(mock_sax_data, mock_modbus_api):
    """Create mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {"test_value": 42}
    coordinator.last_update_success = True
    coordinator.last_update_success_time = 1234567890.0
    coordinator.battery_id = "battery_a"
    coordinator._first_update_done = False

    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    coordinator.async_set_updated_data = MagicMock()
    coordinator.async_set_updated_data = MagicMock()
    coordinator.update_sax_item_state = MagicMock()
    coordinator._async_update_data = AsyncMock(return_value={"test_value": 42})

    # Add sax_data attribute for device info
    coordinator.sax_data = mock_sax_data
    # Add modbus_api attribute
    coordinator.modbus_api = mock_modbus_api

    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create mock config entry with power manager support.

    Performance:
        Comprehensive fixture for all test scenarios

    Security:
        OWASP A05: Validates configuration structure
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        # Battery configuration
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "battery_b_host": "192.168.1.101",
        "battery_b_port": 502,
        "batteries": {
            "battery_a": {
                "name": "Battery A",
                "slave_id": 1,
                "is_master": True,
                "phase": "L1",
                "enabled": True,
            },
            "battery_b": {
                "name": "Battery B",
                "slave_id": 2,
                "is_master": False,
                "phase": "L2",
                "enabled": True,
            },
        },
        # Power manager configuration
        CONF_PILOT_FROM_HA: False,
        CONF_GRID_POWER_SENSOR: None,
        CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
        CONF_ENABLE_SOLAR_CHARGING: False,
        CONF_MANUAL_CONTROL: False,
        # SOC configuration
        CONF_MIN_SOC: DEFAULT_MIN_SOC,
        # Legacy pilot configuration
        CONF_POWER_SENSOR: None,
        CONF_PF_SENSOR: None,
        CONF_PRIORITY_DEVICES: [],
    }
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    return entry


# Models-specific fixtures
@pytest.fixture
def mock_hass():
    """Create mock HomeAssistant instance for models tests."""
    mock_hass = MagicMock()
    mock_hass.data = {}
    mock_hass.states = MagicMock()
    mock_hass.states.get = MagicMock(return_value=None)
    return mock_hass


@pytest.fixture
def mock_config_entry_single_battery():
    """Create mock config entry for single battery setup."""
    entry = MagicMock()
    entry.data = {
        "battery_count": 1,
        "master_battery": "battery_a",
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
    }
    return entry


@pytest.fixture
def mock_config_entry_dual_battery():
    """Create mock config entry for dual battery setup."""
    entry = MagicMock()
    entry.data = {
        "battery_count": 2,
        "master_battery": "battery_a",
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "battery_b_host": "192.168.1.101",
        "battery_b_port": 502,
    }
    return entry


@pytest.fixture
def mock_config_entry_pilot():
    """Create mock config entry with pilot features enabled."""
    entry = MagicMock()
    entry.data = {
        "battery_count": 1,
        "master_battery": "battery_a",
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "pilot_from_ha": True,
        "limit_power": True,
        "power_sensor": "sensor.grid_power",
        "pf_sensor": "sensor.power_factor",
        "priority_devices": ["switch.ev_charger"],
        "min_soc": 20,
        "auto_pilot_interval": 60,
        "enable_solar_charging": True,
        "manual_control": False,
    }
    return entry


@pytest.fixture
def mock_config_entry_pilot_enabled():
    """Create mock config entry with pilot features enabled."""
    entry = MagicMock()
    entry.data = {
        "battery_count": 1,
        "master_battery": "battery_a",
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "pilot_from_ha": True,
        "limit_power": True,
        "power_sensor": "sensor.grid_power",
        "pf_sensor": "sensor.power_factor",
        "priority_devices": ["switch.ev_charger"],
        "min_soc": 20,
        "auto_pilot_interval": 60,
        "enable_solar_charging": True,
        "manual_control": False,
    }
    return entry


# ModbusItem fixtures
@pytest.fixture
def mock_modbus_item():
    """Create mock ModbusItem."""
    return ModbusItem(
        name="test_item",
        address=100,
        battery_device_id=1,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.BESS,
        factor=10,
    )


@pytest.fixture
def battery_model_data_basic():
    """Provide basic battery model data for testing."""
    return {
        "device_id": "battery_a",
        "name": "SAX Battery A",
        "host": "192.168.1.100",
        "port": 502,
        "is_master": True,
    }


@pytest.fixture
def battery_model_data_slave():
    """Provide slave battery model data for testing."""
    return {
        "device_id": "battery_b",
        "name": "SAX Battery B",
        "host": "192.168.1.101",
        "port": 502,
        "is_master": False,
    }


# Config Flow Test Fixtures
@pytest.fixture
def mock_config_entry_with_features():
    """Create mock config entry with features."""
    mock_entry = MagicMock()
    mock_entry.data = {
        "features": ["smart_meter", "power_control"],
        "batteries": {"battery_a": {"role": "master"}},
    }
    return mock_entry


@pytest.fixture
def mock_coordinator_pilot():
    """Create mock coordinator for pilot tests."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.hass = MagicMock()
    coordinator.data = {
        "battery_a": {
            "sax_soc": 75.0,
            "sax_power": 2000.0,
            "sax_max_charge": 4500.0,
            "sax_max_discharge": 3600.0,
        }
    }
    coordinator.battery_id = "battery_a"
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.data = {
        "battery_count": 1,
        "min_soc": 20,
        "auto_pilot_interval": 30,
    }
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def pilot_items_mixed():
    """Create mixed pilot items for testing."""
    return [
        SAXItem(
            name=SAX_NOMINAL_POWER,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.BESS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_POWER,
        ),
        SAXItem(
            name="manual_control_switch",
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.BESS,
        ),
        SAXItem(
            name="solar_charging_switch",
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.BESS,
        ),
    ]


@pytest.fixture
def mock_state_factory():
    """Factory for creating mock state objects.

    Performance:
        Reusable factory pattern reduces test setup overhead
    """

    def _create_state(value: str) -> MagicMock:
        """Create mock state with value."""
        state = MagicMock()
        state.state = value
        return state

    return _create_state


@pytest.fixture
def mock_pilot_states(mock_state_factory):
    """Common state mocks for pilot tests."""

    def _get_states(**kwargs):
        """Get state map with custom overrides."""
        defaults = {
            "sensor.total_power": "1000.0",
            "sensor.total_pf": "1.0",
            "sensor.priority_device_1": "0.0",
            "sensor.priority_device_2": "0.0",
            "sensor.sax_battery_combined_power": "0.0",
        }
        defaults.update(kwargs)
        return {k: mock_state_factory(v) for k, v in defaults.items()}

    return _get_states


# Sensor Test Fixtures
@pytest.fixture
def calc_sax_item():
    """Create calculated SAX item for sensor tests."""

    return SAXItem(
        name=SAX_COMBINED_SOC,
        mtype=TypeConstants.SENSOR_CALC,
        device=DeviceConstants.BESS,
        entitydescription=DESCRIPTION_SAX_COMBINED_SOC,
    )


# simulate Entity ID generation
@pytest.fixture
def mock_device_info_cluster():
    """Create mock device info for cluster device."""
    return DeviceInfo(
        identifiers={(DOMAIN, "cluster")},
        name="SAX Cluster",
        manufacturer="SAX",
        model="Battery System",
        sw_version="1.0",
    )


@pytest.fixture
def simulate_unique_id_min_soc(mock_device_info_cluster, sax_item_min_soc_base):
    """Generate expected unique ID for SAXBatteryConfigNumber with min SOC."""
    # Following the pattern: f"number.{device_name.lower()}_{clean_item_name}"
    device_name = mock_device_info_cluster["name"]  # "SAX Cluster"

    # Get the actual entity description name from the SAX item
    entity_desc_name = sax_item_min_soc_base.entitydescription.name  # "Sax Minimum SOC"

    # Clean the entity description name by removing "Sax " prefix and converting to lowercase
    clean_item_name = (
        entity_desc_name.removeprefix("Sax ").lower().replace(" ", "_")
    )  # "minimum_soc"

    # Generate the expected unique ID for number platform
    expected_unique_id = (
        f"number.{device_name.lower().replace(' ', '_')}_{clean_item_name}"
    )
    # Result: "number.sax_cluster_minimum_soc"

    return expected_unique_id  # noqa: RET504


@pytest.fixture
def simulate_unique_id_max_charge(
    mock_device_info_cluster, modbus_item_max_charge_base
) -> str:
    """Generate expected unique ID for SAXBatteryConfigNumber with max charge."""
    # Following the pattern: f"number.{device_name.lower()}_{sax_item_name.removeprefix('sax_').replace(' ', '_')}"
    device_name = mock_device_info_cluster["name"]  # "SAX Cluster"
    sax_item_name = (
        modbus_item_max_charge_base.entitydescription.name
    )  # "Sax Maximum Charge"

    # Clean the item name by removing "Sax " prefix -> "maximum_charge"
    clean_item_name = sax_item_name.removeprefix("Sax ").lower().replace(" ", "_")

    # Generate the expected unique ID
    expected_unique_id = (
        f"number.{device_name.lower().replace(' ', '_')}_{clean_item_name}"
    )
    # Result: "number.sax_cluster_min_soc"

    return expected_unique_id  # noqa: RET504


@pytest.fixture
def modbus_item_on_off_base() -> ModbusItem:
    """Create mock ModBus item for ON/OFF switch."""
    return ModbusItem(
        address=100,
        name=SAX_STATUS,
        mtype=TypeConstants.SWITCH,
        device=DeviceConstants.SYS,
        entitydescription=DESCRIPTION_SAX_STATUS_SWITCH,
    )


@pytest.fixture
def simulate_unique_id_on_off(mock_device_info_cluster, modbus_item_on_off_base) -> str:
    """Generate expected unique ID for SAXBatteryConfigNumber with max charge."""
    # Following the pattern: f"switch.{device_name.lower()}_{sax_item_name.removeprefix('sax_').replace(' ', '_')}"
    device_name = mock_device_info_cluster["name"]  # "SAX Cluster"
    sax_item_name = (
        modbus_item_on_off_base.entitydescription.name
    )  # "Sax Status Switch"

    # Clean the item name by removing "Sax " prefix -> "status_switch"
    clean_item_name = (
        sax_item_name.removeprefix("Sax ").lower().replace(" ", "_").replace("/", "_")
    )

    # Generate the expected unique ID
    expected_unique_id = (
        f"switch.{device_name.lower().replace(' ', '_')}_{clean_item_name}"
    )
    # Result: "number.sax_cluster_min_soc"

    return expected_unique_id  # noqa: RET504


@pytest.fixture
def simulate_unique_id_combined_soc(mock_device_info_cluster, calc_sax_item) -> str:
    """Generate expected unique ID for SAXBatteryCalculatedSensor with combined SOC."""
    # Following the pattern: f"sensor.{device_name.lower()}_{sax_item_name.removeprefix('sax_').replace(' ', '_')}"
    device_name = mock_device_info_cluster["name"]  # "SAX Cluster"
    sax_item_name = calc_sax_item.entitydescription.name  # "Combined SOC"

    # Clean the item name -> "combined_soc" (no "Sax " prefix to remove in this case)
    clean_item_name = sax_item_name.removeprefix("Sax ").lower().replace(" ", "_")

    # Generate the expected unique ID for sensor platform
    expected_unique_id = (
        f"sensor.{device_name.lower().replace(' ', '_')}_{clean_item_name}"
    )
    # Result: "sensor.sax_cluster_combined_soc"

    return expected_unique_id  # noqa: RET504


@pytest.fixture
def mock_device_info_battery_a():
    """Create mock device info for battery A device."""
    return DeviceInfo(
        identifiers={(DOMAIN, "battery_a")},
        name="SAX Battery A",
        manufacturer="SAX",
        model="Battery System",
        sw_version="1.0",
    )


@pytest.fixture
def simulate_unique_id_temperature(
    mock_device_info_battery_a, temperature_modbus_item_sensor
) -> str:
    """Generate expected unique ID for SAXBatteryModbusSensor with temperature."""
    # Following the pattern: f"sensor.{device_name.lower()}_{battery_id}_{clean_item_name}"
    device_name = mock_device_info_battery_a["name"]  # "Battery A"
    modbus_item_name = (
        temperature_modbus_item_sensor.entitydescription.name
    )  # "Temperature"

    # Clean the item name -> "temperature" (lowercase, no prefix to remove)
    clean_item_name = modbus_item_name.removeprefix("Sax ").lower().replace(" ", "_")

    # Generate the expected unique ID for modbus sensor platform
    # Pattern: sax_{battery_id}_{clean_item_name}
    expected_unique_id = (
        f"sensor.{device_name.lower().replace(' ', '_')}_{clean_item_name}"
    )
    # Result: "sensor.sax_battery_a_temperature"

    return expected_unique_id  # noqa: RET504
