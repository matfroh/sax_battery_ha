"""Test SOC constraint enforcement in pilot."""

from unittest.mock import AsyncMock, patch

from custom_components.sax_battery.soc_manager import SOCConstraintResult


class TestSOCConstraints:
    """Test SOC-based power constraints."""

    async def test_discharge_blocked_below_min_soc(self, pilot_with_config_test):
        """Test discharge is blocked when SOC below minimum."""
        mock_soc_result = SOCConstraintResult(
            allowed=False,
            original_value=500.0,
            constrained_value=0.0,
            reason="Discharge blocked: SOC 20.0% < min 15%",
        )

        pilot_with_config_test.coordinator.soc_manager.apply_constraints = AsyncMock(
            return_value=mock_soc_result
        )

        with patch.object(
            pilot_with_config_test, "_get_combined_soc", return_value=20.0
        ):
            result = await pilot_with_config_test._apply_soc_constraints(500.0)

            assert result == 0.0
            pilot_with_config_test.coordinator.soc_manager.apply_constraints.assert_called_once_with(
                500.0
            )

    async def test_charge_blocked_above_max_soc(self, pilot_with_config_test):
        """Test charge is blocked when SOC at maximum."""
        mock_soc_result = SOCConstraintResult(
            allowed=False,
            original_value=-500.0,
            constrained_value=0.0,
            reason="Charge blocked: SOC at maximum 100%",
        )

        pilot_with_config_test.coordinator.soc_manager.apply_constraints = AsyncMock(
            return_value=mock_soc_result
        )

        with patch.object(
            pilot_with_config_test, "_get_combined_soc", return_value=100.0
        ):
            result = await pilot_with_config_test._apply_soc_constraints(-500.0)

            assert result == 0.0

    async def test_power_allowed_within_soc_range(self, pilot_with_config_test):
        """Test power operation allowed when SOC in valid range."""
        mock_soc_result = SOCConstraintResult(
            allowed=True, original_value=300.0, constrained_value=300.0, reason=None
        )

        pilot_with_config_test.coordinator.soc_manager.apply_constraints = AsyncMock(
            return_value=mock_soc_result
        )

        with patch.object(
            pilot_with_config_test, "_get_combined_soc", return_value=50.0
        ):
            result = await pilot_with_config_test._apply_soc_constraints(300.0)

            assert result == 300.0
