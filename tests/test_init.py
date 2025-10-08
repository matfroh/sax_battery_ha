"""Test SAX Battery integration initialization."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# custom_component cannot use "from tests.common import MockConfigEntry"
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sax_battery import (
    _get_battery_configurations,
    _log_comprehensive_setup_summary,
    _log_registry_state_before_setup,
    _setup_battery_coordinator,
    _validate_battery_config,
    _validate_host,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.sax_battery.const import (
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_ENABLED,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_BATTERY_PORT,
    CONF_MASTER_BATTERY,
    CONF_PILOT_FROM_HA,
    DOMAIN,
)
from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.models import SAXBatteryData
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

_LOGGER = logging.getLogger(__name__)


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_single_battery_success(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test successful setup with single battery."""
        # Create new entry with proper data instead of modifying existing
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )
        entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ) as mock_forward,
        ):
            result = await async_setup_entry(hass, entry)
            assert result is True
            mock_forward.assert_called_once()

    async def test_setup_multi_battery_success(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test successful setup with multiple batteries."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERIES: {
                    "battery_a": {
                        CONF_BATTERY_HOST: "192.168.1.100",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: True,
                        CONF_BATTERY_PHASE: "L1",
                        CONF_BATTERY_ENABLED: True,
                    },
                    "battery_b": {
                        CONF_BATTERY_HOST: "192.168.1.101",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: False,
                        CONF_BATTERY_PHASE: "L2",
                        CONF_BATTERY_ENABLED: True,
                    },
                    "battery_c": {
                        CONF_BATTERY_HOST: "192.168.1.102",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: False,
                        CONF_BATTERY_PHASE: "L3",
                        CONF_BATTERY_ENABLED: True,
                    },
                },
            },
        )
        entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ),
        ):
            result = await async_setup_entry(hass, entry)
            assert result is True
            assert len(hass.data[DOMAIN][entry.entry_id]["coordinators"]) == 3

    async def test_setup_with_power_manager_enabled(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test setup with power manager enabled."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
                CONF_PILOT_FROM_HA: True,
            },
        )
        entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch(
                "custom_components.sax_battery.PowerManager.async_start",
                new=AsyncMock(),
            ) as mock_power_manager_start,
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ),
        ):
            result = await async_setup_entry(hass, entry)
            assert result is True
            mock_power_manager_start.assert_called_once()

    async def test_setup_with_disabled_battery(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test setup with disabled battery."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERIES: {
                    "battery_a": {
                        CONF_BATTERY_HOST: "192.168.1.100",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: True,
                        CONF_BATTERY_PHASE: "L1",
                        CONF_BATTERY_ENABLED: False,
                    },
                },
            },
        )
        entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    async def test_setup_connection_failure(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test setup with connection failure."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )
        entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=False,
            ),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, entry)

    async def test_setup_initial_refresh_failure(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test setup with initial refresh failure."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )
        entry.add_to_hass(hass)

        with (  # noqa: SIM117
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                side_effect=Exception("Refresh failed"),
            ),
        ):
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

    async def test_setup_no_valid_batteries(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test setup with no valid battery configurations."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 0,
            },
        )
        entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    async def test_setup_all_batteries_disabled(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test setup when all batteries are disabled."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERIES: {
                    "battery_a": {
                        CONF_BATTERY_HOST: "192.168.1.100",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: True,
                        CONF_BATTERY_PHASE: "L1",
                        CONF_BATTERY_ENABLED: False,
                    },
                },
            },
        )
        entry.add_to_hass(hass)

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)


