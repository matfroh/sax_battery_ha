"""Global fixtures for SAX Battery integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MIN_SOC,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DESCRIPTION_SAX_COMBINED_SOC,
    DESCRIPTION_SAX_MAX_CHARGE,
    DESCRIPTION_SAX_MIN_SOC,
    DESCRIPTION_SAX_NOMINAL_POWER,
    DESCRIPTION_SAX_POWER,
    DESCRIPTION_SAX_SOC,
    DESCRIPTION_SAX_TEMPERATURE,
    PILOT_ITEMS,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MIN_SOC,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem, SAXItem
from custom_components.sax_battery.modbusobject import ModbusAPI
from custom_components.sax_battery.number import SAXBatteryModbusNumber
from homeassistant.components.number import NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
def modbus_item_power_base():
    """Create power number ModbusItem for testing."""
    return ModbusItem(
        address=100,
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
        device=DeviceConstants.SYS,
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
def modbus_item_pilot_factor_base():
    """Create pilot control power factor ModbusItem for testing."""
    return ModbusItem(
        address=42,
        name=SAX_NOMINAL_FACTOR,
        mtype=TypeConstants.NUMBER_WO,
        device=DeviceConstants.SYS,
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
def sax_item_min_soc_base():
    """Create SAXItem for MIN_SOC testing."""
    return next(
        (item for item in PILOT_ITEMS if item.name == SAX_MIN_SOC),
        None,
    )


# Cleanup Fixtures
@pytest.fixture(autouse=True)
def reset_pilot_control_state():
    """Reset pilot control transactions before each test."""
    SAXBatteryModbusNumber._pilot_control_transaction.clear()
    yield
    SAXBatteryModbusNumber._pilot_control_transaction.clear()


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


# Core fixtures
@pytest.fixture
def mock_smart_meter_data():
    """Create mock smart meter data."""
    smart_meter = MagicMock()
    smart_meter.set_value = MagicMock()
    smart_meter.data = {"smartmeter_total_power": 2500.0}
    return smart_meter


@pytest.fixture
def mock_sax_data(mock_smart_meter_data):
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
def sax_battery_coordinator(hass, mock_sax_data, mock_modbus_api):
    """Create actual SAXBatteryCoordinator instance for testing."""
    mock_config_entry = MagicMock(spec=ConfigEntry)
    mock_config_entry.entry_id = "test_entry_id"

    return SAXBatteryCoordinator(
        hass=hass,
        battery_id="battery_a",
        sax_data=mock_sax_data,
        modbus_api=mock_modbus_api,
        config_entry=mock_config_entry,
        battery_config={"is_master": True, "phase": "L1"},
    )


@pytest.fixture
def mock_config_entry():
    """Create mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
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
        battery_slave_id=1,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.SYS,
        factor=10,
    )


@pytest.fixture
def smart_meter_modbus_item():
    """Create a smart meter ModbusItem for testing."""
    return ModbusItem(
        name="smartmeter_power",
        device=DeviceConstants.SYS,
        mtype=TypeConstants.SENSOR,
        address=1000,
        battery_slave_id=1,
        factor=1.0,
    )


@pytest.fixture
def temperature_modbus_item():
    """Create temperature modbus item with proper entity description."""
    return ModbusItem(
        address=40117,
        name="sax_temperature",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
        battery_slave_id=40,
        factor=10.0,
        entitydescription=DESCRIPTION_SAX_TEMPERATURE,
    )


@pytest.fixture
def percentage_modbus_item():
    """Create percentage modbus item with proper entity description."""
    return ModbusItem(
        address=46,
        name="sax_soc",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
        battery_slave_id=64,
        factor=1.0,
        entitydescription=DESCRIPTION_SAX_SOC,
    )


