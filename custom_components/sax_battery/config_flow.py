"""Config flow for SAX Battery integration."""
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_BATTERY_COUNT,
    CONF_POWER_SENSOR,
    CONF_PF_SENSOR,
    CONF_MASTER_BATTERY,
    DEFAULT_PORT,
)

class SAXBatteryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SAX Battery."""

    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self._data: Dict[str, Any] = {}
        self._battery_count: Optional[int] = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Store battery count and move to battery configuration
            self._battery_count = user_input[CONF_BATTERY_COUNT]
            self._data.update(user_input)
            return await self.async_step_sensors()

        # Initial form - just ask for battery count
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_BATTERY_COUNT, default=1): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=10)
                ),
            }),
            errors=errors,
        )

    async def async_step_sensors(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Configure power and PF sensors."""
        errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery_config()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
                vol.Required(CONF_PF_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
            }),
            errors=errors,
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