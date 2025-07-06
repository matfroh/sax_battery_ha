"""Comprehensive tests for the SAX Battery switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import CONF_PILOT_FROM_HA, DOMAIN, SAX_STATUS
from custom_components.sax_battery.switch import async_setup_entry
from homeassistant.core import HomeAssistant


@pytest.fixture(name="mock_sax_switch_entry")
def mock_sax_switch_entry_fixture():
    """Mock SAX Battery config entry for switch tests."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_switch_entry"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 1,
        CONF_PILOT_FROM_HA: True,
    }
    return mock_entry


@pytest.fixture(name="mock_sax_switch_entry_no_pilot")
def mock_sax_switch_entry_no_pilot_fixture():
    """Mock SAX Battery config entry without pilot control."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_switch_entry_no_pilot"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 2,
        CONF_PILOT_FROM_HA: False,
    }
    return mock_entry


@pytest.fixture(name="mock_battery_data_switch")
def mock_battery_data_switch_fixture():
    """Mock SAX Battery data for switch tests."""
    mock_battery_data = MagicMock()
    mock_battery_data.device_id = "test_device_switch"

    # Mock coordinator with data
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "battery_a": {SAX_STATUS: {"is_charging": True}},
        "battery_b": {SAX_STATUS: {"is_charging": False}},
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
    mock_modbus_api.write_battery_switch = AsyncMock(return_value=True)
    mock_battery_data.modbus_api = mock_modbus_api

    # Mock pilot
    mock_pilot = MagicMock()
    mock_pilot.set_solar_charging = AsyncMock()
    mock_battery_data.pilot = mock_pilot

    return mock_battery_data


class TestSAXBatterySwitches:
    """Test SAX Battery switch setup and functionality."""

    async def test_switch_setup_with_pilot(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test switch setup with pilot control enabled."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Verify entities were created
        assert len(entities) > 0, "No switch entities were created"

        # Check for pilot-related switches (solar charging and manual control)
        pilot_switches = [
            e
            for e in entities
            if "solar" in str(e.unique_id).lower()
            or "manual" in str(e.unique_id).lower()
        ]
        assert len(pilot_switches) == 2, "Expected 2 pilot switches"

        # Check for battery on/off switches
        battery_switches = [
            e
            for e in entities
            if "battery_" in str(e.unique_id) and "_switch" in str(e.unique_id)
        ]
        assert len(battery_switches) == 2, "Expected 2 battery on/off switches"

    async def test_switch_setup_without_pilot(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry_no_pilot,
        mock_battery_data_switch,
    ) -> None:
        """Test switch setup without pilot control."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry_no_pilot.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry_no_pilot, mock_add_entities)

        # Verify entities were created
        assert len(entities) > 0, "No switch entities were created"

        # Check that no pilot switches were created
        pilot_switches = [
            e
            for e in entities
            if "solar" in str(e.unique_id).lower()
            or "manual" in str(e.unique_id).lower()
        ]
        assert len(pilot_switches) == 0, "No pilot switches should be created"

        # Check for battery on/off switches only
        battery_switches = [
            e
            for e in entities
            if "battery_" in str(e.unique_id) and "_switch" in str(e.unique_id)
        ]
        assert len(battery_switches) == 2, "Expected 2 battery on/off switches"

    async def test_battery_on_off_switch_properties(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry_no_pilot,
        mock_battery_data_switch,
    ) -> None:
        """Test battery on/off switch properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry_no_pilot.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry_no_pilot, mock_add_entities)

        # Find a battery switch
        battery_switch = None
        for entity in entities:
            if "battery_a" in str(entity.unique_id) and "_switch" in str(
                entity.unique_id
            ):
                battery_switch = entity
                break

        assert battery_switch is not None, "Battery switch not found"

        # Test properties
        assert battery_switch.unique_id == f"{DOMAIN}_battery_a_switch"
        assert "Battery A" in battery_switch.name
        assert battery_switch.device_info is not None
        assert battery_switch.device_info["identifiers"] == {
            (DOMAIN, "test_device_switch")
        }

        # Test is_on property
        assert battery_switch.is_on is True  # Based on mock data

    async def test_battery_switch_turn_on(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry_no_pilot,
        mock_battery_data_switch,
    ) -> None:
        """Test turning battery switch on."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry_no_pilot.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        # Add async_request_refresh mock
        mock_battery_data_switch.coordinator.async_request_refresh = AsyncMock()

        await async_setup_entry(hass, mock_sax_switch_entry_no_pilot, mock_add_entities)

        # Find a battery switch
        battery_switch = None
        for entity in entities:
            if "battery_a" in str(entity.unique_id) and "_switch" in str(
                entity.unique_id
            ):
                battery_switch = entity
                break

        assert battery_switch is not None, "Battery switch not found"

        # Test the turn on method
        await battery_switch.async_turn_on()

        # Verify modbus API was called
        mock_battery_data_switch.modbus_api.write_battery_switch.assert_called_once_with(
            mock_battery_data_switch.battery_configs["battery_a"], True
        )

        # Verify coordinator refresh was requested
        mock_battery_data_switch.coordinator.async_request_refresh.assert_called_once()

    async def test_battery_switch_turn_off(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry_no_pilot,
        mock_battery_data_switch,
    ) -> None:
        """Test turning battery switch off."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry_no_pilot.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        # Add async_request_refresh mock
        mock_battery_data_switch.coordinator.async_request_refresh = AsyncMock()

        await async_setup_entry(hass, mock_sax_switch_entry_no_pilot, mock_add_entities)

        # Find a battery switch
        battery_switch = None
        for entity in entities:
            if "battery_a" in str(entity.unique_id) and "_switch" in str(
                entity.unique_id
            ):
                battery_switch = entity
                break

        assert battery_switch is not None, "Battery switch not found"

        # Test the turn off method
        await battery_switch.async_turn_off()

        # Verify modbus API was called
        mock_battery_data_switch.modbus_api.write_battery_switch.assert_called_with(
            mock_battery_data_switch.battery_configs["battery_a"], False
        )

        # Verify coordinator refresh was requested
        mock_battery_data_switch.coordinator.async_request_refresh.assert_called()

    async def test_solar_charging_switch_properties(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test solar charging switch properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find solar charging switch
        solar_switch = None
        for entity in entities:
            if "solar" in str(entity.unique_id).lower():
                solar_switch = entity
                break

        assert solar_switch is not None, "Solar charging switch not found"

        # Test properties
        assert solar_switch.unique_id == f"{DOMAIN}_solar_charging"
        assert "Solar Charging" in solar_switch.name
        assert solar_switch.device_info is not None

    async def test_manual_control_switch_properties(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test manual control switch properties."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find manual control switch
        manual_switch = None
        for entity in entities:
            if "manual" in str(entity.unique_id).lower():
                manual_switch = entity
                break

        assert manual_switch is not None, "Manual control switch not found"

        # Test properties
        assert manual_switch.unique_id == f"{DOMAIN}_manual_control"
        assert "Manual Control" in manual_switch.name
        assert manual_switch.device_info is not None

    async def test_switch_device_info(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry_no_pilot,
        mock_battery_data_switch,
    ) -> None:
        """Test that all switches have correct device info."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry_no_pilot.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry_no_pilot, mock_add_entities)

        # Check device info on all entities
        for entity in entities:
            assert hasattr(entity, "device_info"), (
                f"Entity {entity} missing device_info"
            )
            assert entity.device_info is not None, (
                f"Entity {entity} has None device_info"
            )
            assert entity.device_info["identifiers"] == {(DOMAIN, "test_device_switch")}
            assert entity.device_info["manufacturer"] == "SAX"
            assert entity.device_info["model"] == "SAX Battery"

    async def test_unique_ids(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test that all switches have unique IDs."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Check unique IDs
        unique_ids = [entity.unique_id for entity in entities]
        assert len(unique_ids) == len(set(unique_ids)), "Duplicate unique IDs found"

        # Check that all unique IDs are valid strings
        for uid in unique_ids:
            assert isinstance(uid, str), f"Unique ID {uid} is not a string"
            assert len(uid) > 0, f"Unique ID {uid} is empty"
            assert DOMAIN in uid, f"Unique ID {uid} does not contain domain"


class TestSAXSwitchErrorHandling:
    """Test error handling scenarios for SAX Battery switches."""

    async def test_battery_switch_turn_on_connection_error(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry_no_pilot,
        mock_battery_data_switch,
    ) -> None:
        """Test battery switch turn on with connection error."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry_no_pilot.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        # Make modbus API raise ConnectionError
        mock_battery_data_switch.modbus_api.write_battery_switch.side_effect = (
            ConnectionError("Connection failed")
        )
        mock_battery_data_switch.coordinator.async_request_refresh = AsyncMock()

        await async_setup_entry(hass, mock_sax_switch_entry_no_pilot, mock_add_entities)

        # Find a battery switch
        battery_switch = None
        for entity in entities:
            if "battery_a" in str(entity.unique_id) and "_switch" in str(
                entity.unique_id
            ):
                battery_switch = entity
                break

        assert battery_switch is not None, "Battery switch not found"

        # Test that connection error is handled gracefully
        with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
            await battery_switch.async_turn_on()
            mock_logger.error.assert_called_once()
            assert "Failed to turn on battery" in str(mock_logger.error.call_args)

    async def test_battery_switch_turn_off_value_error(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry_no_pilot,
        mock_battery_data_switch,
    ) -> None:
        """Test battery switch turn off with value error."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry_no_pilot.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        # Make modbus API raise ValueError
        mock_battery_data_switch.modbus_api.write_battery_switch.side_effect = (
            ValueError("Invalid value")
        )
        mock_battery_data_switch.coordinator.async_request_refresh = AsyncMock()

        await async_setup_entry(hass, mock_sax_switch_entry_no_pilot, mock_add_entities)

        # Find a battery switch
        battery_switch = None
        for entity in entities:
            if "battery_a" in str(entity.unique_id) and "_switch" in str(
                entity.unique_id
            ):
                battery_switch = entity
                break

        assert battery_switch is not None, "Battery switch not found"

        # Test that value error is handled gracefully
        with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
            await battery_switch.async_turn_off()
            mock_logger.error.assert_called_once()
            assert "Failed to turn off battery" in str(mock_logger.error.call_args)

    async def test_solar_charging_switch_turn_on_error(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test solar charging switch turn on with error."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find solar charging switch
        solar_switch = None
        for entity in entities:
            if "solar" in str(entity.unique_id).lower():
                solar_switch = entity
                break

        assert solar_switch is not None, "Solar charging switch not found"

        # Make pilot raise an error
        mock_battery_data_switch.pilot.set_solar_charging.side_effect = ConnectionError(
            "Pilot connection failed"
        )

        # Test that error is handled gracefully
        with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
            await solar_switch.async_turn_on()
            mock_logger.error.assert_called_once()
            assert "Failed to enable solar charging" in str(mock_logger.error.call_args)

    async def test_solar_charging_switch_turn_off_error(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test solar charging switch turn off with error."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find solar charging switch
        solar_switch = None
        for entity in entities:
            if "solar" in str(entity.unique_id).lower():
                solar_switch = entity
                break

        assert solar_switch is not None, "Solar charging switch not found"

        # Make pilot raise an error
        mock_battery_data_switch.pilot.set_solar_charging.side_effect = ValueError(
            "Invalid solar charging value"
        )

        # Test that error is handled gracefully
        with patch("custom_components.sax_battery.switch._LOGGER") as mock_logger:
            await solar_switch.async_turn_off()
            mock_logger.error.assert_called_once()
            assert "Failed to disable solar charging" in str(
                mock_logger.error.call_args
            )

    async def test_manual_control_switch_turn_on_error(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test manual control switch turn on with error."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find manual control switch
        manual_switch = None
        for entity in entities:
            if "manual" in str(entity.unique_id).lower():
                manual_switch = entity
                break

        assert manual_switch is not None, "Manual control switch not found"

        # Set hass reference for the entity to avoid RuntimeError
        manual_switch.hass = hass

        # Make pilot raise an error
        mock_battery_data_switch.pilot.set_solar_charging.side_effect = ConnectionError(
            "Pilot connection failed"
        )

        # Test that error is handled gracefully
        with (
            patch("custom_components.sax_battery.switch._LOGGER") as mock_logger,
            patch.object(manual_switch, "async_write_ha_state"),
            patch.object(manual_switch.hass.config_entries, "async_update_entry"),
        ):
            await manual_switch.async_turn_on()
            mock_logger.error.assert_called_once()
            assert "Failed to disable solar charging" in str(
                mock_logger.error.call_args
            )

    async def test_manual_control_switch_turn_off_error(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test manual control switch turn off with error."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find manual control switch
        manual_switch = None
        for entity in entities:
            if "manual" in str(entity.unique_id).lower():
                manual_switch = entity
                break

        assert manual_switch is not None, "Manual control switch not found"

        # Set hass reference for the entity to avoid RuntimeError
        manual_switch.hass = hass

        # Make pilot raise an error
        mock_battery_data_switch.pilot.set_solar_charging.side_effect = ValueError(
            "Invalid solar charging value"
        )

        # Test that error is handled gracefully
        with (
            patch("custom_components.sax_battery.switch._LOGGER") as mock_logger,
            patch.object(manual_switch, "async_write_ha_state"),
            patch.object(manual_switch.hass.config_entries, "async_update_entry"),
        ):
            await manual_switch.async_turn_off()
            mock_logger.error.assert_called_once()
            assert "Failed to disable manual control" in str(
                mock_logger.error.call_args
            )

    async def test_solar_charging_switch_with_other_switch_interaction(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test solar charging switch interaction with manual control switch."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find both switches
        solar_switch = None
        manual_switch = None
        for entity in entities:
            if "solar" in str(entity.unique_id).lower():
                solar_switch = entity
            elif "manual" in str(entity.unique_id).lower():
                manual_switch = entity

        assert solar_switch is not None, "Solar charging switch not found"
        assert manual_switch is not None, "Manual control switch not found"

        # Set hass reference for entities to avoid RuntimeError
        solar_switch.hass = hass
        manual_switch.hass = hass

        # Simulate manual switch being on
        manual_switch._attr_is_on = True
        manual_switch.async_turn_off = AsyncMock()

        # Test that turning on solar charging turns off manual control
        with (
            patch.object(solar_switch, "async_write_ha_state"),
            patch.object(solar_switch.hass.config_entries, "async_update_entry"),
        ):
            await solar_switch.async_turn_on()

        # Verify manual switch was turned off
        manual_switch.async_turn_off.assert_called_once()

    async def test_manual_control_switch_with_other_switch_interaction(
        self,
        hass: HomeAssistant,
        mock_sax_switch_entry,
        mock_battery_data_switch,
    ) -> None:
        """Test manual control switch interaction with solar charging switch."""
        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_switch_entry.entry_id] = (
            mock_battery_data_switch
        )

        entities = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities.extend(new_entities)

        await async_setup_entry(hass, mock_sax_switch_entry, mock_add_entities)

        # Find both switches
        solar_switch = None
        manual_switch = None
        for entity in entities:
            if "solar" in str(entity.unique_id).lower():
                solar_switch = entity
            elif "manual" in str(entity.unique_id).lower():
                manual_switch = entity

        assert solar_switch is not None, "Solar charging switch not found"
        assert manual_switch is not None, "Manual control switch not found"

        # Set hass reference for entities to avoid RuntimeError
        solar_switch.hass = hass
        manual_switch.hass = hass

        # Simulate solar switch being on
        solar_switch._attr_is_on = True
        solar_switch.async_turn_off = AsyncMock()

        # Test that turning on manual control turns off solar charging
        with (
            patch.object(manual_switch, "async_write_ha_state"),
            patch.object(manual_switch.hass.config_entries, "async_update_entry"),
        ):
            await manual_switch.async_turn_on()

        # Verify solar switch was turned off
        solar_switch.async_turn_off.assert_called_once()
