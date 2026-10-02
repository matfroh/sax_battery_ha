"""Test SAX Battery transaction-ID error tracker.

Validates that TxidErrorHandler correctly intercepts pymodbus
transaction-ID mismatch log records and reports rolling error rates.

Security:
    OWASP A05: Validates anomaly detection and bounded memory usage
"""

from __future__ import annotations

import collections.abc
from datetime import datetime, timedelta
import logging

import pytest

import custom_components.sax_battery.txid_error_tracker as tracker_module
from custom_components.sax_battery.txid_error_tracker import (
    TxidErrorHandler,
    get_errors_per_hour,
    get_total_errors,
    setup_handler,
)


@pytest.fixture(autouse=True)
def reset_singleton() -> collections.abc.Generator:
    """Reset module-level singleton before each test to avoid cross-test pollution."""
    tracker_module._handler = None
    pymodbus_logger = logging.getLogger("pymodbus")
    for h in list(pymodbus_logger.handlers):
        if isinstance(h, TxidErrorHandler):
            pymodbus_logger.removeHandler(h)
    yield
    tracker_module._handler = None
    for h in list(pymodbus_logger.handlers):
        if isinstance(h, TxidErrorHandler):
            pymodbus_logger.removeHandler(h)


class TestTxidErrorHandler:
    """Tests for TxidErrorHandler.emit() and errors_per_hour()."""

    def _make_record(self, message: str) -> logging.LogRecord:
        """Create a minimal LogRecord with the given message."""
        return logging.LogRecord(
            name="pymodbus",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )

    def test_emit_records_matching_message(self) -> None:
        """emit() should append a timestamp for matching log records."""
        handler = TxidErrorHandler()
        record = self._make_record(
            "request ask for transaction_id=1 but got id=0, Skipping."
        )
        handler.emit(record)

        assert len(handler._timestamps) == 1

    def test_emit_ignores_non_matching_message(self) -> None:
        """emit() should not record timestamps for unrelated log messages."""
        handler = TxidErrorHandler()
        record = self._make_record("Connected to device at 192.168.1.100:502")
        handler.emit(record)

        assert len(handler._timestamps) == 0

    def test_emit_records_multiple_matching_messages(self) -> None:
        """emit() should record each matching log record separately."""
        handler = TxidErrorHandler()
        for i in range(5):
            record = self._make_record(
                f"request ask for transaction_id={i} but got id=0, Skipping."
            )
            handler.emit(record)

        assert len(handler._timestamps) == 5

    def test_errors_per_hour_returns_zero_when_empty(self) -> None:
        """errors_per_hour() returns 0.0 when no errors recorded."""
        handler = TxidErrorHandler()
        assert handler.errors_per_hour() == 0.0

    def test_errors_per_hour_counts_recent_errors(self) -> None:
        """errors_per_hour() counts timestamps within the last 60 minutes."""
        handler = TxidErrorHandler()
        now = datetime.now()
        # Add 10 timestamps within the last hour
        for i in range(10):
            handler._timestamps.append(now - timedelta(minutes=i * 5))

        assert handler.errors_per_hour() == 10.0

    def test_errors_per_hour_excludes_old_errors(self) -> None:
        """errors_per_hour() excludes timestamps older than 60 minutes."""
        handler = TxidErrorHandler()
        now = datetime.now()
        handler._timestamps.append(now - timedelta(minutes=30))  # Recent
        handler._timestamps.append(now - timedelta(minutes=61))  # Too old

        assert handler.errors_per_hour() == 1.0

    def test_errors_per_hour_prunes_beyond_two_hours(self) -> None:
        """errors_per_hour() prunes entries older than 2 hours from deque."""
        handler = TxidErrorHandler()
        now = datetime.now()
        # Add entries spanning 3 hours ago to 30 minutes ago
        handler._timestamps.append(now - timedelta(hours=3))  # Will be pruned
        handler._timestamps.append(now - timedelta(hours=2, minutes=1))  # Pruned
        handler._timestamps.append(now - timedelta(hours=1, minutes=30))  # Old but kept
        handler._timestamps.append(now - timedelta(minutes=30))  # Recent

        result = handler.errors_per_hour()

        # Only the most recent entry (30 min ago) is within the last hour
        assert result == 1.0
        # Entries older than 2 hours should have been pruned
        assert all(ts >= now - timedelta(hours=2) for ts in handler._timestamps)

    def test_total_errors_reflects_deque_size(self) -> None:
        """total_errors() returns the number of items in the timestamp deque."""
        handler = TxidErrorHandler()
        now = datetime.now()
        for i in range(7):
            handler._timestamps.append(now - timedelta(minutes=i))

        assert handler.total_errors() == 7

    def test_maxlen_bounded_deque(self) -> None:
        """Handler respects maxlen bound to prevent unbounded memory growth."""
        handler = TxidErrorHandler(maxlen=5)
        now = datetime.now()
        for i in range(10):
            handler._timestamps.append(now - timedelta(minutes=i))

        assert len(handler._timestamps) == 5


class TestSetupHandler:
    """Tests for the setup_handler() module function."""

    def test_setup_handler_creates_handler(self) -> None:
        """setup_handler() creates and returns a TxidErrorHandler."""
        result = setup_handler()

        assert isinstance(result, TxidErrorHandler)
        assert tracker_module._handler is result

    def test_setup_handler_registers_on_pymodbus_logger(self) -> None:
        """setup_handler() attaches handler to the pymodbus logger."""
        setup_handler()
        pymodbus_logger = logging.getLogger("pymodbus")

        assert any(isinstance(h, TxidErrorHandler) for h in pymodbus_logger.handlers)

    def test_setup_handler_is_idempotent_singleton(self) -> None:
        """setup_handler() called twice returns the same handler instance."""
        h1 = setup_handler()
        h2 = setup_handler()

        assert h1 is h2

    def test_setup_handler_does_not_register_twice(self) -> None:
        """setup_handler() called twice does not double-register the handler."""
        setup_handler()
        setup_handler()
        pymodbus_logger = logging.getLogger("pymodbus")

        txid_handlers = [
            h for h in pymodbus_logger.handlers if isinstance(h, TxidErrorHandler)
        ]
        assert len(txid_handlers) == 1


class TestModuleLevelFunctions:
    """Tests for get_errors_per_hour() and get_total_errors() module functions."""

    def test_get_errors_per_hour_returns_zero_without_setup(self) -> None:
        """get_errors_per_hour() returns 0.0 when handler not set up."""
        assert get_errors_per_hour() == 0.0

    def test_get_total_errors_returns_zero_without_setup(self) -> None:
        """get_total_errors() returns 0 when handler not set up."""
        assert get_total_errors() == 0

    def test_get_errors_per_hour_after_setup(self) -> None:
        """get_errors_per_hour() delegates to handler after setup."""
        handler = setup_handler()
        handler._timestamps.append(datetime.now() - timedelta(minutes=10))
        handler._timestamps.append(datetime.now() - timedelta(minutes=20))

        assert get_errors_per_hour() == 2.0

    def test_get_total_errors_after_setup(self) -> None:
        """get_total_errors() delegates to handler after setup."""
        handler = setup_handler()
        handler._timestamps.append(datetime.now() - timedelta(minutes=10))

        assert get_total_errors() == 1
