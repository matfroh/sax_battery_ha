"""Test power manager for SAX Battery integration."""

from __future__ import annotations

from datetime import datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

# custom_component cannot use "from tests.common import MockConfigEntry"
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.const import (
    CONF_POWER_SENSOR,
    DOMAIN,
    GRID_CHARGING_MODE,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    PV_CHARGING_MODE,
    SAX_AC_POWER_TOTAL,
    SAX_COMBINED_SOC,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.power_manager import PowerManager, PowerManagerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class TestPowerManagerInitialization:
    """Test PowerManager __init__ and setup."""

    def test_initialization_defaults(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test PowerManager initialization with default values."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        assert power_manager.hass == hass
        assert power_manager.coordinator == mock_coordinator_master
        assert power_manager.battery_count == 1
        assert power_manager._running is False

    def test_initialization_with_multi_battery(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test PowerManager initialization with multiple batteries."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        mock_coordinator_master.sax_data.coordinators = {
            "battery_a": mock_coordinator_master,
            "battery_b": MagicMock(),
            "battery_c": MagicMock(),
        }

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        assert power_manager.battery_count == 3
        expected_ui_max_discharge = 3 * LIMIT_MAX_DISCHARGE_PER_BATTERY
        expected_ui_max_charge = 3 * LIMIT_MAX_CHARGE_PER_BATTERY
        assert power_manager.ui_max_discharge_power == expected_ui_max_discharge
        assert power_manager.ui_max_charge_power == expected_ui_max_charge
        assert power_manager._state.pv_charging_enabled is False


class TestPowerManagerLifecycle:
    """Test PowerManager start/stop lifecycle."""

    async def test_start_success(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test successful power manager start."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        with patch(
            "custom_components.sax_battery.power_manager.async_track_time_interval"
        ) as mock_track:
            await power_manager.async_start()

            assert power_manager._running is True
            assert mock_track.called

    async def test_start_already_running(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test starting power manager when already running."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        with patch(
            "custom_components.sax_battery.power_manager.async_track_time_interval"
        ):
            await power_manager.async_start()
            assert power_manager._running is True

            # Try starting again
            await power_manager.async_start()
            assert power_manager._running is True

    async def test_stop_success(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test successful power manager stop."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        mock_remove_interval = MagicMock()
        mock_remove_config = MagicMock()
        power_manager._remove_interval_update = mock_remove_interval
        power_manager._remove_config_update = mock_remove_config
        power_manager._running = True

        await power_manager.async_stop()

        assert power_manager._running is False
        mock_remove_interval.assert_called_once()
        mock_remove_config.assert_called_once()

    async def test_stop_not_running(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test stopping power manager when not running."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        await power_manager.async_stop()
        assert power_manager._running is False


class TestPvChargingMode:
    """Test PV charging mode functionality."""

    async def test_pv_charging_update_with_valid_grid_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test PV charging update with valid grid sensor.

        Security:
            OWASP A05: Validates proper state machine access and SOC constraints
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        # Mock grid sensor state
        hass.states.async_set("sensor.grid_power", "-1000")  # 1kW export

        # Mock coordinator.data for SAX_AC_POWER_TOTAL
        mock_battery_item = MagicMock()
        mock_battery_item.item = MagicMock()
        mock_coordinator_master.data = {
            SAX_AC_POWER_TOTAL: mock_battery_item,
        }

        # Patch entity registry and sax_data.get_unique_id_for_item
        with patch("homeassistant.helpers.entity_registry.async_get") as mock_ent_reg:
            mock_reg = MagicMock()
            mock_reg.async_get_entity_id = MagicMock(
                return_value="sensor.battery_a_ac_power_total"
            )
            mock_ent_reg.return_value = mock_reg

            # Set battery power state in state machine
            hass.states.async_set("sensor.battery_a_ac_power_total", "500")

            # ✅ FIX: Direct attribute assignment instead of configure_mock
            mock_coordinator_master.sax_data.get_entity_id_for_item.return_value = (  # type: ignore[attr-defined]
                "sensor.battery_a_ac_power_total"
            )

            power_manager = PowerManager(
                hass=hass,
                coordinator=mock_coordinator_master,
                config_entry=entry,
            )
            power_manager._state.pv_charging_enabled = True

            # ✅ FIX: Use patch.object instead of direct assignment
            with patch.object(
                power_manager, "update_nominal_power", new_callable=AsyncMock
            ) as mock_update:
                await power_manager._update_pv_charging_power()

                mock_update.assert_called_once()
                call_args = mock_update.call_args[0]
                # New Battery Power = Current Battery Power - Grid Power
                # Battery: 500W, Grid: -1000W (exporting)
                # Target = 500 - (-1000) = 1500W
                assert call_args[0] == 1500

    async def test_pv_charging_with_unavailable_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test PV charging handles unavailable sensor."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        # Mock unavailable sensor
        hass.states.async_set("sensor.grid_power", "unavailable")

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.pv_charging_enabled = True

        # ✅ FIX: Use patch.object instead of direct assignment
        with patch.object(
            power_manager, "update_nominal_power", new_callable=AsyncMock
        ) as mock_update:
            await power_manager._update_pv_charging_power()

            # Should not update power when sensor unavailable
            mock_update.assert_not_called()

    async def test_pv_charging_with_missing_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test PV charging handles missing sensor."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.nonexistent",
            },
        )
        entry.add_to_hass(hass)

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.pv_charging_enabled = True

        # ✅ FIX: Use patch.object instead of direct assignment
        with patch.object(
            power_manager, "update_nominal_power", new_callable=AsyncMock
        ) as mock_update:
            await power_manager._update_pv_charging_power()

            mock_update.assert_not_called()

    async def test_pv_charging_with_invalid_sensor_value(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test PV charging handles invalid sensor value."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "invalid_value")

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.pv_charging_enabled = True

        # ✅ FIX: Use patch.object instead of direct assignment
        with patch.object(
            power_manager, "update_nominal_power", new_callable=AsyncMock
        ) as mock_update:
            await power_manager._update_pv_charging_power()

            mock_update.assert_not_called()

    async def test_pv_charging_applies_soc_constraints(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test PV charging applies SOC constraints.

        Security:
            OWASP A05: Validates SOC constraint enforcement in PV charging
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        # Mock grid sensor state - large export (excess solar)
        hass.states.async_set("sensor.grid_power", "-5000")  # 5kW export

        # Mock coordinator.data for SAX_AC_POWER_TOTAL
        mock_battery_item = MagicMock()
        mock_battery_item.item = MagicMock()
        mock_coordinator_master.data = {
            SAX_AC_POWER_TOTAL: mock_battery_item,
        }

        # Setup SOC manager with low SOC to trigger constraint
        mock_soc_manager = MagicMock()
        mock_soc_manager.min_soc = 20.0
        mock_coordinator_master.soc_manager = mock_soc_manager

        # Patch entity registry and sax_data methods
        with patch("homeassistant.helpers.entity_registry.async_get") as mock_ent_reg:
            mock_reg = MagicMock()
            mock_reg.async_get_entity_id = MagicMock(
                return_value="sensor.battery_a_ac_power_total"
            )
            mock_ent_reg.return_value = mock_reg

            # Current battery power: 1kW discharging
            hass.states.async_set("sensor.battery_a_ac_power_total", "1000")

            # ✅ FIX: Direct attribute assignment instead of configure_mock
            mock_coordinator_master.sax_data.get_entity_id_for_item.return_value = (  # type: ignore[attr-defined]
                "sensor.battery_a_ac_power_total"
            )

            power_manager = PowerManager(
                hass=hass,
                coordinator=mock_coordinator_master,
                config_entry=entry,
            )
            power_manager._state.pv_charging_enabled = True

            # ✅ FIX: Use patch.object instead of direct assignment
            with patch.object(
                power_manager, "update_nominal_power", new_callable=AsyncMock
            ) as mock_update:
                await power_manager._update_pv_charging_power()

                # VERIFY: Power setpoint was updated
                mock_update.assert_called_once()

                call_args = mock_update.call_args[0]
                constrained_power = call_args[0]

                # VERIFY: Power is clamped to per-battery discharge limit
                assert constrained_power == LIMIT_MAX_DISCHARGE_PER_BATTERY

    async def test_pv_charging_respects_soc_manager_constraints(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test PV charging respects SOC manager discharge constraints.

        Security:
            OWASP A05: Validates SOC constraint enforcement prevents battery damage
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        # Mock grid importing
        hass.states.async_set("sensor.grid_power", "2000")  # 2kW import

        # Mock battery power
        mock_battery_item = MagicMock()
        mock_battery_item.item = MagicMock()
        mock_coordinator_master.data = {
            SAX_AC_POWER_TOTAL: mock_battery_item,
            SAX_COMBINED_SOC: 15.0,  # Below minimum
        }

        # Setup SOC manager
        mock_soc_manager = MagicMock()
        mock_soc_manager.min_soc = 20.0
        mock_soc_manager.check_and_enforce_discharge_limit = AsyncMock(
            return_value=True
        )
        mock_coordinator_master.soc_manager = mock_soc_manager

        with patch("homeassistant.helpers.entity_registry.async_get") as mock_ent_reg:
            mock_reg = MagicMock()
            mock_reg.async_get_entity_id.return_value = (
                "sensor.battery_a_ac_power_total"
            )
            mock_ent_reg.return_value = mock_reg

            hass.states.async_set("sensor.battery_a_ac_power_total", "500")

            # ✅ FIX: Direct attribute assignment instead of configure_mock
            mock_coordinator_master.sax_data.get_entity_id_for_item.return_value = (  # type: ignore[attr-defined]
                "sensor.battery_a_ac_power_total"
            )

            power_manager = PowerManager(
                hass=hass,
                coordinator=mock_coordinator_master,
                config_entry=entry,
            )
            power_manager._state.pv_charging_enabled = True

            # ✅ FIX: Use patch.object instead of direct assignment
            with patch.object(
                power_manager, "update_nominal_power", new_callable=AsyncMock
            ) as mock_update:
                await power_manager._update_pv_charging_power()

                mock_update.assert_called_once()
                call_args = mock_update.call_args[0]
                target_power = call_args[0]

                # Charging is allowed (negative value)
                assert target_power < 0
                assert target_power == -1500.0


class TestGridBalanceMode:
    """Test grid power balancing mode."""

    async def test_grid_balance_with_import(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test grid balance when importing power from grid."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "-1000")
        mock_coordinator_master.data = {
            SAX_AC_POWER_TOTAL: 500.0,
            SAX_COMBINED_SOC: 60.0,
        }

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        # ✅ FIX: Use patch.object for method mocking
        with patch.object(power_manager, "_get_battery_power", return_value=500.0):
            await power_manager._update_grid_balance_mode()

        assert power_manager._state.target_power > 500.0

    async def test_grid_balance_with_export(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test grid balance when exporting power to grid."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "500")
        mock_coordinator_master.data = {
            SAX_AC_POWER_TOTAL: 1000.0,
            SAX_COMBINED_SOC: 60.0,
        }

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        # ✅ FIX: Use patch.object for method mocking
        with patch.object(power_manager, "_get_battery_power", return_value=1000.0):
            await power_manager._update_grid_balance_mode()

        assert power_manager._state.target_power < 1000.0


class TestBatteryPowerLookup:
    """Test _get_battery_power error paths."""

    async def test_get_battery_power_item_not_found(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _get_battery_power when SAX_AC_POWER_TOTAL not found."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # ✅ FIX: Direct attribute assignment instead of configure_mock
        mock_coordinator_master.sax_data.get_entity_id_for_item.return_value = None  # type: ignore[attr-defined]

        result = await power_manager._get_battery_power()
        assert result is None

    async def test_get_battery_power_invalid_state(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _get_battery_power with invalid state value."""
        # ✅ FIX: Direct attribute assignment instead of configure_mock
        mock_coordinator_master.sax_data.get_entity_id_for_item.return_value = (  # type: ignore[attr-defined]
            "sensor.battery_power"
        )

        hass.states.async_set("sensor.battery_power", "not_a_number")

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        result = await power_manager._get_battery_power()
        assert result is None


class TestPowerManagerProperties:
    """Test PowerManager property accessors and state management."""

    def test_current_mode_property(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test current_mode property."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        assert power_manager.current_mode == PV_CHARGING_MODE

        power_manager._state.mode = GRID_CHARGING_MODE
        assert power_manager.current_mode == GRID_CHARGING_MODE

    def test_current_power_property(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test current_power property."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        assert power_manager.current_power == 0.0

        power_manager._state.target_power = 1500.0
        assert power_manager.current_power == 1500.0

    def test_get_charge_from_grid_mode_enabled_property(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get_charge_from_grid_mode_enabled property."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        assert power_manager.get_grid_charging_enabled is False

        power_manager._state.grid_charging_enabled = True
        assert power_manager.get_grid_charging_enabled is True

    def test_get_pv_charging_enabled_property(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get_pv_charging_enabled property."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        assert power_manager.get_pv_charging_enabled is False

        power_manager._state.pv_charging_enabled = True
        assert power_manager.get_pv_charging_enabled is True

    def test_get_grid_charging_enabled_property(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get_grid_charging_enabled property."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        assert power_manager.get_grid_charging_enabled is False

        power_manager._state.grid_charging_enabled = True
        assert power_manager.get_grid_charging_enabled is True


class TestErrorHandling:
    """Test error handling in power manager."""

    async def test_update_power_handles_os_error(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test update power handles OSError gracefully."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "-1000")

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.pv_charging_enabled = True

        # Should not raise exception
        await power_manager._async_update_power(None)

    async def test_update_power_handles_value_error(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test update power handles ValueError gracefully."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "-1000")

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.pv_charging_enabled = True

        # Should not raise exception
        await power_manager._async_update_power(None)


class TestPowerManagerState:
    """Test PowerManagerState dataclass."""

    def test_state_initialization(self) -> None:
        """Test PowerManagerState initialization."""
        state = PowerManagerState(
            mode=PV_CHARGING_MODE,
            target_power=1500.0,
            last_update=datetime.now(),
        )

        assert state.mode == PV_CHARGING_MODE
        assert state.target_power == 1500.0
        assert state.pv_charging_enabled is False
        assert state.grid_charging_enabled is False

    def test_state_with_flags(self) -> None:
        """Test PowerManagerState with mode flags."""
        state = PowerManagerState(
            mode=GRID_CHARGING_MODE,
            target_power=0.0,
            last_update=datetime.now(),
            pv_charging_enabled=False,
            grid_charging_enabled=True,
        )

        assert state.mode == GRID_CHARGING_MODE
        assert state.grid_charging_enabled is True
        assert state.pv_charging_enabled is False


class TestChargeFromGridMode:
    """Test charge from grid power control mode."""

    async def test_enable_manual_mode_with_discharge_power(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test enabling charge from grid mode with discharge power."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        power_manager._state.pv_charging_enabled = True

        await power_manager.set_grid_charging_mode(True, 2000.0)

        assert power_manager._state.grid_charging_enabled is False
        assert power_manager._state.pv_charging_enabled is False
        assert power_manager._state.mode == "grid_charging"
        assert power_manager._state.previous_pv_state is True

    async def test_enable_manual_mode_with_charge_power(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test enabling manual mode with charge power (negative)."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        await power_manager.set_grid_charging_mode(True, -3000.0)

        assert power_manager._state.grid_charging_enabled is False
        assert power_manager._state.mode == "grid_charging"

    async def test_disable_manual_mode_restores_pv_state(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test disabling manual mode restores previous PV state."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        power_manager._state.pv_charging_enabled = True

        await power_manager.set_grid_charging_mode(True, 1000.0)
        assert power_manager._state.pv_charging_enabled is False

        await power_manager.set_grid_charging_mode(False)

        assert power_manager._state.grid_charging_enabled is False
        assert power_manager._state.pv_charging_enabled is True
        assert power_manager._state.mode == PV_CHARGING_MODE

    async def test_disable_manual_mode_restores_grid_state(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test disabling manual mode restores previous grid state."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        power_manager._state.grid_charging_enabled = True

        await power_manager.set_grid_charging_mode(True, 500.0)
        assert power_manager._state.grid_charging_enabled is False

        await power_manager.set_grid_charging_mode(False)

        assert power_manager._state.grid_charging_enabled is True
        assert power_manager._state.mode == GRID_CHARGING_MODE

    async def test_manual_mode_priority_in_update_loop(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test manual mode has priority over other modes in update loop."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        power_manager._state.grid_charging_enabled = True
        power_manager._state.pv_charging_enabled = True

        await power_manager._async_update_power(None)

        assert power_manager._state.grid_charging_enabled is True


class TestPowerConstraintEngine:
    """Test power constraint enforcement engine."""

    async def test_constraint_discharge_blocked_at_min_soc(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test discharge blocked when SOC <= MIN_SOC."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 10.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        constrained_power = await power_manager.apply_power_constraints(
            target_power=2000.0,
            combined_soc=10.0,
        )

        assert constrained_power == 0.0

    async def test_constraint_discharge_allowed_above_min_soc(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test discharge allowed when SOC > MIN_SOC."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        constrained_power = await power_manager.apply_power_constraints(
            target_power=2000.0,
            combined_soc=50.0,
        )

        assert constrained_power > 0.0

    async def test_constraint_charge_blocked_at_max_soc(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test charge blocked when SOC >= MAX_SOC_CHARGING."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 90.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        constrained_power = await power_manager.apply_power_constraints(
            target_power=-3000.0,
            combined_soc=90.0,
        )

        assert constrained_power == 0.0

    async def test_constraint_charge_allowed_below_max_soc(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test charge allowed when SOC < MAX_SOC_CHARGING."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        constrained_power = await power_manager.apply_power_constraints(
            target_power=-2000.0,
            combined_soc=50.0,
        )

        assert constrained_power < 0.0

    async def test_constraint_charge_limited_to_max_charge(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test charge power limited to MAX_CHARGE per battery."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        constrained_power = await power_manager.apply_power_constraints(
            target_power=-10000.0,
            combined_soc=50.0,
        )

        assert constrained_power >= -LIMIT_MAX_CHARGE_PER_BATTERY

    async def test_constraint_discharge_limited_to_max_discharge(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test discharge power limited to MAX_DISCHARGE per battery."""
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        constrained_power = await power_manager.apply_power_constraints(
            target_power=15000.0,
            combined_soc=50.0,
        )

        assert constrained_power <= LIMIT_MAX_DISCHARGE_PER_BATTERY

    async def test_power_distribution_across_batteries(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test power distributed equally across multiple batteries."""
        mock_coordinator = MagicMock(spec=SAXBatteryCoordinator)
        mock_coordinator.battery_id = "battery_a"
        mock_coordinator.data = {SAX_COMBINED_SOC: 50.0}
        mock_coordinator.config_entry = mock_config_entry

        mock_sax_data = MagicMock()
        mock_sax_data.coordinators = {
            "battery_a": mock_coordinator,
            "battery_b": MagicMock(),
            "battery_c": MagicMock(),
        }
        mock_sax_data.get_entity_id_for_item = MagicMock(return_value=None)
        mock_coordinator.sax_data = mock_sax_data

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
        )

        constrained_power = await power_manager.apply_power_constraints(
            target_power=6000.0,
            combined_soc=50.0,
        )

        # apply_power_constraints now receives per-battery values directly
        # and clamps to per-battery hardware limits
        assert constrained_power <= LIMIT_MAX_DISCHARGE_PER_BATTERY


class TestPowerManagerDiagnostics:
    """Test power manager diagnostics."""

    def test_diagnostics_includes_grid_charging_fields(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test diagnostics include grid charging state."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        power_manager._state.grid_charging_enabled = True

        diagnostics = power_manager.get_diagnostics()

        assert "grid_charging_enabled" in diagnostics
        assert diagnostics["grid_charging_enabled"] is True

    def test_diagnostics_complete_structure(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test diagnostics contain all expected fields."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        diagnostics = power_manager.get_diagnostics()

        expected_fields = [
            "running",
            "mode",
            "target_power",
            "pv_charging_enabled",
            "grid_charging_enabled",
            "last_update",
            "battery_count",
            "ui_max_discharge_power",
            "ui_max_charge_power",
            "configured_max_charge",
            "configured_max_discharge",
            "hw_limit_charge_per_battery",
            "hw_limit_discharge_per_battery",
            "update_interval_seconds",
        ]

        for field in expected_fields:
            assert field in diagnostics


class TestConstraintLimitGetters:
    """Test constraint limit getter methods."""

    async def test_get_min_soc_limit_from_config(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test _get_min_soc_limit retrieves value from config."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "min_soc": 15.0,
            },
        )
        entry.add_to_hass(hass)

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        min_soc = await power_manager._get_min_soc_limit()
        assert min_soc == 15.0

    async def test_get_min_soc_limit_default(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _get_min_soc_limit uses default when not configured."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        min_soc = await power_manager._get_min_soc_limit()
        assert min_soc >= 0.0

    async def test_get_max_soc_charging_limit_fallback(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _get_max_soc_charging_limit uses fallback."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        max_soc = await power_manager._get_max_soc_charging_limit()
        assert max_soc == 90.0

    async def test_get_max_charge_limit_fallback(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _get_max_charge_limit uses fallback."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        max_charge = await power_manager._get_max_charge_limit()
        assert max_charge == LIMIT_MAX_CHARGE_PER_BATTERY

    async def test_get_max_discharge_limit_fallback(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _get_max_discharge_limit uses fallback."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        max_discharge = await power_manager._get_max_discharge_limit()
        assert max_discharge == LIMIT_MAX_DISCHARGE_PER_BATTERY