class TestAsyncUnloadEntry:
    """Test async_unload_entry function."""

    async def test_unload_success(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test successful unload."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )
        entry.add_to_hass(hass)

        # Setup first
        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ),
        ):
            await async_setup_entry(hass, entry)

        # Then unload
        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=True
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True
            assert entry.entry_id not in hass.data[DOMAIN]

    async def test_unload_with_power_manager(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test unload with power manager."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
                CONF_PILOT_FROM_HA: True,
            },
        )
        entry.add_to_hass(hass)

        # Setup with power manager
        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch(
                "custom_components.sax_battery.PowerManager.async_start",
                new=AsyncMock(),
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ),
        ):
            await async_setup_entry(hass, entry)

        # Unload with power manager stop
        with (
            patch.object(
                hass.config_entries, "async_unload_platforms", return_value=True
            ),
            patch(
                "custom_components.sax_battery.PowerManager.async_stop",
                new=AsyncMock(),
            ) as mock_power_manager_stop,
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True
            mock_power_manager_stop.assert_called_once()

    async def test_unload_multiple_batteries(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test unload with multiple batteries."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERIES: {
                    "battery_a": {
                        CONF_BATTERY_HOST: "192.168.1.100",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: True,
                        CONF_BATTERY_PHASE: "L1",
                        CONF_BATTERY_ENABLED: True,
                    },
                    "battery_b": {
                        CONF_BATTERY_HOST: "192.168.1.101",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: False,
                        CONF_BATTERY_PHASE: "L2",
                        CONF_BATTERY_ENABLED: True,
                    },
                },
            },
        )
        entry.add_to_hass(hass)

        # Setup
        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ),
        ):
            await async_setup_entry(hass, entry)

        # Unload
        with (
            patch.object(
                hass.config_entries, "async_unload_platforms", return_value=True
            ),
            patch(
                "custom_components.sax_battery.ModbusAPI.close",
                return_value=True,
            ) as mock_close,
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True
            assert mock_close.call_count == 2  # Two batteries

    async def test_unload_connection_close_failure(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test unload with connection close failure."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )
        entry.add_to_hass(hass)

        # Setup
        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ),
        ):
            await async_setup_entry(hass, entry)

        # Unload with close failure
        with (
            patch.object(
                hass.config_entries, "async_unload_platforms", return_value=True
            ),
            patch(
                "custom_components.sax_battery.ModbusAPI.close",
                return_value=False,
            ),
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True  # Should still succeed despite close failure

    async def test_unload_platform_failure(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test unload with platform unload failure."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )
        entry.add_to_hass(hass)

        # Setup
        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new=AsyncMock(),
            ),
        ):
            await async_setup_entry(hass, entry)

        # Unload with platform failure
        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=False
        ):
            result = await async_unload_entry(hass, entry)
            assert result is False
            # Data should not be removed on failure
            assert entry.entry_id in hass.data[DOMAIN]

    async def test_unload_no_integration_data(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test unload when no integration data exists."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )
        entry.add_to_hass(hass)

        # Don't setup, try to unload directly
        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=True
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True


class TestGetBatteryConfigurations:
    """Test _get_battery_configurations function."""

    async def test_nested_configuration_format(
        self, mock_config_entry: ConfigEntry
    ) -> None:
        """Test nested configuration format."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERIES: {
                    "battery_a": {
                        CONF_BATTERY_HOST: "192.168.1.100",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: True,
                        CONF_BATTERY_PHASE: "L1",
                        CONF_BATTERY_ENABLED: True,
                    },
                },
            },
        )

        configs = await _get_battery_configurations(entry)
        assert len(configs) == 1
        assert "battery_a" in configs
        assert configs["battery_a"][CONF_BATTERY_HOST] == "192.168.1.100"

    async def test_legacy_configuration_format(
        self, mock_config_entry: ConfigEntry
    ) -> None:
        """Test legacy configuration format."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
                "battery_a_host": "192.168.1.100",
                "battery_a_port": 502,
            },
        )

        configs = await _get_battery_configurations(entry)
        assert len(configs) == 1
        assert "battery_a" in configs

    async def test_configuration_with_invalid_battery(
        self, mock_config_entry: ConfigEntry
    ) -> None:
        """Test configuration with invalid battery."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERIES: {
                    "battery_a": {
                        CONF_BATTERY_HOST: "192.168.1.100",
                        CONF_BATTERY_PORT: 502,
                        CONF_BATTERY_IS_MASTER: True,
                        CONF_BATTERY_PHASE: "L1",
                        CONF_BATTERY_ENABLED: True,
                    },
                    "battery_invalid": {
                        CONF_BATTERY_HOST: "invalid",
                        CONF_BATTERY_PORT: 99999,
                    },
                },
            },
        )

        configs = await _get_battery_configurations(entry)
        assert len(configs) == 1  # Only valid battery
        assert "battery_a" in configs
        assert "battery_invalid" not in configs


class TestValidateBatteryConfig:
    """Test _validate_battery_config function."""

    def test_valid_configuration(self) -> None:
        """Test valid configuration."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
            CONF_BATTERY_IS_MASTER: True,
            CONF_BATTERY_PHASE: "L1",
            CONF_BATTERY_ENABLED: True,
        }
        assert _validate_battery_config("battery_a", config) is True

    def test_invalid_battery_id(self) -> None:
        """Test invalid battery ID."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
        }
        assert _validate_battery_config("battery_invalid", config) is False

    def test_missing_required_keys(self) -> None:
        """Test missing required keys."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            # Missing port
        }
        assert _validate_battery_config("battery_a", config) is False

    def test_invalid_host_format(self) -> None:
        """Test invalid host format."""
        config = {
            CONF_BATTERY_HOST: "",  # Empty host
            CONF_BATTERY_PORT: 502,
        }
        assert _validate_battery_config("battery_a", config) is False

    def test_invalid_port_range(self) -> None:
        """Test invalid port range."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 99999,  # Out of range
        }
        assert _validate_battery_config("battery_a", config) is False

    def test_invalid_port_type(self) -> None:
        """Test invalid port type."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: "not_a_number",
        }
        assert _validate_battery_config("battery_a", config) is False

    def test_invalid_phase(self) -> None:
        """Test invalid phase."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
            CONF_BATTERY_PHASE: "L4",  # Invalid phase
        }
        assert _validate_battery_config("battery_a", config) is False

    def test_invalid_boolean_fields(self) -> None:
        """Test invalid boolean fields."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
            CONF_BATTERY_ENABLED: "not_a_bool",
        }
        assert _validate_battery_config("battery_a", config) is False

    def test_port_string_conversion(self) -> None:
        """Test port string to int conversion."""
        config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: "502",  # String port
        }
        assert _validate_battery_config("battery_a", config) is True


