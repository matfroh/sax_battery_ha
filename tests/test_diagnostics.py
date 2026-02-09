"""Tests for SAX Battery diagnostics platform.

Security:
    OWASP A02: Validates sensitive data redaction in diagnostics output
    OWASP A05: Validates graceful handling of missing/broken components
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from custom_components.sax_battery.const import (
    CONF_CONTROL_POWER,
    CONF_ENABLE_GRID_CHARGING,
    CONF_LIMIT_POWER,
    CONF_MANUAL_CONTROL,
    CONF_MIN_SOC,
    CONF_POWER_SENSOR,
    DEFAULT_MIN_SOC,
    DOMAIN,
    PV_CHARGING_MODE,
)
from custom_components.sax_battery.diagnostics import (
    _get_coordinator_diagnostics,
    _redact_battery_config,
    async_get_config_entry_diagnostics,
)
from custom_components.sax_battery.modbusobject import ModbusAPI, OperationStatus
from custom_components.sax_battery.power_manager import PowerManager
from custom_components.sax_battery.soc_manager import SOCManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_hass_diagnostics():
    """Create mock Home Assistant instance for diagnostics tests."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def mock_entry_diagnostics():
    """Create mock config entry for diagnostics tests."""
    entry = MagicMock()
    entry.entry_id = "diag_entry_id"
    entry.data = {
        "battery_a_host": "192.168.1.100",
        "battery_a_port": 502,
        "battery_b_host": "192.168.1.101",
        "battery_b_port": 502,
        "batteries": {
            "bess_a": {
                "host": "192.168.1.100",
                "port": 502,
                "is_master": True,
                "phase": "L1",
                "enabled": True,
            },
            "bess_b": {
                "host": "192.168.1.101",
                "port": 502,
                "is_master": False,
                "phase": "L2",
                "enabled": True,
            },
        },
        CONF_CONTROL_POWER: False,
        CONF_POWER_SENSOR: "sensor.grid_power",
        CONF_ENABLE_GRID_CHARGING: False,
        CONF_MIN_SOC: DEFAULT_MIN_SOC,
        CONF_LIMIT_POWER: True,
    }
    entry.options = {}
    return entry


@pytest.fixture
def mock_circuit_breaker_diagnostics():
    """Create mock circuit breaker with diagnostics for tests."""
    cb = MagicMock()
    cb.get_diagnostics.return_value = {
        "state": "closed",
        "consecutive_failures": 0,
        "failure_threshold": 3,
        "cooldown_seconds": 60,
        "total_failures": 2,
        "total_successes": 500,
        "total_blocked": 0,
        "recent_errors": 1,
    }
    cb.cycle_times = deque([0.5, 0.6, 0.7])
    cb.error_history = deque()
    return cb


@pytest.fixture
def mock_modbus_api_diagnostics():
    """Create mock ModbusAPI with diagnostics for tests."""
    api = MagicMock(spec=ModbusAPI)
    api.get_diagnostics.return_value = {
        "connected": True,
        "port": 502,
        "battery_id": "bess_a",
        "consecutive_failures": 0,
        "last_operation": {
            "success": True,
            "error_type": None,
            "error_message": None,
            "timestamp": "2026-02-08T10:00:00",
            "register_address": 40001,
        },
    }
    return api


@pytest.fixture
def mock_soc_manager_diagnostics():
    """Create mock SOCManager with diagnostics for tests."""
    manager = MagicMock(spec=SOCManager)
    manager.get_diagnostics.return_value = {
        "enabled": True,
        "min_soc": 15,
        "coordinator_is_master": True,
        "coordinator_battery_id": "bess_a",
        "combined_soc": 72.5,
    }
    return manager


@pytest.fixture
def mock_coordinator_diagnostics(
    mock_circuit_breaker_diagnostics,
    mock_modbus_api_diagnostics,
    mock_soc_manager_diagnostics,
):
    """Create mock coordinator with all diagnostic sub-components."""
    coordinator = MagicMock()
    coordinator.battery_id = "bess_a"
    coordinator.is_master = True
    coordinator.last_update_success = True
    coordinator.update_interval = MagicMock()
    coordinator.update_interval.__str__ = lambda s: "0:00:15"
    coordinator.last_update_success_time = datetime(2026, 2, 8, 10, 0, 0)
    coordinator._total_updates = 100
    coordinator._failed_updates = 2

    # Sub-components
    coordinator._circuit_breaker = mock_circuit_breaker_diagnostics
    coordinator._statistics = MagicMock()
    coordinator._statistics.cycle_time_statistics = {
        "average": 0.6,
        "min": 0.5,
        "max": 0.7,
        "stddev": 0.1,
        "last": 0.7,
        "errors_per_hour": 1.0,
        "circuit_breaker_open": 0.0,
    }
    coordinator.modbus_api = mock_modbus_api_diagnostics
    coordinator.soc_manager = mock_soc_manager_diagnostics

    return coordinator


