"""Test pilot platform for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    CONF_PRIORITY_DEVICES,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_NOMINAL_POWER,
)
from custom_components.sax_battery.pilot import SAXBatteryPilot, async_setup_entry


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_entry_with_master_battery(
        self,
        mock_hass,
        mock_config_entry_pilot,
        mock_sax_data,
        mock_coordinator_pilot,
        pilot_items_mixed,
    ):
        """Test setup entry creates pilot entities for master battery."""
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
        """Test setup entry when pilot from HA is disabled."""
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
        """Test setup entry with no master battery creates no entities."""
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


class TestAsyncSetupEntryComprehensive:
    """Comprehensive tests for async_setup_entry scenarios."""

    async def test_setup_entry_with_multiple_coordinators_but_no_master(
        self, mock_hass
    ):
        """Test setup when there are coordinators but no master battery."""
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

    async def test_setup_entry_with_master_not_in_coordinators(self, mock_hass):
        """Test setup when master battery ID doesn't exist in coordinators."""
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

    async def test_setup_entry_with_empty_coordinators(self, mock_hass):
        """Test setup with empty coordinators dictionary."""
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


class TestSAXBatteryPilot:
    """Test SAXBatteryPilot class."""

    @pytest.fixture
    def pilot_instance_test(
        self,
        mock_hass,
        mock_sax_data,
        mock_coordinator,
    ) -> SAXBatteryPilot:
        """Create SAXBatteryPilot instance for testing."""
        # Set up proper coordinators data
        mock_sax_data.coordinators = {"battery_a": mock_coordinator}

        # Mock entry data with real values
        mock_sax_data.entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_POWER_SENSOR: "sensor.power",
            CONF_PF_SENSOR: "sensor.pf",
            CONF_MIN_SOC: DEFAULT_MIN_SOC,
            CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
        }

        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

    def test_initialization(self, pilot_instance_test):
        """Test pilot initialization sets correct values."""
        assert pilot_instance_test.battery_count == 1
        assert pilot_instance_test.calculated_power == 0.0
        assert pilot_instance_test.max_discharge_power == LIMIT_MAX_CHARGE_PER_BATTERY
        assert pilot_instance_test.max_charge_power == LIMIT_MAX_DISCHARGE_PER_BATTERY
        assert pilot_instance_test.power_sensor_entity_id == "sensor.power"
        assert pilot_instance_test.pf_sensor_entity_id == "sensor.pf"
        assert pilot_instance_test.update_interval == DEFAULT_AUTO_PILOT_INTERVAL

    async def test_async_start_already_running(self, pilot_instance_test):
        """Test starting pilot when already running."""
        pilot_instance_test._running = True

        await pilot_instance_test.async_start()

        # Should return early without setting up tracking
        assert pilot_instance_test._running is True

    async def test_async_start_success(self, pilot_instance_test):
        """Test successful pilot start."""
        with (
            patch(
                "custom_components.sax_battery.pilot.async_track_time_interval"
            ) as mock_track,
            patch.object(
                pilot_instance_test, "_async_update_pilot", new_callable=AsyncMock
            ) as mock_update,
        ):
            mock_track.return_value = MagicMock()

            await pilot_instance_test.async_start()

            assert pilot_instance_test._running is True
            mock_track.assert_called_once()
            mock_update.assert_called_once_with(None)

    async def test_async_stop_not_running(self, pilot_instance_test):
        """Test stopping pilot when not running."""
        pilot_instance_test._running = False

        await pilot_instance_test.async_stop()

        # Should return early
        assert pilot_instance_test._running is False

    async def test_async_stop_success(self, pilot_instance_test):
        """Test successful pilot stop."""
        mock_remove_interval = MagicMock()
        mock_remove_config = MagicMock()

        pilot_instance_test._running = True
        pilot_instance_test._remove_interval_update = mock_remove_interval
        pilot_instance_test._remove_config_update = mock_remove_config

        await pilot_instance_test.async_stop()

        assert pilot_instance_test._running is False
        mock_remove_interval.assert_called_once()
        mock_remove_config.assert_called_once()

    async def test_async_config_updated(self, pilot_instance_test):
        """Test config update handling."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_AUTO_PILOT_INTERVAL: 30,
        }

        with patch.object(
            pilot_instance_test, "_async_update_pilot", new_callable=AsyncMock
        ) as mock_update:
            await pilot_instance_test._async_config_updated(
                pilot_instance_test.hass, mock_entry
            )

            assert pilot_instance_test.update_interval == 30
            mock_update.assert_called_once_with(None)

    async def test_get_combined_soc_no_data(self, pilot_instance_test):
        """Test getting combined SOC with no coordinator data."""
        pilot_instance_test.coordinator.data = None

        result = await pilot_instance_test._get_combined_soc()

        assert result == 0.0

    async def test_get_combined_soc_valid_data(self, pilot_instance_test):
        """Test getting combined SOC with valid data."""
        pilot_instance_test.coordinator.data = {SAX_COMBINED_SOC: 85.5}

        result = await pilot_instance_test._get_combined_soc()

        assert result == 85.5

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_charge_power_limit_success(self, pilot_instance_test):
        """Test setting charge power limit successfully."""
        mock_item = MagicMock()
        mock_item.name = SAX_MAX_CHARGE

        with (
            patch.object(
                pilot_instance_test.sax_data,
                "get_modbus_items_for_battery",
                return_value=[mock_item],
            ),
            patch.object(
                pilot_instance_test.coordinator,
                "async_write_number_value",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_write,
        ):
            result = await pilot_instance_test.set_charge_power_limit(3000)

            assert result is True
            mock_write.assert_called_once_with(mock_item, float(3000))

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_charge_power_limit_no_item(self, pilot_instance_test):
        """Test setting charge power limit with no item."""
        with patch.object(
            pilot_instance_test.sax_data,
            "get_modbus_items_for_battery",
            return_value=[],  # No items found
        ):
            result = await pilot_instance_test.set_charge_power_limit(3000)

            assert result is False


class TestPilotExceptionHandling:
    """Test exception handling in pilot module."""

    @pytest.fixture
    def pilot_for_exception_test(self, mock_hass, mock_sax_data):
        """Create pilot instance for exception testing."""
        mock_coordinator = MagicMock()
        mock_coordinator.data = None
        mock_sax_data.entry.data = {CONF_MIN_SOC: 20}

        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

    async def test_async_update_pilot_os_error(self, pilot_for_exception_test):
        """Test async_update_pilot with OS error."""
        with patch.object(
            pilot_for_exception_test,
            "_get_combined_soc",
            side_effect=OSError("Connection failed"),
        ):
            # Should not raise exception
            await pilot_for_exception_test._async_update_pilot(None)

            # Pilot should still be in valid state
            assert pilot_for_exception_test.calculated_power == 0.0


class TestPilotEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def pilot_for_edge_test(self, mock_hass):
        """Create pilot instance for edge case testing."""
        mock_sax_data = MagicMock()
        mock_coordinator = MagicMock()
        mock_sax_data.coordinators = {
            "battery_a": mock_coordinator,
            "battery_b": mock_coordinator,
        }
        mock_sax_data.entry.data = {}

        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

    def test_battery_count_calculation(self, pilot_for_edge_test):
        """Test battery count is calculated correctly from coordinators."""
        assert pilot_for_edge_test.battery_count == 2

    def test_modbus_item_without_name_attribute(self, pilot_for_edge_test):
        """Test handling modbus item without name attribute."""
        mock_item_without_name = MagicMock(spec=[])  # No name attribute
        pilot_for_edge_test.sax_data._get_modbus_item_by_name = MagicMock(
            return_value=[mock_item_without_name]
        )

        result = pilot_for_edge_test._get_modbus_item_by_name("test_item")

        assert result is None


class TestSAXBatteryPilotComprehensive:
    """Comprehensive tests for SAXBatteryPilot functionality."""

    @pytest.fixture
    def pilot_with_config_test(self, mock_hass, mock_sax_data, mock_coordinator):
        """Create pilot instance with full configuration for comprehensive testing."""
        # Mock SOC manager on coordinator with proper AsyncMock
        mock_soc_manager = MagicMock()
        mock_soc_manager.min_soc = DEFAULT_MIN_SOC
        mock_soc_manager.enabled = True

        # Critical: Use AsyncMock for async methods
        mock_soc_manager.apply_constraints = AsyncMock()
        mock_soc_manager.check_discharge_allowed = AsyncMock()
        mock_soc_manager.check_charge_allowed = AsyncMock()
        mock_soc_manager.get_current_soc = AsyncMock(return_value=50.0)

        mock_coordinator.soc_manager = mock_soc_manager

        # Rest of fixture setup...
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_AUTO_PILOT_INTERVAL: DEFAULT_AUTO_PILOT_INTERVAL,
            CONF_POWER_SENSOR: "sensor.total_power",
            CONF_PF_SENSOR: "sensor.power_factor",
            CONF_PRIORITY_DEVICES: [
                "sensor.priority_device_1",
                "sensor.priority_device_2",
            ],
            CONF_MIN_SOC: DEFAULT_MIN_SOC,
            CONF_ENABLE_SOLAR_CHARGING: True,
            CONF_MANUAL_CONTROL: False,
        }

        mock_sax_data.entry = mock_entry
        mock_sax_data.coordinators = {"battery_a": mock_coordinator}
        mock_sax_data.master_battery_id = "battery_a"

        pilot = SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)
        pilot.entry = mock_entry

        return pilot

    async def test_async_update_pilot_manual_mode_with_constraints(
        self, pilot_with_config_test
    ):
        """Test async_update_pilot in manual mode with SOC constraints."""
        # Set manual mode and current power
        pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL] = True
        pilot_with_config_test.calculated_power = 500.0

        with (
            patch.object(
                pilot_with_config_test, "_apply_soc_constraints", return_value=0.0
            ) as mock_constraints,
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Should apply constraints and adjust power
            mock_constraints.assert_called_once_with(500.0)
            mock_send.assert_called_once_with(0.0, 1.0)
            assert pilot_with_config_test.calculated_power == 0.0

    async def test_async_update_pilot_manual_mode_no_adjustment(
        self, pilot_with_config_test
    ):
        """Test async_update_pilot in manual mode with no adjustment needed."""
        # Set manual mode
        pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL] = True
        pilot_with_config_test.calculated_power = 300.0

        with (
            patch.object(
                pilot_with_config_test, "_apply_soc_constraints", return_value=300.0
            ) as mock_constraints,
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Should check constraints but not send command
            mock_constraints.assert_called_once_with(300.0)
            mock_send.assert_not_called()

    async def test_async_update_pilot_missing_power_sensor(
        self, pilot_with_config_test
    ):
        """Test async_update_pilot with missing power sensor."""
        pilot_with_config_test.power_sensor_entity_id = None

        await pilot_with_config_test._async_update_pilot(None)

        # Should exit early without error
        assert pilot_with_config_test.calculated_power == 0.0

    async def test_async_update_pilot_power_sensor_not_found(
        self, pilot_with_config_test
    ):
        """Test async_update_pilot when power sensor entity doesn't exist."""
        pilot_with_config_test.hass.states.get.return_value = None

        await pilot_with_config_test._async_update_pilot(None)

        # Should exit early
        pilot_with_config_test.hass.states.get.assert_called_with("sensor.total_power")

    async def test_async_update_pilot_power_sensor_unavailable(
        self, pilot_with_config_test
    ):
        """Test async_update_pilot with unavailable power sensor."""
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        pilot_with_config_test.hass.states.get.return_value = mock_state

        await pilot_with_config_test._async_update_pilot(None)

        # Should exit early without processing
        assert pilot_with_config_test.calculated_power == 0.0

    async def test_async_update_pilot_invalid_power_value(self, pilot_with_config_test):
        """Test async_update_pilot with invalid power sensor value."""
        mock_power_state = MagicMock()
        mock_power_state.state = "invalid_number"
        pilot_with_config_test.hass.states.get.return_value = mock_power_state

        await pilot_with_config_test._async_update_pilot(None)

        # Should handle ValueError gracefully
        assert pilot_with_config_test.calculated_power == 0.0

    async def test_async_update_pilot_missing_pf_sensor(self, pilot_with_config_test):
        """Test async_update_pilot with missing PF sensor configuration."""
        # Mock valid power sensor
        mock_power_state = MagicMock()
        mock_power_state.state = "1500.0"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            return None

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state
        pilot_with_config_test.pf_sensor_entity_id = None

        await pilot_with_config_test._async_update_pilot(None)

        # Should exit when PF sensor is not configured
        assert pilot_with_config_test.calculated_power == 0.0

    async def test_async_update_pilot_invalid_pf_value(self, pilot_with_config_test):
        """Test async_update_pilot with invalid PF sensor value."""
        mock_power_state = MagicMock()
        mock_power_state.state = "1500.0"
        mock_pf_state = MagicMock()
        mock_pf_state.state = "not_a_number"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            return None

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        await pilot_with_config_test._async_update_pilot(None)

        # Should handle ValueError for PF conversion
        assert pilot_with_config_test.calculated_power == 0.0

    async def test_async_update_pilot_invalid_priority_device_value(
        self, pilot_with_config_test
    ):
        """Test handling of invalid priority device values."""
        mock_power_state = MagicMock()
        mock_power_state.state = "1500.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        mock_device1_state = MagicMock()
        mock_device1_state.state = "invalid"  # Invalid value

        mock_device2_state = MagicMock()
        mock_device2_state.state = "200.0"

        def mock_get_state(entity_id):
            state_map = {
                "sensor.total_power": mock_power_state,
                "sensor.power_factor": mock_pf_state,
                "sensor.priority_device_1": mock_device1_state,  # FIX: Match fixture config
                "sensor.priority_device_2": mock_device2_state,  # FIX: Match fixture config
                "sensor.sax_battery_combined_power": None,  # No battery power sensor
            }
            return state_map.get(entity_id)

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(
                pilot_with_config_test, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,  # noqa: F841
            patch.object(
                pilot_with_config_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Should handle invalid priority device value gracefully
            # Only device2 (200W) should be counted, total priority_power = 200W > 50
            expected_power = 0.0
            assert pilot_with_config_test.calculated_power == expected_power

    async def test_async_update_pilot_missing_battery_power_sensor(
        self, pilot_with_config_test
    ):
        """Test power calculation with missing battery power sensor."""
        mock_power_state = MagicMock()
        mock_power_state.state = "1000.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "0.98"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            if entity_id in ["sensor.device1", "sensor.device2"]:
                return None  # No priority devices
            if entity_id == "sensor.sax_battery_combined_power":
                return None  # No battery power sensor
            return None

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(
                pilot_with_config_test, "_get_combined_soc", return_value=40.0
            ),
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,  # noqa: F841
            patch.object(
                pilot_with_config_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Should use battery_power = 0.0 when sensor is missing
            # net_power = total_power - battery_power = 1000 - 0 = 1000
            # target_power = -1000
            expected_power = -1000.0
            assert pilot_with_config_test.calculated_power == expected_power

    async def test_async_update_pilot_power_limits_applied(
        self, pilot_with_config_test
    ):
        """Test that power limits are correctly applied."""
        # Set up scenario that would exceed limits
        pilot_with_config_test.max_discharge_power = 1000  # Lower limit for testing
        pilot_with_config_test.max_charge_power = 2000

        mock_power_state = MagicMock()
        mock_power_state.state = "5000.0"  # High power

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            if entity_id == "sensor.sax_battery_combined_power":
                mock_battery_state = MagicMock()
                mock_battery_state.state = "0.0"
                return mock_battery_state
            return None

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(
                pilot_with_config_test, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,  # noqa: F841
            patch.object(
                pilot_with_config_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # The calculation: net_power = 5000 - 0 = 5000, target_power = -5000
            # Limited to max_charge_power = 2000 (positive value for charging)
            # But the implementation applies: max(-1000, min(2000, -5000)) = max(-1000, -5000) = -1000
            expected_power = -1000.0  # Limited by max_discharge_power
            assert pilot_with_config_test.calculated_power == expected_power

    async def test_async_update_pilot_solar_charging_disabled(
        self, pilot_with_config_test
    ):
        """Test that power command is not sent when solar charging is disabled."""
        mock_power_state = MagicMock()
        mock_power_state.state = "1000.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            return None

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(
                pilot_with_config_test, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
            patch.object(
                pilot_with_config_test, "get_solar_charging_enabled", return_value=False
            ),
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Should calculate power but not send command
            assert pilot_with_config_test.calculated_power == -1000.0
            mock_send.assert_not_called()

    async def test_get_combined_soc_invalid_value(self, pilot_with_config_test):
        """Test getting combined SOC with invalid data."""
        pilot_with_config_test.coordinator.data = {SAX_COMBINED_SOC: "invalid"}

        result = await pilot_with_config_test._get_combined_soc()

        assert result == 0.0

    async def test_send_power_command_success(self, pilot_with_config_test):
        """Test successful power command sending."""
        mock_item = MagicMock()
        mock_item.name = SAX_NOMINAL_POWER

        # Fix: Properly mock the async method on the coordinator
        pilot_with_config_test.coordinator.async_write_pilot_control_value = AsyncMock(
            return_value=True
        )

        with patch.object(
            pilot_with_config_test,
            "_get_modbus_item_by_name",
            return_value=mock_item,
        ):
            await pilot_with_config_test.send_power_command(1500.0, 0.95)

            pilot_with_config_test.coordinator.async_write_pilot_control_value.assert_called_once_with(
                mock_item, mock_item, 1500.0, int(0.95)
            )

    async def test_send_power_command_no_item(self, pilot_with_config_test):
        """Test power command when modbus item not found."""
        with patch.object(
            pilot_with_config_test, "_get_modbus_item_by_name", return_value=None
        ):
            # Should not raise exception
            await pilot_with_config_test.send_power_command(1500.0, 1.0)

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_manual_power_with_constraints(self, pilot_with_config_test):
        """Test setting manual power with SOC constraints applied."""
        with (
            patch.object(
                pilot_with_config_test, "_apply_soc_constraints", return_value=0.0
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            await pilot_with_config_test.set_manual_power(500.0)

            assert pilot_with_config_test.calculated_power == 0.0
            mock_send.assert_called_once_with(0.0, 1.0)

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_discharge_power_limit_success(self, pilot_with_config_test):
        """Test setting discharge power limit successfully."""
        mock_item = MagicMock()
        mock_item.name = SAX_MAX_DISCHARGE

        with (
            patch.object(
                pilot_with_config_test.sax_data,
                "get_modbus_items_for_battery",
                return_value=[mock_item],
            ),
            patch.object(
                pilot_with_config_test.coordinator,
                "async_write_number_value",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_write,
        ):
            result = await pilot_with_config_test.set_discharge_power_limit(2500)

            assert result is True
            mock_write.assert_called_once_with(mock_item, float(2500))

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_discharge_power_limit_no_item(self, pilot_with_config_test):
        """Test setting discharge power limit with no item found."""
        with patch.object(
            pilot_with_config_test.sax_data,
            "get_modbus_items_for_battery",
            return_value=[],
        ):
            result = await pilot_with_config_test.set_discharge_power_limit(2500)

            assert result is False

    def test_get_solar_charging_enabled_true(self, pilot_with_config_test):
        """Test getting solar charging enabled state when True."""
        pilot_with_config_test.entry.data[CONF_ENABLE_SOLAR_CHARGING] = True

        result = pilot_with_config_test.get_solar_charging_enabled()

        assert result is True

    def test_get_solar_charging_enabled_false(self, pilot_with_config_test):
        """Test getting solar charging enabled state when False."""
        pilot_with_config_test.entry.data[CONF_ENABLE_SOLAR_CHARGING] = False

        result = pilot_with_config_test.get_solar_charging_enabled()

        assert result is False

    def test_get_solar_charging_disabled_default(self, pilot_with_config_test):
        """Test getting solar charging enabled state with default value."""
        # Remove the key to test default
        if CONF_ENABLE_SOLAR_CHARGING in pilot_with_config_test.entry.data:
            del pilot_with_config_test.entry.data[CONF_ENABLE_SOLAR_CHARGING]

        result = pilot_with_config_test.get_solar_charging_enabled()

        assert result is False  # Default is False

    def test_get_manual_control_enabled_true(self, pilot_with_config_test):
        """Test getting manual control enabled state when True."""
        pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL] = True

        result = pilot_with_config_test.get_manual_control_enabled()

        assert result is True

    def test_get_manual_control_enabled_false(self, pilot_with_config_test):
        """Test getting manual control enabled state when False."""
        pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL] = False

        result = pilot_with_config_test.get_manual_control_enabled()

        assert result is False

    def test_get_manual_control_enabled_default(self, pilot_with_config_test):
        """Test getting manual control enabled state with default value."""
        # Remove the key to test default
        if CONF_MANUAL_CONTROL in pilot_with_config_test.entry.data:
            del pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL]

        result = pilot_with_config_test.get_manual_control_enabled()

        assert result is True  # Default is True

    async def test_async_update_pilot_with_floating_point_precision(
        self, pilot_with_config_test
    ):
        """Test power calculation with floating point precision."""
        mock_power_state = MagicMock()
        mock_power_state.state = "1234.567"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "0.987654"

        mock_device1_state = MagicMock()
        mock_device1_state.state = "12.345"

        mock_device2_state = MagicMock()
        mock_device2_state.state = "23.456"

        mock_battery_power_state = MagicMock()
        mock_battery_power_state.state = "567.890"

        def mock_get_state(entity_id):
            state_map = {
                "sensor.total_power": mock_power_state,
                "sensor.power_factor": mock_pf_state,
                "sensor.device1": mock_device1_state,
                "sensor.device2": mock_device2_state,
                "sensor.sax_battery_combined_power": mock_battery_power_state,
            }
            return state_map.get(entity_id)

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(
                pilot_with_config_test, "_get_combined_soc", return_value=45.67
            ),
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,  # noqa: F841
            patch.object(
                pilot_with_config_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Priority devices total = 35.801, condition: priority_power <= 50
            # net_power = 1234.567 - 567.890 = 666.677
            # target_power = -666.677
            expected_power = -666.677
            assert abs(pilot_with_config_test.calculated_power - expected_power) < 0.001

    async def test_async_update_pilot_negative_power_values(
        self, pilot_with_config_test
    ):
        """Test handling of negative power values from sensors."""
        mock_power_state = MagicMock()
        mock_power_state.state = "-500.0"  # Negative grid power (export)

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        mock_device1_state = MagicMock()
        mock_device1_state.state = "-10.0"  # Negative priority device power

        mock_battery_power_state = MagicMock()
        mock_battery_power_state.state = "-200.0"  # Battery charging

        def mock_get_state(entity_id):
            state_map = {
                "sensor.total_power": mock_power_state,
                "sensor.power_factor": mock_pf_state,
                "sensor.device1": mock_device1_state,
                "sensor.sax_battery_combined_power": mock_battery_power_state,
            }
            return state_map.get(entity_id)

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(
                pilot_with_config_test, "_get_combined_soc", return_value=30.0
            ),
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,  # noqa: F841
            patch.object(
                pilot_with_config_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Priority power = -10.0, condition: priority_power <= 50
            # net_power = -500.0 - (-200.0) = -300.0
            # target_power = -(-300.0) = 300.0
            expected_power = 300.0
            assert pilot_with_config_test.calculated_power == expected_power

    async def test_async_update_pilot_very_low_power_factor(
        self, pilot_with_config_test
    ):
        """Test handling of very low power factor values."""
        mock_power_state = MagicMock()
        mock_power_state.state = "1000.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "0.001"  # Very low power factor

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            return None

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(
                pilot_with_config_test, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
            patch.object(
                pilot_with_config_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_config_test._async_update_pilot(None)

            # Should handle very low power factor gracefully
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert call_args[1] == 0.001  # Power factor preserved

    async def test_get_modbus_item_multiple_matches(self, pilot_with_config_test):
        """Test _get_modbus_item_by_name when multiple items have same name."""
        mock_item1 = MagicMock()
        mock_item1.name = "test_item"
        mock_item2 = MagicMock()
        mock_item2.name = "test_item"
        mock_item3 = MagicMock()
        mock_item3.name = "other_item"

        pilot_with_config_test.sax_data.get_modbus_items_for_battery.return_value = [
            mock_item1,
            mock_item2,
            mock_item3,
        ]

        result = pilot_with_config_test._get_modbus_item_by_name("test_item")

        # Should return the first match
        assert result == mock_item1

    async def test_get_modbus_item_no_matches(self, pilot_with_config_test):
        """Test _get_modbus_item_by_name when no items match."""
        mock_item = MagicMock()
        mock_item.name = "other_item"

        pilot_with_config_test.sax_data.get_modbus_items_for_battery.return_value = [
            mock_item
        ]

        result = pilot_with_config_test._get_modbus_item_by_name("nonexistent_item")

        assert result is None

    async def test_get_modbus_item_empty_list(self, pilot_with_config_test):
        """Test _get_modbus_item_by_name with empty items list."""
        pilot_with_config_test.sax_data.get_modbus_items_for_battery.return_value = []

        result = pilot_with_config_test._get_modbus_item_by_name("any_item")

        assert result is None

    def test_update_config_values_comprehensive(self, pilot_with_config_test):
        """Test _update_config_values with comprehensive configuration."""
        # Update entry data with new values
        pilot_with_config_test.entry.data = {
            CONF_POWER_SENSOR: "sensor.new_power",
            CONF_PF_SENSOR: "sensor.new_pf",
            CONF_PRIORITY_DEVICES: ["sensor.new_device1", "sensor.new_device2"],
            CONF_AUTO_PILOT_INTERVAL: 45,
        }

        pilot_with_config_test._update_config_values()

        assert pilot_with_config_test.power_sensor_entity_id == "sensor.new_power"
        assert pilot_with_config_test.pf_sensor_entity_id == "sensor.new_pf"
        assert pilot_with_config_test.priority_devices == [
            "sensor.new_device1",
            "sensor.new_device2",
        ]
        assert pilot_with_config_test.update_interval == 45

    async def test_send_power_command_write_failure(self, pilot_with_config_test):
        """Test send_power_command when write operation returns False."""
        mock_item = MagicMock()
        mock_item.name = SAX_NOMINAL_POWER

        # Fix: Properly mock the async method on the coordinator
        pilot_with_config_test.coordinator.async_write_pilot_control_value = AsyncMock(
            return_value=False
        )

        with patch.object(
            pilot_with_config_test,
            "_get_modbus_item_by_name",
            return_value=mock_item,
        ):
            # Should handle write failure gracefully
            await pilot_with_config_test.send_power_command(1500.0, 0.95)

            pilot_with_config_test.coordinator.async_write_pilot_control_value.assert_called_once()

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_manual_power_with_negative_value(self, pilot_with_config_test):
        """Test setting manual power with negative value (charging)."""
        with (
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                return_value=-2000.0,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            await pilot_with_config_test.set_manual_power(-2500.0)

            assert pilot_with_config_test.calculated_power == -2000.0
            mock_send.assert_called_once_with(-2000.0, 1.0)

    def test_battery_count_with_single_battery(self, pilot_with_config_test):
        """Test battery count calculation with single battery."""
        # Modify coordinators to have only one battery
        pilot_with_config_test.sax_data.coordinators = {"battery_a": MagicMock()}
        pilot_new = SAXBatteryPilot(
            pilot_with_config_test.hass,
            pilot_with_config_test.sax_data,
            pilot_with_config_test.coordinator,
        )

        assert pilot_new.battery_count == 1
        assert pilot_new.max_discharge_power == LIMIT_MAX_CHARGE_PER_BATTERY
        assert pilot_new.max_charge_power == LIMIT_MAX_DISCHARGE_PER_BATTERY

    def test_battery_count_with_many_batteries(self, pilot_with_config_test):
        """Test battery count calculation with many batteries."""
        # Create many coordinators
        many_coordinators = {f"battery_{i}": MagicMock() for i in range(10)}
        pilot_with_config_test.sax_data.coordinators = many_coordinators
        pilot_new = SAXBatteryPilot(
            pilot_with_config_test.hass,
            pilot_with_config_test.sax_data,
            pilot_with_config_test.coordinator,
        )

        assert pilot_new.battery_count == 10
        assert (
            pilot_new.max_discharge_power == 35000
        )  # 10 * LIMIT_MAX_CHARGE_PER_BATTERY00
        assert (
            pilot_new.max_charge_power == 46000
        )  # 10 * LIMIT_MAX_DISCHARGE_PER_BATTERY


class TestPilotAdditionalEdgeCases:
    """Additional edge case tests for comprehensive coverage."""

    @pytest.fixture
    def pilot_boundary_test(self, mock_hass, mock_sax_data, mock_coordinator):
        """Create pilot for boundary testing."""
        mock_sax_data.coordinators = {"battery_a": mock_coordinator}
        mock_sax_data.entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_POWER_SENSOR: "sensor.total_power",
            CONF_PF_SENSOR: "sensor.power_factor",
            CONF_MIN_SOC: 0,  # Boundary value
            CONF_AUTO_PILOT_INTERVAL: 1,  # Minimum interval
            CONF_PRIORITY_DEVICES: [],
            CONF_ENABLE_SOLAR_CHARGING: True,
            CONF_MANUAL_CONTROL: False,
        }
        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

    def test_pilot_with_zero_batteries(
        self, mock_hass, mock_sax_data, mock_coordinator
    ):
        """Test pilot initialization with zero batteries."""
        mock_sax_data.coordinators = {}  # No batteries
        mock_sax_data.entry.data = {}

        pilot = SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

        assert pilot.battery_count == 0
        assert pilot.max_discharge_power == 0
        assert pilot.max_charge_power == 0

    async def test_priority_devices_with_unavailable_states(self, pilot_boundary_test):
        """Test priority device calculation with unavailable device states."""
        pilot_boundary_test.priority_devices = [
            "sensor.device1",
            "sensor.device2",
            "sensor.device3",
        ]

        mock_power_state = MagicMock()
        mock_power_state.state = "1000.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            if entity_id == "sensor.device1":
                mock_state = MagicMock()
                mock_state.state = "100.0"
                return mock_state
            if entity_id == "sensor.device2":
                return None  # Device not found
            if entity_id == "sensor.device3":
                mock_state = MagicMock()
                mock_state.state = "unavailable"
                return mock_state
            return None

        pilot_boundary_test.hass.states.get.side_effect = mock_get_state

        with (
            patch.object(pilot_boundary_test, "_get_combined_soc", return_value=50.0),
            patch.object(
                pilot_boundary_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_boundary_test, "send_power_command", new_callable=AsyncMock
            ),
            patch.object(
                pilot_boundary_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_boundary_test._async_update_pilot(None)

            # Should only count device1 (100W), others are unavailable/not found
            # Priority power = 100W > 50, so net_power = 0
            assert pilot_boundary_test.calculated_power == 0.0


class TestPilotPerformanceAndEdgeCases:
    """Test performance and edge cases."""

    @pytest.fixture
    def pilot_performance_test(self, mock_hass, mock_sax_data, mock_coordinator):
        """Create pilot for performance testing."""
        # Create multiple coordinators to test battery counting
        mock_sax_data.coordinators = {
            f"battery_{chr(97 + i)}": mock_coordinator
            for i in range(5)  # a-e
        }
        mock_sax_data.entry.data = {
            CONF_PRIORITY_DEVICES: [
                f"sensor.device_{i}" for i in range(10)
            ],  # Many devices
        }
        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

    def test_multiple_battery_power_calculation(self, pilot_performance_test):
        """Test power calculation scales with battery count."""
        assert pilot_performance_test.battery_count == 5
        assert (
            pilot_performance_test.max_discharge_power
            == 5 * LIMIT_MAX_CHARGE_PER_BATTERY
        )
        assert (
            pilot_performance_test.max_charge_power
            == 5 * LIMIT_MAX_DISCHARGE_PER_BATTERY
        )

    async def test_empty_priority_devices_list(self, pilot_performance_test):
        """Test with empty priority devices list."""
        pilot_performance_test.priority_devices = []

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                mock_state = MagicMock()
                mock_state.state = "1000.0"
                return mock_state
            if entity_id == "sensor.power_factor":
                mock_state = MagicMock()
                mock_state.state = "1.0"
                return mock_state
            return None

        pilot_performance_test.hass.states.get.side_effect = mock_get_state
        pilot_performance_test.power_sensor_entity_id = "sensor.total_power"
        pilot_performance_test.pf_sensor_entity_id = "sensor.power_factor"

        with (
            patch.object(
                pilot_performance_test, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_performance_test,
                "_apply_soc_constraints",
                side_effect=lambda x: x,
            ),
            patch.object(
                pilot_performance_test, "send_power_command", new_callable=AsyncMock
            ),
            patch.object(
                pilot_performance_test, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_performance_test._async_update_pilot(None)

        # With no priority devices, priority_power = 0, net_power = total_power - battery_power
        # target_power = -1000
        assert pilot_performance_test.calculated_power == -1000.0


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
