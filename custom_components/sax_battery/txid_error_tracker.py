"""Track pymodbus transaction-ID mismatch errors.

The SAX battery firmware has a bug: write_registers (FC 0x10) responses
return 0x00 in the high byte of the MBAP transaction identifier instead of
echoing the request's transaction ID. pymodbus detects this and logs:

  ERROR: request ask for transaction_id=X but got id=Y, Skipping.

This module intercepts those log records via a logging.Handler attached to
the pymodbus logger, maintains a rolling 1-hour counter, and exposes the
rate via get_errors_per_hour() for use in the txid_error_rate diagnostic
sensor.

The handler is a process-wide singleton because the pymodbus logger is also
process-wide — registering one handler is sufficient regardless of how many
battery coordinators are active.

Security:
    OWASP A05: Error tracking for firmware anomaly detection
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import logging

_TXID_ERROR_PATTERN = "request ask for transaction_id="
_LOGGER = logging.getLogger(__name__)

# Module-level singleton — one handler per HA process is sufficient.
_handler: TxidErrorHandler | None = None


class TxidErrorHandler(logging.Handler):
    """Logging handler that counts pymodbus transaction-ID mismatch events.

    Attaches to the 'pymodbus' logger and records a timestamp each time a
    transaction-ID mismatch message is emitted.  The rolling 1-hour count
    is exposed via errors_per_hour() for the diagnostic sensor.

    Security:
        OWASP A05: Bounded deque prevents unbounded memory growth
    """

    def __init__(self, maxlen: int = 500) -> None:
        """Initialize handler with a bounded timestamp buffer.

        Args:
            maxlen: Maximum number of timestamps to keep in memory.
                    At ~40 errors/hr this covers over 12 hours of history.
        """
        super().__init__()
        self._timestamps: deque[datetime] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        """Record the current time when a transaction-ID mismatch is logged."""
        if _TXID_ERROR_PATTERN in record.getMessage():
            self._timestamps.append(datetime.now())

    def errors_per_hour(self) -> float:
        """Count transaction-ID errors in the last 60-minute rolling window.

        Returns:
            Number of matching log records in the past hour.

        Performance:
            Prunes entries older than 2 hours to keep memory bounded.
        Security:
            OWASP A05: Time-windowed tracking prevents unbounded memory usage
        """
        if not self._timestamps:
            return 0.0

        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        count = sum(1 for ts in self._timestamps if ts >= one_hour_ago)

        # Prune entries older than 2 hours to keep the deque lean
        cutoff = now - timedelta(hours=2)
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

        return float(count)

    def total_errors(self) -> int:
        """Return the total number of errors recorded since handler setup."""
        return len(self._timestamps)


def setup_handler() -> TxidErrorHandler:
    """Create and attach the handler to the pymodbus logger (idempotent).

    Safe to call multiple times — the handler is registered at most once per
    HA process even if setup_entry is called for multiple config entries.

    Returns:
        The active TxidErrorHandler instance.

    Security:
        OWASP A05: Guard against duplicate handler registration
    """
    global _handler  # noqa: PLW0603
    if _handler is None:
        _handler = TxidErrorHandler()

    pymodbus_logger = logging.getLogger("pymodbus")
    if not any(isinstance(h, TxidErrorHandler) for h in pymodbus_logger.handlers):
        pymodbus_logger.addHandler(_handler)
        _LOGGER.debug("TxidErrorHandler registered on pymodbus logger")

    return _handler


def get_errors_per_hour() -> float:
    """Return the current transaction-ID error rate (errors in the last hour).

    Returns 0.0 when the handler has not yet been set up (e.g., in unit tests
    that do not call setup_handler()).
    """
    if _handler is None:
        return 0.0
    return _handler.errors_per_hour()


def get_total_errors() -> int:
    """Return the total number of transaction-ID errors recorded since setup.

    Returns 0 when the handler has not yet been set up.
    """
    if _handler is None:
        return 0
    return _handler.total_errors()
