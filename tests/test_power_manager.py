"""Test power manager for SAX Battery integration."""

from __future__ import annotations

from datetime import datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# custom_component cannot use "from tests.common import MockConfigEntry"
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_GRID_POWER_SENSOR,
    CONF_MANUAL_CONTROL,
    DOMAIN,
    LIMIT_MAX_CHARGE_PER_BATTERY,
    LIMIT_MAX_DISCHARGE_PER_BATTERY,
    MANUAL_CONTROL_MODE,
    SAX_AC_POWER_TOTAL,
    SAX_NOMINAL_FACTOR,
    SAX_NOMINAL_POWER,
    SOLAR_CHARGING_MODE,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.power_manager import PowerManager, PowerManagerState
from custom_components.sax_battery.soc_manager import SOCConstraintResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

SERVICE_SET_VALUE = "set_value"

_LOGGER = logging.getLogger(__name__)


@pytest.fixture
def mock_power_manager_devices(
    hass: HomeAssistant,
) -> None:
    """Set up mock devices and entities for power manager tests."""

    real_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "battery_a_host": "192.168.1.100",
            "battery_a_port": 502,
        },
        entry_id="test_power_manager_entry",
    )
    real_entry.add_to_hass(hass)

    # Get registries
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    # Create device in registry
    device = dev_reg.async_get_or_create(
        config_entry_id=real_entry.entry_id,
        identifiers={(DOMAIN, "test_cluster")},
        name="SAX Cluster",
        manufacturer="SAX",
        model="Battery System",
    )

    # Register entities...
    ent_reg.async_get_or_create(
        "number",
        DOMAIN,
        f"test_cluster_{SAX_NOMINAL_POWER}",
        suggested_object_id=f"sax_cluster_{SAX_NOMINAL_POWER}",
        config_entry=real_entry,
        device_id=device.id,
    )

    ent_reg.async_get_or_create(
        "number",
        DOMAIN,
        f"test_cluster_{SAX_NOMINAL_FACTOR}",
        suggested_object_id=f"sax_cluster_{SAX_NOMINAL_FACTOR}",
        config_entry=real_entry,
        device_id=device.id,
    )


class TestPowerManagerInitialization:
    """Test PowerManager initialization."""

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
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
                CONF_AUTO_PILOT_INTERVAL: 10,
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
        expected_max_discharge = 3 * LIMIT_MAX_CHARGE_PER_BATTERY
        expected_max_charge = 3 * LIMIT_MAX_DISCHARGE_PER_BATTERY
        assert power_manager.max_discharge_power == expected_max_discharge
        assert power_manager.max_charge_power == expected_max_charge
        assert power_manager._state.solar_charging_enabled is False

    def test_configuration_update(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test configuration values are properly loaded."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
                CONF_AUTO_PILOT_INTERVAL: 15,
                SOLAR_CHARGING_MODE: True,
                CONF_MANUAL_CONTROL: False,
            },
        )
        entry.add_to_hass(hass)

        # Mock SAXBatteryData.get_unique_id_for_item to return valid unique IDs
        mock_sax_data = MagicMock()
        mock_sax_data.get_unique_id_for_item.return_value = "test_power_entity"
        mock_coordinator_master.sax_data = mock_sax_data

        # Register entities in entity registry
        ent_reg = er.async_get(hass)
        ent_reg.async_get_or_create(
            "number",
            DOMAIN,
            "test_power_entity",
            suggested_object_id="sax_nominal_power",
        )

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        # manual power control should be disabled due to solar charging enabled
        assert power_manager.grid_power_sensor == "sensor.grid_power"
        assert power_manager.update_interval == 15
        assert power_manager._state.manual_control_enabled is False


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


