"""Tests for circuit breaker pattern.

Security:
    OWASP A05: Validates circuit breaker prevents resource exhaustion
    from repeated connection attempts to unresponsive devices.
Performance:
    Verifies automatic recovery mechanism and cooldown enforcement.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.sax_battery.circuit_breaker import (
    CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CircuitBreaker,
    CircuitBreakerState,
)


class TestCircuitBreakerInit:
    """Test circuit breaker initialization."""

    def test_initial_state_is_closed(self) -> None:
        """Test circuit breaker starts in closed state.

        Security:
            OWASP A05: Default state allows normal operation
        """
        cb = CircuitBreaker(name="test_battery")

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False
        assert cb.consecutive_failures == 0
        assert cb.total_failures == 0
        assert cb.total_blocked == 0

    def test_custom_thresholds(self) -> None:
        """Test circuit breaker with custom thresholds."""
        cb = CircuitBreaker(
            name="test_battery",
            failure_threshold=5,
            cooldown_seconds=120,
        )

        assert cb._failure_threshold == 5
        assert cb._cooldown_seconds == 120

    def test_default_thresholds(self) -> None:
        """Test circuit breaker uses default thresholds."""
        cb = CircuitBreaker(name="test_battery")

        assert cb._failure_threshold == CIRCUIT_BREAKER_FAILURE_THRESHOLD
        assert cb._cooldown_seconds == CIRCUIT_BREAKER_COOLDOWN_SECONDS


class TestCircuitBreakerPreUpdateCheck:
    """Test pre-update check logic."""

    def test_closed_allows_request(self) -> None:
        """Test closed state allows requests.

        Performance:
            Normal operation path has minimal overhead
        """
        cb = CircuitBreaker(name="test_battery")

        assert cb.pre_update_check() is True

    def test_open_blocks_request_during_cooldown(self) -> None:
        """Test open state blocks requests during cooldown.

        Security:
            OWASP A05: Validates request blocking during cooldown
        """
        cb = CircuitBreaker(name="test_battery")
        # Force open state
        cb._state = CircuitBreakerState.OPEN
        cb._opened_at = datetime.now()

        assert cb.pre_update_check() is False
        assert cb.total_blocked == 1

    def test_open_transitions_to_half_open_after_cooldown(self) -> None:
        """Test open state transitions to half-open after cooldown.

        Performance:
            Enables automatic recovery after device becomes responsive
        """
        cb = CircuitBreaker(name="test_battery")
        cb._state = CircuitBreakerState.OPEN
        cb._opened_at = datetime.now() - timedelta(
            seconds=CIRCUIT_BREAKER_COOLDOWN_SECONDS + 1
        )

        assert cb.pre_update_check() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_allows_request(self) -> None:
        """Test half-open state allows test request."""
        cb = CircuitBreaker(name="test_battery")
        cb._state = CircuitBreakerState.HALF_OPEN

        assert cb.pre_update_check() is True

    def test_multiple_blocked_requests_counted(self) -> None:
        """Test blocked request counter increments correctly."""
        cb = CircuitBreaker(name="test_battery")
        cb._state = CircuitBreakerState.OPEN
        cb._opened_at = datetime.now()

        cb.pre_update_check()
        cb.pre_update_check()
        cb.pre_update_check()

        assert cb.total_blocked == 3


class TestCircuitBreakerRecordSuccess:
    """Test success recording."""

    def test_resets_failure_counter(self) -> None:
        """Test success resets consecutive failure counter."""
        cb = CircuitBreaker(name="test_battery")
        cb._consecutive_failures = 2

        cb.record_success()

        assert cb.consecutive_failures == 0
        assert cb.state == CircuitBreakerState.CLOSED

    def test_closes_circuit_from_half_open(self) -> None:
        """Test success in half-open state closes circuit.

        Performance:
            Confirms recovery and resumes normal polling
        """
        cb = CircuitBreaker(name="test_battery")
        cb._state = CircuitBreakerState.HALF_OPEN
        cb._consecutive_failures = 3
        cb._opened_at = datetime.now()

        cb.record_success()

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.is_closed is True
        assert cb.consecutive_failures == 0
        assert cb._opened_at is None

    def test_increments_success_counter(self) -> None:
        """Test success counter tracks total successes."""
        cb = CircuitBreaker(name="test_battery")

        cb.record_success()
        cb.record_success()

        assert cb.total_failures == 0
        assert cb._total_successes == 2

    def test_success_when_already_closed(self) -> None:
        """Test success in closed state is a no-op for state."""
        cb = CircuitBreaker(name="test_battery")

        cb.record_success()

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb._total_successes == 1


class TestCircuitBreakerRecordFailure:
    """Test failure recording."""

    def test_increments_failure_counter(self) -> None:
        """Test failure increments consecutive counter."""
        cb = CircuitBreaker(name="test_battery")
        error = OSError("Connection refused")

        cb.record_failure(error)

        assert cb.consecutive_failures == 1
        assert cb.total_failures == 1

    def test_opens_circuit_at_threshold(self) -> None:
        """Test circuit opens after threshold failures.

        Security:
            OWASP A05: Validates circuit breaker threshold enforcement
        """
        cb = CircuitBreaker(name="test_battery")

        for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure(OSError(f"Failure {i + 1}"))

        assert cb.state == CircuitBreakerState.OPEN
        assert cb.is_open is True
        assert cb.consecutive_failures == CIRCUIT_BREAKER_FAILURE_THRESHOLD
        assert cb._opened_at is not None

    def test_does_not_open_below_threshold(self) -> None:
        """Test circuit stays closed below threshold."""
        cb = CircuitBreaker(name="test_battery")

        for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1):
            cb.record_failure(OSError(f"Failure {i + 1}"))

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1

    def test_records_error_in_history(self) -> None:
        """Test error is recorded in history for diagnostics.

        Performance:
            Error history enables diagnostics without excessive logging
        """
        cb = CircuitBreaker(name="test_battery")
        error = OSError("Connection refused")

        cb.record_failure(error)

        assert len(cb.error_history) == 1
        timestamp, message, number = cb.error_history[0]
        assert isinstance(timestamp, datetime)
        assert number is None
        assert "OSError" in message
        assert "Connection refused" in message

    def test_reopens_circuit_on_continued_failures(self) -> None:
        """Test circuit stays open with fresh cooldown on more failures.

        Security:
            OWASP A05: Prevents premature recovery attempts
        """
        cb = CircuitBreaker(name="test_battery")

        # Open the circuit
        for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure(OSError(f"Failure {i + 1}"))

        assert cb.state == CircuitBreakerState.OPEN
        first_opened_at = cb._opened_at

        # Record more failures - should refresh cooldown
        cb.record_failure(OSError("Another failure"))

        assert cb.state == CircuitBreakerState.OPEN
        assert cb.consecutive_failures == CIRCUIT_BREAKER_FAILURE_THRESHOLD + 1
        assert cb._opened_at is not None
        assert cb._opened_at >= first_opened_at  # type: ignore[operator]

    def test_error_history_bounded(self) -> None:
        """Test error history does not grow unbounded.

        Performance:
            Bounded deque prevents memory leaks
        """
        cb = CircuitBreaker(name="test_battery", failure_threshold=1000)

        for i in range(100):
            cb.record_failure(OSError(f"Error {i}"))

        # Error history should be capped at ERROR_HISTORY_SIZE (50)
        assert len(cb.error_history) <= 50


class TestCircuitBreakerFullCycle:
    """Test complete circuit breaker lifecycle."""

    def test_closed_to_open_to_half_open_to_closed(self) -> None:
        """Test full lifecycle: closed → open → half-open → closed.

        Security:
            OWASP A05: Validates complete circuit breaker lifecycle
        Performance:
            Verifies automatic recovery mechanism works end-to-end
        """
        cb = CircuitBreaker(name="test_battery")

        # Phase 1: CLOSED → accumulate failures
        assert cb.state == CircuitBreakerState.CLOSED
        for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure(OSError(f"Failure {i + 1}"))

        # Phase 2: Verify OPEN
        assert cb.state == CircuitBreakerState.OPEN  # type: ignore[comparison-overlap]
        assert cb.pre_update_check() is False  # blocked

        # Phase 3: Simulate cooldown expiry → HALF_OPEN
        cb._opened_at = datetime.now() - timedelta(
            seconds=CIRCUIT_BREAKER_COOLDOWN_SECONDS + 1
        )
        assert cb.pre_update_check() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Phase 4: Success → CLOSED
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 0

    def test_half_open_failure_reopens_circuit(self) -> None:
        """Test failure in half-open state reopens circuit.

        Security:
            OWASP A05: Prevents premature recovery on continued failures
        """
        cb = CircuitBreaker(name="test_battery")

        # Open the circuit
        for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure(OSError(f"Failure {i + 1}"))

        # Simulate cooldown → half-open
        cb._opened_at = datetime.now() - timedelta(
            seconds=CIRCUIT_BREAKER_COOLDOWN_SECONDS + 1
        )
        cb.pre_update_check()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Failure in half-open → back to OPEN
        cb.record_failure(OSError("Still failing"))
        assert cb.state == CircuitBreakerState.OPEN  # type: ignore[comparison-overlap]
        assert cb.consecutive_failures == CIRCUIT_BREAKER_FAILURE_THRESHOLD + 1

    def test_intermittent_failures_reset_on_success(self) -> None:
        """Test intermittent failures don't accumulate across successes."""
        cb = CircuitBreaker(name="test_battery")

        # 2 failures (below threshold)
        cb.record_failure(OSError("Fail 1"))
        cb.record_failure(OSError("Fail 2"))
        assert cb.consecutive_failures == 2

        # Success resets counter
        cb.record_success()
        assert cb.consecutive_failures == 0

        # 2 more failures (still below threshold)
        cb.record_failure(OSError("Fail 3"))
        cb.record_failure(OSError("Fail 4"))
        assert cb.consecutive_failures == 2
        assert cb.state == CircuitBreakerState.CLOSED


