"""Test SAX Battery data update coordinator."""

from __future__ import annotations

import logging

from pymodbus import ModbusException

from custom_components.sax_battery.enums import DeviceConstants, TypeConstants
from custom_components.sax_battery.items import ModbusItem

_LOGGER = logging.getLogger(__name__)


class TestSAXBatteryCoordinator:
    """Test SAX Battery data update coordinator."""

    async def test_update_smart_meter_data_success(
        self,
        sax_battery_coordinator,
        mock_sax_data,
        mock_modbus_api,
        smart_meter_modbus_item,
    ):
        """Test successful smart meter data update."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_modbus_item]
        mock_modbus_api.read_holding_registers.return_value = 1500

        data = {}
        await sax_battery_coordinator._update_smart_meter_data(data)

        # Verify data was updated
        assert data["smartmeter_power"] == 1500.0

        # Verify modbus API was called correctly with new signature
        mock_modbus_api.read_holding_registers.assert_called_once_with(
            count=1, modbus_item=smart_meter_modbus_item
        )

        # Verify smart meter data was updated
        mock_sax_data.smart_meter_data.set_value.assert_called_once_with(
            "smartmeter_power", 1500.0
        )

    async def test_update_smart_meter_data_modbus_exception(
        self,
        sax_battery_coordinator,
        mock_sax_data,
        mock_modbus_api,
        smart_meter_modbus_item,
    ):
        """Test smart meter data update with modbus exception."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_modbus_item]
        mock_modbus_api.read_holding_registers.side_effect = ModbusException(
            "Connection failed"
        )

        data = {}
        await sax_battery_coordinator._update_smart_meter_data(data)

        # Should set None value on error
        assert data["smartmeter_power"] is None

    async def test_update_smart_meter_data_no_smart_meter(
        self, sax_battery_coordinator, mock_sax_data
    ):
        """Test smart meter data update when no smart meter data exists."""
        mock_sax_data.smart_meter_data = None
        mock_sax_data.get_smart_meter_items.return_value = []

        data = {}
        await sax_battery_coordinator._update_smart_meter_data(data)

        # Should not crash and data should remain empty
        assert data == {}

    async def test_update_smart_meter_data_empty_response(
        self,
        sax_battery_coordinator,
        mock_sax_data,
        mock_modbus_api,
        smart_meter_modbus_item,
    ):
        """Test smart meter data update with empty modbus response."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_modbus_item]
        mock_modbus_api.read_holding_registers.return_value = None

        data = {}
        await sax_battery_coordinator._update_smart_meter_data(data)

        # When response is None, the item is added to data with None value
        assert data["smartmeter_power"] is None

    async def test_update_smart_meter_data_with_factor(
        self,
        sax_battery_coordinator,
        mock_sax_data,
        mock_modbus_api,
    ):
        """Test smart meter data update with factor applied."""
        item_with_factor = ModbusItem(
            name="smartmeter_voltage",
            device=DeviceConstants.SYS,
            mtype=TypeConstants.SENSOR,
            address=1001,
            battery_slave_id=1,
            factor=10.0,
        )

        mock_sax_data.get_smart_meter_items.return_value = [item_with_factor]
        mock_modbus_api.read_holding_registers.return_value = 2300

        data = {}
        await sax_battery_coordinator._update_smart_meter_data(data)

        # Factor is not applied in coordinator - raw value is stored
        assert data["smartmeter_voltage"] == 2300.0

    async def test_update_smart_meter_data_oserror(
        self,
        sax_battery_coordinator,
        mock_sax_data,
        mock_modbus_api,
        smart_meter_modbus_item,
    ):
        """Test smart meter data update with OSError."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_modbus_item]
        mock_modbus_api.read_holding_registers.side_effect = OSError("Network error")

        data = {}
        await sax_battery_coordinator._update_smart_meter_data(data)

        # Should set None value on error
        assert data["smartmeter_power"] is None

    async def test_update_smart_meter_data_timeout_error(
        self,
        sax_battery_coordinator,
        mock_sax_data,
        mock_modbus_api,
        smart_meter_modbus_item,
    ):
        """Test smart meter data update with TimeoutError."""
        mock_sax_data.get_smart_meter_items.return_value = [smart_meter_modbus_item]
        mock_modbus_api.read_holding_registers.side_effect = TimeoutError("Timeout")

        data = {}
        await sax_battery_coordinator._update_smart_meter_data(data)

        # Should set None value on error
        assert data["smartmeter_power"] is None
