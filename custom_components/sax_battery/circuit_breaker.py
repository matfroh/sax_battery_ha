"""Circuit breaker pattern for SAX Battery Modbus communication.

Security:
    OWASP A05: Prevents resource exhaustion from repeated connection attempts
    to unresponsive devices by implementing the circuit breaker pattern.

Performance:
    Stops polling unresponsive devices, reducing wasted I/O and CPU cycles.
    Automatic recovery via half-open state after cooldown period.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from enum import Enum
import logging

_LOGGER = logging.getLogger(__name__)

# Circuit breaker thresholds
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 60

# Error history size for diagnostics
ERROR_HISTORY_SIZE = 50


class CircuitBreakerState(Enum):
    """Circuit breaker states.

    Security:
        OWASP A05: Explicit state machine prevents ambiguous failure handling
    """

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Cooldown expired, allowing one test request


class CircuitBreaker:
    """Circuit breaker for Modbus communication protection.

    Prevents repeated connection attempts to unresponsive SAX battery devices.
    Implements standard circuit breaker pattern with three states:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Requests blocked after consecutive failures exceed threshold
    - HALF_OPEN: After cooldown, allows one test request to check recovery

    Security:
        OWASP A05: Resource exhaustion protection
    Performance:
        Eliminates wasted polling cycles to unresponsive devices
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        cooldown_seconds: int = CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            name: Identifier for logging (e.g., battery_id)
            failure_threshold: Number of consecutive failures before opening
            cooldown_seconds: Seconds to wait before attempting half-open
        """
        self._name = name
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds

        # State tracking
        self._state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._last_failure_time: datetime | None = None
        self._opened_at: datetime | None = None

        # Statistics
        self._total_failures: int = 0
        self._total_successes: int = 0
        self._total_blocked: int = 0
        self._error_history: deque[tuple[datetime, str, int | None]] = deque(
            maxlen=ERROR_HISTORY_SIZE
        )

        # Cycle time tracking
        self._cycle_times: deque[float] = deque(maxlen=100)

    @property
    def state(self) -> CircuitBreakerState:
        """Return current circuit breaker state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Return True if circuit breaker is open (blocking requests)."""
        return self._state == CircuitBreakerState.OPEN

    @property
    def is_closed(self) -> bool:
        """Return True if circuit breaker is closed (allowing requests)."""
        return self._state == CircuitBreakerState.CLOSED

    @property
    def consecutive_failures(self) -> int:
        """Return number of consecutive failures."""
        return self._consecutive_failures

    @property
    def total_failures(self) -> int:
        """Return total number of failures recorded."""
        return self._total_failures

    @property
    def total_blocked(self) -> int:
        """Return total number of blocked requests."""
        return self._total_blocked

    @property
    def error_history(self) -> deque[tuple[datetime, str, int | None]]:
        """Return error history for diagnostics."""
        return self._error_history

    @property
    def cycle_times(self) -> deque[float]:
        """Return recorded cycle times for performance monitoring."""
        return self._cycle_times

    @property
    def cooldown_remaining(self) -> float:
        """Return remaining cooldown time in seconds, or 0 if not open."""
        if self._state != CircuitBreakerState.OPEN or self._opened_at is None:
            return 0.0
        elapsed = (datetime.now() - self._opened_at).total_seconds()
        remaining = self._cooldown_seconds - elapsed
        return max(0.0, remaining)

    def pre_update_check(self) -> bool:
        """Check if update should proceed.

        Returns:
            True if update should proceed, False if blocked by circuit breaker.

        Security:
            OWASP A05: Prevents requests to unresponsive devices
        Performance:
            Skips polling when device is known to be unresponsive
        """
        if self._state == CircuitBreakerState.CLOSED:
            return True

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Already in half-open, allow the test request
            return True

        # State is OPEN - check if cooldown has expired
        if self._opened_at is not None:
            elapsed = (datetime.now() - self._opened_at).total_seconds()
            if elapsed >= self._cooldown_seconds:
                # Transition to half-open
                self._state = CircuitBreakerState.HALF_OPEN
                _LOGGER.info(
                    "%s: Circuit breaker entering half-open state"
                    " (cooldown expired after %ds)",
                    self._name,
                    int(elapsed),
                )
                return True

        # Still in cooldown
        self._total_blocked += 1
        _LOGGER.debug(
            "%s: Circuit breaker blocking request (cooldown: %.0fs remaining)",
            self._name,
            self.cooldown_remaining,
        )
        return False

    def record_success(self) -> None:
        """Record a successful operation.

        Resets failure counter and closes circuit breaker if in half-open state.

        Performance:
            Enables automatic recovery after device becomes responsive
        """
        if self._consecutive_failures > 0:
            _LOGGER.info(
                "%s: Connection recovered after %d consecutive failures",
                self._name,
                self._consecutive_failures,
            )

        self._consecutive_failures = 0
        self._total_successes += 1

        if self._state != CircuitBreakerState.CLOSED:
            _LOGGER.info(
                "%s: Circuit breaker CLOSED (recovery confirmed)",
                self._name,
            )
            self._state = CircuitBreakerState.CLOSED
            self._opened_at = None
            self._last_failure_time = None

    def record_failure(self, error: Exception) -> None:
        """Record a failed operation.

        Increments failure counter and opens circuit breaker if threshold
        is reached.

        Args:
            error: The exception that caused the failure

        Security:
            OWASP A05: Opens circuit breaker to protect against resource
            exhaustion from repeated failures
        """
        self._consecutive_failures += 1
        self._total_failures += 1
        self._last_failure_time = datetime.now()

        # Record error in history for diagnostics
        self._error_history.append(
            (datetime.now(), f"{type(error).__name__}: {error}", None)
        )

        if self._consecutive_failures >= self._failure_threshold:
            if self._state != CircuitBreakerState.OPEN:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = datetime.now()
                _LOGGER.error(
                    "%s: Circuit breaker OPENED after %d consecutive"
                    " failures (cooldown: %ds). Last error: %s",
                    self._name,
                    self._consecutive_failures,
                    self._cooldown_seconds,
                    error,
                )
            else:
                # Already open, update timestamp for fresh cooldown
                self._opened_at = datetime.now()
                _LOGGER.warning(
                    "%s: Circuit breaker remains OPEN"
                    " (%d consecutive failures). Last error: %s",
                    self._name,
                    self._consecutive_failures,
                    error,
                )
        else:
            _LOGGER.warning(
                "%s: Update failed (%d/%d consecutive failures): %s",
                self._name,
                self._consecutive_failures,
                self._failure_threshold,
                error,
            )

    def record_cycle_time(self, duration: float) -> None:
        """Record cycle time for performance monitoring.

        Args:
            duration: Cycle duration in seconds

        Performance:
            Enables cycle time statistics and performance diagnostics
        """
        self._cycle_times.append(duration)

    def get_diagnostics(self) -> dict[str, object]:
        """Return diagnostic information for troubleshooting.

        Returns:
            Dictionary with circuit breaker state and statistics

        Performance:
            Provides performance metrics without excessive logging
        """
        diagnostics: dict[str, object] = {
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self._failure_threshold,
            "cooldown_seconds": self._cooldown_seconds,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "total_blocked": self._total_blocked,
            "recent_errors": len(self._error_history),
        }

        if self._opened_at is not None:
            diagnostics["opened_at"] = self._opened_at.isoformat()
            diagnostics["cooldown_remaining"] = self.cooldown_remaining

        if self._last_failure_time is not None:
            diagnostics["last_failure"] = self._last_failure_time.isoformat()

        if self._cycle_times:
            diagnostics["avg_cycle_time"] = sum(self._cycle_times) / len(
                self._cycle_times
            )
            diagnostics["last_cycle_time"] = self._cycle_times[-1]

        return diagnostics