class TestValidateHostFormat:
    """Test _validate_host function."""

    def test_valid_ipv4(self) -> None:
        """Test valid IPv4 address."""
        assert _validate_host("192.168.1.100") is True
        assert _validate_host("10.0.0.1") is True
        assert _validate_host("255.255.255.255") is True

    def test_valid_hostname(self) -> None:
        """Test validation of valid hostnames."""
        assert _validate_host("battery-server") is True
        assert _validate_host("sax-battery.example.com") is True
        assert _validate_host("battery.local") is True

    def test_invalid_empty_host(self) -> None:
        """Test invalid empty host."""
        assert _validate_host("") is False

    def test_invalid_too_long_hostname(self) -> None:
        """Test invalid too long hostname."""
        assert _validate_host("a" * 254) is False

    def test_invalid_ipv4_format(self) -> None:
        """Test invalid IPv4 format."""
        assert _validate_host("256.1.1.1") is False
        assert _validate_host("192.168.1") is False
        assert _validate_host("192.168.1.1.1") is False

    def test_invalid_hostname_format(self) -> None:
        """Test validation fails for invalid hostname."""
        assert _validate_host("-invalid") is False
        assert _validate_host("invalid-") is False
        assert _validate_host("in..valid") is False


class TestSetupBatteryCoordinator:
    """Test _setup_battery_coordinator function."""

    async def test_coordinator_setup_success(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test successful coordinator setup."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
            },
        )

        battery_config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
            CONF_BATTERY_IS_MASTER: True,
            CONF_BATTERY_PHASE: "L1",
        }

        # Create SAXBatteryData
        sax_data = SAXBatteryData(hass, entry)

        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=True,
            ),
            patch(
                "custom_components.sax_battery.SAXBatteryCoordinator.async_config_entry_first_refresh",
                return_value=None,
            ),
        ):
            coordinator = await _setup_battery_coordinator(
                hass, entry, sax_data, "battery_a", battery_config
            )
            assert coordinator is not None
            assert coordinator.battery_id == "battery_a"

    async def test_coordinator_setup_invalid_host(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test coordinator setup with invalid host."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
            },
        )

        battery_config = {
            CONF_BATTERY_HOST: "",  # Invalid host
            CONF_BATTERY_PORT: 502,
        }

        sax_data = SAXBatteryData(hass, entry)

        with pytest.raises(ConfigEntryNotReady):
            await _setup_battery_coordinator(
                hass, entry, sax_data, "battery_a", battery_config
            )

    async def test_coordinator_setup_invalid_port(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test coordinator setup with invalid port."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
            },
        )

        battery_config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 99999,  # Invalid port
        }

        sax_data = SAXBatteryData(hass, entry)

        with pytest.raises(ConfigEntryNotReady):
            await _setup_battery_coordinator(
                hass, entry, sax_data, "battery_a", battery_config
            )

    async def test_coordinator_setup_connection_failure(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test coordinator setup with connection failure."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
                CONF_MASTER_BATTERY: "battery_a",
            },
        )

        battery_config = {
            CONF_BATTERY_HOST: "192.168.1.100",
            CONF_BATTERY_PORT: 502,
        }

        sax_data = SAXBatteryData(hass, entry)

        with (
            patch(
                "custom_components.sax_battery.ModbusAPI.connect",
                return_value=False,
            ),
            pytest.raises(ConfigEntryNotReady),
        ):
            await _setup_battery_coordinator(
                hass, entry, sax_data, "battery_a", battery_config
            )


class TestLoggingFunctions:
    """Test logging utility functions."""

    async def test_log_registry_state_before_setup(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test _log_registry_state_before_setup function."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
            },
        )

        mock_coordinator_a = MagicMock(spec=SAXBatteryCoordinator)
        coordinators: dict[str, SAXBatteryCoordinator] = {
            "battery_a": mock_coordinator_a,
        }

        sax_data = SAXBatteryData(hass, entry)

        # Should not raise exception
        await _log_registry_state_before_setup(hass, entry, coordinators, sax_data)

    @pytest.mark.skip("mock is not correct")
    async def test_log_comprehensive_setup_summary(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Test _log_comprehensive_setup_summary function."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_BATTERY_COUNT: 1,
            },
        )

        mock_coordinator_a = MagicMock(spec=SAXBatteryCoordinator)
        coordinators: dict[str, SAXBatteryCoordinator] = {
            "battery_a": mock_coordinator_a,
        }

        config_data = {
            CONF_BATTERY_COUNT: 1,
        }

        # Should not raise exception
        await _log_comprehensive_setup_summary(hass, entry, coordinators, config_data)
