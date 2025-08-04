"""Test SAX Battery coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from pymodbus import ModbusException
import pytest

from custom_components.sax_battery.coordinator import SAXBatteryCoordinator
from custom_components.sax_battery.enums import (
    DeviceConstants,
    FormatConstants,
    TypeConstants,
)
from custom_components.sax_battery.items import ApiItem, ModbusItem, SAXItem
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed


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
        # Setup mock battery with data
        mock_battery = MagicMock()
        mock_battery.data = {"test_value": 42}
        mock_sax_data.batteries = {"battery_a": mock_battery}
        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.should_poll_smart_meter.return_value = False

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        data = await coordinator._async_update_data()

        assert data == {"test_value": 42}
        assert coordinator._first_update_done

    async def test_update_battery_not_found(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test update when battery not found."""
        mock_sax_data.batteries = {}
        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.should_poll_smart_meter.return_value = False

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Should not raise an error, just return empty data
        data = await coordinator._async_update_data()
        assert data == {}

    async def test_first_update_failure(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test first update failure raises ConfigEntryNotReady."""
        # Setup mock to simulate read failure
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        # Create a modbus item that will trigger reading
        mock_item = MagicMock()
        mock_item.address = 100
        mock_item.battery_slave_id = 1
        mock_sax_data.get_modbus_items_for_battery.return_value = [mock_item]
        mock_sax_data.should_poll_smart_meter.return_value = False

        # Make the API call fail
        mock_modbus_api.read_holding_registers = AsyncMock(
            side_effect=ModbusException("Connection failed")
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
        # Setup mock battery and item
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        mock_item = MagicMock()
        mock_item.address = 100
        mock_item.battery_slave_id = 1
        mock_sax_data.get_modbus_items_for_battery.return_value = [mock_item]
        mock_sax_data.should_poll_smart_meter.return_value = False

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Simulate successful first update
        coordinator._first_update_done = True

        # Make the API call fail
        mock_modbus_api.read_holding_registers = AsyncMock(
            side_effect=ModbusException("Connection failed")
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

        # Mock successful write
        with patch(
            "custom_components.sax_battery.modbusobject.ModbusObject.async_write_value",
            return_value=True,
        ):
            success = await coordinator.async_write_number_value(mock_modbus_item, 50.0)

        assert success

    async def test_write_modbus_register_failure(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
        mock_modbus_item,
    ) -> None:
        """Test failed Modbus register write."""
        # Make the ModbusObject's async_write_value fail
        with patch(
            "custom_components.sax_battery.modbusobject.ModbusObject.async_write_value",
            return_value=False,
        ):
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
            await coordinator.async_write_number_value(mock_modbus_item, 60.0)

            mock_sleep.assert_called_once()

    async def test_value_conversion_modbus_item(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test value conversion for ModbusItem with different formats."""
        coordinator = SAXBatteryCoordinator(  # noqa: F841
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Test percentage format (should clamp to 0-100)
        percentage_item = ModbusItem(
            name="test_percentage",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.PERCENTAGE,
            mtype=TypeConstants.NUMBER,
            address=100,
            divider=1.0,
        )

        # Test clamping to max
        result = percentage_item.convert_to_raw_value(150.0)
        assert result == 100  # Clamped to max

        # Test clamping to min
        result = percentage_item.convert_to_raw_value(-10.0)
        assert result == 0  # Clamped to min

        # Test normal value
        result = percentage_item.convert_to_raw_value(75.0)
        assert result == 75

    async def test_value_conversion_api_item(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test value conversion for ApiItem with different formats."""
        coordinator = SAXBatteryCoordinator(  # noqa: F841
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Test number format with divider
        number_item = ApiItem(
            name="test_number",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.NUMBER,
            address=100,
            divider=10.0,
        )

        # Test raw value conversion
        result = number_item.convert_raw_value(500)  # 500 / 10 = 50.0
        assert result == 50.0

        # Test to raw value conversion
        result = number_item.convert_to_raw_value(25.5)  # 25.5 * 10 = 255
        assert result == 255

    async def test_smart_meter_polling_master_only(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test smart meter polling only on master battery."""
        # Setup mock battery
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        # Mock master battery
        mock_sax_data.should_poll_smart_meter.return_value = True
        mock_smart_meter_item = ModbusItem(
            name="smartmeter_total_power",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            address=200,
            battery_slave_id=1,
            divider=1.0,
        )
        mock_sax_data.get_smart_meter_items.return_value = [mock_smart_meter_item]
        mock_sax_data.get_modbus_items_for_battery.return_value = []

        # Mock successful read
        mock_modbus_api.read_input_registers = AsyncMock(return_value=[2500])

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        await coordinator._async_update_data()

        # Should call smart meter update
        mock_modbus_api.read_input_registers.assert_called_with(200, slave=1)

    async def test_convert_modbus_to_api_item(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test conversion from ModbusItem to ApiItem."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        modbus_item = ModbusItem(
            name="test_item",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=10.0,
        )

        api_item = coordinator._convert_modbus_to_api_item(modbus_item)

        assert api_item.name == modbus_item.name
        assert api_item.device == modbus_item.device
        assert api_item.mformat == modbus_item.mformat
        assert api_item.mtype == modbus_item.mtype
        assert api_item.address == modbus_item.address
        assert api_item.battery_slave_id == modbus_item.battery_slave_id
        assert api_item.divider == modbus_item.divider

    async def test_convert_api_to_modbus_item(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test conversion from ApiItem to ModbusItem."""
        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        api_item = ApiItem(
            name="test_item",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=10.0,
        )

        modbus_item = coordinator._convert_api_to_modbus_item(api_item)

        assert modbus_item.name == api_item.name
        assert modbus_item.device == api_item.device
        assert modbus_item.mformat == api_item.mformat
        assert modbus_item.mtype == api_item.mtype
        assert modbus_item.address == api_item.address
        assert modbus_item.battery_slave_id == api_item.battery_slave_id
        assert modbus_item.divider == api_item.divider

    async def test_update_sax_item_state(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test updating SAX item state."""
        # Setup mock battery
        mock_battery = MagicMock()
        mock_sax_data.batteries = {"battery_a": mock_battery}

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Test with string item name
        coordinator.update_sax_item_state("test_item", 42.0)
        mock_battery.data.__setitem__.assert_called_with("test_item", 42.0)

        # Test with SAXItem object
        sax_item = SAXItem(
            name="test_sax_item",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
        )

        coordinator.update_sax_item_state(sax_item, 84.0)
        assert sax_item.state == 84.0
        mock_battery.data.__setitem__.assert_called_with("test_sax_item", 84.0)
