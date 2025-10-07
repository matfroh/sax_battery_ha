"""Test pilot exception handling and error cases."""

from unittest.mock import AsyncMock, MagicMock, patch

from pymodbus.exceptions import ModbusException
import pytest

from custom_components.sax_battery.const import CONF_MIN_SOC
from custom_components.sax_battery.pilot import SAXBatteryPilot
from custom_components.sax_battery.soc_manager import SOCConstraintResult


class TestPilotErrorHandling:
    """Test pilot error handling for external failures."""

    async def test_modbus_exception_during_power_send(self, pilot_with_full_config):
        """Test ModbusException is handled gracefully during power send.

        Security:
            OWASP A05: Proper error handling prevents information leakage
        """
        # Mock SOC manager to allow the power command
        mock_soc_result = SOCConstraintResult(
            allowed=True, original_value=100.0, constrained_value=100.0, reason=None
        )
        pilot_with_full_config.coordinator.soc_manager.apply_constraints = AsyncMock(
            return_value=mock_soc_result
        )

        # Mock send_power_command to raise ModbusException
        original_send = pilot_with_full_config.send_power_command  # noqa: F841

        async def mock_send_with_exception(*args, **kwargs):
            raise ModbusException("Connection lost")

        pilot_with_full_config.send_power_command = mock_send_with_exception

        # Should catch exception and log error, not propagate
        try:
            await pilot_with_full_config.set_manual_power(100.0)
            # If we reach here, exception was handled (expected behavior)
        except ModbusException:
            pytest.fail("ModbusException should have been caught and handled")

    async def test_missing_sensor_graceful_handling(self, pilot_with_full_config):
        """Test missing sensor is handled without crash."""
        pilot_with_full_config.hass.states.get.return_value = None

        with (
            patch.object(
                pilot_with_full_config, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_with_full_config, "send_power_command", new_callable=AsyncMock
            ),
        ):
            # Should not raise exception, just log warning
            await pilot_with_full_config._async_update_pilot(None)

            # Verify calculated_power is 0 when sensors are missing
            assert pilot_with_full_config.calculated_power == 0.0


class TestPilotExceptionHandling:
    """Test exception handling in pilot module."""

    @pytest.fixture
    def pilot_for_exception_test(self, mock_hass, mock_sax_data):
        """Create pilot instance for exception testing."""
        mock_coordinator = MagicMock()
        mock_coordinator.data = None

        # Set up mock_sax_data with required attributes
        mock_sax_data.entry.data = {CONF_MIN_SOC: 20}
        mock_sax_data.device_name = "test_battery"
        mock_sax_data.battery_count = 1

        # Mock the coordinator's soc_manager
        mock_soc_manager = MagicMock()
        mock_coordinator.soc_manager = mock_soc_manager

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
