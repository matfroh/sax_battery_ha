"""Core pilot functionality tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_NOMINAL_POWER,
)


class TestSAXBatteryPilotCore:
    """Core pilot functionality tests."""

    def test_initialization(self, pilot_with_config_test):
        """Test pilot initialization."""
        assert pilot_with_config_test.battery_count == 1
        assert pilot_with_config_test.calculated_power == 0.0
        assert (
            pilot_with_config_test.max_discharge_power == LIMIT_MAX_CHARGE_PER_BATTERY
        )
        assert (
            pilot_with_config_test.max_charge_power == LIMIT_MAX_DISCHARGE_PER_BATTERY
        )

    async def test_async_start_success(self, pilot_with_config_test):
        """Test successful pilot start."""
        with (
            patch(
                "custom_components.sax_battery.pilot.async_track_time_interval"
            ) as mock_track,
            patch.object(
                pilot_with_config_test, "_async_update_pilot", new_callable=AsyncMock
            ) as mock_update,
        ):
            mock_track.return_value = MagicMock()
            await pilot_with_config_test.async_start()

            assert pilot_with_config_test._running is True
            mock_track.assert_called_once()
            mock_update.assert_called_once_with(None)

    async def test_async_stop_success(self, pilot_with_config_test):
        """Test successful pilot stop."""
        pilot_with_config_test._running = True
        pilot_with_config_test._remove_interval_update = MagicMock()
        pilot_with_config_test._remove_config_update = MagicMock()

        await pilot_with_config_test.async_stop()

        assert pilot_with_config_test._running is False

    async def test_get_combined_soc_valid_data(self, pilot_with_config_test):
        """Test getting combined SOC with valid data."""
        pilot_with_config_test.coordinator.data = {SAX_COMBINED_SOC: 85.5}
        result = await pilot_with_config_test._get_combined_soc()
        assert result == 85.5


class TestPilotConfiguration:
    """Test pilot configuration management."""

    async def test_async_config_updated(self, pilot_with_config_test):
        """Test config update handling."""
        mock_entry = MagicMock()
        mock_entry.data = {CONF_AUTO_PILOT_INTERVAL: 30}

        with patch.object(
            pilot_with_config_test, "_async_update_pilot", new_callable=AsyncMock
        ) as mock_update:
            await pilot_with_config_test._async_config_updated(
                pilot_with_config_test.hass, mock_entry
            )
            assert pilot_with_config_test.update_interval == 30
            mock_update.assert_called_once()

    def test_update_config_values_comprehensive(self, pilot_with_config_test):
        """Test comprehensive configuration update."""
        pilot_with_config_test.entry.data = {
            "power_sensor": "sensor.new_power",
            "pf_sensor": "sensor.new_pf",
            CONF_AUTO_PILOT_INTERVAL: 45,
        }
        pilot_with_config_test._update_config_values()

        assert pilot_with_config_test.update_interval == 45


class TestPilotPowerCommands:
    """Test pilot power command functionality."""

    async def test_send_power_command_success(self, pilot_with_config_test):
        """Test successful power command."""
        mock_item = MagicMock()
        mock_item.name = SAX_NOMINAL_POWER
        pilot_with_config_test.coordinator.async_write_pilot_control_value = AsyncMock(
            return_value=True
        )

        with patch.object(
            pilot_with_config_test, "_get_modbus_item_by_name", return_value=mock_item
        ):
            await pilot_with_config_test.send_power_command(500.0, 1.0)
            pilot_with_config_test.coordinator.async_write_pilot_control_value.assert_called_once()

    async def test_set_manual_power_with_constraints(self, pilot_with_config_test):
        """Test manual power with SOC constraints."""
        pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL] = True

        with (
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                new_callable=AsyncMock,
                return_value=0.0,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            await pilot_with_config_test.set_manual_power(500.0)
            mock_send.assert_called_once_with(0.0, 1.0)


class TestPilotPowerLimits:
    """Test power limit management."""

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_charge_power_limit_success(self, pilot_with_config_test):
        """Test setting charge power limit."""
        mock_item = MagicMock()
        mock_item.name = SAX_MAX_CHARGE

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
            ),
        ):
            result = await pilot_with_config_test.set_charge_power_limit(3000)
            assert result is True

    @pytest.mark.skip("set_charge_power_limit disabled ")
    async def test_set_discharge_power_limit_success(self, pilot_with_config_test):
        """Test setting discharge power limit."""
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
            ),
        ):
            result = await pilot_with_config_test.set_discharge_power_limit(2000)
            assert result is True


class TestPilotSensorHandling:
    """Test sensor state handling."""

    async def test_async_update_pilot_missing_power_sensor(
        self, pilot_with_config_test
    ):
        """Test missing power sensor handling."""
        pilot_with_config_test.power_sensor_entity_id = None
        await pilot_with_config_test._async_update_pilot(None)
        assert pilot_with_config_test.calculated_power == 0.0

    async def test_async_update_pilot_invalid_power_value(self, pilot_with_config_test):
        """Test invalid power sensor value."""
        mock_state = MagicMock()
        mock_state.state = "invalid_number"
        pilot_with_config_test.hass.states.get.return_value = mock_state

        await pilot_with_config_test._async_update_pilot(None)
        assert pilot_with_config_test.calculated_power == 0.0


class TestPilotManualMode:
    """Test manual mode functionality."""

    async def test_async_update_pilot_manual_mode_with_constraints(
        self, pilot_with_config_test
    ):
        """Test manual mode with SOC constraints."""
        pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL] = True
        pilot_with_config_test.calculated_power = 500.0

        with (
            patch.object(
                pilot_with_config_test,
                "_apply_soc_constraints",
                new_callable=AsyncMock,
                return_value=0.0,
            ),
            patch.object(
                pilot_with_config_test, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
        ):
            await pilot_with_config_test._async_update_pilot(None)
            mock_send.assert_called_once()


class TestPilotFeatureFlags:
    """Test feature flag behavior."""

    def test_get_solar_charging_enabled(self, pilot_with_config_test):
        """Test solar charging state."""
        pilot_with_config_test.entry.data[CONF_ENABLE_SOLAR_CHARGING] = True
        assert pilot_with_config_test.get_solar_charging_enabled() is True

    def test_get_manual_control_enabled(self, pilot_with_config_test):
        """Test manual control state."""
        pilot_with_config_test.entry.data[CONF_MANUAL_CONTROL] = True
        assert pilot_with_config_test.get_manual_control_enabled() is True


class TestPilotModbusItems:
    """Test ModbusItem handling."""

    async def test_get_modbus_item_by_name_found(self, pilot_with_config_test):
        """Test finding ModbusItem by name."""
        mock_item = MagicMock()
        mock_item.name = "test_item"
        pilot_with_config_test.sax_data.get_modbus_items_for_battery.return_value = [
            mock_item
        ]

        result = pilot_with_config_test._get_modbus_item_by_name("test_item")
        assert result == mock_item

    async def test_get_modbus_item_by_name_not_found(self, pilot_with_config_test):
        """Test ModbusItem not found."""
        pilot_with_config_test.sax_data.get_modbus_items_for_battery.return_value = []
        result = pilot_with_config_test._get_modbus_item_by_name("nonexistent")
        assert result is None