class TestSolarChargingMode:
    """Test solar charging mode functionality."""

    @pytest.mark.skip("fix mock line 345")
    async def test_solar_charging_update_with_valid_grid_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test solar charging update with valid grid sensor.

        Security:
            OWASP A05: Validates proper state machine access and SOC constraints
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        # Mock grid sensor state
        hass.states.async_set("sensor.grid_power", "-1000")  # 1kW export

        # Mock SOC manager
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type: ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                constrained_value=1000,
                reason=None,
            )
        )

        # Mock coordinator.data for SAX_AC_POWER_TOTAL
        mock_battery_item = MagicMock()
        mock_battery_item.item = MagicMock()
        mock_coordinator_master.data = {
            SAX_AC_POWER_TOTAL: mock_battery_item,
        }

        # Mock entity registry for battery power lookup
        with patch("homeassistant.helpers.entity_registry.async_get") as mock_ent_reg:
            mock_reg = MagicMock()
            mock_reg.async_get_entity_id = MagicMock(
                return_value="sensor.battery_a_ac_power_total"
            )
            mock_ent_reg.return_value = mock_reg

            # Mock sax_data.get_unique_id_for_item
            mock_coordinator_master.sax_data.get_unique_id_for_item.return_value = (  # type: ignore[attr-defined]
                "battery_a_ac_power_total"
            )

            # Mock battery power state in state machine
            hass.states.async_set(
                "sensor.battery_a_ac_power_total", "500"
            )  # 500W discharging

            power_manager = PowerManager(
                hass=hass,
                coordinator=mock_coordinator_master,
                config_entry=entry,
            )
            power_manager._state.solar_charging_enabled = True

            with patch.object(
                power_manager, "update_power_setpoint", new=AsyncMock()
            ) as mock_update:
                await power_manager._update_solar_charging_power()

                mock_update.assert_called_once()

                # Verify calculation: current_battery (500W) - grid_power (-1000W) = 1500W
                # Then constrained to 1000W by SOC manager
                call_args = mock_update.call_args[0]
                assert call_args[0] == 1000

    async def test_solar_charging_with_unavailable_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test solar charging handles unavailable sensor."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
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
        power_manager._state.solar_charging_enabled = True

        with patch.object(
            power_manager, "update_power_setpoint", new=AsyncMock()
        ) as mock_update:
            await power_manager._update_solar_charging_power()

            # Should not update power when sensor unavailable
            mock_update.assert_not_called()

    async def test_solar_charging_with_missing_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test solar charging handles missing sensor."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_GRID_POWER_SENSOR: "sensor.nonexistent",
            },
        )
        entry.add_to_hass(hass)

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.solar_charging_enabled = True

        with patch.object(
            power_manager, "update_power_setpoint", new=AsyncMock()
        ) as mock_update:
            await power_manager._update_solar_charging_power()

            mock_update.assert_not_called()

    async def test_solar_charging_with_invalid_sensor_value(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test solar charging handles invalid sensor value."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "invalid_value")

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.solar_charging_enabled = True

        with patch.object(
            power_manager, "update_power_setpoint", new=AsyncMock()
        ) as mock_update:
            await power_manager._update_solar_charging_power()

            mock_update.assert_not_called()

    @pytest.mark.skip("fix mock line 510")
    async def test_solar_charging_applies_soc_constraints(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test solar charging applies SOC constraints.

        Security:
            OWASP A05: Validates SOC constraint enforcement in solar charging
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        # Mock grid sensor state
        hass.states.async_set("sensor.grid_power", "-5000")  # 5kW export

        # Mock SOC manager to constrain power
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                constrained_value=2000,  # Constrained
                reason="SOC too high",
            )
        )

        # Mock coordinator.data for SAX_AC_POWER_TOTAL
        mock_battery_item = MagicMock()
        mock_battery_item.item = MagicMock()
        mock_coordinator_master.data = {
            SAX_AC_POWER_TOTAL: mock_battery_item,
        }

        # Mock entity registry for battery power lookup
        with patch("homeassistant.helpers.entity_registry.async_get") as mock_ent_reg:
            mock_reg = MagicMock()
            mock_reg.async_get_entity_id = MagicMock(
                return_value="sensor.battery_a_ac_power_total"
            )
            mock_ent_reg.return_value = mock_reg

            # Mock sax_data.get_unique_id_for_item
            mock_coordinator_master.sax_data.get_unique_id_for_item.return_value = (  # type: ignore[attr-defined]
                "battery_a_ac_power_total"
            )

            # Mock battery power state in state machine
            hass.states.async_set(
                "sensor.battery_a_ac_power_total", "1000"
            )  # 1kW discharging

            power_manager = PowerManager(
                hass=hass,
                coordinator=mock_coordinator_master,
                config_entry=entry,
            )
            power_manager._state.solar_charging_enabled = True

            with patch.object(
                power_manager, "update_power_setpoint", new=AsyncMock()
            ) as mock_update:
                await power_manager._update_solar_charging_power()

                # Should use constrained value
                mock_update.assert_called_once_with(2000)

                # Verify SOC manager was called with calculated power
                # current_battery (1000W) - grid_power (-5000W) = 6000W (before constraint)
                mock_coordinator_master.soc_manager.apply_constraints.assert_called_once()


