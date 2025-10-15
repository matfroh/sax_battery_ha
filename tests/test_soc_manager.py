"""Tests for SOC manager."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.sax_battery.const import SAX_COMBINED_SOC
from custom_components.sax_battery.soc_manager import SOCConstraintResult, SOCManager


@pytest.fixture
def mock_coordinator():
    """Create mock coordinator."""
    coordinator = Mock()
    coordinator.data = {SAX_COMBINED_SOC: 50.0}
    coordinator.async_write_number_value = AsyncMock(return_value=True)
    coordinator.hass = Mock()

    # Mock config_entry with entry_id
    mock_entry = Mock()
    mock_entry.entry_id = "test_entry_123"
    coordinator.config_entry = mock_entry

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
        assert manager._last_enforced_soc is None

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


class TestSOCManagerProperties:
    """Test SOC manager property setters."""

    async def test_min_soc_setter_clamps_values(self, soc_manager):
        """Test min_soc setter clamps to valid range."""
        # Test upper bound
        soc_manager.min_soc = 150.0
        assert soc_manager.min_soc == 100.0

        # Test lower bound
        soc_manager.min_soc = -10.0
        assert soc_manager.min_soc == 0.0

        # Test valid value
        soc_manager.min_soc = 30.0
        assert soc_manager.min_soc == 30.0

    async def test_min_soc_setter_logs_increase(self, soc_manager):
        """Test min_soc setter logs when value increases."""
        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            soc_manager.min_soc = 25.0  # Increase from 20.0

            # Should log debug message about increase
            mock_logger.debug.assert_called()
            assert mock_logger.debug.call_count >= 2  # Update + enforcement trigger

    async def test_enabled_setter(self, soc_manager):
        """Test enabled property setter."""
        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            # Disable
            soc_manager.enabled = False
            assert soc_manager.enabled is False
            mock_logger.debug.assert_called_with("SOC constraints %s", "disabled")

            # Enable
            soc_manager.enabled = True
            assert soc_manager.enabled is True
            mock_logger.debug.assert_called_with("SOC constraints %s", "enabled")

    async def test_enabled_setter_converts_to_bool(self, soc_manager):
        """Test enabled setter converts values to bool."""
        soc_manager.enabled = 1
        assert soc_manager.enabled is True

        soc_manager.enabled = 0
        assert soc_manager.enabled is False


class TestGetCurrentSOC:
    """Test get_current_soc method."""

    async def test_get_soc_from_coordinator_data(self, soc_manager):
        """Test getting SOC from coordinator data."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 75.5}

        soc = await soc_manager.get_current_soc()

        assert soc == 75.5

    async def test_get_soc_with_no_coordinator_data(self, soc_manager):
        """Test returns 0.0 when coordinator data is None."""
        soc_manager.coordinator.data = None

        soc = await soc_manager.get_current_soc()

        assert soc == 0.0

    async def test_get_soc_with_missing_key(self, soc_manager):
        """Test returns 0 when SAX_COMBINED_SOC key missing."""
        soc_manager.coordinator.data = {}

        soc = await soc_manager.get_current_soc()

        assert soc == 0

    async def test_get_soc_with_invalid_value_type(self, soc_manager):
        """Test handles invalid SOC value types."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: "invalid"}

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            soc = await soc_manager.get_current_soc()

            assert soc == 0.0
            mock_logger.warning.assert_called_once()

    async def test_get_soc_with_none_value(self, soc_manager):
        """Test handles None SOC value."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: None}

        with patch("custom_components.sax_battery.soc_manager._LOGGER"):
            soc = await soc_manager.get_current_soc()

            assert soc == 0.0


