"""Number platform for SAX Battery integration."""
import logging
from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfPower
from .const import DOMAIN, CONF_LIMIT_POWER

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the SAX Battery number entities."""
    if not entry.data.get(CONF_LIMIT_POWER, False):
        return

    sax_battery_data = hass.data[DOMAIN][entry.entry_id]
    battery_count = len(sax_battery_data.batteries)
    
    entities = [
        SAXBatteryMaxChargeNumber(sax_battery_data, battery_count * 3500),
        SAXBatteryMaxDischargeNumber(sax_battery_data, battery_count * 4600)
    ]
    
    async_add_entities(entities)

class SAXBatteryMaxChargeNumber(NumberEntity):
    """SAX Battery Maximum Charge Power number."""
    
    def __init__(self, sax_battery_data, max_value):
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_max_charge"
        self._attr_name = "Maximum Charge Power"
        self._attr_native_min_value = 0
        self._attr_native_max_value = max_value
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        try:
            client = self._data_manager.master_battery._data_manager.modbus_clients[
                self._data_manager.master_battery.battery_id
            ]
            result = await self._data_manager.hass.async_add_executor_job(
                client.write_register,
                44,  # Register for max charge
                int(value),
                64   # slave
            )
            if not hasattr(result, 'isError') or not result.isError():
                self._attr_native_value = value
            else:
                _LOGGER.error(f"Error setting max charge: {result}")
        except Exception as err:
            _LOGGER.error(f"Failed to set max charge: {err}")

class SAXBatteryMaxDischargeNumber(NumberEntity):
    """SAX Battery Maximum Discharge Power number."""
    
    def __init__(self, sax_battery_data, max_value):
        self._data_manager = sax_battery_data
        self._attr_unique_id = f"{DOMAIN}_max_discharge"
        self._attr_name = "Maximum Discharge Power"
        self._attr_native_min_value = 0
        self._attr_native_max_value = max_value
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._data_manager.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        try:
            client = self._data_manager.master_battery._data_manager.modbus_clients[
                self._data_manager.master_battery.battery_id
            ]
            result = await self._data_manager.hass.async_add_executor_job(
                lambda: client.write_register(
                    address=44,  # Register for max charge
                    value=int(value),
                    slave=64
                )
            )
            if hasattr(result, 'registers') or (not hasattr(result, 'isError') or not result.isError()):
                self._attr_native_value = value
            else:
                _LOGGER.error(f"Error setting max discharge: {result}")
        except Exception as err:
            _LOGGER.error(f"Failed to set max discharge: {err}")