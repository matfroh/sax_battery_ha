"""Test pilot power calculation logic."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.sax_battery.soc_manager import SOCConstraintResult


class TestPilotPowerCalculation:
    """Test basic power calculation scenarios."""

    async def test_power_calculation_with_priority_devices(
        self, pilot_with_full_config
    ):
        """Test power calculation with priority device consumption."""

        # Mock states with CORRECT entity IDs matching fixture config
        def mock_get_state(entity_id):
            state_map = {
                "sensor.total_power": self._create_state("2000.0"),
                "sensor.total_pf": self._create_state("0.95"),  # FIX: Use total_pf
                "sensor.priority_device_1": self._create_state("300.0"),
                "sensor.priority_device_2": self._create_state("200.0"),
                "sensor.sax_battery_combined_power": self._create_state("800.0"),
            }
            return state_map.get(entity_id)

        pilot_with_full_config.hass.states.get.side_effect = mock_get_state

        # Mock SOC manager
        mock_soc_result = SOCConstraintResult(
            allowed=True, original_value=0.0, constrained_value=0.0, reason=None
        )
        pilot_with_full_config.coordinator.soc_manager.apply_constraints = AsyncMock(
            return_value=mock_soc_result
        )

        with (
            patch.object(
                pilot_with_full_config, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_with_full_config, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
            patch.object(
                pilot_with_full_config, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_full_config._async_update_pilot(None)

            # Priority devices total = 500W > 50W threshold, net_power = 0
            assert pilot_with_full_config.calculated_power == 0.0
            mock_send.assert_called_once_with(0.0, 0.95)

    @staticmethod
    def _create_state(value: str) -> MagicMock:
        """Create mock state with value."""
        state = MagicMock()
        state.state = value
        return state


class TestPilotPowerLimits:
    """Test power limit enforcement."""

    async def test_discharge_power_limited(self, pilot_with_full_config):
        """Test discharge power is limited by max_discharge_power."""
        pilot_with_full_config.max_discharge_power = 500
        pilot_with_full_config.max_charge_power = 4500

        def mock_get_state(entity_id):
            state_map = {
                "sensor.total_power": self._create_state("0.0"),
                "sensor.total_pf": self._create_state("1.0"),  # FIX: Use total_pf
                "sensor.sax_battery_combined_power": self._create_state("-2000.0"),
            }
            return state_map.get(entity_id)

        pilot_with_full_config.hass.states.get.side_effect = mock_get_state

        # Mock SOC manager to allow the operation
        mock_soc_result = SOCConstraintResult(
            allowed=True, original_value=-500.0, constrained_value=-500.0, reason=None
        )
        pilot_with_full_config.coordinator.soc_manager.apply_constraints = AsyncMock(
            return_value=mock_soc_result
        )

        with (
            patch.object(
                pilot_with_full_config, "_get_combined_soc", return_value=50.0
            ),
            patch.object(
                pilot_with_full_config, "send_power_command", new_callable=AsyncMock
            ) as mock_send,
            patch.object(
                pilot_with_full_config, "get_solar_charging_enabled", return_value=True
            ),
        ):
            await pilot_with_full_config._async_update_pilot(None)

            # Limited by max_discharge_power
            assert pilot_with_full_config.calculated_power == -500.0
            mock_send.assert_called_once_with(-500.0, 1.0)

    @staticmethod
    def _create_state(value: str) -> MagicMock:
        """Create mock state with value."""
        state = MagicMock()
        state.state = value
        return state
