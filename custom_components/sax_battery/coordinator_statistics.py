"""SAX Battery coordinator statistics and monitoring.

Encapsulates error collection, error rate calculation, cycle time statistics,
and diagnostic logging. Extracted from coordinator.py to satisfy
the 1000-line file size limit (SRP / Ruff D103).

Performance:
    Uses lazy aggregation with generation-based cache invalidation.
    Statistics are computed on-demand only when underlying data changes,
    reducing per-cycle overhead by ~95% (Issue #43).

Security:
    OWASP A05: Performance monitoring and error tracking for anomaly detection
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import logging
from statistics import mean, stdev
from typing import TYPE_CHECKING, Any

from . import txid_error_tracker

if TYPE_CHECKING:
    from collections.abc import Callable

    from .circuit_breaker import CircuitBreaker
    from .modbusobject import OperationStatus

_LOGGER = logging.getLogger(__name__)


class CoordinatorStatistics:
    """Statistics and monitoring for SAX Battery coordinator.

    Encapsulates error collection, error rate calculation,
    cycle time statistics, and diagnostic logging.

    Uses composition pattern — instantiated by SAXBatteryCoordinator
    and given a reference to its CircuitBreaker for data access.

    Security:
        OWASP A05: Aggregated error metrics for monitoring and alerts
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        battery_id: str,
        last_cycle_duration_fn: Callable[[], float | None],
    ) -> None:
        """Initialize statistics tracker.

        Args:
            circuit_breaker: Circuit breaker instance for error/cycle data
            battery_id: Battery identifier for log messages
            last_cycle_duration_fn: Callable returning the last cycle duration

        Security:
            OWASP A05: Explicit dependencies prevent hidden state access
        """
        self._circuit_breaker = circuit_breaker
        self._battery_id = battery_id
        self._last_cycle_duration_fn = last_cycle_duration_fn

        # Lazy aggregation: generation-based cache invalidation (Issue #43)
        # Statistics are only recomputed when _data_generation > _cache_generation
        self._data_generation: int = 0
        self._cache_generation: int = -1  # Force initial computation
        self._cached_stats: dict[str, Any] = {}

        # BMS unavailability tracking: sliding-window deque (500 covers ~2h at 15s interval)
        self._bms_unavailability_history: deque[datetime] = deque(maxlen=500)

    def mark_dirty(self) -> None:
        """Mark statistics cache as dirty, forcing recomputation on next access.

        Call this when underlying data changes (cycle time recorded, etc.).

        Performance:
            O(1) operation - just increments a counter (Issue #43)
        """
        self._data_generation += 1

    def collect_modbus_error(self, status: OperationStatus) -> None:
        """Collect error from last ModbusAPI operation for statistics.

        Args:
            status: Last operation status from ModbusAPI

        Security:
            OWASP A05: Aggregates errors for monitoring (not circuit breaker)
        """
        if not status.success and status.error_type:
            # Include all 3 tuple elements (timestamp, error_type, register_address)
            self._circuit_breaker.error_history.append(
                (
                    status.timestamp or datetime.now(),
                    status.error_type,
                    status.register_address,  # Include register_address (can be None)
                )
            )
            self._data_generation += 1  # Invalidate cache

    def calculate_errors_per_hour(self) -> float:
        """Calculate error rate from collected history with time-based decay.

        Returns:
            Number of errors that occurred in the last 60 minutes

        Security:
            OWASP A05: Time-windowed error tracking prevents unbounded growth
        """
        if not self._circuit_breaker.error_history:
            return 0.0

        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Only count errors within last hour (automatic decay)
        recent_error_count = sum(
            1
            for timestamp, _, _ in self._circuit_breaker.error_history
            if timestamp >= one_hour_ago
        )

        # Clean up old errors beyond 1 hour to prevent unbounded growth
        # This ensures the deque doesn't fill with ancient errors
        cutoff_time = now - timedelta(hours=2)  # Keep 2 hours for safety margin
        while (
            self._circuit_breaker.error_history
            and self._circuit_breaker.error_history[0][0] < cutoff_time
        ):
            self._circuit_breaker.error_history.popleft()

        return float(recent_error_count)

    def collect_bms_unavailability(self, timestamp: datetime | None = None) -> None:
        """Record one BMS unavailability event (SAX_STATUS absent after a successful poll).

        Args:
            timestamp: When the unavailability was detected; defaults to now

        Security:
            OWASP A05: Tracks entity-level unavailability for anomaly detection
        """
        self._bms_unavailability_history.append(timestamp or datetime.now())
        self._data_generation += 1  # Invalidate cache

    def calculate_txid_errors_per_hour(self) -> float:
        """Return the transaction-ID error rate from the process-wide handler.

        Delegates to txid_error_tracker.get_errors_per_hour() which reads from
        the logging handler attached to the pymodbus logger.

        Returns:
            Number of transaction-ID mismatch errors in the last hour.
            Returns 0.0 when the handler is not set up (e.g., in unit tests).

        Security:
            OWASP A05: Exposes firmware anomaly rate for monitoring
        """
        return txid_error_tracker.get_errors_per_hour()

    def calculate_bms_unavailability_per_hour(self) -> float:
        """Count BMS unavailability events in the last 60-minute rolling window.

        Returns:
            Number of unavailability events that occurred in the last hour

        Performance:
            Prunes entries older than 2 hours to prevent unbounded growth
        Security:
            OWASP A05: Time-windowed tracking prevents unbounded memory usage
        """
        if not self._bms_unavailability_history:
            return 0.0

        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        recent_count = sum(
            1 for ts in self._bms_unavailability_history if ts >= one_hour_ago
        )

        # Prune entries older than 2 hours to keep memory bounded
        cutoff_time = now - timedelta(hours=2)
        while (
            self._bms_unavailability_history
            and self._bms_unavailability_history[0] < cutoff_time
        ):
            self._bms_unavailability_history.popleft()

        return float(recent_count)

    def log_cycle_statistics(self) -> None:
        """Log coordinator cycle time statistics.

        Uses cached statistics to avoid redundant computation.

        Logs:
        - Average cycle time
        - Min/Max cycle times
        - Standard deviation
        - Errors per hour (instead of failure rate percentage)

        Performance:
            Reuses cached stats from cycle_time_statistics property (Issue #43)
        Security:
            OWASP A05: Performance monitoring for anomaly detection
        """
        if not self._circuit_breaker.cycle_times:
            return

        # Reuse cached statistics instead of recomputing
        stats = self.cycle_time_statistics

        _LOGGER.info(
            "%s: Cycle stats (n=%d): avg=%.2fs, min=%.2fs, max=%.2fs, "
            "stddev=%.2fs, errors/hr=%.1f, circuit_breaker=%s",
            self._battery_id,
            len(self._circuit_breaker.cycle_times),
            stats["average"],
            stats["min"],
            stats["max"],
            stats["stddev"],
            stats["errors_per_hour"],
            "OPEN" if self._circuit_breaker.is_open else "CLOSED",
        )
        # Log detailed error breakdown
        self.log_error_statistics()

    def log_error_statistics(self) -> None:
        """Log detailed error statistics for diagnostics.

        Uses time-filtered error breakdown (last hour) for logging.
        This method runs only every ~240 cycles so full iteration is acceptable.

        Performance:
            Called infrequently (~once per hour). Time-filtered view
            is intentionally different from cached total counts (Issue #43).
        Security:
            OWASP A05: Structured error logging for monitoring and alerts
        """
        if not self._circuit_breaker.error_history:
            return

        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Time-filtered error breakdown for logging (last hour only)
        error_counts: dict[str, int] = {}
        register_errors: dict[int, int] = {}

        for (
            timestamp,
            error_type,
            register_address,
        ) in self._circuit_breaker.error_history:
            # Only count errors in last hour
            if timestamp < one_hour_ago:
                continue

            # Count by error type
            if error_type:
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

            # Count by register address
            if register_address is not None:
                register_errors[register_address] = (
                    register_errors.get(register_address, 0) + 1
                )

        # Log error breakdown for diagnostics
        total_errors = sum(error_counts.values())
        if total_errors > 0:
            # Format error counts for logging
            error_breakdown = ", ".join(
                f"{error_type}: {count}"
                for error_type, count in sorted(error_counts.items())
            )

            _LOGGER.info(
                "%s: Error statistics (last hour): %d total errors - %s",
                self._battery_id,
                total_errors,
                error_breakdown,
            )

            # Log top 3 most affected registers
            if register_errors:
                top_registers = sorted(
                    register_errors.items(), key=lambda x: x[1], reverse=True
                )[:3]
                register_summary = ", ".join(
                    f"addr_{addr}: {count}" for addr, count in top_registers
                )
                _LOGGER.info(
                    "%s: Most affected registers: %s",
                    self._battery_id,
                    register_summary,
                )

    def _compute_error_breakdown(
        self,
    ) -> tuple[dict[str, int], dict[int, int]]:
        """Compute error type counts and failed register counts.

        Returns:
            Tuple of (error_counts_by_type, failed_registers_by_address)

        Performance:
            Centralized computation, called once per cache refresh (Issue #43)
        """
        error_counts: dict[str, int] = {}
        failed_registers: dict[int, int] = {}

        for _, error_type, register_address in self._circuit_breaker.error_history:
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
            if register_address is not None:
                failed_registers[register_address] = (
                    failed_registers.get(register_address, 0) + 1
                )

        return error_counts, failed_registers

    @property
    def cycle_time_statistics(self) -> dict[str, Any]:
        """Get cycle time and error statistics with lazy caching.

        Returns cached statistics if underlying data hasn't changed.
        Only recomputes when data_generation advances (new errors or
        cycle times recorded).

        Returns:
            Dictionary with performance metrics

        Performance:
            O(1) cache hit on most calls; full recomputation only when
            dirty. Reduces per-cycle overhead by ~95% (Issue #43)
        Security:
            OWASP A05: Exposes aggregated error metrics
        """
        # Return cached stats if data hasn't changed
        if self._cache_generation == self._data_generation:
            return self._cached_stats

        # Recompute statistics
        error_counts, failed_registers = self._compute_error_breakdown()

        if not self._circuit_breaker.cycle_times:
            self._cached_stats = {
                "average": 0.0,
                "min": 0.0,
                "max": 0.0,
                "stddev": 0.0,
                "last": 0.0,
                "errors_per_hour": self.calculate_errors_per_hour(),
                "bms_unavailability_per_hour": self.calculate_bms_unavailability_per_hour(),
                "txid_errors_per_hour": self.calculate_txid_errors_per_hour(),
                "circuit_breaker_open": 0.0,
                "modbus_errors": error_counts.get("modbus", 0),
                "network_errors": error_counts.get("network", 0),
                "timeout_errors": error_counts.get("timeout", 0),
                "failed_registers": failed_registers,
                "last_error_time": (
                    self._circuit_breaker.error_history[-1][0].isoformat()
                    if self._circuit_breaker.error_history
                    else None
                ),
            }
        else:
            self._cached_stats = {
            "average": mean(self._circuit_breaker.cycle_times),
            "min": min(self._circuit_breaker.cycle_times),
            "max": max(self._circuit_breaker.cycle_times),
            "stddev": (
                stdev(self._circuit_breaker.cycle_times)
                if len(self._circuit_breaker.cycle_times) > 1
                else 0.0
            ),
            "last": self._last_cycle_duration_fn() or 0.0,
            "errors_per_hour": self.calculate_errors_per_hour(),
                "bms_unavailability_per_hour": self.calculate_bms_unavailability_per_hour(),
                "txid_errors_per_hour": self.calculate_txid_errors_per_hour(),
            "circuit_breaker_open": (1.0 if self._circuit_breaker.is_open else 0.0),
            "modbus_errors": error_counts.get("modbus", 0),
            "network_errors": error_counts.get("network", 0),
            "timeout_errors": error_counts.get("timeout", 0),
            "failed_registers": failed_registers,
            "last_error_time": (
                self._circuit_breaker.error_history[-1][0].isoformat()
                if self._circuit_breaker.error_history
                else None
            ),
        }

        self._cache_generation = self._data_generation
        return self._cached_stats
