"""Tests for SOC manager."""

from unittest.mock import Mock

import pytest

from custom_components.sax_battery.const import SAX_COMBINED_SOC
from custom_components.sax_battery.soc_manager import SOCManager


@pytest.fixture
def mock_coordinator():
    """Create mock coordinator."""
    coordinator = Mock()
    coordinator.data = {SAX_COMBINED_SOC: 50.0}
    return coordinator


@pytest.fixture
def soc_manager(mock_coordinator):
    """Create SOC manager instance."""
    return SOCManager(
        coordinator=mock_coordinator,
        min_soc=20.0,
        enabled=True,
    )


class TestSOCManagerInitialization:
    """Test SOC manager initialization."""

    async def test_init_with_valid_values(self, mock_coordinator):
        """Test initialization with valid values."""
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=25.0,
            enabled=True,
        )

        assert manager.min_soc == 25.0
        assert manager.enabled is True

    async def test_init_clamps_min_soc_to_range(self, mock_coordinator):
        """Test min_soc is clamped to valid range."""
        # Test upper bound
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=150.0,
            enabled=True,
        )
        assert manager.min_soc == 100.0

        # Test lower bound
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=-10.0,
            enabled=True,
        )
        assert manager.min_soc == 0.0


class TestSOCConstraintChecks:
    """Test SOC constraint checking."""

    async def test_discharge_allowed_above_min_soc(self, soc_manager):
        """Test discharge allowed when SOC above minimum."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 50.0}

        result = await soc_manager.check_discharge_allowed(1000.0)

        assert result.allowed is True
        assert result.constrained_value == 1000.0

    async def test_discharge_blocked_below_min_soc(self, soc_manager):
        """Test discharge blocked when SOC below minimum."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        result = await soc_manager.check_discharge_allowed(1000.0)

        assert result.allowed is False
        assert result.constrained_value == 0.0
        assert "below minimum" in result.reason

    async def test_charge_allowed_below_max_soc(self, soc_manager):
        """Test charge allowed when SOC below maximum."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 80.0}

        result = await soc_manager.check_charge_allowed(-1000.0)

        assert result.allowed is True
        assert result.constrained_value == -1000.0

    async def test_charge_blocked_at_max_soc(self, soc_manager):
        """Test charge blocked when SOC at maximum."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 100.0}

        result = await soc_manager.check_charge_allowed(-1000.0)

        assert result.allowed is False
        assert result.constrained_value == 0.0
        assert "maximum" in result.reason


class TestSOCManagerDisabled:
    """Test SOC manager when disabled."""

    async def test_constraints_bypassed_when_disabled(self, mock_coordinator):
        """Test all constraints bypassed when disabled."""
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=20.0,
            enabled=False,
        )

        mock_coordinator.data = {SAX_COMBINED_SOC: 10.0}

        # Discharge should be allowed even below min SOC
        result = await manager.apply_constraints(1000.0)
        assert result.allowed is True
        assert result.constrained_value == 1000.0
