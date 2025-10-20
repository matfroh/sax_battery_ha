"""Tests for SOC manager."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.sax_battery.const import SAX_COMBINED_SOC, SAX_MAX_DISCHARGE
from custom_components.sax_battery.soc_manager import SOCConstraintResult, SOCManager


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

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_writes_to_entity(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement writes to SAX_MAX_DISCHARGE entity.

        Security:
            OWASP A05: Validates proper constraint enforcement
        """
        # Setup low SOC condition
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8.0}

        # Mock ModbusItem for SAX_MAX_DISCHARGE
        mock_modbus_item = MagicMock()
        mock_modbus_item.item = MagicMock()
        soc_manager.coordinator.data[SAX_MAX_DISCHARGE] = mock_modbus_item

        # Mock entity registry to return valid entity_id
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id = MagicMock(
            return_value="number.sax_cluster_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Mock successful unique_id generation
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_cluster_max_discharge"
        )

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Verify successful enforcement
        assert result is True
        assert soc_manager._last_enforced_soc == 8.0

        # Verify service was called with correct parameters
        soc_manager.hass.services.async_call.assert_called_once_with(
            "number",
            "set_value",
            {
                "entity_id": "number.sax_cluster_max_discharge",
                "value": 0.0,
            },
            blocking=True,
        )

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_handles_service_failure(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement handles service call failures gracefully.

        Security:
            OWASP A05: Validates error handling
        """
        # Setup low SOC condition
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 5.0}

        # Mock ModbusItem
        mock_modbus_item = MagicMock()
        mock_modbus_item.item = MagicMock()
        soc_manager.coordinator.data[SAX_MAX_DISCHARGE] = mock_modbus_item

        # Mock successful registry lookups
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_cluster_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_cluster_max_discharge"
        )

        # Mock service call failure
        soc_manager.hass.services.async_call = AsyncMock(
            side_effect=Exception("Service call failed")
        )

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False on service failure
        assert result is False
        assert soc_manager._last_enforced_soc is None

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_skips_when_soc_above_minimum(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement skipped when SOC above minimum.

        Security:
            OWASP A05: Validates constraint logic
        """
        # Setup SOC above minimum
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 50.0}

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return True without calling service
        assert result is True
        assert soc_manager._last_enforced_soc is None

        # Verify service was NOT called
        soc_manager.hass.services.async_call.assert_not_called()

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_handles_missing_unique_id(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement handles missing unique_id gracefully.

        Security:
            OWASP A05: Validates proper error handling
        """
        # Setup low SOC condition
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8.0}

        # Mock ModbusItem
        mock_modbus_item = MagicMock()
        mock_modbus_item.item = MagicMock()
        soc_manager.coordinator.data[SAX_MAX_DISCHARGE] = mock_modbus_item

        # Mock unique_id generation failure
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = None

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False due to missing unique_id
        assert result is False

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_handles_missing_entity_id(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement handles missing entity_id gracefully.

        Security:
            OWASP A05: Validates proper error handling
        """
        # Setup low SOC condition
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8.0}

        # Mock ModbusItem
        mock_modbus_item = MagicMock()
        mock_modbus_item.item = MagicMock()
        soc_manager.coordinator.data[SAX_MAX_DISCHARGE] = mock_modbus_item

        # Mock successful unique_id but no entity_id
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_cluster_max_discharge"
        )

        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = None
        mock_entity_registry.return_value = mock_ent_reg

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False due to missing entity
        assert result is False

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_disabled_when_not_enabled(
        self,
        mock_entity_registry,
        mock_coordinator,
    ) -> None:
        """Test enforcement disabled when manager not enabled.

        Security:
            OWASP A05: Validates configuration control
        """
        # Create disabled manager
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=20.0,
            enabled=False,
        )

        # Setup low SOC condition
        manager.coordinator.data = {SAX_COMBINED_SOC: 5.0}

        # Execute enforcement
        result = await manager.check_and_enforce_discharge_limit()

        # Should return False without attempting enforcement
        assert result is False

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_handles_missing_config_entry(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement handles missing config entry.

        Security:
            OWASP A05: Validates proper error handling
        """
        # Setup low SOC condition
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 5.0}

        # Remove config entry
        soc_manager.coordinator.config_entry = None

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False due to missing config entry
        assert result is False

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_tracks_last_enforced_soc(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement tracks last enforced SOC value.

        Security:
            OWASP A05: Validates state tracking
        """
        # Setup low SOC condition
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 12.5}

        # Mock ModbusItem
        mock_modbus_item = MagicMock()
        mock_modbus_item.item = MagicMock()
        soc_manager.coordinator.data[SAX_MAX_DISCHARGE] = mock_modbus_item

        # Mock successful enforcement
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_cluster_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_cluster_max_discharge"
        )

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Verify SOC was tracked
        assert result is True
        assert soc_manager._last_enforced_soc == 12.5

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_handles_missing_modbus_item(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement handles missing ModbusItem gracefully.

        Security:
            OWASP A05: Validates proper error handling
        """
        # Setup low SOC condition with no ModbusItem
        soc_manager.coordinator.data = {
            SAX_COMBINED_SOC: 8.0,
            SAX_MAX_DISCHARGE: "not_a_modbus_item",  # Missing .item attribute
        }

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False due to missing ModbusItem
        assert result is False

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_handles_missing_sax_data(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement handles missing sax_data attribute.

        Security:
            OWASP A05: Validates proper error handling
        """
        # Setup low SOC condition
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8.0}

        # Mock ModbusItem
        mock_modbus_item = MagicMock()
        mock_modbus_item.item = MagicMock()
        soc_manager.coordinator.data[SAX_MAX_DISCHARGE] = mock_modbus_item

        # Remove sax_data attribute
        delattr(soc_manager.coordinator, "sax_data")

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False due to missing sax_data
        assert result is False


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