@pytest.fixture
def mock_power_manager_diagnostics():
    """Create mock PowerManager with diagnostics for tests."""
    pm = MagicMock(spec=PowerManager)
    pm.get_diagnostics.return_value = {
        "running": True,
        "mode": PV_CHARGING_MODE,
        "target_power": 0.0,
        "pv_charging_enabled": False,
        "grid_charging_enabled": True,
        "last_update": "2026-02-08T10:00:00",
        "battery_count": 2,
        "ui_max_discharge_power": 9200,
        "ui_max_charge_power": 7000,
        "configured_max_charge": 3500,
        "configured_max_discharge": 4600,
        "hw_limit_charge_per_battery": 3500,
        "hw_limit_discharge_per_battery": 4600,
        "update_interval_seconds": 30.0,
    }
    return pm


# ---------------------------------------------------------------------------
# Tests: _redact_battery_config
# ---------------------------------------------------------------------------
class TestRedactBatteryConfig:
    """Tests for config data redaction."""

    def test_redacts_top_level_host(self, mock_entry_diagnostics) -> None:
        """Test that top-level host IPs are redacted.

        Security: OWASP A02 - no IP addresses exposed
        """
        result = _redact_battery_config(dict(mock_entry_diagnostics.data))

        assert result["battery_a_host"] == "**REDACTED**"
        assert result["battery_b_host"] == "**REDACTED**"

    def test_redacts_nested_battery_hosts(self, mock_entry_diagnostics) -> None:
        """Test that nested battery host IPs are redacted.

        Security: OWASP A02 - nested structures also redacted
        """
        result = _redact_battery_config(dict(mock_entry_diagnostics.data))

        assert result["batteries"]["bess_a"]["host"] == "**REDACTED**"
        assert result["batteries"]["bess_b"]["host"] == "**REDACTED**"

    def test_preserves_non_sensitive_data(self, mock_entry_diagnostics) -> None:
        """Test that non-sensitive config data is preserved."""
        result = _redact_battery_config(dict(mock_entry_diagnostics.data))

        assert result["battery_a_port"] == 502
        assert result[CONF_MIN_SOC] == DEFAULT_MIN_SOC
        assert result[CONF_LIMIT_POWER] is True

    def test_preserves_nested_battery_non_sensitive(
        self, mock_entry_diagnostics
    ) -> None:
        """Test that non-sensitive nested battery data is preserved."""
        result = _redact_battery_config(dict(mock_entry_diagnostics.data))

        assert result["batteries"]["bess_a"]["port"] == 502
        assert result["batteries"]["bess_a"]["is_master"] is True
        assert result["batteries"]["bess_a"]["phase"] == "L1"

    def test_handles_missing_batteries_key(self) -> None:
        """Test graceful handling when batteries key is absent."""
        data = {"battery_a_host": "10.0.0.1", "some_key": "value"}
        result = _redact_battery_config(data)

        assert result["battery_a_host"] == "**REDACTED**"
        assert result["some_key"] == "value"

    def test_handles_empty_config(self) -> None:
        """Test with empty config data."""
        result = _redact_battery_config({})
        assert result == {}


