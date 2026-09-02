"""Tests for EnergyIntegrator trapezoidal integration module."""

from __future__ import annotations

import math
import time
from unittest.mock import patch

import pytest

from custom_components.sax_battery.energy_integration import (
    MAX_SAMPLE_GAP_S,
    MIN_SAMPLE_INTERVAL_S,
    EnergyIntegrator,
)


class TestEnergyIntegratorBasic:
    """Test basic EnergyIntegrator functionality."""

    def test_initial_state(self) -> None:
        """Test integrator starts at zero."""
        integrator = EnergyIntegrator()
        assert integrator.accumulated_wh == 0.0

    def test_first_sample_no_accumulation(self) -> None:
        """Test first sample initializes but doesn't accumulate."""
        integrator = EnergyIntegrator()
        result = integrator.add_sample(1000.0, timestamp=100.0)
        assert result == 0.0

    def test_two_samples_trapezoidal(self) -> None:
        """Test trapezoidal integration with two samples.

        Power: 1000W constant for 60s = 1000 * 60/3600 ≈ 16.67 Wh
        """
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        result = integrator.add_sample(1000.0, timestamp=60.0)
        assert result == pytest.approx(16.67, abs=0.01)

    def test_trapezoidal_varying_power(self) -> None:
        """Test trapezoidal integration with varying power.

        P1=0W, P2=1000W, dt=60s → (0+1000)/2 * 60/3600 ≈ 8.33 Wh
        """
        integrator = EnergyIntegrator()
        integrator.add_sample(0.0, timestamp=0.0)
        result = integrator.add_sample(1000.0, timestamp=60.0)
        assert result == pytest.approx(8.33, abs=0.01)

    def test_accumulation_over_multiple_samples(self) -> None:
        """Test energy accumulates correctly over multiple samples.

        3 intervals of 15s each at 1000W constant:
        3 * (1000 * 15/3600) = 3 * 4.1667 = 12.5 Wh
        """
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        integrator.add_sample(1000.0, timestamp=15.0)
        integrator.add_sample(1000.0, timestamp=30.0)
        result = integrator.add_sample(1000.0, timestamp=45.0)
        # 3 intervals * 1000W * 15s / 3600 = 12.5 Wh
        assert result == 12.5

    def test_ramp_up_power(self) -> None:
        """Test trapezoidal integration during power ramp-up.

        0W -> 500W -> 1000W, each 60s apart
        Interval 1: (0+500)/2 * 60/3600 ≈ 4.17 Wh
        Interval 2: (500+1000)/2 * 60/3600 ≈ 12.5 Wh
        Total ≈ 16.67 Wh
        """
        integrator = EnergyIntegrator()
        integrator.add_sample(0.0, timestamp=0.0)
        integrator.add_sample(500.0, timestamp=60.0)
        result = integrator.add_sample(1000.0, timestamp=120.0)
        assert result == pytest.approx(16.67, abs=0.01)

    def test_short_interval_15_seconds(self) -> None:
        """Test typical coordinator poll interval of 15 seconds."""
        integrator = EnergyIntegrator()
        integrator.add_sample(3000.0, timestamp=0.0)
        result = integrator.add_sample(3000.0, timestamp=15.0)
        # 3000W * 15s / 3600s = 12.5 Wh
        assert result == 12.5


class TestEnergyIntegratorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_negative_power_clamped_to_zero(self) -> None:
        """Test negative power values are clamped to zero.

        Security: OWASP A03 - prevents negative energy accumulation.
        """
        integrator = EnergyIntegrator()
        integrator.add_sample(-500.0, timestamp=0.0)
        result = integrator.add_sample(-500.0, timestamp=3600.0)
        assert result == 0.0

    def test_zero_power(self) -> None:
        """Test zero power produces zero energy."""
        integrator = EnergyIntegrator()
        integrator.add_sample(0.0, timestamp=0.0)
        result = integrator.add_sample(0.0, timestamp=3600.0)
        assert result == 0.0

    def test_sample_gap_too_small_skipped(self) -> None:
        """Test samples closer than MIN_SAMPLE_INTERVAL_S are skipped."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        # Add sample too quickly (less than MIN_SAMPLE_INTERVAL_S)
        result = integrator.add_sample(1000.0, timestamp=0.5)
        assert result == 0.0  # No accumulation

    def test_sample_gap_exactly_min_interval(self) -> None:
        """Test samples at exactly MIN_SAMPLE_INTERVAL_S are accepted."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        result = integrator.add_sample(1000.0, timestamp=MIN_SAMPLE_INTERVAL_S)
        # 1000W * 1s / 3600 ≈ 0.28 Wh
        assert result > 0.0

    def test_sample_gap_too_large_skipped(self) -> None:
        """Test samples with gap > MAX_SAMPLE_GAP_S skip the interval."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        # Gap larger than MAX_SAMPLE_GAP_S
        result = integrator.add_sample(1000.0, timestamp=MAX_SAMPLE_GAP_S + 1)
        assert result == 0.0  # Interval skipped

    def test_sample_gap_at_max_boundary(self) -> None:
        """Test samples at exactly MAX_SAMPLE_GAP_S are still integrated."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        result = integrator.add_sample(1000.0, timestamp=MAX_SAMPLE_GAP_S)
        # Should integrate (boundary is inclusive)
        assert result > 0.0

    def test_recovery_after_large_gap(self) -> None:
        """Test integrator recovers normally after a large gap."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        integrator.add_sample(1000.0, timestamp=15.0)  # Normal: +4.17 Wh

        # Large gap - skipped
        integrator.add_sample(1000.0, timestamp=300.0)

        # Normal interval resumes
        result = integrator.add_sample(1000.0, timestamp=315.0)
        # First interval: 1000 * 15/3600 = 4.17 Wh
        # Gap skipped
        # Third interval: 1000 * 15/3600 = 4.17 Wh
        expected = round(1000.0 * 15.0 / 3600.0 * 2, 2)
        assert result == expected

    def test_default_timestamp_uses_monotonic(self) -> None:
        """Test that default timestamp uses time.monotonic()."""
        integrator = EnergyIntegrator()
        with patch.object(time, "monotonic", return_value=100.0):
            integrator.add_sample(1000.0)

        with patch.object(time, "monotonic", return_value=115.0):
            result = integrator.add_sample(1000.0)

        # 1000W * 15s / 3600 ≈ 4.17 Wh
        assert result == pytest.approx(4.17, abs=0.01)

    def test_very_small_power(self) -> None:
        """Test integration with very small power values."""
        integrator = EnergyIntegrator()
        integrator.add_sample(0.1, timestamp=0.0)
        result = integrator.add_sample(0.1, timestamp=60.0)
        # 0.1W * 60s / 3600 ≈ 0.0017 Wh → rounds to 0.0
        assert result == pytest.approx(0.0, abs=0.01)

    def test_very_large_power(self) -> None:
        """Test integration with large power values (full battery output)."""
        integrator = EnergyIntegrator()
        integrator.add_sample(5000.0, timestamp=0.0)
        result = integrator.add_sample(5000.0, timestamp=60.0)
        # 5000W * 60s / 3600 ≈ 83.33 Wh
        assert result == pytest.approx(83.33, abs=0.01)


class TestEnergyIntegratorRestore:
    """Test state restoration for HA restart persistence."""

    def test_restore_positive_value(self) -> None:
        """Test restoring a positive accumulated value."""
        integrator = EnergyIntegrator()
        integrator.restore(12345.67)
        assert integrator.accumulated_wh == 12345.67

    def test_restore_zero(self) -> None:
        """Test restoring zero value."""
        integrator = EnergyIntegrator()
        integrator.restore(0.0)
        assert integrator.accumulated_wh == 0.0

    def test_restore_negative_clamped_to_zero(self) -> None:
        """Test restoring negative value is clamped to zero.

        Security: OWASP A03 - prevents negative energy state.
        """
        integrator = EnergyIntegrator()
        integrator.restore(-100.0)
        assert integrator.accumulated_wh == 0.0

    def test_restore_then_accumulate(self) -> None:
        """Test accumulation continues correctly after restore."""
        integrator = EnergyIntegrator()
        integrator.restore(1000.0)

        # Now add samples: 500W for 60s = 500 * 60/3600 ≈ 8.33 Wh
        integrator.add_sample(500.0, timestamp=0.0)
        result = integrator.add_sample(500.0, timestamp=60.0)

        # 1000 (restored) + 8.33 (new) ≈ 1008.33 Wh
        assert result == pytest.approx(1008.33, abs=0.01)

    def test_restore_overwrites_existing(self) -> None:
        """Test restore overwrites any existing accumulated value."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        integrator.add_sample(1000.0, timestamp=60.0)
        # accumulated ≈ 16.67 Wh

        integrator.restore(5000.0)
        assert integrator.accumulated_wh == 5000.0


