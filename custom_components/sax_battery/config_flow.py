"""Config flow for SAX Battery integration."""

from __future__ import annotations

import logging
import re
from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .const import (
    BATTERY_IDS,
    BATTERY_PHASES,
    CONF_AUTO_PILOT_INTERVAL,
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_ENABLED,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_BATTERY_PORT,
    CONF_DEVICE_ID,
    CONF_ENABLE_SOLAR_CHARGING,
    CONF_GRID_POWER_SENSOR,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_MIN_SOC,
    CONF_PF_SENSOR,
    CONF_PILOT_FROM_HA,
    CONF_POWER_SENSOR,
    CONF_PRIORITY_DEVICES,
    DEFAULT_AUTO_PILOT_INTERVAL,
    DEFAULT_MIN_SOC,
    DEFAULT_PORT,
    DOMAIN,
    SAX_PILOT_POWER,
)
from .utils import get_unique_id_for_item

_LOGGER = logging.getLogger(__name__)


class SAXBatteryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SAX Battery."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._battery_count: int | None = None
        self._device_id: str = str(uuid.uuid4())  # Generate unique device ID
        self._pilot_from_ha: bool = False
        self._limit_power: bool = False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SAXBatteryOptionsFlowHandler:
        """Create the options flow."""
        return SAXBatteryOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store battery count and move to control options
            self._battery_count = user_input[CONF_BATTERY_COUNT]
            self._data.update(user_input)
            self._data[CONF_DEVICE_ID] = self._device_id  # Store device ID
            return await self.async_step_control_options()

        # Initial form - just ask for battery count
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BATTERY_COUNT, default=1): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=3)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_control_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle control options step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._pilot_from_ha = user_input[CONF_PILOT_FROM_HA]
            self._limit_power = user_input[CONF_LIMIT_POWER]
            self._data.update(user_input)

            #  Set solar charging default based on pilot mode
            if not self._pilot_from_ha:
                self._data[CONF_ENABLE_SOLAR_CHARGING] = False

            # Debug logging to verify configuration storage
            _LOGGER.debug(
                "Control options saved: pilot_from_ha=%s, limit_power=%s, solar_charging=%s",
                self._pilot_from_ha,
                self._limit_power,
                self._data.get(CONF_ENABLE_SOLAR_CHARGING, False),
            )

            # Route to appropriate next step based on selections
            if self._pilot_from_ha:
                return await self.async_step_pilot_options()
            # Skip pilot-specific steps if not enabled
            return await self.async_step_battery_config()

        return self.async_show_form(
            step_id="control_options",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PILOT_FROM_HA, default=False): bool,
                    vol.Required(CONF_LIMIT_POWER, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "pilot_description": "Enable pilot mode to control battery power (registers 41, 42)",
                "limit_description": "Enable power limits to set max charge/discharge (registers 43, 44)",
            },
        )

    async def async_step_pilot_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure pilot options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Custom validation that allows us to show specific error messages
            validation_passed = True

            try:
                min_soc = int(user_input.get(CONF_MIN_SOC, DEFAULT_MIN_SOC))
                if not 0 <= min_soc <= 100:
                    errors[CONF_MIN_SOC] = "invalid_min_soc"
                    validation_passed = False
            except (ValueError, TypeError):
                errors[CONF_MIN_SOC] = "invalid_min_soc"
                validation_passed = False

            try:
                auto_pilot_interval = int(
                    user_input.get(
                        CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
                    )
                )
                if not 5 <= auto_pilot_interval <= 300:
                    errors[CONF_AUTO_PILOT_INTERVAL] = "invalid_interval"
                    validation_passed = False
            except (ValueError, TypeError):
                errors[CONF_AUTO_PILOT_INTERVAL] = "invalid_interval"
                validation_passed = False

            # If validation passed, save data and move to next step
            if validation_passed:
                self._data.update(user_input)
                _LOGGER.debug("Pilot options saved: %s", user_input)
                # Move to the NEXT step (not the same step!)
                return await self.async_step_sensors()  # Or whatever comes next

        # Show the form
        return self.async_show_form(
            step_id="pilot_options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MIN_SOC,
                        default=self._data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                    vol.Required(
                        CONF_AUTO_PILOT_INTERVAL,
                        default=self._data.get(
                            CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
            errors=errors,
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure power and PF sensors."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            # If pilot is enabled and sensors configured, go to priority devices
            if self._pilot_from_ha:
                return await self.async_step_priority_devices()

            # Otherwise proceed to battery config
            return await self.async_step_battery_config()

        # Create schema based on pilot configuration
        schema = {}
        if self._pilot_from_ha:
            schema.update(
                {
                    vol.Required(CONF_GRID_POWER_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="power",
                        )
                    ),
                    vol.Optional(CONF_POWER_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="power",
                        )
                    ),
                    vol.Optional(CONF_PF_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="power_factor",
                        )
                    ),
                }
            )

        # If no sensors are needed, skip this step
        # if not schema:
        #     return await self.async_step_battery_config() Line 242 - UNREACHABLE

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "grid_power_description": "Select grid power sensor for power manager (required)",
                "power_sensor_description": "Select smart meter power sensor (optional, for legacy pilot)",
                "pf_sensor_description": "Select power factor sensor (optional, for legacy pilot)",
            },
        )

    async def async_step_priority_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure priority devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery_config()

        return self.async_show_form(
            step_id="priority_devices",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PRIORITY_DEVICES): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "priority_devices_description": "Select devices that should have priority over battery usage (e.g., EV charger, heat pump)"
            },
        )

    async def async_step_battery_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure individual batteries using consistent constants."""
        errors: dict[str, str] = {}

        if user_input is not None:
            battery_count = self._battery_count or 1
            battery_configs: dict[str, dict[str, Any]] = {}
            validation_passed = True

            for i in range(1, battery_count + 1):
                battery_id = BATTERY_IDS[i - 1]  # Use consistent battery IDs
                host_key = f"{battery_id}_host"
                port_key = f"{battery_id}_port"

                host = user_input.get(host_key, "").strip()
                port = user_input.get(port_key, DEFAULT_PORT)

                # Validation logic (unchanged)
                if not host:
                    errors[host_key] = "invalid_host"
                    validation_passed = False
                    continue

                if not self._validate_host(host):
                    errors[host_key] = "invalid_host_format"
                    validation_passed = False
                    continue

                try:
                    port_int = int(port)
                    if not (1 <= port_int <= 65535):
                        errors[port_key] = "invalid_port"
                        validation_passed = False
                        continue
                except (ValueError, TypeError):
                    errors[port_key] = "invalid_port"
                    validation_passed = False
                    continue

                # Store using new constants
                battery_configs[battery_id] = {
                    CONF_BATTERY_HOST: host,
                    CONF_BATTERY_PORT: port_int,
                    CONF_BATTERY_ENABLED: True,
                    CONF_BATTERY_PHASE: BATTERY_PHASES[battery_id],
                    CONF_BATTERY_IS_MASTER: False,  # Set below
                }

            if validation_passed:
                # Set master battery using new constants
                if battery_count > 1 and CONF_MASTER_BATTERY in user_input:
                    master_battery = user_input[CONF_MASTER_BATTERY]
                    if master_battery in battery_configs:
                        self._data[CONF_MASTER_BATTERY] = master_battery
                        battery_configs[master_battery][CONF_BATTERY_IS_MASTER] = True
                    else:
                        errors[CONF_MASTER_BATTERY] = "invalid_master"
                        validation_passed = False
                # Single battery - set battery_a as master
                elif "battery_a" in battery_configs:
                    self._data[CONF_MASTER_BATTERY] = "battery_a"
                    battery_configs["battery_a"][CONF_BATTERY_IS_MASTER] = True

                if validation_passed:
                    # Store nested configuration using new constant
                    self._data[CONF_BATTERIES] = battery_configs

                    return self.async_create_entry(
                        title=f"SAX Battery System ({battery_count} batteries)",
                        data=self._data,
                    )

        # Generate schema using consistent battery IDs
        schema: dict[vol.Marker, Any] = {}
        battery_choices: list[str] = []
        battery_count = self._battery_count or 1

        for i in range(1, battery_count + 1):
            battery_id = BATTERY_IDS[i - 1]
            battery_choices.append(battery_id)

            schema[vol.Required(f"{battery_id}_host")] = str
            schema[vol.Required(f"{battery_id}_port", default=DEFAULT_PORT)] = vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            )

        if battery_count > 1:
            schema[vol.Required(CONF_MASTER_BATTERY, default="battery_a")] = vol.In(
                battery_choices
            )

        return self.async_show_form(
            step_id="battery_config",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "battery_description": f"Configure network settings for {battery_count} SAX batteries",
                "phase_info": "Battery A→L1, Battery B→L2, Battery C→L3",
            },
        )

    def _validate_host(self, host: str) -> bool:
        """Validate host format for security.

        Args:
            host: Hostname or IP address to validate

        Returns:
            bool: True if host format is valid

        Security:
            Prevents malformed hosts that could cause issues in network operations

        """
        if not host or len(host) > 253:
            return False

        # Validate IPv4 address with proper octet range checking
        ipv4_parts = host.split(".")
        if len(ipv4_parts) == 4:
            # Security: Validate each octet is in valid range 0-255
            for part in ipv4_parts:
                # Ensure part is not empty and contains only digits
                if not part or not part.isdigit():
                    # Not a valid IPv4, try hostname validation below
                    return False
                    break  # type: ignore[unreachable]
                octet = int(part)
                if not (0 <= octet <= 255):
                    return False
            else:
                # All parts validated successfully as IPv4
                return True

        # Allow hostnames only
        hostname_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"

        return bool(re.match(hostname_pattern, host))

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        # Validate entry ID first - before processing any input
        entry_id = self.context.get("entry_id")
        if entry_id is None:
            return self.async_abort(reason="unknown")

        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            return self.async_abort(reason="unknown")

        # Get existing entry data
        if user_input is not None:
            # Debug logging for reconfiguration
            _LOGGER.debug("Reconfiguration data: %s", user_input)

            return self.async_create_entry(
                title="SAX Battery",
                data=user_input,
            )

        # Load existing configuration data
        # Copy existing data to allow modification
        self._data = dict(entry.data)
        self._battery_count = self._data.get(CONF_BATTERY_COUNT, 1)
        self._pilot_from_ha = self._data.get(CONF_PILOT_FROM_HA, False)
        self._limit_power = self._data.get(CONF_LIMIT_POWER, False)

        # Start reconfiguration from control options
        return await self.async_step_control_options()


class SAXBatteryOptionsFlowHandler(config_entries.OptionsFlow):
    """SAX Battery config flow options handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize SAX Battery options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Get the current configuration values
            current_pilot_from_ha = self.config_entry.data.get(
                CONF_PILOT_FROM_HA, False
            )
            current_limit_power = self.config_entry.data.get(CONF_LIMIT_POWER, False)

            # Extract pilot-specific options from user input
            pilot_options: dict[str, Any] = {}
            if CONF_MIN_SOC in user_input:
                pilot_options[CONF_MIN_SOC] = user_input[CONF_MIN_SOC]
            if CONF_AUTO_PILOT_INTERVAL in user_input:
                pilot_options[CONF_AUTO_PILOT_INTERVAL] = user_input[
                    CONF_AUTO_PILOT_INTERVAL
                ]
            if CONF_ENABLE_SOLAR_CHARGING in user_input:
                pilot_options[CONF_ENABLE_SOLAR_CHARGING] = user_input[
                    CONF_ENABLE_SOLAR_CHARGING
                ]

            # Build result data - always include feature toggles
            result_data = {
                CONF_PILOT_FROM_HA: user_input.get(
                    CONF_PILOT_FROM_HA, current_pilot_from_ha
                ),
                CONF_LIMIT_POWER: user_input.get(CONF_LIMIT_POWER, current_limit_power),
            }

            # Only include pilot-specific options when pilot is enabled
            if user_input.get(CONF_PILOT_FROM_HA, current_pilot_from_ha):
                result_data.update(pilot_options)

            # Check if pilot mode was disabled and disable entity
            new_pilot_from_ha = user_input.get(
                CONF_PILOT_FROM_HA, current_pilot_from_ha
            )
            if current_pilot_from_ha and not new_pilot_from_ha:
                await self._async_disable_pilot_power_entity()

            _LOGGER.debug("Options flow result data: %s", result_data)

            return self.async_create_entry(title="", data=result_data)

        # Get current configuration for form display
        pilot_enabled = self.config_entry.data.get(CONF_PILOT_FROM_HA, False)
        limit_power_enabled = self.config_entry.data.get(CONF_LIMIT_POWER, False)

        schema: dict[vol.Marker, Any] = {}

        # Always show feature toggle options
        schema.update(
            {
                vol.Optional(
                    CONF_PILOT_FROM_HA,
                    default=self.config_entry.options.get(
                        CONF_PILOT_FROM_HA,
                        self.config_entry.data.get(CONF_PILOT_FROM_HA, False),
                    ),
                ): bool,
                vol.Optional(
                    CONF_LIMIT_POWER,
                    default=self.config_entry.options.get(
                        CONF_LIMIT_POWER,
                        self.config_entry.data.get(CONF_LIMIT_POWER, False),
                    ),
                ): bool,
            }
        )

        # Show pilot-specific options if pilot is currently enabled
        if pilot_enabled:
            schema.update(
                {
                    vol.Optional(
                        CONF_MIN_SOC,
                        default=self.config_entry.options.get(
                            CONF_MIN_SOC,
                            self.config_entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                    vol.Optional(
                        CONF_AUTO_PILOT_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_AUTO_PILOT_INTERVAL,
                            self.config_entry.data.get(
                                CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL
                            ),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                    vol.Optional(
                        CONF_ENABLE_SOLAR_CHARGING,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_SOLAR_CHARGING,
                            self.config_entry.data.get(
                                CONF_ENABLE_SOLAR_CHARGING, True
                            ),
                        ),
                    ): bool,
                }
            )

        # Show informative description based on current feature states
        description_placeholders = {
            "feature_toggles": "Enable or disable pilot mode (registers 41,42) and power limits (registers 43,44)",
        }

        if pilot_enabled:
            description_placeholders["pilot_options"] = "Configure pilot mode settings"
        else:
            description_placeholders["pilot_options"] = (
                "Pilot mode is disabled - enable it above to configure settings"
            )

        if limit_power_enabled:
            description_placeholders["power_limit_status"] = (
                "Power limits are enabled (registers 43,44 active)"
            )
        else:
            description_placeholders["power_limit_status"] = "Power limits are disabled"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            description_placeholders=description_placeholders,
        )

    async def _async_disable_pilot_power_entity(self) -> None:
        """Disable SAX_PILOT_POWER entity when pilot mode is disabled.

        Security:
            OWASP A01: Ensures entity access control follows configuration

        Performance:
            Single entity registry lookup and update
        """
        ent_reg = er.async_get(self.hass)

        # Get unique_id for SAX_PILOT_POWER entity
        unique_id = get_unique_id_for_item(
            self.hass,
            self.config_entry.entry_id,
            SAX_PILOT_POWER,
        )

        if not unique_id:
            _LOGGER.warning("Could not generate unique_id for SAX_PILOT_POWER entity")
            return

        # Find entity in registry
        entity_id = ent_reg.async_get_entity_id("number", DOMAIN, unique_id)

        if not entity_id:
            _LOGGER.debug(
                "SAX_PILOT_POWER entity not found in registry (unique_id=%s)",
                unique_id,
            )
            return

        # Disable entity
        ent_reg.async_update_entity(
            entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
        )

        _LOGGER.info(
            "Disabled SAX_PILOT_POWER entity (entity_id=%s) because CONF_PILOT_FROM_HA was set to False",
            entity_id,
        )