class TestSOCConstraintChecks:
    """Test SOC constraint checking."""

    async def test_discharge_allowed_above_min_soc(self, soc_manager):
        """Test discharge allowed when SOC above minimum."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 50.0}

        result = await soc_manager.check_discharge_allowed(1000.0)

        assert result.allowed is True
        assert result.constrained_value == 1000.0
        assert result.reason is None

    async def test_discharge_blocked_below_min_soc(self, soc_manager):
        """Test discharge blocked when SOC below minimum."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        result = await soc_manager.check_discharge_allowed(1000.0)

        assert result.allowed is False
        assert result.constrained_value == 0.0
        assert "below minimum" in result.reason

    async def test_charge_not_blocked_below_min_soc(self, soc_manager):
        """Test charging allowed when SOC below minimum (negative power)."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        result = await soc_manager.check_discharge_allowed(-1000.0)

        assert result.allowed is True
        assert result.constrained_value == -1000.0

    async def test_discharge_attempts_hardware_enforcement(self, soc_manager):
        """Test discharge blocking attempts hardware enforcement."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        with patch.object(
            soc_manager,
            "check_and_enforce_discharge_limit",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await soc_manager.check_discharge_allowed(1000.0)

            assert result.allowed is False
            soc_manager.check_and_enforce_discharge_limit.assert_called_once()

    async def test_discharge_handles_enforcement_error(self, soc_manager):
        """Test discharge handles hardware enforcement errors gracefully."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        with patch.object(  # noqa: SIM117
            soc_manager,
            "check_and_enforce_discharge_limit",
            side_effect=RuntimeError("Test error"),
        ):
            with patch(
                "custom_components.sax_battery.soc_manager._LOGGER"
            ) as mock_logger:
                result = await soc_manager.check_discharge_allowed(1000.0)

                assert result.allowed is False
                mock_logger.debug.assert_called()


class TestApplyConstraints:
    """Test apply_constraints method."""

    async def test_apply_discharge_constraint(self, soc_manager):
        """Test applying discharge constraint."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        with patch.object(
            soc_manager,
            "check_and_enforce_discharge_limit",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await soc_manager.apply_constraints(1000.0)

            assert result.allowed is False
            assert result.constrained_value == 0.0
            assert "Discharge blocked" in result.reason

    async def test_apply_charge_constraint_at_max_soc(self, soc_manager):
        """Test charge blocked at 100% SOC."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 100.0}

        result = await soc_manager.apply_constraints(-1000.0)

        assert result.allowed is False
        assert result.constrained_value == 0.0
        assert "Charge blocked" in result.reason
        assert "maximum 100%" in result.reason

    async def test_apply_no_constraint_within_limits(self, soc_manager):
        """Test no constraint applied when within limits."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 50.0}

        result = await soc_manager.apply_constraints(1000.0)

        assert result.allowed is True
        assert result.constrained_value == 1000.0
        assert result.reason is None

    async def test_apply_constraints_logs_enforcement(self, soc_manager):
        """Test constraint application logs hardware enforcement."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        with patch.object(  # noqa: SIM117
            soc_manager,
            "check_and_enforce_discharge_limit",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "custom_components.sax_battery.soc_manager._LOGGER"
            ) as mock_logger:
                await soc_manager.apply_constraints(1000.0)

                # Should log constraint application with enforcement indicator
                info_calls = [str(call) for call in mock_logger.info.call_args_list]
                assert any("hardware enforced" in call for call in info_calls)


class TestCheckAndEnforceDischargeLimit:
    """Test check_and_enforce_discharge_limit method."""

    async def test_enforce_returns_false_if_disabled(self, soc_manager):
        """Test returns False when constraints disabled."""
        soc_manager.enabled = False

        result = await soc_manager.check_and_enforce_discharge_limit()

        assert result is False

    async def test_enforce_returns_false_if_no_config_entry(self, soc_manager):
        """Test returns False when config entry not available."""
        soc_manager.coordinator.config_entry = None

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            result = await soc_manager.check_and_enforce_discharge_limit()

            assert result is False
            mock_logger.error.assert_called_once()

    async def test_enforce_returns_false_if_soc_above_minimum(self, soc_manager):
        """Test returns False when SOC above minimum."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 50.0}

        result = await soc_manager.check_and_enforce_discharge_limit()

        assert result is False

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_writes_to_entity(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test successfully writes to max_discharge entity."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        # Mock unique_id generation
        mock_unique_id.return_value = "sax_max_discharge"

        # Mock entity registry
        mock_ent_reg = Mock()
        mock_ent_reg.async_get_entity_id.return_value = "number.battery_max_discharge"
        mock_reg.return_value = mock_ent_reg

        # Mock entity platform and entity
        mock_entity = Mock()
        mock_entity.entity_id = "number.battery_max_discharge"
        mock_entity.async_set_native_value = AsyncMock()

        mock_plat = Mock()
        mock_plat.entities = {mock_entity.entity_id: mock_entity}
        mock_platform.return_value = mock_plat

        result = await soc_manager.check_and_enforce_discharge_limit()

        assert result is True
        mock_entity.async_set_native_value.assert_called_once_with(0.0)
        assert soc_manager._last_enforced_soc == 15.0

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    async def test_enforce_handles_missing_entity(
        self, mock_reg, mock_unique_id, soc_manager
    ):
        """Test handles missing entity in registry."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        mock_unique_id.return_value = "sax_max_discharge"

        # Mock entity registry returning None (entity not found)
        mock_ent_reg = Mock()
        mock_ent_reg.async_get_entity_id.return_value = None
        mock_reg.return_value = mock_ent_reg

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            result = await soc_manager.check_and_enforce_discharge_limit()

            assert result is False
            mock_logger.error.assert_called()

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_handles_missing_platform(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test handles missing entity platform."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        mock_unique_id.return_value = "sax_max_discharge"
        mock_ent_reg = Mock()
        mock_ent_reg.async_get_entity_id.return_value = "number.battery_max_discharge"
        mock_reg.return_value = mock_ent_reg

        # Platform not available
        mock_platform.return_value = None

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            result = await soc_manager.check_and_enforce_discharge_limit()

            assert result is False
            mock_logger.error.assert_called()

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_handles_entity_not_in_platform(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test handles entity not found in platform entities."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        mock_unique_id.return_value = "sax_max_discharge"
        mock_ent_reg = Mock()
        mock_ent_reg.async_get_entity_id.return_value = "number.battery_max_discharge"
        mock_reg.return_value = mock_ent_reg

        # Platform exists but entity not in entities dict
        mock_plat = Mock()
        mock_plat.entities = {}
        mock_platform.return_value = mock_plat

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            result = await soc_manager.check_and_enforce_discharge_limit()

            assert result is False
            mock_logger.error.assert_called()

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_handles_entity_without_set_method(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test handles entity without async_set_native_value method."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        mock_unique_id.return_value = "sax_max_discharge"
        mock_ent_reg = Mock()
        mock_ent_reg.async_get_entity_id.return_value = "number.battery_max_discharge"
        mock_reg.return_value = mock_ent_reg

        # Entity without async_set_native_value
        mock_entity = Mock(spec=[])  # No methods
        mock_entity.entity_id = "number.battery_max_discharge"

        mock_plat = Mock()
        mock_plat.entities = {mock_entity.entity_id: mock_entity}
        mock_platform.return_value = mock_plat

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            result = await soc_manager.check_and_enforce_discharge_limit()

            assert result is False
            mock_logger.error.assert_called()

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_handles_write_exception(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test handles exception during entity write."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        mock_unique_id.return_value = "sax_max_discharge"
        mock_ent_reg = Mock()
        mock_ent_reg.async_get_entity_id.return_value = "number.battery_max_discharge"
        mock_reg.return_value = mock_ent_reg

        mock_entity = Mock()
        mock_entity.entity_id = "number.battery_max_discharge"
        mock_entity.async_set_native_value = AsyncMock(
            side_effect=Exception("Write failed")
        )

        mock_plat = Mock()
        mock_plat.entities = {mock_entity.entity_id: mock_entity}
        mock_platform.return_value = mock_plat

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            result = await soc_manager.check_and_enforce_discharge_limit()

            assert result is False
            mock_logger.error.assert_called()

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_uses_fallback_unique_id(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test uses fallback unique_id when primary returns None."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}

        # Primary unique_id returns None
        mock_unique_id.return_value = None

        mock_ent_reg = Mock()
        mock_ent_reg.async_get_entity_id.return_value = "number.battery_max_discharge"
        mock_reg.return_value = mock_ent_reg

        mock_entity = Mock()
        mock_entity.entity_id = "number.battery_max_discharge"
        mock_entity.async_set_native_value = AsyncMock()

        mock_plat = Mock()
        mock_plat.entities = {mock_entity.entity_id: mock_entity}
        mock_platform.return_value = mock_plat

        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should use fallback unique_id (removeprefix logic)
        assert result is True
        mock_ent_reg.async_get_entity_id.assert_called()

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_skips_redundant_writes(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test skips redundant writes when SOC hasn't changed."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 15.0}
        soc_manager._last_enforced_soc = 15.0  # Already enforced at this SOC

        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should skip enforcement
        assert result is False
        mock_unique_id.assert_not_called()

    @patch("custom_components.sax_battery.soc_manager.get_unique_id_for_item")
    @patch("custom_components.sax_battery.soc_manager.er.async_get")
    @patch(
        "custom_components.sax_battery.soc_manager.entity_platform.async_get_current_platform"
    )
    async def test_enforce_resets_on_soc_recovery(
        self, mock_platform, mock_reg, mock_unique_id, soc_manager
    ):
        """Test resets enforcement state when SOC recovers."""
        soc_manager._last_enforced_soc = 15.0  # Previously enforced
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 25.0}  # Now above minimum

        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            result = await soc_manager.check_and_enforce_discharge_limit()

            assert result is False
            assert soc_manager._last_enforced_soc is None
            mock_logger.info.assert_called()


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

    async def test_discharge_check_bypassed_when_disabled(self, mock_coordinator):
        """Test discharge check bypassed when disabled."""
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=20.0,
            enabled=False,
        )

        mock_coordinator.data = {SAX_COMBINED_SOC: 10.0}

        result = await manager.check_discharge_allowed(1000.0)
        assert result.allowed is True


class TestSOCConstraintResultDataclass:
    """Test SOCConstraintResult dataclass."""

    def test_dataclass_creation(self):
        """Test creating SOCConstraintResult instance."""
        result = SOCConstraintResult(
            allowed=False,
            constrained_value=0.0,
            reason="Test reason",
        )

        assert result.allowed is False
        assert result.constrained_value == 0.0
        assert result.reason == "Test reason"

    def test_dataclass_default_reason(self):
        """Test reason defaults to None."""
        result = SOCConstraintResult(
            allowed=True,
            constrained_value=1000.0,
        )

        assert result.reason is None
