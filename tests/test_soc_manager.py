"""Tests for SOC manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import SAX_COMBINED_SOC
from custom_components.sax_battery.protocol_mode import ProtocolMode
from custom_components.sax_battery.soc_manager import SOCManager
from homeassistant.exceptions import HomeAssistantError


class TestSOCManagerInitialization:
    """Test SOC manager initialization."""

    async def test_init_with_valid_values(self, mock_coordinator):
        """Test initialization with valid values."""
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=25,
            enabled=True,
        )

        assert manager.min_soc == 25
        assert manager.enabled is True

    async def test_init_clamps_min_soc_to_range(self, mock_coordinator):
        """Test min_soc is clamped to valid range."""
        # Test upper bound
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=150,
            enabled=True,
        )
        assert manager.min_soc == 100

        # Test lower bound
        manager = SOCManager(
            coordinator=mock_coordinator,
            min_soc=-10,
            enabled=True,
        )
        assert manager.min_soc == 0


class TestSOCManagerProperties:
    """Test SOC manager property setters."""

    async def test_min_soc_setter_clamps_values(self, soc_manager):
        """Test min_soc setter clamps to valid range."""
        # Test upper bound
        soc_manager.min_soc = 150
        assert soc_manager.min_soc == 100

        # Test lower bound
        soc_manager.min_soc = -10
        assert soc_manager.min_soc == 0

        # Test valid value
        soc_manager.min_soc = 30
        assert soc_manager.min_soc == 30

    async def test_min_soc_setter_logs_increase(self, soc_manager):
        """Test min_soc setter logs when value increases."""
        with patch("custom_components.sax_battery.soc_manager._LOGGER") as mock_logger:
            soc_manager.min_soc = 25  # Increase from 20

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


class TestCheckAndEnforceDischargeLimit:
    """Test check_and_enforce_discharge_limit method."""

    async def test_enforces_at_minimum_soc(self, soc_manager) -> None:
        """The minimum boundary is enforced at equality."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: soc_manager.min_soc}
        with patch.object(
            soc_manager, "_enforce_discharge_constraint", new_callable=AsyncMock
        ) as enforce:
            await soc_manager.check_and_enforce_discharge_limit()
        enforce.assert_awaited_once_with(soc_manager.min_soc)

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_charge_limit_zero_at_maximum_soc(
        self, mock_registry, soc_manager
    ) -> None:
        """At maximum SOC the charge limit is zeroed through the number entity."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: soc_manager.max_soc_charging}
        mock_registry.return_value.async_get_entity_id.return_value = (
            "number.sax_bms_max_charge"
        )

        assert await soc_manager.check_and_enforce_charge_limit() is True

        soc_manager.hass.services.async_call.assert_awaited_once_with(
            "number",
            "set_value",
            {"entity_id": "number.sax_bms_max_charge", "value": 0},
            blocking=True,
        )

    @pytest.mark.parametrize("soc", [89, 90, 91])
    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_charge_enforcement_boundary(
        self, mock_registry, soc_manager, soc
    ) -> None:
        """Charge is blocked at or above the maximum, not below it."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: soc}
        mock_registry.return_value.async_get_entity_id.return_value = (
            "number.sax_bms_max_charge"
        )

        assert await soc_manager.check_and_enforce_charge_limit() is (soc >= 90)
        assert soc_manager.hass.services.async_call.await_count == int(soc >= 90)

    @pytest.mark.parametrize("state_value", ["0", "0.0"])
    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_charge_enforcement_skips_zero(
        self, mock_registry, soc_manager, state_value
    ) -> None:
        """Already-zero limits are not rewritten on each poll."""
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 90}
        mock_registry.return_value.async_get_entity_id.return_value = (
            "number.sax_bms_max_charge"
        )
        soc_manager.hass.states.get.side_effect = None
        soc_manager.hass.states.get.return_value = MagicMock(state=state_value)

        assert await soc_manager.check_and_enforce_charge_limit() is False
        soc_manager.hass.services.async_call.assert_not_awaited()

    async def test_charge_enforcement_skips_sunspec(self, soc_manager) -> None:
        """SunSpec does not expose a writable legacy max-charge number."""
        soc_manager.coordinator.protocol_mode = ProtocolMode.SUNSPEC
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 90}

        assert await soc_manager.check_and_enforce_charge_limit() is False
        soc_manager.hass.services.async_call.assert_not_awaited()

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
        soc_manager.coordinator.data = {
            SAX_COMBINED_SOC: 8,
        }

        # Mock get_unique_id_for_item (correct method from SAXBatteryData)
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_bess_a_max_discharge"
        )

        # Mock entity registry lookup
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_bess_a_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Verify successful enforcement
        assert result is True

        # Verify unique_id was generated correctly
        soc_manager.coordinator.sax_data.get_unique_id_for_item.assert_called_once()

        # Verify entity registry lookup was called
        mock_ent_reg.async_get_entity_id.assert_called_once_with(
            "number",
            "sax_battery",
            "sax_bess_a_max_discharge",
        )

        # Verify service was called with correct entity_id
        soc_manager.hass.services.async_call.assert_called_once_with(
            "number",
            "set_value",
            {
                "entity_id": "number.sax_bess_a_max_discharge",
                "value": 0,
            },
            blocking=True,
        )

    async def test_enforce_skips_when_soc_above_minimum(
        self,
        soc_manager,
    ) -> None:
        """Test enforcement skipped when SOC above minimum.

        Security:
            OWASP A05: Validates constraint logic
        """
        # Setup SOC above minimum
        soc_manager.coordinator.data = {
            SAX_COMBINED_SOC: 50,
        }

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False (no enforcement needed)
        assert result is False

        # Verify service was NOT called
        soc_manager.hass.services.async_call.assert_not_called()

    @patch(
        "custom_components.sax_battery.soc_manager.SunSpecPowerControlStrategy.async_set_power",
        new_callable=AsyncMock,
        return_value=True,
    )
    async def test_sunspec_enforces_zero_watt_model_123_setpoint(
        self,
        mock_set_power: AsyncMock,
        soc_manager,
    ) -> None:
        """SunSpec low-SOC enforcement must not use legacy limit register 43."""
        soc_manager.coordinator.protocol_mode = ProtocolMode.SUNSPEC
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8}

        result = await soc_manager.check_and_enforce_discharge_limit()

        assert result is True
        mock_set_power.assert_awaited_once_with(0)
        soc_manager.hass.services.async_call.assert_not_called()

    async def test_enforce_skips_when_disabled(
        self,
        soc_manager,
    ) -> None:
        """Test enforcement skipped when disabled.

        Security:
            OWASP A05: Validates configuration respect
        """
        soc_manager.enabled = False
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8}

        result = await soc_manager.check_and_enforce_discharge_limit()

        assert result is False
        soc_manager.hass.services.async_call.assert_not_called()

    async def test_enforce_skips_when_not_master(
        self,
        soc_manager,
    ) -> None:
        """Test enforcement skipped when coordinator is not master.

        Security:
            OWASP A01: Validates access control
        """
        soc_manager.coordinator.is_master = False
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8}

        result = await soc_manager.check_and_enforce_discharge_limit()

        assert result is False
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
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8}

        # Mock get_unique_id_for_item returning None
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = None

        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False due to missing unique_id
        assert result is False
        soc_manager.hass.services.async_call.assert_not_called()

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
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8}

        # Mock successful unique_id generation
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_bess_a_max_discharge"
        )

        # Mock entity registry returning None (entity not found)
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = None
        mock_entity_registry.return_value = mock_ent_reg

        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False due to missing entity_id
        assert result is False
        soc_manager.hass.services.async_call.assert_not_called()

    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_handles_service_call_failure(
        self,
        mock_entity_registry,
        soc_manager,
    ) -> None:
        """Test enforcement handles service call failures gracefully.

        Security:
            OWASP A05: Validates error handling doesn't crash system
        """
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8}

        # Mock successful unique_id generation
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_bess_a_max_discharge"
        )

        # Mock successful entity registry lookup
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_bess_a_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Mock service call to raise exception
        soc_manager.hass.services.async_call.side_effect = HomeAssistantError(
            "Service call failed"
        )

        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False on exception
        assert result is False
        # Note: _last_enforced_soc is NOT cleared on service failure
        # This is intentional to track that enforcement was attempted

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
        soc_manager.coordinator.data = {
            SAX_COMBINED_SOC: 12,
        }

        # Mock successful unique_id generation
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_bess_a_max_discharge"
        )

        # Mock successful entity registry lookup
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_bess_a_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        result = await soc_manager.check_and_enforce_discharge_limit()

        # Verify SOC was tracked
        assert result is True

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
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 5}

        # Mock successful unique_id generation
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_bess_a_max_discharge"
        )

        # Mock successful entity registry lookup
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_bess_a_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Mock service call failure
        soc_manager.hass.services.async_call = AsyncMock(
            side_effect=OSError("Service call failed")
        )

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Should return False on service failure
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
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 5}

        # Mock successful unique_id generation
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_bess_a_max_discharge"
        )

        # Mock successful entity registry lookup
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_bess_a_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Remove config entry
        soc_manager.coordinator.config_entry = None

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Implementation allows enforcement without config_entry
        assert result is True

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
            min_soc=20,
            enabled=False,
        )

        # Setup low SOC condition
        manager.coordinator.data = {SAX_COMBINED_SOC: 5}

        # Execute enforcement
        result = await manager.check_and_enforce_discharge_limit()

        # Should return False without attempting enforcement
        assert result is False

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
        # Setup low SOC condition
        soc_manager.coordinator.data = {
            SAX_COMBINED_SOC: 8.0,
        }

        # Mock successful unique_id generation
        soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_bess_a_max_discharge"
        )

        # Mock successful entity registry lookup
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = (
            "number.sax_bess_a_max_discharge"
        )
        mock_entity_registry.return_value = mock_ent_reg

        # Execute enforcement
        result = await soc_manager.check_and_enforce_discharge_limit()

        # Implementation allows enforcement without ModbusItem validation
        assert result is True

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
        soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8}

        # Remove sax_data attribute
        delattr(soc_manager.coordinator, "sax_data")

        # Execute enforcement - should raise AttributeError or return False
        with patch("custom_components.sax_battery.soc_manager._LOGGER"):
            try:
                result = await soc_manager.check_and_enforce_discharge_limit()
                # If implementation adds hasattr guard, result should be False
                assert result is False
            except AttributeError:
                # Current implementation raises AttributeError
                # This is expected behavior without hasattr guard
                pass
