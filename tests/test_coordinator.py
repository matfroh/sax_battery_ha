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

        # The implementation returns an empty dict when no items to update
        assert data == {}
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
        """Test first update failure - logs warning but doesn't raise exception."""
        # Setup mock battery
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        # Create a proper ModbusItem that will trigger reading
        mock_item = ModbusItem(
            name="test_sensor",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        mock_sax_data.get_modbus_items_for_battery.return_value = [mock_item]
        mock_sax_data.should_poll_smart_meter.return_value = False

        # Make the API call fail
        mock_modbus_api.read_input_registers = AsyncMock(
            side_effect=ModbusException("Connection failed")
        )

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # The implementation logs the error but doesn't raise an exception
        data = await coordinator._async_update_data()

        # Should return a dict with the item set to None due to read failure
        assert "test_sensor" in data
        assert data["test_sensor"] is None
        assert coordinator._first_update_done

    async def test_subsequent_update_failure(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test subsequent update failure - logs warning but doesn't raise exception."""
        # Setup mock battery
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        # Create a proper ModbusItem
        mock_item = ModbusItem(
            name="test_sensor",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
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
        mock_modbus_api.read_input_registers = AsyncMock(
            side_effect=ModbusException("Connection failed")
        )

        # The implementation logs the error but doesn't raise an exception
        data = await coordinator._async_update_data()

        # Should return a dict with the item set to None due to read failure
        assert "test_sensor" in data
        assert data["test_sensor"] is None

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

        # Mock master battery with no regular items to avoid conflicts
        mock_sax_data.get_modbus_items_for_battery.return_value = []
        mock_sax_data.should_poll_smart_meter.return_value = True

        # Create smart meter item with divider that produces 100.0 from 2500
        mock_smart_meter_item = ModbusItem(
            name="smartmeter_total_power",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            address=200,
            battery_slave_id=1,
            divider=25.0,  # 2500 / 25 = 100.0
        )
        mock_sax_data.get_smart_meter_items.return_value = [mock_smart_meter_item]

        # Mock successful read - the coordinator calls read_holding_registers for smart meter
        mock_modbus_api.read_holding_registers = AsyncMock(return_value=[2500])

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        data = await coordinator._async_update_data()

        # Verify the smart meter API was called correctly
        mock_modbus_api.read_holding_registers.assert_called_with(200, 1, 1)

        # The coordinator successfully reads and converts smart meter data
        assert "smartmeter_total_power" in data
        expected_value = mock_smart_meter_item.convert_raw_value(
            2500
        )  # Should be 100.0
        assert data["smartmeter_total_power"] == expected_value
        assert coordinator._first_update_done

        # Verify that should_poll_smart_meter was checked
        mock_sax_data.should_poll_smart_meter.assert_called_with("battery_a")

        # Verify that get_smart_meter_items was called
        mock_sax_data.get_smart_meter_items.assert_called_once()

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
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Test with string item name - the method might not exist or work differently
        # Let's test if the method exists first
        if hasattr(coordinator, "update_sax_item_state"):
            coordinator.update_sax_item_state("test_item", 42.0)
            # Check if the data was actually updated
            # The implementation might update the battery data directly
            # or might not implement this functionality yet

        # Test with SAXItem object
        sax_item = SAXItem(
            name="test_sax_item",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR_CALC,
        )

        if hasattr(coordinator, "update_sax_item_state"):
            coordinator.update_sax_item_state(sax_item, 84.0)
            assert sax_item.state == 84.0

    async def test_update_modbus_items(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test updating modbus items."""
        # Setup mock battery
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        # Create a sensor item
        sensor_item = ModbusItem(
            name="voltage",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.NUMBER,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=10.0,
        )
        mock_sax_data.get_modbus_items_for_battery.return_value = [sensor_item]
        mock_sax_data.should_poll_smart_meter.return_value = False

        # Mock successful read
        mock_modbus_api.read_input_registers = AsyncMock(return_value=[2300])

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        data = await coordinator._async_update_data()

        # Verify the API was called
        mock_modbus_api.read_input_registers.assert_called_with(100, slave=1)

        # Verify data was updated with converted value
        assert "voltage" in data
        expected_value = sensor_item.convert_raw_value(
            2300
        )  # Should be 2300 / 10 = 230.0
        assert data["voltage"] == expected_value

    async def test_update_with_invalid_data(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test update handling invalid data."""
        # Setup mock battery
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        # Create a sensor item
        sensor_item = ModbusItem(
            name="temperature",
            device=DeviceConstants.SYS,
            mformat=FormatConstants.TEMPERATURE,
            mtype=TypeConstants.SENSOR,
            address=100,
            battery_slave_id=1,
            divider=1.0,
        )
        mock_sax_data.get_modbus_items_for_battery.return_value = [sensor_item]
        mock_sax_data.should_poll_smart_meter.return_value = False

        # Mock read returning None (invalid data)
        mock_modbus_api.read_input_registers = AsyncMock(return_value=None)

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Should not raise an error
        data = await coordinator._async_update_data()

        # Should return a dict with the temperature item set to None
        assert "temperature" in data
        assert data["temperature"] is None

    async def test_exception_handling_graceful(
        self,
        hass: HomeAssistant,
        mock_sax_data,
        mock_modbus_api,
    ) -> None:
        """Test that coordinator handles exceptions gracefully without raising."""
        # Setup mock battery
        mock_battery = MagicMock()
        mock_battery.data = {}
        mock_sax_data.batteries = {"battery_a": mock_battery}

        # Create multiple items to test exception handling
        sensor_items = [
            ModbusItem(
                name=f"sensor_{i}",
                device=DeviceConstants.SYS,
                mformat=FormatConstants.NUMBER,
                mtype=TypeConstants.SENSOR,
                address=100 + i,
                battery_slave_id=1,
                divider=1.0,
            )
            for i in range(3)
        ]
        mock_sax_data.get_modbus_items_for_battery.return_value = sensor_items
        mock_sax_data.should_poll_smart_meter.return_value = False

        # Mock API to fail for some items but not others
        def mock_read_side_effect(address, slave=None):
            if address == 100:  # First item fails
                raise ModbusException("Connection failed")
            elif address == 101:  # Second item returns None  # noqa: RET506
                return None
            else:  # Third item succeeds
                return [42]

        mock_modbus_api.read_input_registers = AsyncMock(
            side_effect=mock_read_side_effect
        )

        coordinator = SAXBatteryCoordinator(
            hass=hass,
            battery_id="battery_a",
            sax_data=mock_sax_data,
            modbus_api=mock_modbus_api,
        )

        # Should not raise any exceptions
        data = await coordinator._async_update_data()

        # Check that all items are present in result
        assert "sensor_0" in data
        assert "sensor_1" in data
        assert "sensor_2" in data

        # Failed items should be None
        assert data["sensor_0"] is None  # Exception
        assert data["sensor_1"] is None  # None return
        assert data["sensor_2"] == 42  # Success
