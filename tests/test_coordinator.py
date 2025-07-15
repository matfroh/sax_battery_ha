"""Test SAX Battery coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from pymodbus import ModbusException
import pytest

from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ModbusItem
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_modbus_api():
    """Create mock ModbusAPI."""
    api = MagicMock()
    api.write_holding_register = AsyncMock(return_value=True)
    api.read_holding_registers = AsyncMock(return_value=[100])

    # Mock the modbus client that gets returned by get_device()
    mock_client = MagicMock()
    mock_client.connected = True
    mock_client.write_register = AsyncMock(return_value=True)
    api.get_device.return_value = mock_client

    return api


@pytest.fixture
def mock_sax_data():
    """Create mock SAX battery data."""
    data = MagicMock()
    data.batteries = {"battery_a": MagicMock()}
    data.batteries["battery_a"].async_update = AsyncMock()
    data.batteries["battery_a"].data = {"test_value": 42}
    data.should_poll_smart_meter = MagicMock(return_value=False)
    data.get_modbus_items_for_battery = MagicMock(return_value=[])
    data.smart_meter_data = MagicMock()
    return data


@pytest.fixture
def mock_modbus_item():
    """Create mock ModbusItem."""
    item = ModbusItem(
        address=100,
        name="test_item",
        mformat=FormatConstants.PERCENTAGE,
        mtype=TypeConstants.NUMBER,
        device=DeviceConstants.UNKNOWN,
    )
    item.divider = 10
    return item


class TestSAXBatteryCoordinator:
    """Test SAX Battery coordinator."""

    async def test_coordinator_init(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test coordinator initialization."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
            update_interval=timedelta(seconds=10),
        )

        assert coordinator.battery_id == "battery_a"
        assert coordinator.sax_data == mock_sax_data
        assert coordinator.modbus_api == mock_modbus_api
        assert not coordinator._first_update_done

    async def test_successful_update(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test successful data update."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        data = await coordinator._async_update_data()

        assert data == {"test_value": 42}
        assert coordinator._first_update_done
        mock_sax_data.batteries["battery_a"].async_update.assert_called_once()

    async def test_update_battery_not_found(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test update when battery not found."""
        mock_sax_data.batteries = {}

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        with pytest.raises(
            ConfigEntryNotReady, match="Failed to setup battery battery_a"
        ):
            await coordinator._async_update_data()

    async def test_first_update_failure(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test first update failure raises ConfigEntryNotReady."""
        mock_sax_data.batteries["battery_a"].async_update.side_effect = Exception(
            "Connection failed"
        )

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        with pytest.raises(
            ConfigEntryNotReady, match="Failed to setup battery battery_a"
        ):
            await coordinator._async_update_data()

    async def test_subsequent_update_failure(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test subsequent update failure raises UpdateFailed."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Simulate successful first update
        coordinator._first_update_done = True
        mock_sax_data.batteries["battery_a"].async_update.side_effect = Exception(
            "Connection failed"
        )

        with pytest.raises(
            UpdateFailed, match="Error communicating with battery battery_a"
        ):
            await coordinator._async_update_data()

    async def test_write_modbus_register_success(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
        mock_modbus_item,
    ) -> None:
        """Test successful Modbus register write."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        success = await coordinator.async_write_number_value(mock_modbus_item, 50.0)

        assert success
        # The coordinator uses ModbusObject which calls write_register on the client
        mock_client = mock_modbus_api.get_device.return_value
        mock_client.write_register.assert_called_once_with(
            100,  # address
            100,  # 50.0 * 10 (divider) = 500, but clamped to 100 due to PERCENTAGE format
            slave=1,  # default slave_id
        )

    async def test_write_modbus_register_failure(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
        mock_modbus_item,
    ) -> None:
        """Test failed Modbus register write."""
        # Make the client's write_register raise an exception to simulate failure
        mock_client = mock_modbus_api.get_device.return_value
        mock_client.write_register.side_effect = ModbusException("Write failed")

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        success = await coordinator.async_write_number_value(mock_modbus_item, 50.0)

        assert not success

    @pytest.mark.skip(reason="Throttling not yet implemented")
    async def test_write_throttling(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
        mock_modbus_item,
    ) -> None:
        """Test write throttling prevents rapid writes."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # First write
        await coordinator.async_write_number_value(mock_modbus_item, 50.0)

        # Second write should be throttled
        with (
            patch("time.time", return_value=1000.0),
            patch("asyncio.sleep") as mock_sleep,
        ):
            coordinator._last_write_time[mock_modbus_item.address] = 999.5

            await coordinator.async_write_number_value(mock_modbus_item, 60.0)

            mock_sleep.assert_called_once()

    async def test_value_conversion(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test value conversion for different formats."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Test percentage format (should clamp to 0-100)
        percentage_item = ModbusItem(
            address=100,
            name="test_percentage",
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.NUMBER,
            device=DeviceConstants.UNKNOWN,
        )

        result = coordinator._convert_value_for_writing(percentage_item, 150.0)
        assert result == 100  # Clamped to max

        result = coordinator._convert_value_for_writing(percentage_item, -10.0)
        assert result == 0  # Clamped to min

    async def test_smart_meter_polling_master_only(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test smart meter polling only on master battery."""
        # Mock master battery
        mock_sax_data.should_poll_smart_meter.return_value = True
        mock_smart_meter_item = MagicMock()
        mock_smart_meter_item.name = "smartmeter_total_power"
        mock_smart_meter_item.address = 200
        mock_smart_meter_item.divider = 1
        mock_sax_data.get_modbus_items_for_battery.return_value = [
            mock_smart_meter_item
        ]

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        await coordinator._async_update_data()

        # Should call smart meter update
        mock_modbus_api.read_holding_registers.assert_called_once_with(
            200, 1, "battery_a"
        )