class TestCircuitBreakerCycleTime:
    """Test cycle time tracking."""

    def test_records_cycle_time(self) -> None:
        """Test cycle time is recorded.

        Performance:
            Enables performance monitoring and diagnostics
        """
        cb = CircuitBreaker(name="test_battery")

        cb.record_cycle_time(0.5)
        cb.record_cycle_time(1.2)

        assert len(cb.cycle_times) == 2
        assert cb.cycle_times[0] == 0.5
        assert cb.cycle_times[1] == 1.2

    def test_cycle_time_bounded(self) -> None:
        """Test cycle time history does not grow unbounded.

        Performance:
            Bounded deque prevents memory leaks
        """
        cb = CircuitBreaker(name="test_battery")

        for i in range(200):
            cb.record_cycle_time(float(i))

        assert len(cb.cycle_times) <= 100


class TestCircuitBreakerCooldown:
    """Test cooldown tracking."""

    def test_cooldown_remaining_when_closed(self) -> None:
        """Test cooldown is 0 when circuit is closed."""
        cb = CircuitBreaker(name="test_battery")

        assert cb.cooldown_remaining == 0.0

    def test_cooldown_remaining_when_open(self) -> None:
        """Test cooldown remaining calculation when open."""
        cb = CircuitBreaker(name="test_battery", cooldown_seconds=60)
        cb._state = CircuitBreakerState.OPEN
        cb._opened_at = datetime.now() - timedelta(seconds=20)

        remaining = cb.cooldown_remaining
        # Should be approximately 40 seconds (allow for test execution time)
        assert 38.0 <= remaining <= 42.0

    def test_cooldown_remaining_after_expiry(self) -> None:
        """Test cooldown returns 0 after expiry."""
        cb = CircuitBreaker(name="test_battery", cooldown_seconds=60)
        cb._state = CircuitBreakerState.OPEN
        cb._opened_at = datetime.now() - timedelta(seconds=61)

        assert cb.cooldown_remaining == 0.0


