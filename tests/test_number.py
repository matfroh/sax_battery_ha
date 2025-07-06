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


class TestSAXBatteryMaxChargeNumberMethods:
    """Test specific methods for SAXBatteryMaxChargeNumber."""

    async def test_periodic_write_skips_at_max_value(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _periodic_write skips writing when at max value."""
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

        assert max_charge_entity is not None

        # Set entity at max value
        max_charge_entity._attr_native_value = max_charge_entity._attr_native_max_value
        max_charge_entity._last_written_value = max_charge_entity._attr_native_max_value

        # Mock the _write_value method to track calls
        with patch.object(max_charge_entity, "_write_value") as mock_write:
            await max_charge_entity._periodic_write(None)
            # Should not call _write_value when at max value
            mock_write.assert_not_called()

    async def test_periodic_write_calls_write_value_when_not_at_max(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _periodic_write calls _write_value when not at max value."""
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

        assert max_charge_entity is not None

        # Set entity at non-max value
        max_charge_entity._attr_native_value = 5000.0  # Not at max
        max_charge_entity._last_written_value = 4000.0  # Different from current

        # Mock the _write_value method to track calls
        with patch.object(max_charge_entity, "_write_value") as mock_write:
            await max_charge_entity._periodic_write(None)
            # Should call _write_value when not at max value
            mock_write.assert_called_once_with(5000.0)

    async def test_periodic_write_skips_when_value_is_none(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _periodic_write skips when native_value is None."""
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

        assert max_charge_entity is not None

        # Set entity value to None
        max_charge_entity._attr_native_value = None

        # Mock the _write_value method to track calls
        with patch.object(max_charge_entity, "_write_value") as mock_write:
            await max_charge_entity._periodic_write(None)
            # Should not call _write_value when value is None
            mock_write.assert_not_called()

    async def test_write_value_success(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _write_value successful operation."""
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

        assert max_charge_entity is not None
        max_charge_entity.hass = hass

        # Mock successful modbus write
        mock_battery_data_number.modbus_api.write_max_charge_power.return_value = True

        with patch.object(
            max_charge_entity, "async_write_ha_state"
        ) as mock_write_state:
            await max_charge_entity._write_value(6000.0)

            # Verify modbus API was called
            mock_battery_data_number.modbus_api.write_max_charge_power.assert_called_once_with(
                6000
            )

            # Verify state was updated
            assert max_charge_entity._attr_native_value == 6000.0
            assert max_charge_entity._last_written_value == 6000.0
            mock_write_state.assert_called_once()

    async def test_write_value_modbus_failure(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _write_value when modbus write fails."""
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

        assert max_charge_entity is not None
        max_charge_entity.hass = hass

        # Mock failed modbus write
        mock_battery_data_number.modbus_api.write_max_charge_power.return_value = False

        original_value = max_charge_entity._attr_native_value
        original_last_written = max_charge_entity._last_written_value

        with patch.object(
            max_charge_entity, "async_write_ha_state"
        ) as mock_write_state:
            await max_charge_entity._write_value(6000.0)

            # Verify modbus API was called
            mock_battery_data_number.modbus_api.write_max_charge_power.assert_called_once_with(
                6000
            )

            # Verify state was NOT updated due to failure
            assert max_charge_entity._attr_native_value == original_value
            assert max_charge_entity._last_written_value == original_last_written
            mock_write_state.assert_not_called()

    async def test_write_value_connection_error(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _write_value handles connection errors."""
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

        assert max_charge_entity is not None
        max_charge_entity.hass = hass

        # Mock connection error
        mock_battery_data_number.modbus_api.write_max_charge_power.side_effect = (
            ConnectionError("Connection failed")
        )

        original_value = max_charge_entity._attr_native_value
        original_last_written = max_charge_entity._last_written_value

        with patch.object(
            max_charge_entity, "async_write_ha_state"
        ) as mock_write_state:
            await max_charge_entity._write_value(6000.0)

            # Verify state was NOT updated due to error
            assert max_charge_entity._attr_native_value == original_value
            assert max_charge_entity._last_written_value == original_last_written
            mock_write_state.assert_not_called()

    async def test_write_value_no_modbus_api(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _write_value when modbus_api is None."""
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

        assert max_charge_entity is not None
        max_charge_entity.hass = hass

        # Set modbus_api to None
        mock_battery_data_number.modbus_api = None

        original_value = max_charge_entity._attr_native_value
        original_last_written = max_charge_entity._last_written_value

        with patch.object(
            max_charge_entity, "async_write_ha_state"
        ) as mock_write_state:
            await max_charge_entity._write_value(6000.0)

            # Verify state was NOT updated when no modbus API
            assert max_charge_entity._attr_native_value == original_value
            assert max_charge_entity._last_written_value == original_last_written
            mock_write_state.assert_not_called()


class TestSAXBatteryMaxDischargeNumberMethods:
    """Test specific methods for SAXBatteryMaxDischargeNumber."""

    async def test_periodic_write_skips_at_max_value(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _periodic_write skips writing when at max value."""
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

        assert max_discharge_entity is not None

        # Set entity at max value
        max_discharge_entity._attr_native_value = (
            max_discharge_entity._attr_native_max_value
        )
        max_discharge_entity._last_written_value = (
            max_discharge_entity._attr_native_max_value
        )

        # Mock the _write_value method to track calls
        with patch.object(max_discharge_entity, "_write_value") as mock_write:
            await max_discharge_entity._periodic_write(None)
            # Should not call _write_value when at max value
            mock_write.assert_not_called()

    async def test_periodic_write_calls_write_value_when_not_at_max(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _periodic_write calls _write_value when not at max value."""
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

        assert max_discharge_entity is not None

        # Set entity at non-max value
        max_discharge_entity._attr_native_value = 7000.0  # Not at max
        max_discharge_entity._last_written_value = 6000.0  # Different from current

        # Mock the _write_value method to track calls
        with patch.object(max_discharge_entity, "_write_value") as mock_write:
            await max_discharge_entity._periodic_write(None)
            # Should call _write_value when not at max value
            mock_write.assert_called_once_with(7000.0)

    async def test_write_value_success(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _write_value successful operation."""
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

        assert max_discharge_entity is not None
        max_discharge_entity.hass = hass

        # Mock successful modbus write
        mock_battery_data_number.modbus_api.write_max_discharge_power.return_value = (
            True
        )

        with patch.object(
            max_discharge_entity, "async_write_ha_state"
        ) as mock_write_state:
            await max_discharge_entity._write_value(8000.0)

            # Verify modbus API was called
            mock_battery_data_number.modbus_api.write_max_discharge_power.assert_called_once_with(
                8000
            )

            # Verify state was updated
            assert max_discharge_entity._attr_native_value == 8000.0
            assert max_discharge_entity._last_written_value == 8000.0
            mock_write_state.assert_called_once()

    async def test_write_value_modbus_failure(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _write_value when modbus write fails."""
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

        assert max_discharge_entity is not None
        max_discharge_entity.hass = hass

        # Mock failed modbus write
        mock_battery_data_number.modbus_api.write_max_discharge_power.return_value = (
            False
        )

        original_value = max_discharge_entity._attr_native_value
        original_last_written = max_discharge_entity._last_written_value

        with patch.object(
            max_discharge_entity, "async_write_ha_state"
        ) as mock_write_state:
            await max_discharge_entity._write_value(8000.0)

            # Verify modbus API was called
            mock_battery_data_number.modbus_api.write_max_discharge_power.assert_called_once_with(
                8000
            )

            # Verify state was NOT updated due to failure
            assert max_discharge_entity._attr_native_value == original_value
            assert max_discharge_entity._last_written_value == original_last_written
            mock_write_state.assert_not_called()

    async def test_write_value_connection_error(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _write_value handles connection errors."""
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

        assert max_discharge_entity is not None
        max_discharge_entity.hass = hass

        # Mock connection error
        mock_battery_data_number.modbus_api.write_max_discharge_power.side_effect = (
            TimeoutError("Timeout")
        )

        original_value = max_discharge_entity._attr_native_value
        original_last_written = max_discharge_entity._last_written_value

        with patch.object(
            max_discharge_entity, "async_write_ha_state"
        ) as mock_write_state:
            await max_discharge_entity._write_value(8000.0)

            # Verify state was NOT updated due to error
            assert max_discharge_entity._attr_native_value == original_value
            assert max_discharge_entity._last_written_value == original_last_written
            mock_write_state.assert_not_called()


class TestSAXBatteryManualPowerEntityMethods:
    """Test specific methods for SAXBatteryManualPowerEntity."""

    async def test_update_icon_charging(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _update_icon sets charging icon for positive values."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None

        # Set positive value (charging)
        manual_power_entity._attr_native_value = 1500.0
        manual_power_entity._update_icon()

        assert manual_power_entity._attr_icon == "mdi:battery-charging"

    async def test_update_icon_discharging(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _update_icon sets discharging icon for negative values."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None

        # Set negative value (discharging)
        manual_power_entity._attr_native_value = -2000.0
        manual_power_entity._update_icon()

        assert manual_power_entity._attr_icon == "mdi:battery-minus"

    async def test_update_icon_zero_value(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _update_icon sets default icon for zero value."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None

        # Set zero value
        manual_power_entity._attr_native_value = 0.0
        manual_power_entity._update_icon()

        assert manual_power_entity._attr_icon == "mdi:battery"

    async def test_update_icon_none_value(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test _update_icon sets default icon for None value."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None

        # Set None value
        manual_power_entity._attr_native_value = None
        manual_power_entity._update_icon()

        assert manual_power_entity._attr_icon == "mdi:battery"

    async def test_async_set_native_value_with_pilot(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test async_set_native_value calls pilot and updates state."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None
        manual_power_entity.hass = hass

        # Mock pilot
        mock_pilot = AsyncMock()
        mock_battery_data_number.pilot = mock_pilot

        with (
            patch.object(manual_power_entity, "_update_icon") as mock_update_icon,
            patch.object(
                manual_power_entity, "async_write_ha_state"
            ) as mock_write_state,
        ):
            await manual_power_entity.async_set_native_value(2500.0)

            # Verify value was set
            assert manual_power_entity._attr_native_value == 2500.0

            # Verify pilot was called
            mock_pilot.set_manual_power.assert_called_once_with(2500.0)

            # Verify icon was updated
            mock_update_icon.assert_called_once()

            # Verify state was written
            mock_write_state.assert_called_once()

    async def test_async_set_native_value_without_pilot(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test async_set_native_value works without pilot."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None
        manual_power_entity.hass = hass

        # Remove pilot attribute
        if hasattr(mock_battery_data_number, "pilot"):
            delattr(mock_battery_data_number, "pilot")

        with (
            patch.object(manual_power_entity, "_update_icon") as mock_update_icon,
            patch.object(
                manual_power_entity, "async_write_ha_state"
            ) as mock_write_state,
        ):
            await manual_power_entity.async_set_native_value(-1800.0)

            # Verify value was set
            assert manual_power_entity._attr_native_value == -1800.0

            # Verify icon was updated
            mock_update_icon.assert_called_once()

            # Verify state was written
            mock_write_state.assert_called_once()

    async def test_async_set_native_value_negative_value(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test async_set_native_value with negative value (discharge)."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None
        manual_power_entity.hass = hass

        # Mock pilot
        mock_pilot = AsyncMock()
        mock_battery_data_number.pilot = mock_pilot

        with (
            patch.object(manual_power_entity, "_update_icon") as mock_update_icon,
            patch.object(
                manual_power_entity, "async_write_ha_state"
            ) as mock_write_state,
        ):
            await manual_power_entity.async_set_native_value(-3000.0)

            # Verify value was set
            assert manual_power_entity._attr_native_value == -3000.0

            # Verify pilot was called with negative value
            mock_pilot.set_manual_power.assert_called_once_with(-3000.0)

            # Verify icon was updated
            mock_update_icon.assert_called_once()

            # Verify state was written
            mock_write_state.assert_called_once()

    async def test_async_added_to_hass_calls_update_icon(
        self,
        hass: HomeAssistant,
        mock_sax_number_entry_full,
        mock_battery_data_number,
    ) -> None:
        """Test async_added_to_hass calls _update_icon."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_number_entry_full.entry_id] = (
            mock_battery_data_number
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_number_entry_full, mock_add_entities)

        # Find manual power entity
        manual_power_entity = None
        for entity in entities:
            if "manual_power" in str(entity.unique_id).lower():
                manual_power_entity = entity
                break

        assert manual_power_entity is not None
        manual_power_entity.hass = hass

        with patch.object(manual_power_entity, "_update_icon") as mock_update_icon:
            await manual_power_entity.async_added_to_hass()

            # Verify _update_icon was called
            mock_update_icon.assert_called_once()
