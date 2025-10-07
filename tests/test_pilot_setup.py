"""Test pilot platform setup and initialization."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.sax_battery.const import CONF_PILOT_FROM_HA, DOMAIN
from custom_components.sax_battery.pilot import async_setup_entry


class TestPilotSetup:
    """Test pilot platform setup."""

    async def test_setup_entry_with_master_battery(
        self,
        mock_hass,
        mock_config_entry_pilot,
        mock_sax_data,
        mock_coordinator_pilot,
        pilot_items_mixed,
    ):
        """Test successful setup with master battery."""
        # Update sax_data with coordinator
        mock_sax_data.coordinators = {"battery_a": mock_coordinator_pilot}

        with (
            patch(
                "custom_components.sax_battery.pilot.async_track_time_interval"
            ) as mock_track,
            patch(
                "custom_components.sax_battery.pilot.SAXBatteryPilot"
            ) as mock_pilot_class,
        ):
            # Setup mock pilot instance
            mock_pilot = MagicMock()
            mock_pilot.async_start = AsyncMock()
            mock_pilot_class.return_value = mock_pilot

            mock_track.return_value = MagicMock()

            # Mock entity instances

            mock_hass.data = {
                DOMAIN: {
                    mock_config_entry_pilot.entry_id: {
                        "coordinators": mock_sax_data.coordinators,
                        "sax_data": mock_sax_data,
                    }
                }
            }

            async_add_entities = MagicMock()

            await async_setup_entry(
                mock_hass,
                mock_config_entry_pilot,
                async_add_entities,
            )

            # Verify pilot was created and started
            mock_pilot_class.assert_called_once()
            mock_pilot.async_start.assert_called_once()

    async def test_setup_entry_pilot_disabled(self, mock_hass, mock_sax_data):
        """Test setup when pilot is disabled."""
        # Create config entry with pilot disabled
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry_id"
        mock_config_entry.data = {CONF_PILOT_FROM_HA: False}

        # Set master battery ID to ensure proper test setup
        mock_sax_data.master_battery_id = "battery_a"
        mock_sax_data.coordinators = {"battery_a": MagicMock()}

        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: {
                    "coordinators": mock_sax_data.coordinators,
                    "sax_data": mock_sax_data,
                }
            }
        }

        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # async_add_entities should NOT be called when pilot is disabled
        async_add_entities.assert_not_called()

    async def test_setup_entry_no_master_battery(
        self, mock_hass, mock_config_entry_pilot
    ):
        """Test setup fails when no master battery configured."""
        mock_sax_data = MagicMock()
        mock_sax_data.master_battery_id = None
        mock_hass.data = {
            DOMAIN: {
                mock_config_entry_pilot.entry_id: {
                    "coordinators": {},
                    "sax_data": mock_sax_data,
                }
            }
        }

        async_add_entities = MagicMock()

        await async_setup_entry(
            mock_hass,
            mock_config_entry_pilot,
            async_add_entities,
        )

        # async_add_entities is NOT called when there are no entities to add
        async_add_entities.assert_not_called()


class TestPilotSetupEdgeCases:
    """Test edge cases in pilot setup."""

    async def test_setup_with_multiple_coordinators_no_master(self, mock_hass):
        """Test setup with multiple coordinators but no master."""
        mock_sax_data = MagicMock()
        mock_sax_data.master_battery_id = None  # No master
        mock_sax_data.coordinators = {
            "battery_a": MagicMock(),
            "battery_b": MagicMock(),
        }

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {CONF_PILOT_FROM_HA: True}

        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: {
                    "coordinators": mock_sax_data.coordinators,
                    "sax_data": mock_sax_data,
                }
            }
        }

        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Should not create any entities
        async_add_entities.assert_not_called()

    async def test_setup_with_master_not_in_coordinators(self, mock_hass):
        """Test setup when master not in coordinator list."""
        mock_sax_data = MagicMock()
        mock_sax_data.master_battery_id = "battery_master"  # Not in coordinators
        mock_sax_data.coordinators = {
            "battery_a": MagicMock(),
            "battery_b": MagicMock(),
        }

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {CONF_PILOT_FROM_HA: True}

        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: {
                    "coordinators": mock_sax_data.coordinators,
                    "sax_data": mock_sax_data,
                }
            }
        }

        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Should not create any entities
        async_add_entities.assert_not_called()

    async def test_setup_with_empty_coordinators(self, mock_hass):
        """Test setup with empty coordinator dictionary."""
        mock_sax_data = MagicMock()
        mock_sax_data.master_battery_id = "battery_a"
        mock_sax_data.coordinators = {}  # Empty

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {CONF_PILOT_FROM_HA: True}

        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: {
                    "coordinators": mock_sax_data.coordinators,
                    "sax_data": mock_sax_data,
                }
            }
        }

        async_add_entities = MagicMock()

        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

        # Should not create any entities
        async_add_entities.assert_not_called()

    async def test_setup_entry_pilot_attribute_persistence(self, mock_hass):
        """Test that pilot attribute is properly assigned to sax_data."""
        mock_sax_data = MagicMock()
        mock_sax_data.master_battery_id = "battery_a"
        mock_sax_data.coordinators = {"battery_a": MagicMock()}

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {CONF_PILOT_FROM_HA: True}

        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: {
                    "coordinators": mock_sax_data.coordinators,
                    "sax_data": mock_sax_data,
                }
            }
        }

        with patch(
            "custom_components.sax_battery.pilot.SAXBatteryPilot"
        ) as mock_pilot_class:
            mock_pilot = MagicMock()
            mock_pilot.async_start = AsyncMock()
            mock_pilot_class.return_value = mock_pilot

            async_add_entities = MagicMock()

            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

            # Verify pilot was assigned and persists
            assert hasattr(mock_sax_data, "pilot")
            assert mock_sax_data.pilot == mock_pilot

            # The implementation always creates a new pilot instance on each call
            # This is correct behavior as each call to async_setup_entry should
            # set up fresh pilot instances
            mock_pilot_class.assert_called_once()


class TestAsyncSetupEntryEdgeCases:
    """Test edge cases for async_setup_entry."""

    async def test_setup_entry_pilot_attribute_assignment(
        self, mock_hass, mock_sax_data
    ):
        """Test that pilot attribute is properly assigned to sax_data."""
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {CONF_PILOT_FROM_HA: True}

        mock_coordinator = MagicMock()
        mock_sax_data.master_battery_id = "battery_a"
        mock_sax_data.coordinators = {"battery_a": mock_coordinator}

        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: {
                    "coordinators": mock_sax_data.coordinators,
                    "sax_data": mock_sax_data,
                }
            }
        }

        with patch(
            "custom_components.sax_battery.pilot.SAXBatteryPilot"
        ) as mock_pilot_class:
            mock_pilot = MagicMock()
            mock_pilot.async_start = AsyncMock()
            mock_pilot_class.return_value = mock_pilot

            async_add_entities = MagicMock()

            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

            # Verify pilot was assigned to sax_data
            assert hasattr(mock_sax_data, "pilot")
            assert mock_sax_data.pilot == mock_pilot

    async def test_setup_entry_with_master_but_pilot_disabled(
        self, mock_hass, mock_sax_data
    ):
        """Test setup with master battery but pilot disabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry"
        mock_config_entry.data = {CONF_PILOT_FROM_HA: False}  # Pilot disabled

        mock_coordinator = MagicMock()
        mock_sax_data.master_battery_id = "battery_a"
        mock_sax_data.coordinators = {"battery_a": mock_coordinator}

        mock_hass.data = {
            DOMAIN: {
                mock_config_entry.entry_id: {
                    "coordinators": mock_sax_data.coordinators,
                    "sax_data": mock_sax_data,
                }
            }
        }

        with patch(
            "custom_components.sax_battery.pilot.SAXBatteryPilot"
        ) as mock_pilot_class:
            mock_pilot = MagicMock()
            mock_pilot.async_start = AsyncMock()
            mock_pilot_class.return_value = mock_pilot

            async_add_entities = MagicMock()

            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)

            # Pilot should be created but entities not added, and pilot not started
            mock_pilot_class.assert_called_once()
            mock_pilot.async_start.assert_not_called()
            async_add_entities.assert_not_called()
