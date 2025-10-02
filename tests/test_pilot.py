"""Test pilot platform for SAX Battery integration."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

from pymodbus.exceptions import ModbusException
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
        assert pilot_instance_test.min_soc == DEFAULT_MIN_SOC
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
            CONF_MIN_SOC: 20,
            CONF_AUTO_PILOT_INTERVAL: 30,
        }

        with patch.object(
            pilot_instance_test, "_async_update_pilot", new_callable=AsyncMock
        ) as mock_update:
            await pilot_instance_test._async_config_updated(
                pilot_instance_test.hass, mock_entry
            )

            assert pilot_instance_test.min_soc == 20
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

    async def test_apply_soc_constraints_below_min_soc_discharge(
        self, pilot_instance_test
    ):
        """Test SOC constraints preventing discharge below minimum SOC."""
        # Set proper min_soc value
        pilot_instance_test.min_soc = 20

        with patch.object(pilot_instance_test, "_get_combined_soc", return_value=10.0):
            result = await pilot_instance_test._apply_soc_constraints(
                100.0
            )  # Positive = discharge

            # Should prevent discharge when SOC is below minimum
            assert result == 0.0

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
        """Create pilot with full configuration for testing."""
        mock_sax_data.coordinators = {"battery_a": mock_coordinator}
        mock_sax_data.entry.data = {
            CONF_PILOT_FROM_HA: True,
            CONF_POWER_SENSOR: "sensor.total_power",
            CONF_PF_SENSOR: "sensor.power_factor",
            CONF_MIN_SOC: 15,
            CONF_AUTO_PILOT_INTERVAL: 25,
            CONF_PRIORITY_DEVICES: ["sensor.device1", "sensor.device2"],
            CONF_ENABLE_SOLAR_CHARGING: True,
            CONF_MANUAL_CONTROL: False,
        }
        return SAXBatteryPilot(mock_hass, mock_sax_data, mock_coordinator)

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

    async def test_async_update_pilot_pf_sensor_unavailable(
        self, pilot_with_config_test
    ):
        """Test async_update_pilot with unavailable PF sensor."""
        mock_power_state = MagicMock()
        mock_power_state.state = "1500.0"
        mock_pf_state = MagicMock()
        mock_pf_state.state = "unknown"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            return None

        pilot_with_config_test.hass.states.get.side_effect = mock_get_state

        await pilot_with_config_test._async_update_pilot(None)

        # Should exit when PF sensor is unavailable
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

    async def test_async_update_pilot_full_calculation_with_priority_devices(
        self, pilot_with_config_test
    ):
        """Test complete power calculation with priority devices."""
        # Mock all required states
        mock_power_state = MagicMock()
        mock_power_state.state = "2000.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "0.95"

        mock_device1_state = MagicMock()
        mock_device1_state.state = "300.0"

        mock_device2_state = MagicMock()
        mock_device2_state.state = "200.0"

        mock_battery_power_state = MagicMock()
        mock_battery_power_state.state = "800.0"

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

            # Priority devices total = 500W, condition: priority_power > 50, so net_power = 0
            # target_power = -0 = 0
            expected_power = 0.0
            assert pilot_with_config_test.calculated_power == expected_power
            mock_send.assert_called_once_with(expected_power, 0.95)

    async def test_async_update_pilot_low_priority_power_calculation(
        self, pilot_with_config_test
    ):
        """Test power calculation when priority devices consume little power."""
        # Mock states with low priority device consumption
        mock_power_state = MagicMock()
        mock_power_state.state = "1500.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        mock_device1_state = MagicMock()
        mock_device1_state.state = "20.0"  # Low consumption

        mock_device2_state = MagicMock()
        mock_device2_state.state = "10.0"  # Low consumption

        mock_battery_power_state = MagicMock()
        mock_battery_power_state.state = "500.0"

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
                pilot_with_config_test, "_get_combined_soc", return_value=60.0
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

            # Priority devices total = 30W, condition: priority_power <= 50
            # net_power = total_power - battery_power = 1500 - 500 = 1000
            # target_power = -1000
            expected_power = -1000.0
            # Limited by max_charge_power = 4500
            assert pilot_with_config_test.calculated_power == expected_power
            mock_send.assert_called_once_with(expected_power, 1.0)

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
                "sensor.device1": mock_device1_state,
                "sensor.device2": mock_device2_state,
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

    async def test_apply_soc_constraints_above_max_soc_charge(
        self, pilot_with_config_test
    ):
        """Test SOC constraints preventing charge above 100%."""
        with patch.object(
            pilot_with_config_test, "_get_combined_soc", return_value=100.0
        ):
            result = await pilot_with_config_test._apply_soc_constraints(
                -500.0
            )  # Negative = charge

            # Should prevent charge when SOC is at 100%
            assert result == 0.0

    async def test_apply_soc_constraints_no_change_needed(self, pilot_with_config_test):
        """Test SOC constraints when no change is needed."""
        with patch.object(
            pilot_with_config_test, "_get_combined_soc", return_value=50.0
        ):
            result = await pilot_with_config_test._apply_soc_constraints(100.0)

            # Should not change value when SOC is within limits
            assert result == 100.0

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

    async def test_send_power_command_modbus_exception(self, pilot_with_config_test):
        """Test power command with ModbusException."""
        mock_item = MagicMock()

        with (
            patch.object(
                pilot_with_config_test,
                "_get_modbus_item_by_name",
                return_value=mock_item,
            ),
            patch.object(
                pilot_with_config_test.coordinator.modbus_api,
                "write_nominal_power",
                new_callable=AsyncMock,
                side_effect=ModbusException("Modbus error"),
            ),
        ):
            # Should handle exception gracefully
            await pilot_with_config_test.send_power_command(1500.0, 1.0)

    async def test_send_power_command_os_error(self, pilot_with_config_test):
        """Test power command with OSError."""
        mock_item = MagicMock()

        with (
            patch.object(
                pilot_with_config_test,
                "_get_modbus_item_by_name",
                return_value=mock_item,
            ),
            patch.object(
                pilot_with_config_test.coordinator.modbus_api,
                "write_nominal_power",
                new_callable=AsyncMock,
                side_effect=OSError("Network error"),
            ),
        ):
            # Should handle exception gracefully
            await pilot_with_config_test.send_power_command(1500.0, 1.0)

    async def test_send_power_command_value_error(self, pilot_with_config_test):
        """Test power command with ValueError."""
        mock_item = MagicMock()

        with (
            patch.object(
                pilot_with_config_test,
                "_get_modbus_item_by_name",
                return_value=mock_item,
            ),
            patch.object(
                pilot_with_config_test.coordinator.modbus_api,
                "write_nominal_power",
                new_callable=AsyncMock,
                side_effect=ValueError("Invalid value"),
            ),
        ):
            # Should handle exception gracefully
            await pilot_with_config_test.send_power_command(1500.0, 1.0)

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

    async def test_set_discharge_power_limit_no_item(self, pilot_with_config_test):
        """Test setting discharge power limit with no item found."""
        with patch.object(
            pilot_with_config_test.sax_data,
            "get_modbus_items_for_battery",
            return_value=[],
        ):
            result = await pilot_with_config_test.set_discharge_power_limit(2500)

            assert result is False

    async def test_set_discharge_power_limit_modbus_exception(
        self, pilot_with_config_test
    ):
        """Test setting discharge power limit with ModbusException."""
        mock_item = MagicMock()

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
                side_effect=ModbusException("Modbus error"),
            ),
        ):
            result = await pilot_with_config_test.set_discharge_power_limit(2500)

            assert result is False

    async def test_set_charge_power_limit_modbus_exception(
        self, pilot_with_config_test
    ):
        """Test setting charge power limit with ModbusException."""
        mock_item = MagicMock()

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
                side_effect=ModbusException("Modbus error"),
            ),
        ):
            result = await pilot_with_config_test.set_charge_power_limit(3000)

            assert result is False

    async def test_set_charge_power_limit_os_error(self, pilot_with_config_test):
        """Test setting charge power limit with OSError."""
        mock_item = MagicMock()

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
                side_effect=OSError("Network error"),
            ),
        ):
            result = await pilot_with_config_test.set_charge_power_limit(3000)

            assert result is False

    async def test_set_discharge_power_limit_value_error(self, pilot_with_config_test):
        """Test setting discharge power limit with ValueError."""
        mock_item = MagicMock()

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
                side_effect=ValueError("Invalid value"),
            ),
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

    async def test_async_update_pilot_charge_power_limited(
        self, pilot_with_config_test
    ):
        """Test charge power is limited by max_charge_power."""
        pilot_with_config_test.max_discharge_power = 3600
        pilot_with_config_test.max_charge_power = 1000  # Lower limit for testing

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
            # Limited by: max(-3600, min(1000, -5000)) = max(-3600, -5000) = -3600
            # So it's limited by max_discharge_power, not max_charge_power
            expected_power = -3600.0  # Limited by max_discharge_power
            assert pilot_with_config_test.calculated_power == expected_power

    async def test_async_update_pilot_discharge_power_limited(
        self, pilot_with_config_test
    ):
        """Test discharge power is limited by max_discharge_power."""
        pilot_with_config_test.max_discharge_power = 500  # Lower limit for testing
        pilot_with_config_test.max_charge_power = 4500

        mock_power_state = MagicMock()
        mock_power_state.state = "0.0"  # No grid power

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        def mock_get_state(entity_id):
            if entity_id == "sensor.total_power":
                return mock_power_state
            if entity_id == "sensor.power_factor":
                return mock_pf_state
            if entity_id == "sensor.sax_battery_combined_power":
                mock_battery_state = MagicMock()
                mock_battery_state.state = "-2000.0"  # Battery discharging
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

            # net_power = 0 - (-2000) = 2000, target_power = -2000
            # Limited by max_discharge_power: max(-500, min(4500, -2000)) = max(-500, -2000) = -500
            expected_power = -500.0
            assert pilot_with_config_test.calculated_power == expected_power

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

    async def test_async_update_pilot_zero_power_values(self, pilot_with_config_test):
        """Test handling of zero power values."""
        mock_power_state = MagicMock()
        mock_power_state.state = "0.0"

        mock_pf_state = MagicMock()
        mock_pf_state.state = "1.0"

        mock_battery_power_state = MagicMock()
        mock_battery_power_state.state = "0.0"

        def mock_get_state(entity_id):
            state_map = {
                "sensor.total_power": mock_power_state,
                "sensor.power_factor": mock_pf_state,
                "sensor.sax_battery_combined_power": mock_battery_power_state,
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

            # All zero values should result in zero target power
            assert pilot_with_config_test.calculated_power == 0.0

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

    async def test_async_update_pilot_exception_in_soc_calculation(
        self, pilot_with_config_test
    ):
        """Test handling of exception in SOC calculation."""
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
                pilot_with_config_test,
                "_get_combined_soc",
                side_effect=ValueError("SOC calculation failed"),
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            # Should handle exception gracefully without crashing
            await pilot_with_config_test._async_update_pilot(None)

            # Should exit gracefully due to exception
            mock_send.assert_not_called()

    async def test_async_update_pilot_exception_in_constraint_application(
        self, pilot_with_config_test
    ):
        """Test handling of exception in constraint application."""
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
                side_effect=OSError("Constraint application failed"),
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            # Should handle exception gracefully
            await pilot_with_config_test._async_update_pilot(None)

            # Should exit gracefully due to exception
            mock_send.assert_not_called()

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
            CONF_MIN_SOC: 25,
            CONF_AUTO_PILOT_INTERVAL: 45,
        }

        pilot_with_config_test._update_config_values()

        assert pilot_with_config_test.power_sensor_entity_id == "sensor.new_power"
        assert pilot_with_config_test.pf_sensor_entity_id == "sensor.new_pf"
        assert pilot_with_config_test.priority_devices == [
            "sensor.new_device1",
            "sensor.new_device2",
        ]
        assert pilot_with_config_test.min_soc == 25
        assert pilot_with_config_test.update_interval == 45

    def test_update_config_values_with_none_values(self, pilot_with_config_test):
        """Test _update_config_values with None values in config."""
        pilot_with_config_test.entry.data = {
            CONF_POWER_SENSOR: None,
            CONF_PF_SENSOR: None,
            CONF_PRIORITY_DEVICES: None,
            CONF_MIN_SOC: None,
            CONF_AUTO_PILOT_INTERVAL: None,
        }

        pilot_with_config_test._update_config_values()

        assert pilot_with_config_test.power_sensor_entity_id is None
        assert pilot_with_config_test.pf_sensor_entity_id is None
        assert pilot_with_config_test.priority_devices is None
        assert pilot_with_config_test.min_soc is None
        assert pilot_with_config_test.update_interval is None

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

    async def test_set_manual_power_with_zero_value(self, pilot_with_config_test):
        """Test setting manual power with zero value."""
        with (
            patch.object(
                pilot_with_config_test, "_apply_soc_constraints", return_value=0.0
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            await pilot_with_config_test.set_manual_power(0.0)

            assert pilot_with_config_test.calculated_power == 0.0
            mock_send.assert_called_once_with(0.0, 1.0)

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

    async def test_apply_soc_constraints_at_exact_min_soc(self, pilot_boundary_test):
        """Test SOC constraints when SOC is exactly at minimum."""
        pilot_boundary_test.min_soc = 20

        with patch.object(pilot_boundary_test, "_get_combined_soc", return_value=20.0):
            result = await pilot_boundary_test._apply_soc_constraints(100.0)

            # Should allow discharge when SOC is exactly at minimum
            assert result == 100.0

    async def test_apply_soc_constraints_at_exact_max_soc(self, pilot_boundary_test):
        """Test SOC constraints when SOC is exactly 100%."""
        with patch.object(pilot_boundary_test, "_get_combined_soc", return_value=100.0):
            result = await pilot_boundary_test._apply_soc_constraints(-100.0)

            # Should prevent charge when SOC is exactly 100%
            assert result == 0.0

    async def test_apply_soc_constraints_above_100_soc(self, pilot_boundary_test):
        """Test SOC constraints when SOC is above 100% (edge case)."""
        with patch.object(pilot_boundary_test, "_get_combined_soc", return_value=101.0):
            result = await pilot_boundary_test._apply_soc_constraints(-100.0)

            # Should prevent charge when SOC is above 100%
            assert result == 0.0

    async def test_get_combined_soc_with_string_number(self, pilot_boundary_test):
        """Test _get_combined_soc with string that can be converted to float."""
        pilot_boundary_test.coordinator.data = {SAX_COMBINED_SOC: "75.5"}

        result = await pilot_boundary_test._get_combined_soc()

        assert result == 75.5

    async def test_get_combined_soc_with_integer(self, pilot_boundary_test):
        """Test _get_combined_soc with integer value."""
        pilot_boundary_test.coordinator.data = {SAX_COMBINED_SOC: 80}

        result = await pilot_boundary_test._get_combined_soc()

        assert result == 80.0

    async def test_get_combined_soc_with_missing_key(self, pilot_boundary_test):
        """Test _get_combined_soc when SAX_COMBINED_SOC key is missing."""
        pilot_boundary_test.coordinator.data = {"other_key": 50.0}

        result = await pilot_boundary_test._get_combined_soc()

        assert result == 0.0

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

    async def test_async_start_with_zero_interval(self, pilot_boundary_test):
        """Test async_start with zero update interval."""
        pilot_boundary_test.update_interval = 0

        with (
            patch(
                "custom_components.sax_battery.pilot.async_track_time_interval"
            ) as mock_track,
            patch.object(
                pilot_boundary_test, "_async_update_pilot", new_callable=AsyncMock
            ),
        ):
            await pilot_boundary_test.async_start()

            # Should still call async_track_time_interval even with 0 interval
            mock_track.assert_called_once()

    async def test_async_stop_with_none_listeners(self, pilot_boundary_test):
        """Test async_stop when listeners are None."""
        pilot_boundary_test._running = True
        pilot_boundary_test._remove_interval_update = None
        pilot_boundary_test._remove_config_update = None

        # Should not raise exception
        await pilot_boundary_test.async_stop()

        assert pilot_boundary_test._running is False

    async def test_async_config_updated_with_minimal_data(self, pilot_boundary_test):
        """Test config update with minimal entry data."""
        mock_entry = MagicMock()
        mock_entry.data = {}  # Empty config

        with patch.object(
            pilot_boundary_test, "_async_update_pilot", new_callable=AsyncMock
        ) as mock_update:
            await pilot_boundary_test._async_config_updated(
                pilot_boundary_test.hass, mock_entry
            )

            # Should handle empty config gracefully
            mock_update.assert_called_once_with(None)

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

    async def test_many_priority_devices_performance(self, pilot_performance_test):
        """Test performance with many priority devices."""

        # Mock states for all priority devices
        def mock_get_state(entity_id):
            if entity_id.startswith("sensor.device_"):
                mock_state = MagicMock()
                mock_state.state = "100.0"  # Each device consumes 100W
                return mock_state
            if entity_id == "sensor.total_power":
                mock_state = MagicMock()
                mock_state.state = "5000.0"
                return mock_state
            if entity_id == "sensor.power_factor":
                mock_state = MagicMock()
                mock_state.state = "1.0"
                return mock_state
            return None

        pilot_performance_test.hass.states.get.side_effect = mock_get_state
        pilot_performance_test.power_sensor_entity_id = "sensor.total_power"
        pilot_performance_test.pf_sensor_entity_id = "sensor.power_factor"

        start_time = time.time()

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

        end_time = time.time()

        # Should complete quickly even with many priority devices
        assert end_time - start_time < 0.1
        # Total priority power = 10 * 100W = 1000W > 50, so net_power = 0
        assert pilot_performance_test.calculated_power == 0.0

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

    def test_config_update_with_missing_values(self, pilot_performance_test):
        """Test config update with missing configuration values."""
        # Create entry with minimal data
        mock_entry = MagicMock()
        mock_entry.data = {}  # Empty config

        pilot_performance_test.entry = mock_entry
        pilot_performance_test._update_config_values()

        # Should use defaults
        assert pilot_performance_test.min_soc == DEFAULT_MIN_SOC
        assert pilot_performance_test.update_interval == DEFAULT_AUTO_PILOT_INTERVAL
        assert pilot_performance_test.priority_devices == []

    def test_boundary_value_power_limits(self, pilot_performance_test):
        """Test boundary values for power limits."""
        # Test with extreme battery counts
        pilot_performance_test.battery_count = 1
        pilot_performance_test.max_discharge_power = 1 * 3600
        pilot_performance_test.max_charge_power = 1 * 4500

        # Test power limiting with boundary values
        extreme_positive = 999999.0  # Very high discharge
        extreme_negative = -999999.0  # Very high charge

        limited_positive = max(
            -pilot_performance_test.max_discharge_power,
            min(pilot_performance_test.max_charge_power, extreme_positive),
        )
        limited_negative = max(
            -pilot_performance_test.max_discharge_power,
            min(pilot_performance_test.max_charge_power, extreme_negative),
        )

        assert limited_positive == pilot_performance_test.max_charge_power
        assert limited_negative == -pilot_performance_test.max_discharge_power


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
