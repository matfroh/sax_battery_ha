"""SOC constraint management for SAX Battery integration.

Security:
    OWASP A05: Implements resource protection to prevent battery damage

Performance:
    Efficient SOC checking with caching to minimize coordinator queries
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from .const import SAX_COMBINED_SOC

if TYPE_CHECKING:
    from .coordinator import SAXBatteryCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class SOCConstraintResult:
    """Result of SOC constraint check."""

    allowed: bool
    original_value: float
    constrained_value: float
    reason: str | None = None


class SOCManager:
    """Manager for SOC-based battery protection constraints."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        min_soc: float,
        enabled: bool = True,
    ) -> None:
        """Initialize SOC manager.

        Args:
            coordinator: Battery coordinator for SOC data access
            min_soc: Minimum allowed SOC percentage (0-100)
            enabled: Whether constraints are enabled

        Security:
            OWASP A05: Validates min_soc bounds to prevent misconfiguration
        """
        self.coordinator = coordinator
        self._min_soc = max(0.0, min(100.0, min_soc))  # Clamp to valid range
        self._enabled = enabled
        self._soc_cache: float | None = None

    @property
    def min_soc(self) -> float:
        """Get minimum SOC threshold."""
        return self._min_soc

    @min_soc.setter
    def min_soc(self, value: float) -> None:
        """Set minimum SOC threshold with validation."""
        self._min_soc = max(0.0, min(100.0, value))
        _LOGGER.debug("Min SOC updated to %s%%", self._min_soc)

    @property
    def enabled(self) -> bool:
        """Get constraint enabled state."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set constraint enabled state."""
        self._enabled = bool(value)
        _LOGGER.debug("SOC constraints %s", "enabled" if self._enabled else "disabled")

    async def get_current_soc(self) -> float:
        """Get current combined SOC from coordinator.

        Returns:
            Current SOC percentage (0-100)

        Performance:
            Uses coordinator data cache to avoid redundant queries
        """
        if not self.coordinator.data:
            return 0.0

        soc_value = self.coordinator.data.get(SAX_COMBINED_SOC, 0)
        try:
            return float(soc_value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid SOC value: %s", soc_value)
            return 0.0

    async def check_discharge_allowed(self, power_value: float) -> SOCConstraintResult:
        """Check if discharge is allowed at current SOC.

        Args:
            power_value: Proposed power value (positive = discharge)

        Returns:
            SOCConstraintResult with allowed status and reason

        Security:
            OWASP A05: Prevents battery over-discharge damage
        """
        if not self._enabled:
            return SOCConstraintResult(
                allowed=True,
                original_value=power_value,
                constrained_value=power_value,
            )

        current_soc = await self.get_current_soc()

        # Check discharge constraint (positive power = discharge)
        if power_value > 0 and current_soc < self._min_soc:
            _LOGGER.info(
                "Discharge blocked: SOC %s%% < min %s%%",
                current_soc,
                self._min_soc,
            )
            return SOCConstraintResult(
                allowed=False,
                original_value=power_value,
                constrained_value=0.0,
                reason=f"SOC {current_soc:.1f}% below minimum {self._min_soc:.1f}%",
            )

        return SOCConstraintResult(
            allowed=True,
            original_value=power_value,
            constrained_value=power_value,
        )

    async def check_charge_allowed(self, power_value: float) -> SOCConstraintResult:
        """Check if charge is allowed at current SOC.

        Args:
            power_value: Proposed power value (negative = charge)

        Returns:
            SOCConstraintResult with allowed status and reason

        Security:
            OWASP A05: Prevents battery overcharge damage
        """
        if not self._enabled:
            return SOCConstraintResult(
                allowed=True,
                original_value=power_value,
                constrained_value=power_value,
            )

        current_soc = await self.get_current_soc()

        # Check charge constraint (negative power = charge)
        if power_value < 0 and current_soc >= 100.0:
            _LOGGER.info("Charge blocked: SOC at maximum 100%%")
            return SOCConstraintResult(
                allowed=False,
                original_value=power_value,
                constrained_value=0.0,
                reason="SOC at maximum 100%",
            )

        return SOCConstraintResult(
            allowed=True,
            original_value=power_value,
            constrained_value=power_value,
        )

    async def apply_constraints(self, power_value: float) -> SOCConstraintResult:
        """Apply all SOC constraints to a power value.

        Args:
            power_value: Proposed power value
                Positive = discharge
                Negative = charge

        Returns:
            SOCConstraintResult with constrained value

        Security:
            OWASP A05: Comprehensive battery protection

        Performance:
            Single SOC query for all constraint checks
        """
        if not self._enabled:
            return SOCConstraintResult(
                allowed=True,
                original_value=power_value,
                constrained_value=power_value,
            )

        current_soc = await self.get_current_soc()
        constrained_value = power_value
        reason = None

        # Check discharge constraint
        if power_value > 0 and current_soc < self._min_soc:
            constrained_value = 0.0
            reason = (
                f"Discharge blocked: SOC {current_soc:.1f}% < min {self._min_soc:.1f}%"
            )
            _LOGGER.info(reason)

        # Check charge constraint
        elif power_value < 0 and current_soc >= 100.0:
            constrained_value = 0.0
            reason = "Charge blocked: SOC at maximum 100%"
            _LOGGER.info(reason)

        if constrained_value != power_value:
            _LOGGER.info(
                "SOC constraint applied: %sW → %sW",
                power_value,
                constrained_value,
            )

        return SOCConstraintResult(
            allowed=(constrained_value == power_value),
            original_value=power_value,
            constrained_value=constrained_value,
            reason=reason,
        )