# ---------------------------------------------------------------------------
# Tests: _get_coordinator_diagnostics
# ---------------------------------------------------------------------------
class TestGetCoordinatorDiagnostics:
    """Tests for per-coordinator diagnostic collection."""

    def test_basic_coordinator_info(self, mock_coordinator_diagnostics) -> None:
        """Test basic coordinator info is collected."""
        result = _get_coordinator_diagnostics(mock_coordinator_diagnostics)

        assert result["battery_id"] == "bess_a"
        assert result["is_master"] is True
        assert result["last_update_success"] is True
        assert result["total_updates"] == 100
        assert result["failed_updates"] == 2

    def test_circuit_breaker_included(self, mock_coordinator_diagnostics) -> None:
        """Test circuit breaker diagnostics are included."""
        result = _get_coordinator_diagnostics(mock_coordinator_diagnostics)

        assert "circuit_breaker" in result
        assert result["circuit_breaker"]["state"] == "closed"
        assert result["circuit_breaker"]["total_successes"] == 500

    def test_cycle_time_statistics_included(self, mock_coordinator_diagnostics) -> None:
        """Test cycle time statistics are included."""
        result = _get_coordinator_diagnostics(mock_coordinator_diagnostics)

        assert "cycle_time_statistics" in result
        assert result["cycle_time_statistics"]["average"] == 0.6

    def test_modbus_diagnostics_included(self, mock_coordinator_diagnostics) -> None:
        """Test ModbusAPI diagnostics are included."""
        result = _get_coordinator_diagnostics(mock_coordinator_diagnostics)

        assert "modbus" in result
        assert result["modbus"]["connected"] is True
        assert result["modbus"]["consecutive_failures"] == 0

    def test_soc_manager_included(self, mock_coordinator_diagnostics) -> None:
        """Test SOC manager diagnostics are included."""
        result = _get_coordinator_diagnostics(mock_coordinator_diagnostics)

        assert "soc_manager" in result
        assert result["soc_manager"]["enabled"] is True
        assert result["soc_manager"]["min_soc"] == 15

    def test_handles_missing_circuit_breaker(self) -> None:
        """Test graceful handling when circuit breaker is absent."""
        coordinator = MagicMock()
        coordinator.battery_id = "bess_a"
        coordinator.is_master = False
        coordinator.last_update_success = True
        coordinator.update_interval = None
        coordinator.last_update_success_time = None
        coordinator._total_updates = 0
        coordinator._failed_updates = 0
        # No _circuit_breaker attribute
        del coordinator._circuit_breaker
        del coordinator._statistics
        del coordinator.modbus_api
        del coordinator.soc_manager

        result = _get_coordinator_diagnostics(coordinator)

        assert result["battery_id"] == "bess_a"
        assert "circuit_breaker" not in result
        assert "modbus" not in result
        assert "soc_manager" not in result

    def test_last_update_time_formatting(self) -> None:
        """Test that last_update_success_time is formatted correctly."""
        coordinator = MagicMock()
        coordinator.battery_id = "bess_b"
        coordinator.is_master = False
        coordinator.last_update_success = True
        coordinator.update_interval = None
        coordinator.last_update_success_time = datetime(2026, 1, 15, 12, 30, 0)
        coordinator._total_updates = 50
        coordinator._failed_updates = 1
        del coordinator._circuit_breaker
        del coordinator._statistics
        del coordinator.modbus_api
        del coordinator.soc_manager

        result = _get_coordinator_diagnostics(coordinator)

        assert result["last_update_success_time"] == "2026-01-15T12:30:00"