class TestModeTransitions:
    """Test mode transition functionality."""

    async def test_solar_to_manual_transition(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test transition from solar charging to manual control.

        Verifies that enabling manual control automatically disables solar charging.
        """
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                constrained_value=1000,
            )
        )

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # Enable solar charging
        await power_manager.set_solar_charging_mode(True)
        assert power_manager._state.solar_charging_enabled is True
        assert power_manager._state.manual_control_enabled is False

        # Enable manual control (should automatically disable solar)
        with patch.object(power_manager, "update_power_setpoint", new=AsyncMock()):
            await power_manager.set_manual_control_mode(True, 1000)

            # Manual control enabled, solar charging disabled
            assert power_manager._state.manual_control_enabled is True
            assert power_manager._state.solar_charging_enabled is False
            assert power_manager._state.mode == "manual_control"

    async def test_manual_to_solar_transition(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test transition from manual control to solar charging.

        Verifies that enabling solar charging automatically disables manual control.
        """
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # Enable manual control
        with patch.object(power_manager, "update_power_setpoint", new=AsyncMock()):
            await power_manager.set_manual_control_mode(True, 1000)
            assert power_manager._state.manual_control_enabled is True
            assert power_manager._state.solar_charging_enabled is False

        # Enable solar charging (should automatically disable manual control)
        await power_manager.set_solar_charging_mode(True)

        # Solar enabled, manual control disabled
        assert power_manager._state.solar_charging_enabled is True
        assert power_manager._state.manual_control_enabled is False
        assert power_manager._state.mode == "solar_charging"


class TestConfigurationUpdates:
    """Test configuration update handling."""

    async def test_config_entry_update(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test handling of config entry updates."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_AUTO_PILOT_INTERVAL: 10,
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        # Create updated entry
        updated_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_AUTO_PILOT_INTERVAL: 20,
                CONF_GRID_POWER_SENSOR: "sensor.new_grid_power",
            },
        )
        updated_entry.add_to_hass(hass)

        with patch.object(power_manager, "_async_update_power", new=AsyncMock()):
            await power_manager._async_config_updated(hass, updated_entry)

            assert power_manager.update_interval == 20
            assert power_manager.grid_power_sensor == "sensor.new_grid_power"


class TestPowerManagerProperties:
    """Test PowerManager property accessors."""

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

        assert power_manager.current_mode == MANUAL_CONTROL_MODE

        power_manager._state.mode = SOLAR_CHARGING_MODE
        assert power_manager.current_mode == SOLAR_CHARGING_MODE

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
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "-1000")

        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            side_effect=OSError("Network error")
        )

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.solar_charging_enabled = True

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
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "-1000")

        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            side_effect=ValueError("Invalid value")
        )

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )
        power_manager._state.solar_charging_enabled = True

        # Should not raise exception
        await power_manager._async_update_power(None)


class TestPowerManagerState:
    """Test PowerManagerState dataclass."""

    def test_state_initialization(self) -> None:
        """Test PowerManagerState initialization."""
        state = PowerManagerState(
            mode=SOLAR_CHARGING_MODE,
            target_power=1500.0,
            last_update=datetime.now(),
        )

        assert state.mode == SOLAR_CHARGING_MODE
        assert state.target_power == 1500.0
        assert state.solar_charging_enabled is False
        assert state.manual_control_enabled is False

    def test_state_with_flags(self) -> None:
        """Test PowerManagerState with mode flags."""
        state = PowerManagerState(
            mode=MANUAL_CONTROL_MODE,
            target_power=0.0,
            last_update=datetime.now(),
            solar_charging_enabled=False,
            manual_control_enabled=True,
        )

        assert state.mode == MANUAL_CONTROL_MODE
        assert state.manual_control_enabled is True
        assert state.solar_charging_enabled is False
