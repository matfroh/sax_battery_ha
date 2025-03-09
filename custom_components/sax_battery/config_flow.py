"""Config flow for SAX Battery integration."""
from typing import Any, Dict, Optional
import voluptuous as vol
import uuid
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.const import Platform

from .const import (
    DOMAIN,
    CONF_BATTERY_COUNT,
    CONF_POWER_SENSOR,
    CONF_PF_SENSOR,
    CONF_MASTER_BATTERY,
    CONF_DEVICE_ID,
    DEFAULT_PORT,
    CONF_PILOT_FROM_HA,
    CONF_LIMIT_POWER,  
  	CONF_MAX_CHARGE,
	CONF_MAX_DISCHARGE,
	CONF_MIN_SOC,
	DEFAULT_MIN_SOC, 
	CONF_PRIORITY_DEVICES,
	CONF_ENABLE_SOLAR_CHARGING,
	CONF_AUTO_PILOT_INTERVAL,
    DEFAULT_AUTO_PILOT_INTERVAL,
    CONF_MANUAL_CONTROL
    
)

class SAXBatteryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SAX Battery."""

    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self._data: Dict[str, Any] = {}
        self._battery_count: Optional[int] = None
        self._device_id: str = str(uuid.uuid4())  # Generate unique device ID
        self._pilot_from_ha: bool = False
        self._limit_power: bool = False


    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Store battery count and move to battery configuration
            self._battery_count = user_input[CONF_BATTERY_COUNT]
            self._data.update(user_input)
            self._data[CONF_DEVICE_ID] = self._device_id  # Store device ID            
            return await self.async_step_control_options()

        # Initial form - just ask for battery count
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_BATTERY_COUNT, default=1): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=3)
                ),
            }),
            errors=errors,
        )
    async def async_step_control_options(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle control options step."""
        errors = {}

        if user_input is not None:
            self._pilot_from_ha = user_input[CONF_PILOT_FROM_HA]
            self._limit_power = user_input[CONF_LIMIT_POWER]
            self._data.update(user_input)
            
            if self._pilot_from_ha:
                return await self.async_step_pilot_options()
            else:
                return await self.async_step_battery_config()

        return self.async_show_form(
            step_id="control_options",
            data_schema=vol.Schema({
                vol.Required(CONF_PILOT_FROM_HA, default=False): bool,
                vol.Required(CONF_LIMIT_POWER, default=False): bool,
            }),
            errors=errors,
        )

    async def async_step_pilot_options(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Configure pilot options."""
        errors = {}
    
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_sensors()
    
        return self.async_show_form(
            step_id="pilot_options",
            data_schema=vol.Schema({
                vol.Required(CONF_MIN_SOC, default=DEFAULT_MIN_SOC): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=100)
                ),
                vol.Required(CONF_AUTO_PILOT_INTERVAL, default=DEFAULT_AUTO_PILOT_INTERVAL): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=5, max=300)
                ),
                vol.Required(CONF_ENABLE_SOLAR_CHARGING, default=True): bool,
            }),
            errors=errors,
            description_placeholders={
                "min_soc_description": "Minimum State of Charge to maintain (battery won't discharge below this value)",
                "interval_description": "How often to update the battery control values (in seconds)",
                "solar_charging_description": "Enable charging from solar panels"
            }
        )

    async def async_step_sensors(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Configure power and PF sensors."""
        errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_priority_devices()

        # Only make fields required if piloting from HA
        schema = {}
        if self._pilot_from_ha:
            schema.update({
                vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
                vol.Required(CONF_PF_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
            })
        
        # If no sensors are needed, skip this step
        if not schema:
            return await self.async_step_battery_config()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
        
    async def async_step_priority_devices(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Configure priority devices."""
        errors = {}
    
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery_config()
    
        return self.async_show_form(
            step_id="priority_devices",
            data_schema=vol.Schema({
                vol.Optional(CONF_PRIORITY_DEVICES): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", multiple=True),
                ),
            }),
            errors=errors,
            description_placeholders={
                "priority_devices_description": "Select devices that should have priority over battery usage (e.g., EV charger, heat pump)"
            }
        )

    async def async_step_battery_config(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Configure individual batteries."""
        errors = {}

        if user_input is not None:
            self._data.update(user_input)
            
            # Create the entry with all collected data
            return self.async_create_entry(
                title="SAX Battery",
                data=self._data,
            )

        # Generate schema for all batteries
        schema = {}
        battery_choices = []
        
        for i in range(1, self._battery_count + 1):
            battery_id = f"battery_{chr(96+i)}"
            battery_choices.append(battery_id)
            
            schema[vol.Required(f"{battery_id}_host")]: str = str
            schema[vol.Required(f"{battery_id}_port", default=DEFAULT_PORT)]: int = vol.All(
                vol.Coerce(int),
                vol.Range(min=1, max=65535)
            )

        # Add master battery selection
        schema[vol.Required(CONF_MASTER_BATTERY)] = vol.In(battery_choices)

        return self.async_show_form(
            step_id="battery_config",
            data_schema=vol.Schema(schema),
            errors=errors,
        )