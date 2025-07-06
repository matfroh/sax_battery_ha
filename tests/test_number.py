"""Comprehensive tests for the SAX Battery number platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_LIMIT_POWER,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_PILOT_FROM_HA,
    DOMAIN,
)
from custom_components.sax_battery.number import async_setup_entry
from homeassistant.components.number import NumberMode
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant


@pytest.fixture(name="mock_sax_number_entry_full")
def mock_sax_number_entry_full_fixture():
    """Mock SAX Battery config entry with all number features enabled."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_number_entry_full"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 2,
        CONF_LIMIT_POWER: True,
        CONF_PILOT_FROM_HA: True,
        CONF_MANUAL_CONTROL: True,
        CONF_AUTO_PILOT_INTERVAL: 60,
        CONF_MIN_SOC: 20,
    }
    return mock_entry


@pytest.fixture(name="mock_sax_number_entry_minimal")
def mock_sax_number_entry_minimal_fixture():
    """Mock SAX Battery config entry with minimal number features."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_number_entry_minimal"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 1,
        CONF_LIMIT_POWER: False,
        CONF_PILOT_FROM_HA: False,
        CONF_MANUAL_CONTROL: False,
    }
    return mock_entry


@pytest.fixture(name="mock_battery_data_number")
def mock_battery_data_number_fixture():
    """Mock SAX Battery data for number tests."""
    mock_battery_data = MagicMock()
    mock_battery_data.device_id = "test_device_number"

    # Mock coordinator with data
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "battery_a": {"sax_power": 2000, "sax_soc": 85},
        "battery_b": {"sax_power": 1800, "sax_soc": 78},
    }
    mock_battery_data.coordinator = mock_coordinator

    # Mock batteries dictionary (just the keys)
    mock_battery_data.batteries = {
        "battery_a": {},
        "battery_b": {},
    }

    # Mock battery configs
    mock_battery_data.battery_configs = {
        "battery_a": MagicMock(),
        "battery_b": MagicMock(),
    }

    # Mock modbus API
    mock_modbus_api = MagicMock()
    mock_modbus_api.write_max_charge_power = AsyncMock(return_value=True)
    mock_modbus_api.write_max_discharge_power = AsyncMock(return_value=True)
    mock_battery_data.modbus_api = mock_modbus_api

    # Mock pilot service
    mock_pilot = MagicMock()
    mock_pilot.interval = 60
    mock_pilot.min_soc = 20
    mock_pilot.set_interval = AsyncMock()
    mock_pilot.set_min_soc = AsyncMock()
    mock_pilot.set_manual_power = AsyncMock()
    mock_battery_data.pilot = mock_pilot

    return mock_battery_data


class TestSAXBatteryNumbers:
    """Test SAX Battery number setup and functionality."""

    async def test_number_setup_full_features(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test number setup with all features enabled."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Verify entities were created
        assert len(entities) > 0, "No number entities were created"

        # Check for power limiting entities
        power_entities = [
            e
            for e in entities
            if "charge" in str(e.unique_id).lower()
            or "discharge" in str(e.unique_id).lower()
        ]
        assert len(power_entities) == 2, "Expected 2 power limiting entities"

        # Check for pilot-related entities
        pilot_entities = [
            e
            for e in entities
            if "interval" in str(e.unique_id).lower()
            or "soc" in str(e.unique_id).lower()
        ]
        assert len(pilot_entities) == 2, "Expected 2 pilot entities"

        # Check for manual control entity
        manual_entities = [e for e in entities if "manual" in str(e.unique_id).lower()]
        assert len(manual_entities) == 1, "Expected 1 manual control entity"

    async def test_number_setup_minimal_features(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_minimal,
        mock_battery_data_number,
    ) -> None:
        """Test number setup with minimal features."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_minimal.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_minimal, mock_add_entities)

        # Should have no entities when all features are disabled
        assert len(entities) == 0, "No entities should be created with minimal config"

    async def test_max_charge_number_properties(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test maximum charge number properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find max charge entity
        max_charge_entity = None
        for entity in entities:
            if "max_charge" in str(entity.unique_id).lower():
                max_charge_entity = entity
                break

        assert max_charge_entity is not None, "Max charge entity not found"

        # Test properties
        assert max_charge_entity.unique_id == f"{DOMAIN}_max_charge_power"
        assert "Maximum Charge Power" in max_charge_entity.name
        assert max_charge_entity.native_unit_of_measurement == UnitOfPower.WATT
        assert max_charge_entity.mode == NumberMode.SLIDER
        assert max_charge_entity.native_min_value == 0
        assert max_charge_entity.native_max_value == 7000  # 2 batteries * 3500W
        assert max_charge_entity.native_step == 100

    async def test_max_discharge_number_properties(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test maximum discharge number properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find max discharge entity
        max_discharge_entity = None
        for entity in entities:
            if "max_discharge" in str(entity.unique_id).lower():
                max_discharge_entity = entity
                break

        assert max_discharge_entity is not None, "Max discharge entity not found"

        # Test properties
        assert max_discharge_entity.unique_id == f"{DOMAIN}_max_discharge_power"
        assert "Maximum Discharge Power" in max_discharge_entity.name
        assert max_discharge_entity.native_unit_of_measurement == UnitOfPower.WATT
        assert max_discharge_entity.mode == NumberMode.SLIDER
        assert max_discharge_entity.native_min_value == 0
        assert max_discharge_entity.native_max_value == 9200  # 2 batteries * 4600W
        assert max_discharge_entity.native_step == 100

    async def test_pilot_interval_number_properties(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test pilot interval number properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find pilot interval entity
        interval_entity = None
        for entity in entities:
            if "interval" in str(entity.unique_id).lower():
                interval_entity = entity
                break

        assert interval_entity is not None, "Pilot interval entity not found"

        # Test properties
        assert interval_entity.unique_id == f"{DOMAIN}_pilot_interval"
        assert "Pilot Interval" in interval_entity.name
        assert interval_entity.native_min_value == 10
        assert interval_entity.native_max_value == 300
        assert interval_entity.native_step == 10
        assert interval_entity.native_value == 60  # From mock entry data

    async def test_min_soc_number_properties(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test minimum SOC number properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find min SOC entity
        min_soc_entity = None
        for entity in entities:
            if "min_soc" in str(entity.unique_id).lower():
                min_soc_entity = entity
                break

        assert min_soc_entity is not None, "Min SOC entity not found"

        # Test properties
        assert min_soc_entity.unique_id == f"{DOMAIN}_min_soc"
        assert "Minimum State of Charge" in min_soc_entity.name
        assert min_soc_entity.native_unit_of_measurement == PERCENTAGE
        assert min_soc_entity.native_min_value == 5
        assert min_soc_entity.native_max_value == 95
        assert min_soc_entity.native_step == 1
        assert min_soc_entity.native_value == 20  # From mock entry data

    async def test_manual_power_entity_properties(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test manual power entity properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_entity = None
        for entity in entities:
            if "manual" in str(entity.unique_id).lower():
                manual_entity = entity
                break

        assert manual_entity is not None, "Manual power entity not found"

        # Test properties
        assert manual_entity.unique_id == f"{DOMAIN}_manual_power"
        assert "Manual Power" in manual_entity.name
        assert manual_entity.native_unit_of_measurement == UnitOfPower.WATT
        assert manual_entity.mode == NumberMode.SLIDER

    async def test_number_device_info(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test that all number entities have correct device info."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Check device info on all entities
        for entity in entities:
            assert hasattr(entity, "device_info"), (
                f"Entity {entity} missing device_info"
            )
            assert entity.device_info is not None, (
                f"Entity {entity} has None device_info"
            )
            assert entity.device_info["identifiers"] == {(DOMAIN, "test_device_number")}
            assert entity.device_info["manufacturer"] == "SAX"
            assert entity.device_info["model"] == "SAX Battery"

    async def test_number_unique_ids(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test that all number entities have unique IDs."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Check unique IDs
        unique_ids = [entity.unique_id for entity in entities]
        assert len(unique_ids) == len(set(unique_ids)), "Duplicate unique IDs found"

        # Check that all unique IDs are valid strings
        for uid in unique_ids:
            assert isinstance(uid, str), f"Unique ID {uid} is not a string"
            assert len(uid) > 0, f"Unique ID {uid} is empty"
            assert DOMAIN in uid, f"Unique ID {uid} does not contain domain"

    async def test_max_charge_number_set_value(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test setting value on max charge number entity."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find max charge entity
        max_charge_entity = None
        for entity in entities:
            if "max_charge" in str(entity.unique_id).lower():
                max_charge_entity = entity
                break

        assert max_charge_entity is not None, "Max charge entity not found"

        # Set up entity with hass instance
        max_charge_entity.hass = hass
        max_charge_entity.entity_id = "number.test_max_charge"

        # Test setting value
        test_value = 5000.0
        await max_charge_entity.async_set_native_value(test_value)

        # Verify modbus API was called
        mock_battery_data_number.modbus_api.write_max_charge_power.assert_called_once_with(
            int(test_value)
        )

        # Verify value was set
        assert max_charge_entity.native_value == test_value

    async def test_pilot_interval_number_set_value(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test setting value on pilot interval number entity."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find pilot interval entity
        interval_entity = None
        for entity in entities:
            if "interval" in str(entity.unique_id).lower():
                interval_entity = entity
                break

        assert interval_entity is not None, "Pilot interval entity not found"

        # Set up entity with hass instance
        interval_entity.hass = hass
        interval_entity.entity_id = "number.test_pilot_interval"

        # Mock the hass.config_entries.async_update_entry method
        mock_update_entry = MagicMock()

        def update_entry_side_effect(entry, **kwargs):
            if "data" in kwargs:
                entry.data.update(kwargs["data"])

        mock_update_entry.side_effect = update_entry_side_effect
        hass.config_entries = MagicMock()
        hass.config_entries.async_update_entry = mock_update_entry

        # Test setting value
        test_value = 120.0
        await interval_entity.async_set_native_value(test_value)

        # Verify value was set in config entry
        assert mock_sax_number_entry_full.data[CONF_AUTO_PILOT_INTERVAL] == test_value

    @patch("custom_components.sax_battery.number.async_track_time_interval")
    async def test_max_charge_periodic_updates(
        self,
        mock_track_time,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test that max charge entity sets up periodic updates."""
        # Mock the timer removal function
        mock_remove_timer = MagicMock()
        mock_track_time.return_value = mock_remove_timer

        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find max charge entity
        max_charge_entity = None
        for entity in entities:
            if "max_charge" in str(entity.unique_id).lower():
                max_charge_entity = entity
                break

        assert max_charge_entity is not None, "Max charge entity not found"

        # Set up entity with hass instance
        max_charge_entity.hass = hass
        max_charge_entity.entity_id = "number.test_max_charge_periodic"

        # Simulate adding to hass
        await max_charge_entity.async_added_to_hass()

        # Verify periodic tracking was set up
        mock_track_time.assert_called_once()

        # Clean up - simulate removing from hass
        await max_charge_entity.async_will_remove_from_hass()
        mock_remove_timer.assert_called_once()