# ---------------------------------------------------------------------------
# Tests: async_get_config_entry_diagnostics
# ---------------------------------------------------------------------------
class TestAsyncGetConfigEntryDiagnostics:
    """Tests for the main diagnostics entry point."""

    @pytest.mark.asyncio
    async def test_returns_entry_data_redacted(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
        mock_coordinator_diagnostics,
    ) -> None:
        """Test that entry data is included and redacted."""
        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": mock_coordinator_diagnostics,
                    },
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert "entry_data" in result
        assert result["entry_data"]["battery_a_host"] == "**REDACTED**"

    @pytest.mark.asyncio
    async def test_returns_integration_info(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
        mock_coordinator_diagnostics,
    ) -> None:
        """Test that integration info is included."""
        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": mock_coordinator_diagnostics,
                    },
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert result["integration_info"]["domain"] == DOMAIN
        assert result["integration_info"]["entry_id"] == "diag_entry_id"

    @pytest.mark.asyncio
    async def test_returns_battery_diagnostics(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
        mock_coordinator_diagnostics,
    ) -> None:
        """Test that per-battery diagnostics are collected."""
        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": mock_coordinator_diagnostics,
                    },
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert "batteries" in result
        assert "bess_a" in result["batteries"]
        battery_a = result["batteries"]["bess_a"]
        assert battery_a["battery_id"] == "bess_a"
        assert battery_a["is_master"] is True
        assert "circuit_breaker" in battery_a
        assert "modbus" in battery_a
        assert "soc_manager" in battery_a

    @pytest.mark.asyncio
    async def test_multi_battery_diagnostics(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
        mock_coordinator_diagnostics,
    ) -> None:
        """Test diagnostics with multiple batteries."""
        # Create a second coordinator mock
        coordinator_b = MagicMock()
        coordinator_b.battery_id = "bess_b"
        coordinator_b.is_master = False
        coordinator_b.last_update_success = True
        coordinator_b.update_interval = None
        coordinator_b.last_update_success_time = None
        coordinator_b._total_updates = 50
        coordinator_b._failed_updates = 0
        del coordinator_b._circuit_breaker
        del coordinator_b._statistics
        coordinator_b.modbus_api = MagicMock()
        coordinator_b.modbus_api.get_diagnostics.return_value = {
            "connected": True,
            "port": 502,
            "battery_id": "bess_b",
            "consecutive_failures": 0,
            "last_operation": {"success": True},
        }
        del coordinator_b.soc_manager

        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": mock_coordinator_diagnostics,
                        "bess_b": coordinator_b,
                    },
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert len(result["batteries"]) == 2
        assert "bess_a" in result["batteries"]
        assert "bess_b" in result["batteries"]
        assert result["batteries"]["bess_b"]["battery_id"] == "bess_b"
        assert result["batteries"]["bess_b"]["is_master"] is False

    @pytest.mark.asyncio
    async def test_power_manager_included(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
        mock_coordinator_diagnostics,
        mock_power_manager_diagnostics,
    ) -> None:
        """Test that power manager diagnostics are included when enabled."""
        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": mock_coordinator_diagnostics,
                    },
                    "power_manager": mock_power_manager_diagnostics,
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert result["power_manager"] is not None
        assert result["power_manager"]["running"] is True
        assert result["power_manager"]["mode"] == PV_CHARGING_MODE

    @pytest.mark.asyncio
    async def test_power_manager_none_when_disabled(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
        mock_coordinator_diagnostics,
    ) -> None:
        """Test that power manager is None when not enabled."""
        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": mock_coordinator_diagnostics,
                    },
                    # No power_manager key
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert result["power_manager"] is None

    @pytest.mark.asyncio
    async def test_missing_integration_data(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
    ) -> None:
        """Test graceful handling when integration data is not found."""
        mock_hass_diagnostics.data = {}

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert "entry_data" in result
        assert result["error"] == "Integration data not found in hass.data"

    @pytest.mark.asyncio
    async def test_coordinator_exception_handled(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
    ) -> None:
        """Test graceful handling when a coordinator raises an exception.

        Security: OWASP A05 - one broken component must not crash diagnostics
        """
        broken_coordinator = MagicMock()
        # Make battery_id property raise an exception
        type(broken_coordinator).battery_id = PropertyMock(
            side_effect=RuntimeError("broken")
        )

        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": broken_coordinator,
                    },
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert result["batteries"]["bess_a"]["error"] == (
            "Failed to collect diagnostics"
        )

    @pytest.mark.asyncio
    async def test_power_manager_exception_handled(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
        mock_coordinator_diagnostics,
    ) -> None:
        """Test graceful handling when power manager raises an exception."""
        broken_pm = MagicMock()
        broken_pm.get_diagnostics.side_effect = RuntimeError("pm broken")

        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {
                        "bess_a": mock_coordinator_diagnostics,
                    },
                    "power_manager": broken_pm,
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert result["power_manager"]["error"] == ("Failed to collect diagnostics")

    @pytest.mark.asyncio
    async def test_empty_coordinators(
        self,
        mock_hass_diagnostics,
        mock_entry_diagnostics,
    ) -> None:
        """Test diagnostics with no coordinators."""
        mock_hass_diagnostics.data = {
            DOMAIN: {
                mock_entry_diagnostics.entry_id: {
                    "coordinators": {},
                },
            },
        }

        result = await async_get_config_entry_diagnostics(
            mock_hass_diagnostics, mock_entry_diagnostics
        )

        assert result["batteries"] == {}
        assert result["power_manager"] is None


# ---------------------------------------------------------------------------
# Tests: ModbusAPI.get_diagnostics
# ---------------------------------------------------------------------------
class TestModbusAPIGetDiagnostics:
    """Tests for ModbusAPI.get_diagnostics method."""

    def test_returns_connected_state(self) -> None:
        """Test that connection state is reported."""
        api = ModbusAPI(battery_id="bess_a")
        result = api.get_diagnostics()

        assert result["connected"] is False
        assert result["battery_id"] == "bess_a"

    def test_returns_last_operation(self) -> None:
        """Test that last operation status is included."""
        api = ModbusAPI(battery_id="bess_b")
        api.last_operation_status = OperationStatus(
            success=False,
            error_type="timeout",
            error_message="Connection timed out",
            timestamp=datetime(2026, 2, 8, 10, 0, 0),
            register_address=40001,
        )
        result: dict[str, Any] = api.get_diagnostics()

        assert result["last_operation"]["success"] is False
        assert result["last_operation"]["error_type"] == "timeout"
        assert result["last_operation"]["register_address"] == 40001

    def test_returns_consecutive_failures(self) -> None:
        """Test that consecutive failure count is reported."""
        api = ModbusAPI(battery_id="bess_a")
        api.consecutive_failures = 3
        result = api.get_diagnostics()

        assert result["consecutive_failures"] == 3

    def test_returns_port(self) -> None:
        """Test that port number is included."""
        api = ModbusAPI(battery_id="bess_a")
        result = api.get_diagnostics()

        assert result["port"] == 502  # DEFAULT_PORT


