"""Test pilot platform for SAX Battery integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DOMAIN,
    SAX_COMBINED_SOC,
)
from custom_components.sax_battery.pilot import (
    SAXBatteryPilot,
    SAXBatteryPilotPowerEntity,
    async_setup_entry,
)


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

            # Verify entities were added
            async_add_entities.assert_called_once()
            call_args = async_add_entities.call_args
            assert call_args.kwargs["update_before_add"] is True

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
        assert pilot_instance_test.max_discharge_power == 3600
        assert pilot_instance_test.max_charge_power == 4500
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
        mock_item.name = "sax_max_charge_power"

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


class TestSAXBatteryPilotPowerEntity:
    """Test SAXBatteryPilotPowerEntity class."""

    @pytest.fixture
    def power_entity_instance_test(self):
        """Create SAXBatteryPilotPowerEntity instance for testing."""
        mock_pilot = MagicMock()
        mock_pilot.calculated_power = 1500.0
        mock_pilot.max_discharge_power = 3600  # Match implementation values
        mock_pilot.max_charge_power = 4500

        mock_coordinator = MagicMock()
        mock_coordinator.data = {"pilot_power": 1500.0}
        mock_coordinator.sax_data = MagicMock()

        return SAXBatteryPilotPowerEntity(
            mock_pilot,
            mock_coordinator,
            "battery_a",
        )

    def test_device_info(self, power_entity_instance_test):
        """Test device info property."""
        expected_device_info = {"test": "info"}
        power_entity_instance_test.coordinator.sax_data.get_device_info.return_value = (
            expected_device_info
        )

        result = power_entity_instance_test.device_info

        assert result == expected_device_info
        power_entity_instance_test.coordinator.sax_data.get_device_info.assert_called_once_with(
            "battery_a"
        )

    def test_native_value(self, power_entity_instance_test):
        """Test native value property."""
        result = power_entity_instance_test.native_value

        assert result == 1500.0

    async def test_async_set_native_value(self, power_entity_instance_test):
        """Test setting native value."""
        # Mock the async method properly
        power_entity_instance_test._pilot.set_manual_power = AsyncMock()

        await power_entity_instance_test.async_set_native_value(2000.0)

        power_entity_instance_test._pilot.set_manual_power.assert_called_once_with(
            2000.0
        )

    def test_entity_properties(self, power_entity_instance_test):
        """Test entity properties are set correctly."""
        assert "Battery A" in power_entity_instance_test._attr_name
        assert power_entity_instance_test._attr_unique_id == "sax_battery_a_pilot_power"
        # Test with actual numeric values from implementation
        assert power_entity_instance_test._attr_native_min_value == -3600
        assert (
            power_entity_instance_test._attr_native_max_value == 4500
        )  # Match implementation
        assert (
            power_entity_instance_test._attr_native_step == 100
        )  # Match implementation value


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
        pilot_for_edge_test.sax_data.get_modbus_items_for_battery = MagicMock(
            return_value=[mock_item_without_name]
        )

        result = pilot_for_edge_test._get_modbus_item("test_item")

        assert result is None
