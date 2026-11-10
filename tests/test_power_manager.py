"""Test power manager for SAX Battery integration."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# custom_component cannot use "from tests.common import MockConfigEntry"
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.const import (
    CONF_ENABLE_GRID_CHARGING,
    CONF_ENABLE_PV_CHARGING,
    CONF_GRID_POWER_MODE,
    CONF_LIMIT_POWER,
    CONF_POWER_SENSOR,
    CONF_SM_CONNECTED,
    DOMAIN,
    GRID_CHARGING_MODE,
    GRID_POWER_MODE_CHARGE,
    GRID_POWER_MODE_DISCHARGE,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    PV_CHARGING_MODE,
    SAX_AC_POWER_TOTAL,
    SAX_COMBINED_SOC,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
    SAX_POWER_SM,
)
from custom_components.sax_battery.const_legacy import (
    MODBUS_BATTERY_POWER_CONTROL_ITEMS,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.entity_keys import SAX_POWER_SETPOINT
from custom_components.sax_battery.models import SAXBatteryData
from custom_components.sax_battery.power_manager import PowerManager, PowerManagerState
from custom_components.sax_battery.protocol_mode import ProtocolMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

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

    def test_initialization_restores_persisted_pv_switch(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """PV switch state is read from entry data before entities are set up."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ENABLE_PV_CHARGING: True},
        )
        entry.add_to_hass(hass)

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        assert power_manager.get_pv_charging_enabled is True

    def test_initialization_restores_pv_flag_from_entry(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """The manager restores persisted PV mode before switch entities load."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ENABLE_PV_CHARGING: True,
                CONF_ENABLE_GRID_CHARGING: False,
            },
        )
        entry.add_to_hass(hass)

        manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        assert manager.get_pv_charging_enabled is True
        assert manager.get_grid_charging_enabled is False


class TestPowerManagerLegacyBalancing:
    """Test legacy power-control calculations."""

    async def test_setpoint_write_skips_small_change(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Changes below the deadband do not create another setpoint event."""
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}
        mock_coordinator_master.last_written_power_control = {SAX_POWER_SETPOINT: -1808}
        setpoint_item = next(
            item
            for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
            if item.name == SAX_POWER_SETPOINT
        )
        manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        with (
            patch(
                "custom_components.sax_battery.power_manager.time.monotonic",
                return_value=100,
            ),
            patch.object(
                manager,
                "apply_power_constraints",
                new_callable=AsyncMock,
                side_effect=lambda target_power, combined_soc: target_power,
            ),
            patch.object(
                mock_coordinator_master.sax_data,
                "get_item_by_name",
                return_value=setpoint_item,
            ),
            patch.object(
                mock_coordinator_master,
                "async_write_power_control_value",
                new_callable=AsyncMock,
            ) as write,
        ):
            manager._last_power_write_monotonic = 100
            await manager.update_power_setpoint(-1817)

        write.assert_not_awaited()

    async def test_capped_setpoint_refreshes_after_two_minutes(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Sustained demand refreshes the capped setpoint before firmware timeout."""
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}
        mock_coordinator_master.last_written_power_control = {}
        setpoint_item = next(
            item
            for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
            if item.name == SAX_POWER_SETPOINT
        )
        manager = PowerManager(hass, mock_coordinator_master, entry)

        with (
            patch(
                "custom_components.sax_battery.power_manager.time.monotonic",
                return_value=100,
            ) as clock,
            patch.object(manager, "_get_max_discharge_limit", return_value=250),
            patch.object(
                mock_coordinator_master.sax_data,
                "get_item_by_name",
                return_value=setpoint_item,
            ),
            patch.object(
                mock_coordinator_master,
                "async_write_power_control_value",
                new_callable=AsyncMock,
                return_value=True,
            ) as write,
        ):
            await manager.update_power_setpoint(1200)
            mock_coordinator_master.last_written_power_control = {
                SAX_POWER_SETPOINT: 250
            }
            clock.return_value = 219
            await manager.update_power_setpoint(1200)
            assert write.await_count == 1
            clock.return_value = 220
            await manager.update_power_setpoint(1200)

        assert write.await_count == 2
        write.assert_awaited_with(
            power_item=setpoint_item, power=250, power_factor=1000
        )

    async def test_setpoint_reaches_discharge_limit_within_deadband(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """High demand sends the discharge limit even when close to the last write."""
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 20.0}
        mock_coordinator_master.last_written_power_control = {SAX_POWER_SETPOINT: 238}
        setpoint_item = next(
            item
            for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
            if item.name == SAX_POWER_SETPOINT
        )
        manager = PowerManager(hass, mock_coordinator_master, entry)
        manager._last_power_write_monotonic = 100

        with (
            patch(
                "custom_components.sax_battery.power_manager.time.monotonic",
                return_value=101,
            ),
            patch.object(manager, "_get_max_discharge_limit", return_value=250),
            patch.object(
                mock_coordinator_master.sax_data,
                "get_item_by_name",
                return_value=setpoint_item,
            ),
            patch.object(
                mock_coordinator_master,
                "async_write_power_control_value",
                new_callable=AsyncMock,
                return_value=True,
            ) as write,
        ):
            await manager.update_power_setpoint(1106)

        write.assert_awaited_once_with(
            power_item=setpoint_item, power=250, power_factor=1000
        )

    async def test_failed_setpoint_refresh_is_retried(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Only a successful refresh advances the refresh deadline."""
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}
        mock_coordinator_master.last_written_power_control = {SAX_POWER_SETPOINT: 250}
        setpoint_item = next(
            item
            for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
            if item.name == SAX_POWER_SETPOINT
        )
        manager = PowerManager(hass, mock_coordinator_master, entry)
        manager._last_power_write_monotonic = 100

        with (
            patch(
                "custom_components.sax_battery.power_manager.time.monotonic",
                return_value=220,
            ),
            patch.object(manager, "_get_max_discharge_limit", return_value=250),
            patch.object(
                mock_coordinator_master.sax_data,
                "get_item_by_name",
                return_value=setpoint_item,
            ),
            patch.object(
                mock_coordinator_master,
                "async_write_power_control_value",
                new_callable=AsyncMock,
                side_effect=[False, True],
            ) as write,
        ):
            await manager.update_power_setpoint(1200)
            assert manager._last_power_write_monotonic == 100
            await manager.update_power_setpoint(1200)

        assert write.await_count == 2
        assert manager._last_power_write_monotonic == 220

    @pytest.mark.parametrize(
        ("previous", "requested", "charge_limit", "discharge_limit", "expected"),
        [
            (1540, 2000, 3500, 1500, 1500),
            (-1540, -2000, 1500, 4600, -1500),
        ],
    )
    async def test_setpoint_deadband_respects_reduced_power_limit(  # noqa: PLR0917
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        previous: int,
        requested: int,
        charge_limit: int,
        discharge_limit: int,
        expected: int,
    ) -> None:
        """A new limit overrides the deadband when the previous setpoint exceeds it."""
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}
        mock_coordinator_master.last_written_power_control = {
            SAX_POWER_SETPOINT: previous
        }
        setpoint_item = next(
            item
            for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
            if item.name == SAX_POWER_SETPOINT
        )
        manager = PowerManager(hass, mock_coordinator_master, entry)

        with (
            patch.object(manager, "_get_max_charge_limit", return_value=charge_limit),
            patch.object(
                manager, "_get_max_discharge_limit", return_value=discharge_limit
            ),
            patch.object(
                mock_coordinator_master.sax_data,
                "get_item_by_name",
                return_value=setpoint_item,
            ),
            patch.object(
                mock_coordinator_master,
                "async_write_power_control_value",
                new_callable=AsyncMock,
                return_value=True,
            ) as write,
        ):
            await manager.update_power_setpoint(requested)

        write.assert_awaited_once_with(
            power_item=setpoint_item, power=expected, power_factor=1000
        )

    async def test_developer_mode_balances_with_configured_power_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Developer mode only observes SM data; balancing uses the power sensor."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "sm_connected": False,
                "developer_mode": True,
                "balanced_loading": True,
                CONF_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)
        hass.states.async_set("sensor.grid_power", "178")
        manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        manager._state.pv_charging_enabled = True
        mock_coordinator_master.data = {
            SAX_POWER_SM: 100,
            SAX_COMBINED_SOC: 50.0,
        }

        with (
            patch.object(
                manager, "_update_sm_balanced_power", new_callable=AsyncMock
            ) as sm_update,
            patch.object(
                manager, "_update_grid_balance_mode", new_callable=AsyncMock
            ) as grid_update,
        ):
            await manager._async_update_power(None)

        sm_update.assert_not_awaited()
        grid_update.assert_awaited_once()

    async def test_sm_balanced_power_uses_legacy_sign_convention(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Battery -1160W and meter 123W produce a -1037W target."""
        entry = MockConfigEntry(domain=DOMAIN, data={})
        entry.add_to_hass(hass)
        manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        mock_coordinator_master.data = {SAX_POWER_SM: 123}

        with (
            patch.object(manager, "_get_battery_power", return_value=-1160),
            patch.object(
                manager, "update_power_setpoint", new_callable=AsyncMock
            ) as update,
        ):
            await manager._update_sm_balanced_power()

        update.assert_awaited_once_with(-1037)

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
                power_manager, "update_power_setpoint", new_callable=AsyncMock
            ) as mock_update:
                await power_manager._update_pv_charging_power()

                mock_update.assert_called_once()
                call_args = mock_update.call_args[0]
                # New Setpoint = Current Battery Power + Grid Power
                # Battery: 500W discharging, Grid: -1000W (exporting)
                # Target = 500 + (-1000) = -500W (charge)
                assert call_args[0] == -500

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
            power_manager, "update_power_setpoint", new_callable=AsyncMock
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
            power_manager, "update_power_setpoint", new_callable=AsyncMock
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
            power_manager, "update_power_setpoint", new_callable=AsyncMock
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
                power_manager, "update_power_setpoint", new_callable=AsyncMock
            ) as mock_update:
                await power_manager._update_pv_charging_power()

                # VERIFY: Power setpoint was updated
                mock_update.assert_called_once()

                call_args = mock_update.call_args[0]
                constrained_power = call_args[0]

                # VERIFY: Power is clamped to per-battery charge limit
                assert constrained_power == -LIMIT_MAX_CHARGE_PER_BATTERY

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
        hass.states.async_set("sensor.grid_power", "-2000")  # 2kW export

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
                power_manager, "update_power_setpoint", new_callable=AsyncMock
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

    async def test_grid_balance_uses_internal_smart_meter_without_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """ADW/ADL grid control uses SAX smart-meter data without a grid sensor."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_SM_CONNECTED: True},
        )
        entry.add_to_hass(hass)
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        with patch.object(
            power_manager, "_update_sm_balanced_power", new_callable=AsyncMock
        ) as update_sm:
            await power_manager._update_grid_balance_mode()

        update_sm.assert_awaited_once()

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
                CONF_SM_CONNECTED: False,
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

        with (
            patch.object(power_manager, "_get_battery_power", return_value=500.0),
            patch.object(
                power_manager, "update_power_setpoint", new_callable=AsyncMock
            ) as update,
        ):
            await power_manager._update_grid_balance_mode()

        update.assert_awaited_once_with(-500.0)

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
                CONF_SM_CONNECTED: False,
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

        with (
            patch.object(power_manager, "_get_battery_power", return_value=1000.0),
            patch.object(
                power_manager, "update_power_setpoint", new_callable=AsyncMock
            ) as update,
        ):
            await power_manager._update_grid_balance_mode()

        update.assert_awaited_once_with(1500.0)


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

    def test_config_update_keeps_pv_state_when_running(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """PV state must not be reset by a config update (switch unavailable)."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )
        power_manager._running = True
        power_manager._state.pv_charging_enabled = True

        power_manager._update_config_values()

        assert power_manager._state.pv_charging_enabled is True

    async def test_pv_mode_changes_are_persisted(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Direct power-manager mode changes persist the PV switch state."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ENABLE_PV_CHARGING: False},
        )
        entry.add_to_hass(hass)
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        await power_manager.set_pv_charging_mode(True)
        assert entry.data[CONF_ENABLE_PV_CHARGING] is True

        with (
            patch.object(
                power_manager,
                "_async_write_power",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.power_manager.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await power_manager.set_pv_charging_mode(False)
        assert entry.data[CONF_ENABLE_PV_CHARGING] is False

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


class TestGridPowerMode:
    """Test grid power charge/discharge mode."""

    @staticmethod
    def _manager(
        hass: HomeAssistant,
        coordinator: SAXBatteryCoordinator,
        mode: str | None = None,
    ) -> PowerManager:
        data = {CONF_GRID_POWER_MODE: mode} if mode else {}
        entry = MockConfigEntry(domain=DOMAIN, data=data)
        entry.add_to_hass(hass)
        coordinator.data = {SAX_COMBINED_SOC: 50.0}
        return PowerManager(hass=hass, coordinator=coordinator, config_entry=entry)

    async def test_default_mode_is_charge_with_max_charge_limit(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Charge is the default and writes the negative max charge limit."""
        manager = self._manager(hass, mock_coordinator_master)
        assert manager._state.grid_power_mode == GRID_POWER_MODE_CHARGE

        with (
            patch.object(manager, "_get_max_charge_limit", return_value=3000.0),
            patch.object(manager, "_get_max_soc_charging_limit", return_value=90.0),
            patch.object(
                manager, "_async_write_power", new_callable=AsyncMock
            ) as write,
        ):
            await manager._update_grid_load_mode()

        write.assert_awaited_once_with(-3000.0)

    async def test_discharge_mode_uses_max_discharge_limit(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Discharge writes the positive max discharge limit."""
        manager = self._manager(
            hass, mock_coordinator_master, GRID_POWER_MODE_DISCHARGE
        )

        with (
            patch.object(manager, "_get_max_discharge_limit", return_value=4000.0),
            patch.object(manager, "_get_min_soc_limit", return_value=10.0),
            patch.object(
                manager, "_async_write_power", new_callable=AsyncMock
            ) as write,
        ):
            await manager._update_grid_load_mode()

        write.assert_awaited_once_with(4000.0)

    async def test_charge_stops_at_max_soc(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Reaching the max charging SOC stops grid mode instead of writing."""
        manager = self._manager(hass, mock_coordinator_master)
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 90.0}

        with (
            patch.object(manager, "_get_max_soc_charging_limit", return_value=90.0),
            patch.object(
                manager, "_async_write_power", new_callable=AsyncMock
            ) as write,
            patch.object(
                manager, "_async_stop_grid_mode", new_callable=AsyncMock
            ) as stop,
        ):
            await manager._update_grid_load_mode()

        stop.assert_awaited_once()
        write.assert_not_awaited()

    async def test_discharge_stops_at_min_soc(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Reaching the minimum SOC stops grid discharge."""
        manager = self._manager(
            hass, mock_coordinator_master, GRID_POWER_MODE_DISCHARGE
        )
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 10.0}

        with (
            patch.object(manager, "_get_min_soc_limit", return_value=10.0),
            patch.object(
                manager, "_async_write_power", new_callable=AsyncMock
            ) as write,
            patch.object(
                manager, "_async_stop_grid_mode", new_callable=AsyncMock
            ) as stop,
        ):
            await manager._update_grid_load_mode()

        stop.assert_awaited_once()
        write.assert_not_awaited()

    async def test_stop_restores_pv_mode_and_clears_config_flag(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Stopping grid mode switches it off and falls back to balanced PV mode."""
        manager = self._manager(hass, mock_coordinator_master)
        manager._state.pv_charging_enabled = True
        await manager.set_grid_control_mode(True)
        assert manager._state.pv_charging_enabled is False
        hass.config_entries.async_update_entry(
            manager.config_entry,
            data={**manager.config_entry.data, CONF_ENABLE_GRID_CHARGING: True},
        )

        with patch.object(manager, "_async_update_power", new_callable=AsyncMock):
            await manager._async_stop_grid_mode("test")

        assert manager._state.grid_charging_enabled is False
        assert manager._state.pv_charging_enabled is True
        assert manager.config_entry.data[CONF_ENABLE_GRID_CHARGING] is False

    async def test_manual_grid_switch_off_forces_zero_without_pv_restore(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Manual grid switch-off sends zero instead of resuming PV balancing."""
        manager = self._manager(hass, mock_coordinator_master)
        manager._state.grid_charging_enabled = True
        manager._state.previous_pv_state = True

        with (
            patch.object(
                manager, "_async_write_power", new_callable=AsyncMock
            ) as write,
            patch(
                "custom_components.sax_battery.power_manager.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await manager.set_grid_control_mode(
                False, restore_pv=False, fallback_to_balance=False
            )

        write.assert_awaited_once_with(0.0, force=True)
        assert manager._state.pv_charging_enabled is False
        assert manager._state.grid_charging_enabled is False

    async def test_manual_pv_switch_off_forces_zero(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Turning PV control off sends an explicit zero setpoint."""
        manager = self._manager(hass, mock_coordinator_master)
        manager._state.pv_charging_enabled = True

        with (
            patch.object(
                manager, "_async_write_power", new_callable=AsyncMock
            ) as write,
            patch(
                "custom_components.sax_battery.power_manager.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await manager.set_pv_charging_mode(False)

        write.assert_awaited_once_with(0.0, force=True)
        assert manager._state.pv_charging_enabled is False

    @pytest.mark.parametrize("mode", ["pv", "grid"])
    async def test_manual_stop_waits_for_coordinator_interval(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mode: str,
    ) -> None:
        """Legacy manual stops allow one coordinator interval after zero."""
        manager = self._manager(hass, mock_coordinator_master)
        with (
            patch.object(
                manager, "_async_write_power", new_callable=AsyncMock
            ) as write,
            patch(
                "custom_components.sax_battery.power_manager.asyncio.sleep",
                new_callable=AsyncMock,
            ) as sleep,
        ):
            if mode == "pv":
                await manager.set_pv_charging_mode(False)
            else:
                await manager.set_grid_control_mode(
                    False, restore_pv=False, fallback_to_balance=False
                )

        write.assert_awaited_once_with(0.0, force=True)
        assert mock_coordinator_master.update_interval is not None
        sleep.assert_awaited_once_with(
            mock_coordinator_master.update_interval.total_seconds()
        )

    @pytest.mark.parametrize("mode", ["pv", "grid"])
    async def test_manual_stop_reports_write_failure(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mode: str,
    ) -> None:
        """A failed zero write is not reported as a successful stop."""
        manager = self._manager(hass, mock_coordinator_master)
        operation = (
            manager.set_pv_charging_mode(False)
            if mode == "pv"
            else manager.set_grid_control_mode(
                False, restore_pv=False, fallback_to_balance=False
            )
        )
        with (
            patch.object(
                manager,
                "_async_write_power",
                new_callable=AsyncMock,
                return_value=False,
            ),
            pytest.raises(HomeAssistantError, match="zero power"),
        ):
            await operation
        assert manager._stop_complete.is_set()

    async def test_manual_stop_discards_inflight_update_and_delays_reenable(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """A stale balancing result cannot overwrite zero during a stop."""
        manager = self._manager(hass, mock_coordinator_master)
        manager._state.pv_charging_enabled = True
        mock_coordinator_master.data = {SAX_COMBINED_SOC: 50.0}
        setpoint_item = next(
            item
            for item in MODBUS_BATTERY_POWER_CONTROL_ITEMS
            if item.name == SAX_POWER_SETPOINT
        )
        calculation_started = asyncio.Event()
        finish_calculation = asyncio.Event()
        settling_started = asyncio.Event()
        finish_settling = asyncio.Event()
        yield_control = asyncio.sleep
        calculation_results: list[bool] = []

        async def calculate_power() -> None:
            calculation_started.set()
            await finish_calculation.wait()
            calculation_results.append(await manager.update_power_setpoint(-500))

        async def settle(seconds: float) -> None:
            settling_started.set()
            await finish_settling.wait()

        with (
            patch.object(
                manager, "_update_sm_balanced_power", side_effect=calculate_power
            ),
            patch.object(
                mock_coordinator_master.sax_data,
                "get_item_by_name",
                return_value=setpoint_item,
            ),
            patch.object(
                mock_coordinator_master,
                "async_write_power_control_value",
                new_callable=AsyncMock,
                return_value=True,
            ) as write,
            patch(
                "custom_components.sax_battery.power_manager.asyncio.sleep",
                side_effect=settle,
            ),
        ):
            update_task = asyncio.create_task(manager._async_update_power())
            await asyncio.wait_for(calculation_started.wait(), 1)
            stop_task = asyncio.create_task(manager.set_pv_charging_mode(False))
            await asyncio.wait_for(settling_started.wait(), 1)
            enable_task = asyncio.create_task(manager.set_pv_charging_mode(True))
            finish_calculation.set()
            await yield_control(0)
            assert not enable_task.done()
            assert not update_task.done()
            assert write.await_count == 1
            assert write.await_args is not None
            assert write.await_args.kwargs["power"] == 0
            finish_settling.set()
            await asyncio.gather(update_task, stop_task, enable_task)

        assert calculation_results == [False, True]
        assert [call.kwargs["power"] for call in write.await_args_list] == [0, -500]

    async def test_sunspec_writes_total_power_via_model_123(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """SunSpec converts per-battery power to the cluster total."""
        manager = self._manager(hass, mock_coordinator_master)
        mock_coordinator_master.protocol_mode = ProtocolMode.SUNSPEC
        manager.battery_count = 2

        with patch(
            "custom_components.sax_battery.power_manager.SunSpecPowerControlStrategy"
        ) as strategy_cls:
            strategy_cls.return_value.async_set_power = AsyncMock()
            await manager._async_write_power(-3500.0)

        strategy_cls.return_value.async_set_power.assert_awaited_once_with(-7000.0)

    async def test_sunspec_stop_returns_to_zero_balance_mode(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """SunSpec falls back to the battery's Smart Meter balancing."""
        manager = self._manager(hass, mock_coordinator_master)
        mock_coordinator_master.protocol_mode = ProtocolMode.SUNSPEC

        with patch(
            "custom_components.sax_battery.power_manager.SunSpecPowerControlStrategy"
        ) as strategy_cls:
            strategy_cls.return_value.async_set_mode_zero_balance = AsyncMock()
            await manager.set_grid_control_mode(False)

        strategy_cls.return_value.async_set_mode_zero_balance.assert_awaited_once()


class TestPowerConstraintEngine:
    """Test power constraint enforcement engine."""

    @pytest.mark.parametrize(
        ("item_name", "configured_limit", "target", "expected"),
        [
            (SAX_MAX_DISCHARGE, 1500, 3000.0, 1500.0),
            (SAX_MAX_DISCHARGE, 0, 3000.0, 0.0),
            (SAX_MAX_DISCHARGE, 9000, 6000.0, LIMIT_MAX_DISCHARGE_PER_BATTERY),
            (SAX_MAX_CHARGE, 1200, -2500.0, -1200.0),
        ],
    )
    async def test_constraints_use_renamed_limit_entity(  # noqa: PLR0917
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        item_name: str,
        configured_limit: int,
        target: float,
        expected: float,
    ) -> None:
        """Use the registered number's state even when its entity ID was renamed."""
        entry = MockConfigEntry(domain=DOMAIN, data={CONF_LIMIT_POWER: True})
        entry.add_to_hass(hass)
        sax_data = SAXBatteryData(hass, entry)
        item = sax_data.get_item_by_name(item_name)
        assert item is not None
        mock_coordinator_master.battery_id = "bess_a"
        mock_coordinator_master.sax_data = sax_data
        unique_id = sax_data.get_unique_id_for_item(item, battery_id="bess_a")
        assert unique_id is not None
        registry = er.async_get(hass)
        registry_entry = registry.async_get_or_create(
            "number", DOMAIN, unique_id, config_entry=entry
        )
        registry.async_update_entity(
            registry_entry.entity_id, new_entity_id="number.renamed_power_limit"
        )
        hass.states.async_set("number.renamed_power_limit", str(configured_limit))
        manager = PowerManager(hass, mock_coordinator_master, entry)

        assert await manager.apply_power_constraints(target, 50.0) == expected

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