class TestEnergyIntegratorReset:
    """Test reset functionality."""

    def test_reset_clears_everything(self) -> None:
        """Test reset returns integrator to initial state."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        integrator.add_sample(1000.0, timestamp=60.0)

        integrator.reset()
        assert integrator.accumulated_wh == 0.0

    def test_accumulate_after_reset(self) -> None:
        """Test normal accumulation after reset."""
        integrator = EnergyIntegrator()
        integrator.add_sample(1000.0, timestamp=0.0)
        integrator.add_sample(1000.0, timestamp=60.0)

        integrator.reset()

        # New samples after reset: 2000W for 60s = 2000*60/3600 ≈ 33.33 Wh
        integrator.add_sample(2000.0, timestamp=120.0)
        result = integrator.add_sample(2000.0, timestamp=180.0)
        assert result == pytest.approx(33.33, abs=0.01)


class TestEnergyIntegratorAccuracyComparison:
    """Test accuracy compared to HA Riemann sum integration.

    These tests simulate the same scenarios that would be computed by
    the HA integration helper with method=trapezoidal.
    """

    def test_constant_power_long_duration(self) -> None:
        """Test constant power over 24 hours with 15s polling.

        Simulates a full day of battery at 1500W constant discharge.
        Expected: 1500W * 24h = 36000 Wh
        """
        integrator = EnergyIntegrator()
        power_w = 1500.0
        poll_interval = 15.0  # seconds
        duration_hours = 24
        num_samples = int(duration_hours * 3600 / poll_interval)

        for i in range(num_samples + 1):
            integrator.add_sample(power_w, timestamp=i * poll_interval)

        assert integrator.accumulated_wh == 36000.0

    def test_sinusoidal_power_profile(self) -> None:
        """Test with sinusoidal power profile (solar-like pattern).

        Simulates solar production: P(t) = 3000 * sin(pi * t / 12h)
        over 12 hours with 15s polling.
        Analytical integral = 3000 * 2 * 12 / pi ≈ 22918.31 Wh
        """

        integrator = EnergyIntegrator()
        poll_interval = 15.0  # seconds
        duration_s = 12 * 3600  # 12 hours in seconds
        num_samples = int(duration_s / poll_interval)

        for i in range(num_samples + 1):
            t = i * poll_interval
            power = 3000.0 * math.sin(math.pi * t / duration_s)
            power = max(power, 0.0)  # Clamp negative
            integrator.add_sample(power, timestamp=t)

        expected = 3000.0 * 2 * 12 / math.pi  # ≈ 22918.31 Wh
        # Trapezoidal with 15s intervals on a smooth curve is very accurate
        assert integrator.accumulated_wh == pytest.approx(expected, rel=0.001)

    def test_step_change_comparison(self) -> None:
        """Test step changes like battery switching on/off.

        0W for 1h, then 2000W for 1h with 15s polling.
        Expected: 0 + 2000 = 2000 Wh (approx, with trapezoidal ramp at transition)
        """
        integrator = EnergyIntegrator()
        poll_interval = 15.0

        # First hour: 0W
        num_zero = int(3600 / poll_interval)
        for i in range(num_zero):
            integrator.add_sample(0.0, timestamp=i * poll_interval)

        # Second hour: 2000W
        num_power = int(3600 / poll_interval)
        for i in range(num_power + 1):
            integrator.add_sample(2000.0, timestamp=3600.0 + i * poll_interval)

        # Trapezoidal ramp at transition: (0+2000)/2 * 15/3600 ≈ 4.17 Wh
        # Then 2000W for ~1h: 2000 * 3600/3600 = 2000 Wh
        # Minus the half interval at transition ≈ 2000 - 4.17 + 4.17 ≈ 2000
        # Actual: 0 for 1h + ramp + 2000W for (1h - 15s) + ramp ≈ 2000 Wh
        assert integrator.accumulated_wh == pytest.approx(2000.0, rel=0.01)
