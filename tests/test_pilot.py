"""Comprehensive tests for the SAX Battery pilot platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.const import (
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    CONF_PRIORITY_DEVICES,
    DOMAIN,
    SAX_COMBINED_SOC,
)
from custom_components.sax_battery.pilot import (
    SAXBatteryPilot,
    SAXBatteryPilotPowerEntity,
    SAXBatterySolarChargingSwitch,
    async_setup_pilot,
)
from homeassistant.components.number import NumberMode
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant


@pytest.fixture(name="mock_sax_pilot_entry_enabled")
def mock_sax_pilot_entry_enabled_fixture():
    """Mock SAX Battery config entry with pilot enabled."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_pilot_entry_enabled"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 2,
        CONF_PILOT_FROM_HA: True,
        CONF_AUTO_PILOT_INTERVAL: 60,
        CONF_MIN_SOC: 20,
        CONF_ENABLE_SOLAR_CHARGING: True,
        CONF_MANUAL_CONTROL: False,
        CONF_POWER_SENSOR: "sensor.grid_power",
        CONF_PF_SENSOR: "sensor.grid_pf",
        CONF_PRIORITY_DEVICES: ["sensor.priority_device1", "sensor.priority_device2"],
    }
    return mock_entry


@pytest.fixture(name="mock_sax_pilot_entry_disabled")
def mock_sax_pilot_entry_disabled_fixture():
    """Mock SAX Battery config entry with pilot disabled."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_pilot_entry_disabled"
    mock_entry.data = {
        "host": "192.168.1.100",
        "port": 502,
        "device_id": 64,
        "battery_count": 1,
        CONF_PILOT_FROM_HA: False,
    }
    return mock_entry


@pytest.fixture(name="mock_battery_data_pilot")
def mock_battery_data_pilot_fixture():
    """Mock SAX Battery data for pilot tests."""
    mock_battery_data = MagicMock()
    mock_battery_data.device_id = "test_device_pilot"
    mock_battery_data.master_battery_id = "battery_a"

    # Mock entry with default values (will be overridden in tests)
    mock_entry = MagicMock()
    mock_entry.data = {
        CONF_PILOT_FROM_HA: True,
        CONF_AUTO_PILOT_INTERVAL: 60,
        CONF_MIN_SOC: 20,
        CONF_ENABLE_SOLAR_CHARGING: True,
        CONF_MANUAL_CONTROL: False,
        CONF_POWER_SENSOR: "sensor.power",
        CONF_PF_SENSOR: "sensor.power_factor",
        CONF_PRIORITY_DEVICES: [],
    }
    mock_battery_data.entry = mock_entry

    # Mock coordinator with data
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        SAX_COMBINED_SOC: 85,
        "battery_a": {"sax_power": 2000, "sax_soc": 85},
        "battery_b": {"sax_power": 1800, "sax_soc": 78},
    }
    mock_battery_data.coordinator = mock_coordinator

    # Mock batteries dictionary
    mock_battery_data.batteries = {
        "battery_a": MagicMock(),
        "battery_b": MagicMock(),
    }

    # Mock modbus API
    mock_modbus_api = AsyncMock()
    mock_modbus_api.write_registers = AsyncMock(return_value=True)
    mock_battery_data.modbus_api = mock_modbus_api

    return mock_battery_data


class TestSAXBatteryPilotSetup:
    """Test SAX Battery pilot setup functionality."""

    @patch("custom_components.sax_battery.pilot.EntityComponent")
    @patch("custom_components.sax_battery.pilot.async_track_time_interval")
    async def test_pilot_setup_enabled(
        self,
        mock_track_time,
        mock_entity_component,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot setup when pilot mode is enabled."""
        # Override the entry data to ensure pilot is enabled
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        # Mock timer removal function for cleanup
        mock_remove_timer = MagicMock()
        mock_track_time.return_value = mock_remove_timer

        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_pilot_entry_enabled.entry_id] = (
            mock_battery_data_pilot
        )

        # Mock EntityComponent
        mock_component = MagicMock()
        mock_entity_component.return_value = mock_component
        mock_component.async_add_entities = AsyncMock()

        # Test setup
        result = await async_setup_pilot(hass, mock_sax_pilot_entry_enabled.entry_id)

        # Verify setup successful
        assert result is True
        assert mock_battery_data_pilot.pilot is not None
        assert isinstance(mock_battery_data_pilot.pilot, SAXBatteryPilot)

        # Verify entities were created
        mock_component.async_add_entities.assert_called_once()
        entities = mock_component.async_add_entities.call_args[0][0]
        assert len(entities) == 2
        assert any(isinstance(e, SAXBatteryPilotPowerEntity) for e in entities)
        assert any(isinstance(e, SAXBatterySolarChargingSwitch) for e in entities)

        # Clean up - stop the pilot to prevent lingering timers
        await mock_battery_data_pilot.pilot.async_stop()

    async def test_pilot_setup_disabled(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_disabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot setup when pilot mode is disabled."""
        # Override the entry data to ensure pilot is disabled
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_disabled

        # Remove any existing pilot attribute to start clean
        if hasattr(mock_battery_data_pilot, "pilot"):
            delattr(mock_battery_data_pilot, "pilot")

        # Store in hass.data
        hass.data.setdefault(DOMAIN, {})[mock_sax_pilot_entry_disabled.entry_id] = (
            mock_battery_data_pilot
        )

        # Test setup
        result = await async_setup_pilot(hass, mock_sax_pilot_entry_disabled.entry_id)

        # Verify setup was skipped
        assert result is False
        assert not hasattr(mock_battery_data_pilot, "pilot")


class TestSAXBatteryPilot:
    """Test SAX Battery pilot functionality."""

    async def test_pilot_initialization(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot initialization."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Verify initialization
        assert pilot.hass == hass
        assert pilot.sax_data == mock_battery_data_pilot
        assert pilot.entry == mock_sax_pilot_entry_enabled
        assert pilot.battery_count == 2
        assert pilot.calculated_power == 0.0
        assert pilot.max_discharge_power == 2 * 3600  # 2 batteries * 3600W
        assert pilot.max_charge_power == 2 * 4500  # 2 batteries * 4500W
        assert pilot.master_battery_id == "battery_a"
        assert pilot._running is False

    @patch("custom_components.sax_battery.pilot.async_track_time_interval")
    async def test_pilot_start_stop(
        self,
        mock_track_time,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot start and stop functionality."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        # Mock time interval tracking
        mock_remove_tracker = MagicMock()
        mock_track_time.return_value = mock_remove_tracker

        # Mock config entry listener
        mock_remove_listener = MagicMock()
        mock_sax_pilot_entry_enabled.add_update_listener.return_value = (
            mock_remove_listener
        )

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Test start
        with patch.object(pilot, "_async_update_pilot", new=AsyncMock()) as mock_update:
            await pilot.async_start()
            assert pilot._running is True
            mock_track_time.assert_called_once()
            mock_update.assert_called_once()

            # Test stop
            await pilot.async_stop()
            assert pilot._running is False
            mock_remove_tracker.assert_called_once()
            mock_remove_listener.assert_called_once()

    async def test_pilot_soc_constraints(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test SOC constraint application."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Test constraint at minimum SOC (should prevent discharge)
        mock_battery_data_pilot.coordinator.data[SAX_COMBINED_SOC] = 15  # Below min SOC
        result = await pilot._apply_soc_constraints(500)  # Positive = discharge
        assert result == 0  # Should be constrained to 0

        # Test constraint at maximum SOC (should prevent charge)
        mock_battery_data_pilot.coordinator.data[SAX_COMBINED_SOC] = 100  # At max SOC
        result = await pilot._apply_soc_constraints(-500)  # Negative = charge
        assert result == 0  # Should be constrained to 0

        # Test no constraint with normal SOC
        mock_battery_data_pilot.coordinator.data[SAX_COMBINED_SOC] = 50  # Normal SOC
        result = await pilot._apply_soc_constraints(300)
        assert result == 300  # Should pass through unchanged

    async def test_pilot_send_power_command(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test sending power commands via Modbus."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Test power command
        await pilot.send_power_command(1500.0, 0.95)

        # Verify modbus API was called with correct parameters
        mock_battery_data_pilot.modbus_api.write_registers.assert_called_once_with(
            "battery_a",  # master_battery_id
            41,  # Starting register
            [1500, 9],  # power_int=1500, pf_int=9 (0.95 * 10)
        )

    async def test_pilot_solar_charging_control(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test solar charging enable/disable functionality."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        with patch.object(pilot, "_async_update_pilot", new=AsyncMock()) as mock_update:
            # Test enable solar charging
            await pilot.set_solar_charging(True)
            assert pilot.solar_charging_enabled is True
            mock_update.assert_called_once()

            # Reset mock
            mock_update.reset_mock()

            # Test disable solar charging
            await pilot.set_solar_charging(False)
            assert pilot.solar_charging_enabled is False
            # Should send 0 power command when disabled
            mock_battery_data_pilot.modbus_api.write_registers.assert_called_with(
                "battery_a",
                41,
                [0, 10],  # 0 power, 1.0 PF
            )

    async def test_pilot_manual_power_setting(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test manual power setting functionality."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Test manual power setting
        await pilot.set_manual_power(800.0)

        # Verify power was set
        assert pilot.calculated_power == 800.0
        mock_battery_data_pilot.modbus_api.write_registers.assert_called_with(
            "battery_a",
            41,
            [800, 10],  # 800W, 1.0 PF
        )


class TestSAXBatteryPilotEntities:
    """Test SAX Battery pilot entities."""

    async def test_pilot_power_entity_properties(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot power entity properties."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)
        entity = SAXBatteryPilotPowerEntity(pilot)

        # Test properties
        assert entity.unique_id == f"{DOMAIN}_pilot_power_test_device_pilot"
        assert entity.name == "Battery Pilot Power"
        assert entity.native_unit_of_measurement == UnitOfPower.WATT
        assert entity.mode == NumberMode.BOX
        assert entity.native_min_value == -7200  # 2 batteries * 3600W
        assert entity.native_max_value == 9000  # 2 batteries * 4500W
        assert entity.native_step == 100

        # Test native_value property
        pilot.calculated_power = 1500.0
        assert entity.native_value == 1500.0

        # Test icon property
        pilot.calculated_power = 500  # Positive = charging
        assert entity.icon == "mdi:battery-charging"

        pilot.calculated_power = -500  # Negative = discharging
        assert entity.icon == "mdi:battery-minus"

        pilot.calculated_power = 0  # Zero = idle
        assert entity.icon == "mdi:battery"

    async def test_pilot_power_entity_set_value(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test setting value on pilot power entity."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)
        entity = SAXBatteryPilotPowerEntity(pilot)

        # Test setting value
        await entity.async_set_native_value(1200.0)

        # Verify power command was sent and value was set
        assert pilot.calculated_power == 1200.0
        mock_battery_data_pilot.modbus_api.write_registers.assert_called_with(
            "battery_a",
            41,
            [1200, 10],  # 1200W, 1.0 PF
        )

    async def test_solar_charging_switch_properties(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test solar charging switch properties."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)
        entity = SAXBatterySolarChargingSwitch(pilot)

        # Test properties
        assert entity.unique_id == f"{DOMAIN}_solar_charging_test_device_pilot"
        assert entity.name == "Solar Charging"

        # Test is_on property
        pilot.solar_charging_enabled = True
        assert entity.is_on is True
        assert entity.icon == "mdi:solar-power"

        pilot.solar_charging_enabled = False
        assert entity.is_on is False
        assert entity.icon == "mdi:solar-power-off"

    async def test_solar_charging_switch_actions(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test solar charging switch turn on/off actions."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)
        entity = SAXBatterySolarChargingSwitch(pilot)

        with patch.object(
            pilot, "set_solar_charging", new=AsyncMock()
        ) as mock_set_solar:
            # Test turn on
            await entity.async_turn_on()
            mock_set_solar.assert_called_with(True)

            # Test turn off
            await entity.async_turn_off()
            mock_set_solar.assert_called_with(False)


class TestSAXBatteryPilotIntegration:
    """Test SAX Battery pilot integration scenarios."""

    async def test_pilot_update_with_sensors(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot update calculation with sensor data."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        # Create real state objects and set them in hass
        # Set up sensor states in hass
        hass.states.async_set("sensor.grid_power", "2500", {"unit_of_measurement": "W"})
        hass.states.async_set("sensor.grid_pf", "0.95")
        hass.states.async_set(
            "sensor.priority_device1", "100", {"unit_of_measurement": "W"}
        )
        hass.states.async_set(
            "sensor.priority_device2", "50", {"unit_of_measurement": "W"}
        )
        hass.states.async_set(
            "sensor.sax_battery_combined_power", "1800", {"unit_of_measurement": "W"}
        )

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Test update pilot calculations
        await pilot._async_update_pilot()

        # Verify modbus command was sent (calculation details depend on algorithm)
        mock_battery_data_pilot.modbus_api.write_registers.assert_called()

    async def test_pilot_manual_mode(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot behavior in manual control mode."""
        # Enable manual control mode
        mock_sax_pilot_entry_enabled.data[CONF_MANUAL_CONTROL] = True
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)
        pilot.calculated_power = 1000.0  # Set some manual power

        # Test update in manual mode
        await pilot._async_update_pilot()

        # Should apply SOC constraints but not change power calculation
        # (exact behavior depends on SOC constraints)
        assert pilot.calculated_power in {1000.0, 0.0}  # If constrained

    async def test_pilot_error_handling(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test pilot error handling."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        # Make modbus API raise an error
        mock_battery_data_pilot.modbus_api.write_registers.side_effect = (
            ConnectionError("Test error")
        )

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Should not raise exception
        await pilot.send_power_command(100.0, 1.0)

        # Verify error was logged (modbus call still attempted)
        mock_battery_data_pilot.modbus_api.write_registers.assert_called_once()


class TestSAXBatteryPilotErrorHandling:
    """Test error handling scenarios for SAX Battery pilot."""

    async def test_solar_charging_switch_turn_on_error(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test solar charging switch turn on with pilot error."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)
        entity = SAXBatterySolarChargingSwitch(pilot)

        # Mock pilot set_solar_charging to raise an error
        with (
            patch.object(
                pilot, "set_solar_charging", side_effect=ConnectionError("Pilot error")
            ),
            pytest.raises(ConnectionError, match="Pilot error"),
        ):
            # Test that error is propagated (SAXBatterySolarChargingSwitch doesn't handle errors)
            await entity.async_turn_on()

    async def test_solar_charging_switch_turn_off_error(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test solar charging switch turn off with pilot error."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)
        entity = SAXBatterySolarChargingSwitch(pilot)

        # Mock pilot set_solar_charging to raise an error
        with (
            patch.object(
                pilot, "set_solar_charging", side_effect=ValueError("Invalid value")
            ),
            pytest.raises(ValueError, match="Invalid value"),
        ):
            # Test that error is propagated (SAXBatterySolarChargingSwitch doesn't handle errors)
            await entity.async_turn_off()

    async def test_pilot_soc_constraints_edge_cases(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test SOC constraint edge cases."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Test constraint at exact minimum SOC (20%) - should NOT be constrained
        # The constraint only applies when SOC < min_soc, not equal to it
        mock_battery_data_pilot.coordinator.data[SAX_COMBINED_SOC] = 20
        result = await pilot._apply_soc_constraints(100)  # Small discharge
        assert result == 100  # Should NOT be constrained at exactly min_soc

        # Test constraint below minimum SOC (19%) - should be constrained
        mock_battery_data_pilot.coordinator.data[SAX_COMBINED_SOC] = 19
        result = await pilot._apply_soc_constraints(100)  # Small discharge
        assert result == 0  # Should be constrained

        # Test constraint at maximum SOC (100%) for charging
        mock_battery_data_pilot.coordinator.data[SAX_COMBINED_SOC] = 100
        result = await pilot._apply_soc_constraints(-100)  # Charging
        assert result == 0  # Should be constrained

    async def test_pilot_send_power_command_edge_cases(
        self,
        hass: HomeAssistant,
        mock_sax_pilot_entry_enabled,
        mock_battery_data_pilot,
    ) -> None:
        """Test sending power commands with edge cases."""
        mock_battery_data_pilot.entry = mock_sax_pilot_entry_enabled

        pilot = SAXBatteryPilot(hass, mock_battery_data_pilot)

        # Test with negative power (this gets masked to unsigned 16-bit)
        await pilot.send_power_command(-2000.0, 0.95)
        # -2000 & 0xFFFF = 63536 (two's complement 16-bit representation)
        mock_battery_data_pilot.modbus_api.write_registers.assert_called_with(
            "battery_a",
            41,
            [63536, 9],  # pf_int = 0.95 * 10 = 9
        )