# ---------------------------------------------------------------------------
# Tests: SOCManager.get_diagnostics
# ---------------------------------------------------------------------------
class TestSOCManagerGetDiagnostics:
    """Tests for SOCManager.get_diagnostics method."""

    def test_returns_enabled_state(self, mock_soc_manager) -> None:
        """Test that enabled state is reported."""
        result = mock_soc_manager.get_diagnostics()

        assert result["enabled"] is True

    def test_returns_min_soc(self, mock_soc_manager) -> None:
        """Test that min_soc value is reported."""
        result = mock_soc_manager.get_diagnostics()

        assert result["min_soc"] == 20

    def test_returns_combined_soc_when_available(self, mock_soc_manager) -> None:
        """Test that combined SOC is included when coordinator has data."""
        mock_soc_manager.coordinator.data = {"sax_combined_soc": 65.0}
        result = mock_soc_manager.get_diagnostics()

        assert result["combined_soc"] == 65.0

    def test_returns_combined_soc_none_when_no_data(self, mock_soc_manager) -> None:
        """Test that combined SOC is None when no data available."""
        mock_soc_manager.coordinator.data = {}
        result = mock_soc_manager.get_diagnostics()

        assert result["combined_soc"] is None

    def test_returns_coordinator_battery_id(self, mock_soc_manager) -> None:
        """Test that coordinator battery_id is included."""
        result = mock_soc_manager.get_diagnostics()

        assert result["coordinator_battery_id"] == "bess_a"


# ---------------------------------------------------------------------------
# Tests: PowerManager.get_diagnostics
# ---------------------------------------------------------------------------
class TestPowerManagerGetDiagnostics:
    """Tests for PowerManager.get_diagnostics method."""

    def test_returns_running_state(
        self, mock_coordinator_master, mock_config_entry
    ) -> None:
        """Test that running state is reported."""
        pm = PowerManager(
            hass=mock_coordinator_master.hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )
        result = pm.get_diagnostics()

        assert result["running"] is False  # Not started yet

    def test_returns_mode(self, mock_coordinator_master, mock_config_entry) -> None:
        """Test that current mode is reported."""
        pm = PowerManager(
            hass=mock_coordinator_master.hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )
        result = pm.get_diagnostics()

        assert result["mode"] == PV_CHARGING_MODE

    def test_returns_power_limits(
        self, mock_coordinator_master, mock_config_entry
    ) -> None:
        """Test that power limits are reported."""
        pm = PowerManager(
            hass=mock_coordinator_master.hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )
        result = pm.get_diagnostics()

        assert "ui_max_discharge_power" in result
        assert "ui_max_charge_power" in result
        assert "configured_max_charge" in result
        assert "configured_max_discharge" in result
        assert "hw_limit_charge_per_battery" in result
        assert "hw_limit_discharge_per_battery" in result
        # User-configured limits must never exceed hardware limits
        assert result["configured_max_charge"] <= result["hw_limit_charge_per_battery"]  # type: ignore[operator]
        assert result["configured_max_discharge"] <= result["hw_limit_discharge_per_battery"]  # type: ignore[operator] # fmt: skip

    def test_returns_update_interval(
        self, mock_coordinator_master, mock_config_entry
    ) -> None:
        """Test that update interval is included in diagnostics."""
        pm = PowerManager(
            hass=mock_coordinator_master.hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )
        result = pm.get_diagnostics()

        assert "update_interval_seconds" in result

    def test_returns_last_update_timestamp(
        self, mock_coordinator_master, mock_config_entry
    ) -> None:
        """Test that last_update is a valid ISO timestamp."""
        pm = PowerManager(
            hass=mock_coordinator_master.hass,
            coordinator=mock_coordinator_master,
            config_entry=mock_config_entry,
        )
        result = pm.get_diagnostics()

        assert "last_update" in result
        # Verify it's a valid ISO format string
        datetime.fromisoformat(str(result["last_update"]))
