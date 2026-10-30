"""Energy integration calculator for SAX Battery sensors.

Implements trapezoidal integration of power values to produce
accurate cumulative energy sensors, replacing the low-resolution
BMS smart meter register values.

The trapezoidal method matches the accuracy of Home Assistant's
built-in Riemann sum integration helper (platform: integration).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time

_LOGGER = logging.getLogger(__name__)

# Minimum interval between samples to avoid division issues (seconds)
MIN_SAMPLE_INTERVAL_S = 1.0
# Maximum gap between samples before we skip integration (seconds)
# Matches the old YAML config max_sub_interval: 1 minute + margin
MAX_SAMPLE_GAP_S = 120.0


@dataclass
class EnergyIntegrator:
    """Trapezoidal integrator for power-to-energy conversion.

    Accumulates energy (Wh) from instantaneous power readings (W)
    using the trapezoidal method, matching the accuracy of HA's
    built-in Riemann sum integration helper.

    Performance:
        O(1) per update - constant time regardless of history length.
    Security:
        OWASP A05: Validates inputs to prevent unbounded accumulation.
    """

    _accumulated_wh: float = 0.0
    _last_power_w: float | None = field(default=None, repr=False)
    _last_timestamp: float | None = field(default=None, repr=False)

    @property
    def accumulated_wh(self) -> float:
        """Return accumulated energy in Wh, rounded to 2 decimal places."""
        return round(self._accumulated_wh, 2)

    def add_sample(self, power_w: float, timestamp: float | None = None) -> float:
        """Add a power sample and return updated accumulated energy (Wh).

        Uses trapezoidal integration: energy = (P1 + P2) / 2 * dt

        Args:
            power_w: Instantaneous power in watts. Must be non-negative.
            timestamp: Monotonic timestamp in seconds. Uses time.monotonic() if None.

        Returns:
            Accumulated energy in Wh after this sample.

        Security:
            OWASP A03: Validates power_w to prevent negative energy accumulation.
        """
        if timestamp is None:
            timestamp = time.monotonic()

        # Validate input - power should be non-negative for consumption/production
        if power_w < 0:
            _LOGGER.debug(
                "Negative power value %s W clamped to 0 for energy integration",
                power_w,
            )
            power_w = 0.0

        if self._last_power_w is not None and self._last_timestamp is not None:
            dt_seconds = timestamp - self._last_timestamp

            if dt_seconds < MIN_SAMPLE_INTERVAL_S:
                # Skip duplicate/too-fast samples
                return self.accumulated_wh

            if dt_seconds > MAX_SAMPLE_GAP_S:
                # Gap too large - data unreliable, skip this interval
                _LOGGER.debug(
                    "Sample gap %.1fs exceeds max %.1fs, skipping interval",
                    dt_seconds,
                    MAX_SAMPLE_GAP_S,
                )
            else:
                # Trapezoidal integration: area = (P1 + P2) / 2 * dt_hours
                dt_hours = dt_seconds / 3600.0
                energy_wh = (self._last_power_w + power_w) / 2.0 * dt_hours
                self._accumulated_wh += energy_wh

        self._last_power_w = power_w
        self._last_timestamp = timestamp

        return self.accumulated_wh

    def restore(self, accumulated_wh: float) -> None:
        """Restore accumulated value after HA restart.

        Args:
            accumulated_wh: Previously accumulated energy in Wh.

        Security:
            OWASP A03: Validates restored value is non-negative.
        """
        if accumulated_wh < 0:
            _LOGGER.warning(
                "Attempted to restore negative energy value: %s Wh, using 0",
                accumulated_wh,
            )
            accumulated_wh = 0.0
        self._accumulated_wh = accumulated_wh

    def reset(self) -> None:
        """Reset the integrator state completely."""
        self._accumulated_wh = 0.0
        self._last_power_w = None
        self._last_timestamp = None
