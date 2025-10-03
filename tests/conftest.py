"""Global fixtures for SAX Battery integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sax_battery.const import (
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
from homeassistant.components.number import NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

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
def modbus_item_max_charge_base():
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