@pytest.fixture
def power_modbus_item():
    """Create power modbus item with proper entity description."""
    return ModbusItem(
        address=47,
        name="sax_power",
        mtype=TypeConstants.SENSOR,
        device=DeviceConstants.SYS,
        battery_slave_id=64,
        factor=1.0,
        entitydescription=DESCRIPTION_SAX_POWER,
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


@pytest.fixture
def battery_data_values():
    """Provide sample battery data values for testing."""
    return {
        "sax_soc": 75.0,
        "sax_power": 2000.0,
        "voltage_l1": 48.5,
        "current_l1": 41.2,
        "sax_temperature": 25.5,
        "sax_status": "normal",
    }


# Number-specific fixtures
@pytest.fixture
def mock_coordinator_number():
    """Create a mock coordinator for number tests."""
    coordinator = MagicMock(spec=SAXBatteryCoordinator)
    coordinator.data = {}
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.data = {"battery_count": 1}
    coordinator.sax_data = MagicMock()
    coordinator.sax_data.get_device_info.return_value = {"name": "Test Battery"}
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    return coordinator


# Config Flow Test Fixtures
@pytest.fixture
def config_flow_user_input_pilot_config():
    """Create pilot config input for config flow tests."""
    return {
        CONF_MIN_SOC: DEFAULT_MIN_SOC,
        CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
        CONF_ENABLE_SOLAR_CHARGING: True,
    }


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
def mock_async_setup_entry():
    """Mock async_setup_entry for successful setup."""
    with patch("custom_components.sax_battery.async_setup_entry") as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_async_setup_entry_failure():
    """Mock async_setup_entry for failed setup."""
    with patch("custom_components.sax_battery.async_setup_entry") as mock:
        mock.return_value = False
        yield mock


@pytest.fixture
def config_flow_user_input_battery_count():
    """Provide battery count user input for config flow tests."""
    return {"battery_count": 1}


@pytest.fixture
def config_flow_user_input_control_options():
    """Provide control options user input for config flow tests."""
    return {
        "pilot_from_ha": False,
        "limit_power": False,
    }


@pytest.fixture
def config_flow_user_input_battery_config():
    """Provide battery config user input for config flow tests."""
    return {
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
    }


@pytest.fixture
def single_battery_config_data():
    """Provide single battery configuration data."""
    return {
        "battery_count": 1,
        "master_battery": "battery_a",
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "pilot_from_ha": False,
        "limit_power": False,
        "device_id": "test-device-id",
    }


# Pilot Test Fixtures
@pytest.fixture
def pilot_enabled_config_data():
    """Provide pilot-enabled configuration data."""
    return {
        "battery_count": 1,
        "master_battery": "battery_a",
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "pilot_from_ha": True,
        "limit_power": True,
        "power_sensor": "sensor.grid_power",
        "pf_sensor": "sensor.power_factor",
        "min_soc": 20,
        "auto_pilot_interval": 60,
        "enable_solar_charging": True,
        "manual_control": False,
        "device_id": "test-pilot-device-id",
    }


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
            device=DeviceConstants.SYS,
            entitydescription=DESCRIPTION_SAX_NOMINAL_POWER,
        ),
        SAXItem(
            name="manual_control_switch",
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        ),
        SAXItem(
            name="solar_charging_switch",
            mtype=TypeConstants.SWITCH,
            device=DeviceConstants.SYS,
        ),
    ]


@pytest.fixture
def mock_pilot_power_entity():
    """Create mock pilot for power entity."""
    mock_pilot = MagicMock()
    mock_pilot.set_manual_power = AsyncMock()
    mock_pilot.calculated_power = 1500.0
    mock_pilot.max_charge_power = 3600
    mock_pilot.max_discharge_power = 3600
    return mock_pilot


# Sensor Test Fixtures


@pytest.fixture
def calc_sax_item():
    """Create calculated SAX item for sensor tests."""

    return SAXItem(
        name=SAX_COMBINED_SOC,
        mtype=TypeConstants.SENSOR_CALC,
        device=DeviceConstants.SYS,
        entitydescription=DESCRIPTION_SAX_COMBINED_SOC,
    )
