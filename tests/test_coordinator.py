"""Test coordinator.py functionality."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.models import SAXBatteryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def mock_sax_data():
    """Create a mock SAXBatteryData instance."""
    mock_data = MagicMock(spec=SAXBatteryData)
    mock_data.batteries = {}
    return mock_data


@pytest.fixture
def coordinator(mock_hass, mock_sax_data):
    """Create a SAXBatteryCoordinator instance."""
    return SAXBatteryCoordinator(
        mock_hass,
        mock_sax_data,
        update_interval=timedelta(seconds=5),
    )


class TestSAXBatteryCoordinator:
    """Test SAXBatteryCoordinator class."""

    def test_coordinator_init(self, mock_hass, mock_sax_data):
        """Test coordinator initialization."""
        coordinator = SAXBatteryCoordinator(
            mock_hass,
            mock_sax_data,
            update_interval=timedelta(seconds=10),
        )

        assert coordinator.hass == mock_hass
        assert coordinator.sax_data == mock_sax_data
        assert coordinator.update_interval == timedelta(seconds=10)
        assert coordinator._first_update_done is False

    def test_coordinator_init_default_interval(self, mock_hass, mock_sax_data):
        """Test coordinator initialization with default interval."""
        coordinator = SAXBatteryCoordinator(mock_hass, mock_sax_data)

        assert coordinator.update_interval == timedelta(seconds=30)

    async def test_async_update_data_no_batteries(self, coordinator):
        """Test _async_update_data with no batteries."""
        coordinator.sax_data.batteries = {}
        # Mock get_master_battery to return None
        coordinator.sax_data.get_master_battery = MagicMock(return_value=None)

        result = await coordinator._async_update_data()

        assert result == {}
        assert coordinator._first_update_done is True

    async def test_async_update_data_successful(self, coordinator):
        """Test _async_update_data with successful battery updates."""
        # Create mock batteries
        mock_battery1 = MagicMock()
        mock_battery1.async_update = AsyncMock()
        mock_battery1.data = {"sax_power": 1500, "sax_soc": 80}

        mock_battery2 = MagicMock()
        mock_battery2.async_update = AsyncMock()
        mock_battery2.data = {"sax_power": 2000, "sax_soc": 75}

        coordinator.sax_data.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
        }

        result = await coordinator._async_update_data()

        # Verify batteries were updated
        mock_battery1.async_update.assert_called_once()
        mock_battery2.async_update.assert_called_once()

        # Verify result structure
        assert "battery_a" in result
        assert "battery_b" in result
        assert result["battery_a"] == {"sax_power": 1500, "sax_soc": 80}
        assert result["battery_b"] == {"sax_power": 2000, "sax_soc": 75}
        assert coordinator._first_update_done is True

    async def test_async_update_data_with_combined_data(self, coordinator):
        """Test _async_update_data with combined data from master battery."""
        # Create mock master battery with data manager
        mock_master = MagicMock()
        mock_master.async_update = AsyncMock()
        mock_master.data = {"sax_power": 1500}
        mock_master.data_manager.combined_data = {"total_power": 3500, "avg_soc": 77}

        coordinator.sax_data.batteries = {"battery_a": mock_master}
        coordinator.sax_data.get_master_battery = MagicMock(return_value=mock_master)

        result = await coordinator._async_update_data()

        assert "battery_a" in result
        assert "combined" in result
        assert result["combined"] == {"total_power": 3500, "avg_soc": 77}

    async def test_async_update_data_battery_update_exception_first_update(
        self, coordinator
    ):
        """Test _async_update_data with battery update exception on first update."""
        # Create mock battery that raises exception
        mock_battery = MagicMock()
        mock_battery.async_update = AsyncMock(
            side_effect=ConnectionError("Connection failed")
        )

        coordinator.sax_data.batteries = {"battery_a": mock_battery}
        coordinator._first_update_done = False

        with pytest.raises(ConfigEntryNotReady):
            await coordinator._async_update_data()

    async def test_async_update_data_battery_update_exception_subsequent_update(
        self, coordinator
    ):
        """Test _async_update_data with battery update exception on subsequent update."""
        # Create mock batteries, one successful, one failing
        mock_battery1 = MagicMock()
        mock_battery1.async_update = AsyncMock()
        mock_battery1.data = {"sax_power": 1500}

        mock_battery2 = MagicMock()
        mock_battery2.async_update = AsyncMock(
            side_effect=ConnectionError("Connection failed")
        )

        coordinator.sax_data.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
        }
        coordinator._first_update_done = True  # Simulate subsequent update

        with patch("custom_components.sax_battery.coordinator._LOGGER") as mock_logger:
            result = await coordinator._async_update_data()

            # Should still return data from successful battery
            assert "battery_a" in result
            assert result["battery_a"] == {"sax_power": 1500}

            # Should log warning about failed updates
            mock_logger.warning.assert_called_once()
            assert "Some battery updates failed" in str(mock_logger.warning.call_args)

    async def test_async_update_data_general_exception_first_update(self, coordinator):
        """Test _async_update_data with general exception on first update."""
        coordinator.sax_data.batteries = {"battery_a": MagicMock()}

        with patch("asyncio.gather", side_effect=RuntimeError("General error")):
            with pytest.raises(ConfigEntryNotReady) as exc_info:
                await coordinator._async_update_data()

            assert "Failed to setup SAX Battery" in str(exc_info.value)

    async def test_async_update_data_general_exception_subsequent_update(
        self, coordinator
    ):
        """Test _async_update_data with general exception on subsequent update."""
        coordinator.sax_data.batteries = {"battery_a": MagicMock()}
        coordinator._first_update_done = True

        with patch("asyncio.gather", side_effect=RuntimeError("General error")):
            with pytest.raises(UpdateFailed) as exc_info:
                await coordinator._async_update_data()

            assert "Error communicating with SAX Battery" in str(exc_info.value)

    async def test_async_update_data_battery_with_no_data(self, coordinator):
        """Test _async_update_data with battery that has no data."""
        # Create mock battery with no data
        mock_battery1 = MagicMock()
        mock_battery1.async_update = AsyncMock()
        mock_battery1.data = {"sax_power": 1500}

        mock_battery2 = MagicMock()
        mock_battery2.async_update = AsyncMock()
        mock_battery2.data = None  # No data

        coordinator.sax_data.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
        }

        result = await coordinator._async_update_data()

        # Only battery with data should be in result
        assert "battery_a" in result
        assert "battery_b" not in result
        assert result["battery_a"] == {"sax_power": 1500}

    async def test_async_update_data_master_battery_no_data_manager(self, coordinator):
        """Test _async_update_data with master battery without data_manager."""
        # Create mock master battery without data_manager
        mock_master = MagicMock()
        mock_master.async_update = AsyncMock()
        mock_master.data = {"sax_power": 1500}

        # Use spec to limit what attributes are available
        mock_master_limited = MagicMock(spec=["async_update", "data"])
        mock_master_limited.async_update = AsyncMock()
        mock_master_limited.data = {"sax_power": 1500}

        coordinator.sax_data.batteries = {"battery_a": mock_master_limited}
        coordinator.sax_data.get_master_battery = MagicMock(
            return_value=mock_master_limited
        )

        result = await coordinator._async_update_data()

        assert "battery_a" in result
        assert "combined" not in result  # No combined data without data_manager

    async def test_async_update_data_master_battery_no_combined_data(self, coordinator):
        """Test _async_update_data with master battery data_manager without combined_data."""
        # Create mock master battery with data_manager but no combined_data
        mock_data_manager = MagicMock(spec=["some_other_method"])  # No combined_data

        mock_master = MagicMock(spec=["async_update", "data", "data_manager"])
        mock_master.async_update = AsyncMock()
        mock_master.data = {"sax_power": 1500}
        mock_master.data_manager = mock_data_manager

        coordinator.sax_data.batteries = {"battery_a": mock_master}
        coordinator.sax_data.get_master_battery = MagicMock(return_value=mock_master)

        result = await coordinator._async_update_data()

        assert "battery_a" in result
        assert "combined" not in result  # No combined data without combined_data

    async def test_async_update_data_no_master_battery(self, coordinator):
        """Test _async_update_data when get_master_battery returns None."""
        # Create mock battery
        mock_battery = MagicMock()
        mock_battery.async_update = AsyncMock()
        mock_battery.data = {"sax_power": 1500}

        coordinator.sax_data.batteries = {"battery_a": mock_battery}
        coordinator.sax_data.get_master_battery = MagicMock(return_value=None)

        result = await coordinator._async_update_data()

        assert "battery_a" in result
        assert "combined" not in result  # No combined data without master battery

    async def test_async_update_data_concurrent_execution(self, coordinator):
        """Test that battery updates are executed concurrently."""
        # Create mock batteries with async_update that tracks call order
        call_order = []

        async def mock_update_1():
            call_order.append("battery_1_start")
            await asyncio.sleep(0.1)  # Simulate some work
            call_order.append("battery_1_end")

        async def mock_update_2():
            call_order.append("battery_2_start")
            await asyncio.sleep(0.05)  # Shorter work
            call_order.append("battery_2_end")

        mock_battery1 = MagicMock()
        mock_battery1.async_update = mock_update_1
        mock_battery1.data = {"sax_power": 1500}

        mock_battery2 = MagicMock()
        mock_battery2.async_update = mock_update_2
        mock_battery2.data = {"sax_power": 2000}

        coordinator.sax_data.batteries = {
            "battery_a": mock_battery1,
            "battery_b": mock_battery2,
        }

        await coordinator._async_update_data()

        # Both should start before either ends (concurrent execution)
        assert call_order.index("battery_1_start") < call_order.index("battery_1_end")
        assert call_order.index("battery_2_start") < call_order.index("battery_2_end")
        # Battery 2 should finish before battery 1 (it has less work)
        assert call_order.index("battery_2_end") < call_order.index("battery_1_end")