class TestCircuitBreakerDiagnostics:
    """Test diagnostics output."""

    def test_diagnostics_closed_state(self) -> None:
        """Test diagnostics in closed state."""
        cb = CircuitBreaker(name="test_battery")

        diag = cb.get_diagnostics()

        assert diag["state"] == "closed"
        assert diag["consecutive_failures"] == 0
        assert diag["total_failures"] == 0
        assert diag["total_successes"] == 0
        assert diag["total_blocked"] == 0

    def test_diagnostics_open_state(self) -> None:
        """Test diagnostics in open state includes cooldown info."""
        cb = CircuitBreaker(name="test_battery")
        for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
            cb.record_failure(OSError(f"Error {i}"))

        diag = cb.get_diagnostics()

        assert diag["state"] == "open"
        assert diag["consecutive_failures"] == CIRCUIT_BREAKER_FAILURE_THRESHOLD
        assert "opened_at" in diag
        assert "cooldown_remaining" in diag
        assert "last_failure" in diag

    def test_diagnostics_with_cycle_times(self) -> None:
        """Test diagnostics includes cycle time statistics."""
        cb = CircuitBreaker(name="test_battery")
        cb.record_cycle_time(0.5)
        cb.record_cycle_time(1.5)

        diag = cb.get_diagnostics()

        assert diag["avg_cycle_time"] == 1.0
        assert diag["last_cycle_time"] == 1.5

    def test_diagnostics_with_errors(self) -> None:
        """Test diagnostics includes error count."""
        cb = CircuitBreaker(name="test_battery")
        cb.record_failure(OSError("Test error"))

        diag = cb.get_diagnostics()

        assert diag["recent_errors"] == 1
        assert diag["total_failures"] == 1
