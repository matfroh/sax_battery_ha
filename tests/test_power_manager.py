"""Test power manager for SAX Battery integration."""

from __future__ import annotations

from datetime import datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

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
    SOLAR_CHARGING_MODE,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.power_manager import PowerManager, PowerManagerState
from custom_components.sax_battery.soc_manager import SOCConstraintResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)


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

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=entry,
        )

        assert power_manager.grid_power_sensor == "sensor.grid_power"
        assert power_manager.update_interval == 15
        assert power_manager._state.solar_charging_enabled is True
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

    async def test_solar_charging_update_with_valid_grid_sensor(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test solar charging update with valid grid sensor."""
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
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                original_value=1000,
                constrained_value=1000,
                reason=None,
            )
        )

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
            # Grid power -1000W -> target power 1000W (charge)
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

    async def test_solar_charging_applies_soc_constraints(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
    ) -> None:
        """Test solar charging applies SOC constraints."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_GRID_POWER_SENSOR: "sensor.grid_power",
            },
        )
        entry.add_to_hass(hass)

        hass.states.async_set("sensor.grid_power", "-5000")  # 5kW export

        # Mock SOC manager to constrain power
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                original_value=5000,
                constrained_value=2000,  # Constrained
                reason="SOC too high",
            )
        )

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


class TestManualControlMode:
    """Test manual control mode functionality."""

    async def test_enable_manual_control_mode(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test enabling manual control mode."""
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                original_value=1500,
                constrained_value=1500,
            )
        )

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        with patch.object(
            power_manager, "update_power_setpoint", new=AsyncMock()
        ) as mock_update:
            await power_manager.set_manual_control_mode(True, 1500)

            assert power_manager._state.manual_control_enabled is True
            assert power_manager._state.mode == MANUAL_CONTROL_MODE
            mock_update.assert_called_once_with(1500)

    async def test_manual_control_prevents_solar_charging(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test manual control prevents solar charging activation."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # Enable manual control first
        power_manager._state.manual_control_enabled = True

        # Try to enable solar charging
        await power_manager.set_solar_charging_mode(True)

        # Solar charging should not be enabled
        assert power_manager._state.solar_charging_enabled is False

    async def test_manual_control_applies_soc_constraints(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test manual control applies SOC constraints."""
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                original_value=3000,
                constrained_value=2000,  # Constrained
                reason="SOC protection",
            )
        )

        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        with patch.object(
            power_manager, "update_power_setpoint", new=AsyncMock()
        ) as mock_update:
            await power_manager.set_manual_control_mode(True, 3000)

            # Should use constrained value
            mock_update.assert_called_once_with(2000)


class TestPowerSetpointUpdate:
    """Test power setpoint update functionality."""

    async def test_update_power_setpoint_valid_value(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test updating power setpoint with valid value."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # Track service calls
        service_calls: list[ServiceCall] = []

        async def mock_service_handler(call: ServiceCall) -> None:
            """Mock service handler for number.set_value."""
            service_calls.append(call)

        # Register mock for number.set_value service
        hass.services.async_register(
            "number",
            "set_value",
            mock_service_handler,
        )

        await power_manager.update_power_setpoint(1500)

        assert power_manager._state.target_power == 1500
        assert len(service_calls) == 1
        # Verify service was called with correct parameters
        assert service_calls[0].data["value"] == 1500
        assert "sax_nominal_power" in service_calls[0].data["entity_id"]

    async def test_update_power_setpoint_clamping(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test power setpoint clamping to battery limits."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # Track service calls
        service_calls: list[ServiceCall] = []

        async def mock_service_handler(call: ServiceCall) -> None:
            """Mock service handler for number.set_value."""
            service_calls.append(call)

        # Register mock for number.set_value service
        hass.services.async_register(
            "number",
            "set_value",
            mock_service_handler,
        )

        # Test over max charge
        max_charge = power_manager.max_charge_power
        await power_manager.update_power_setpoint(max_charge + 1000)
        assert power_manager._state.target_power == max_charge

        # Test over max discharge
        max_discharge = power_manager.max_discharge_power
        await power_manager.update_power_setpoint(-max_discharge - 1000)
        assert power_manager._state.target_power == -max_discharge

        # Should have made 2 service calls
        assert len(service_calls) == 2
        # Verify clamped values were used
        assert service_calls[0].data["value"] == max_charge
        assert service_calls[1].data["value"] == -max_discharge

    async def test_update_power_setpoint_invalid_type(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test power setpoint rejects invalid type."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # Track service calls
        service_calls: list[ServiceCall] = []

        async def mock_service_handler(call: ServiceCall) -> None:
            """Mock service handler for number.set_value."""
            service_calls.append(call)

        # Register mock for number.set_value service
        hass.services.async_register(
            "number",
            "set_value",
            mock_service_handler,
        )

        await power_manager.update_power_setpoint("invalid")  # type: ignore[arg-type]

        # Should not call service with invalid type
        assert len(service_calls) == 0


class TestModeTransitions:
    """Test mode transition functionality."""

    async def test_solar_to_manual_transition(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test transition from solar charging to manual control.

        Note: Current implementation prevents manual control when solar charging is active.
        This test verifies that behavior is enforced.
        """
        mock_coordinator_master.soc_manager.apply_constraints = AsyncMock(  # type:ignore[method-assign]
            return_value=SOCConstraintResult(
                allowed=True,
                original_value=1000,
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

        # Try to enable manual control (should be prevented by current implementation)
        with patch.object(power_manager, "update_power_setpoint", new=AsyncMock()):
            await power_manager.set_manual_control_mode(True, 1000)

            # Current implementation prevents manual control when solar is active
            assert power_manager._state.manual_control_enabled is False
            assert power_manager._state.solar_charging_enabled is True
            assert power_manager._state.mode == SOLAR_CHARGING_MODE

    async def test_manual_to_solar_transition(
        self,
        hass: HomeAssistant,
        mock_coordinator_master: SAXBatteryCoordinator,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test transition from manual control to solar charging."""
        power_manager = PowerManager(
            hass=hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )

        # Enable manual control
        power_manager._state.manual_control_enabled = True

        # Try to enable solar charging
        await power_manager.set_solar_charging_mode(True)

        # Solar should not be enabled due to manual control
        assert power_manager._state.solar_charging_enabled is False
        assert power_manager._state.manual_control_enabled is True


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
