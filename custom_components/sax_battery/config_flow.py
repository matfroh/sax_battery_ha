"""Config flow for SAX Battery integration."""

from __future__ import annotations

import logging
import re
from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .const import (
    BATTERY_IDS,
    BATTERY_PHASES,
    CONF_BALANCED_LOADING,
    CONF_BATTERIES,
    CONF_BATTERY_COUNT,
    CONF_BATTERY_ENABLED,
    CONF_BATTERY_HOST,
    CONF_BATTERY_IS_MASTER,
    CONF_BATTERY_PHASE,
    CONF_BATTERY_PORT,
    CONF_CONTROL_POWER,
    CONF_DEVICE_ID,
    CONF_LIMIT_POWER,
    CONF_MASTER_BATTERY,
    CONF_MIN_SOC,
    CONF_POWER_SENSOR,
    CONF_SM_CONNECTED,
    DEFAULT_MIN_SOC,
    DEFAULT_PORT,
    DOMAIN,
    SAX_MAX_CHARGE,
    SAX_MAX_DISCHARGE,
)
from .const_legacy import MODBUS_BATTERY_POWER_LIMIT_ITEMS

_LOGGER = logging.getLogger(__name__)


class SAXBatteryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SAX Battery."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._battery_count: int | None = None
        self._device_id: str = str(uuid.uuid4())  # Generate unique device ID
        self._control_power: bool = False
        self._limit_power: bool = False
        self._sm_connected: bool = True
        self._balanced_loading: bool = False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SAXBatteryOptionsFlowHandler:
        """Create the options flow."""
        return SAXBatteryOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # Allow only one SAX hub config entry. Additional batteries must be added
        # by reconfiguring the existing entry.
        if (
            self.context.get("source") != "reconfigure"
            and self._async_current_entries()
        ):
            return self.async_abort(reason="single_instance_allowed")

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
                    vol.Required(
                        CONF_BATTERY_COUNT,
                        default=self._battery_count or 1,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
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
            self._control_power = user_input[CONF_CONTROL_POWER]
            self._limit_power = user_input[CONF_LIMIT_POWER]
            self._data.update(user_input)

            # Debug logging to verify configuration storage
            _LOGGER.debug(
                "Control options saved: control_power=%s, limit_power=%s",
                self._control_power,
                self._limit_power,
            )

            # Route to appropriate next step based on selections
            if self._control_power:
                return await self.async_step_power_options()
            # Skip control-specific steps if not enabled
            return await self.async_step_battery_config()

        return self.async_show_form(
            step_id="control_options",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONTROL_POWER, default=False): bool,
                    vol.Required(CONF_LIMIT_POWER, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "control_power_description": "Enable power control from Home Assistant (registers 41, 42)",
                "limit_description": "Enable power limits to set max charge/discharge (registers 43, 44)",
            },
        )

    async def async_step_power_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure power management options (smart meter, balanced loading)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._sm_connected = user_input.get(CONF_SM_CONNECTED, True)
            self._balanced_loading = user_input.get(CONF_BALANCED_LOADING, False)
            self._data.update(user_input)

            _LOGGER.debug(
                "Power options saved: sm_connected=%s, balanced_loading=%s",
                self._sm_connected,
                self._balanced_loading,
            )

            # Route based on selections
            if not self._sm_connected and self._balanced_loading:
                return await self.async_step_sensors()
            if not self._sm_connected:
                return await self.async_step_battery_config()
            # sm_connected=True → smart meter handles power
            return await self.async_step_battery_config()

        return self.async_show_form(
            step_id="power_options",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SM_CONNECTED, default=self._sm_connected): bool,
                    vol.Required(
                        CONF_BALANCED_LOADING, default=self._balanced_loading
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure Grid power sensor and PV sensor for power balancing."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            # No priority devices step - go directly to battery config
            return await self.async_step_battery_config()

        # Build schema based on current configuration
        schema = {}
        needs_grid_sensor = self._control_power or (
            not self._sm_connected and self._balanced_loading
        )

        if needs_grid_sensor:
            schema[vol.Required(CONF_POWER_SENSOR)] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class="power",
                )
            )

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "power_sensor_description": f"Select Grid power sensor for balanced charging/discharging ({UnitOfPower.WATT} required for power control)",
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
            seen_hosts: set[str] = set()

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

                normalized_host = host.lower()
                if normalized_host in seen_hosts:
                    errors[host_key] = "duplicate_host"
                    validation_passed = False
                    continue

                if self._is_host_used_by_other_entry(normalized_host):
                    errors[host_key] = "duplicate_host"
                    validation_passed = False
                    continue

                seen_hosts.add(normalized_host)

                try:
                    port_int = int(port)
                    if not (1 <= port_int <= 65535):
                        errors[port_key] = "invalid_port"
                        validation_passed = False
                        continue
                except ValueError, TypeError:
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
                # Single battery - set bess_a as master
                elif "bess_a" in battery_configs:
                    self._data[CONF_MASTER_BATTERY] = "bess_a"
                    battery_configs["bess_a"][CONF_BATTERY_IS_MASTER] = True

                if validation_passed:
                    # Store nested configuration using new constant
                    self._data[CONF_BATTERIES] = battery_configs

                    # Handle completion based on flow type
                    if self.context.get("source") == "reconfigure":
                        # Get the config entry from context for reconfiguration
                        entry_id = self.context.get("entry_id")
                        # Type guard: Validate entry_id is not None before passing to async_get_entry
                        if not entry_id:
                            return self.async_abort(
                                reason="reconfigure_entry_not_found"
                            )

                        entry = self.hass.config_entries.async_get_entry(entry_id)

                        if entry is None:
                            return self.async_abort(
                                reason="reconfigure_entry_not_found"
                            )

                        # Update existing entry for reconfiguration
                        self.hass.config_entries.async_update_entry(
                            entry,
                            data={**entry.data, **self._data},
                            title=f"SAX Battery System ({battery_count} batteries)",
                        )
                        return self.async_abort(reason="reconfigure_successful")

                    # Create new entry for initial setup
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
            schema[vol.Required(CONF_MASTER_BATTERY, default="bess_a")] = vol.In(
                battery_choices
            )

        return self.async_show_form(
            step_id="battery_config",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "battery_count": str(self._battery_count),
                "battery_description": f"Configure network settings for {battery_count} SAX batteries",
                "phase_info": "Battery A (L1), Battery B (L2), Battery C (L3)",
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

        # Load existing configuration data
        # Copy existing data to allow modification
        self._data = dict(entry.data)
        self._battery_count = self._data.get(CONF_BATTERY_COUNT, 1)
        self._control_power = self._data.get(CONF_CONTROL_POWER, False)
        self._limit_power = self._data.get(CONF_LIMIT_POWER, False)
        self._sm_connected = self._data.get(CONF_SM_CONNECTED, True)
        self._balanced_loading = self._data.get(CONF_BALANCED_LOADING, False)

        # Start reconfiguration from battery count to allow adding/removing batteries.
        return await self.async_step_user(user_input)

    def _is_host_used_by_other_entry(self, host: str) -> bool:
        """Return True if host is already used by another config entry."""
        current_entry_id = self.context.get("entry_id")

        for entry in self._async_current_entries():
            if current_entry_id and entry.entry_id == current_entry_id:
                continue

            # New nested format.
            batteries = entry.data.get(CONF_BATTERIES, {})
            if isinstance(batteries, dict):
                for config in batteries.values():
                    if not isinstance(config, dict):
                        continue
                    existing_host = config.get(CONF_BATTERY_HOST, "")
                    if (
                        isinstance(existing_host, str)
                        and existing_host.strip().lower() == host
                    ):
                        return True

            # Legacy format fallback.
            battery_count = int(entry.data.get(CONF_BATTERY_COUNT, 1))
            for i in range(1, battery_count + 1):
                battery_id = BATTERY_IDS[i - 1]
                legacy_host = entry.data.get(f"{battery_id}_host", "")
                if isinstance(legacy_host, str) and legacy_host.strip().lower() == host:
                    return True

        return False


class SAXBatteryOptionsFlowHandler(config_entries.OptionsFlow):
    """SAX Battery config flow options handler."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Get the current configuration values
            current_control_power = self.config_entry.data.get(
                CONF_CONTROL_POWER, False
            )
            current_limit_power = self.config_entry.data.get(CONF_LIMIT_POWER, False)
            current_sm_connected = self.config_entry.data.get(CONF_SM_CONNECTED, True)

            # Extract power-specific options from user input
            power_options: dict[str, Any] = {}
            if CONF_MIN_SOC in user_input:
                power_options[CONF_MIN_SOC] = user_input[CONF_MIN_SOC]

            # Build result data - always include feature toggles
            result_data = {
                CONF_CONTROL_POWER: user_input.get(
                    CONF_CONTROL_POWER, current_control_power
                ),
                CONF_LIMIT_POWER: user_input.get(CONF_LIMIT_POWER, current_limit_power),
                CONF_SM_CONNECTED: user_input.get(
                    CONF_SM_CONNECTED, current_sm_connected
                ),
            }

            # Smart meter and balanced loading options
            new_sm_connected = result_data[CONF_SM_CONNECTED]
            if not new_sm_connected:
                result_data[CONF_BALANCED_LOADING] = user_input.get(
                    CONF_BALANCED_LOADING, False
                )
            else:
                # Clear balanced loading config when SM is connected
                result_data[CONF_BALANCED_LOADING] = False

            # Only include power-specific options when control power is enabled
            if user_input.get(CONF_CONTROL_POWER, current_control_power):
                result_data.update(power_options)

            # Update config entry data
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, **result_data},
            )

            # Auto-enable power limit entities if newly enabled
            new_limit_power = user_input.get(CONF_LIMIT_POWER, current_limit_power)
            if new_limit_power and not current_limit_power:
                # User just enabled power limits
                await self._enable_power_limit_entities()

            # Handle feature disabling
            new_control_power = user_input.get(
                CONF_CONTROL_POWER, current_control_power
            )
            new_limit_power = user_input.get(CONF_LIMIT_POWER, current_limit_power)

            # Disable power limit entities if feature was disabled
            if not new_limit_power and current_limit_power:
                await self._async_disable_power_limit_entities()

            # Stop Power Manager if control power was disabled
            if not new_control_power and current_control_power:
                await self._async_stop_power_manager()

            # Update SOC Manager state if limit power changed
            if new_limit_power != current_limit_power:
                await self._async_update_soc_manager_state(new_limit_power)

            # Handle SM entity enable/disable when sm_connected changes
            if new_sm_connected != current_sm_connected:
                if new_sm_connected:
                    await self._async_enable_sm_entities()
                else:
                    await self._async_disable_sm_entities()

            # Reload the integration to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            _LOGGER.debug("Options flow result data: %s", result_data)

            return self.async_create_entry(title="", data=result_data)

        # Get current configuration for form display
        control_power_enabled = self.config_entry.data.get(CONF_CONTROL_POWER, False)
        limit_power_enabled = self.config_entry.data.get(CONF_LIMIT_POWER, False)
        sm_connected = self.config_entry.data.get(CONF_SM_CONNECTED, True)
        balanced_loading = self.config_entry.data.get(CONF_BALANCED_LOADING, False)  # noqa: F841

        schema: dict[vol.Marker, Any] = {}

        # Always show feature toggle options
        schema.update(
            {
                vol.Optional(
                    CONF_CONTROL_POWER,
                    default=self.config_entry.options.get(
                        CONF_CONTROL_POWER,
                        self.config_entry.data.get(CONF_CONTROL_POWER, False),
                    ),
                ): bool,
                vol.Optional(
                    CONF_LIMIT_POWER,
                    default=self.config_entry.options.get(
                        CONF_LIMIT_POWER,
                        self.config_entry.data.get(CONF_LIMIT_POWER, False),
                    ),
                ): bool,
                vol.Optional(
                    CONF_SM_CONNECTED,
                    default=self.config_entry.data.get(CONF_SM_CONNECTED, True),
                ): bool,
            }
        )

        # Show balanced loading options when SM is not connected
        if not sm_connected:
            schema[
                vol.Optional(
                    CONF_BALANCED_LOADING,
                    default=self.config_entry.data.get(CONF_BALANCED_LOADING, False),
                )
            ] = bool

        # Show control-power-specific options if power control is currently enabled
        if control_power_enabled:
            schema.update(
                {
                    vol.Optional(
                        CONF_MIN_SOC,
                        default=self.config_entry.options.get(
                            CONF_MIN_SOC,
                            self.config_entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                }
            )

        # Show informative description based on current feature states
        description_placeholders = {
            "feature_toggles": "Enable or disable power control (registers 41,42) and power limits (registers 43,44)",
        }

        if control_power_enabled:
            description_placeholders["control_power_options"] = (
                "Configure power control settings"
            )
        else:
            description_placeholders["control_power_options"] = (
                "Power control is disabled - enable it above to configure settings"
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

    async def _enable_power_limit_entities(self) -> None:
        """Enable SAX_MAX_DISCHARGE and SAX_MAX_CHARGE entities when power limits enabled.

        Security:
            OWASP A01: Ensures entity access control follows configuration

        Performance:
            Efficient registry lookups with proper validation
        """
        ent_reg = er.async_get(self.hass)

        # Get SAXBatteryData instance from integration data
        integration_data = self.hass.data.get(DOMAIN, {}).get(
            self.config_entry.entry_id
        )

        if not integration_data:
            _LOGGER.error(
                "Integration data not found, cannot enable power limit entities"
            )
            return

        sax_data = integration_data.get("sax_data")
        if not sax_data:
            _LOGGER.error(
                "SAXBatteryData not found, cannot enable power limit entities"
            )
            return

        # Power limit items to enable
        power_limit_items = [
            item
            for item in MODBUS_BATTERY_POWER_LIMIT_ITEMS
            if item.name in [SAX_MAX_DISCHARGE, SAX_MAX_CHARGE]
        ]

        enabled_count = 0

        for item in power_limit_items:
            try:
                # Use SAXBatteryData method for unique_id generation (cluster entity)
                unique_id = sax_data.get_unique_id_for_item(
                    item,
                    battery_id=None,  # Cluster-wide entity
                )

                if not unique_id:
                    _LOGGER.warning(
                        "Could not generate unique_id for %s",
                        item.name,
                    )
                    continue

                # Find entity in registry
                entity_id = ent_reg.async_get_entity_id("number", DOMAIN, unique_id)

                if not entity_id:
                    _LOGGER.warning(
                        "Entity %s not found in registry (unique_id: %s)",
                        item.name,
                        unique_id,
                    )
                    continue

                # Enable entity
                ent_reg.async_update_entity(
                    entity_id,
                    disabled_by=None,
                )
                enabled_count += 1

                _LOGGER.info(
                    "Enabled power limit entity %s (entity_id=%s) because CONF_LIMIT_POWER was set to True",
                    item.name,
                    entity_id,
                )

            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Failed to enable power limit entity %s: %s",
                    item.name,
                    err,
                )

        if enabled_count > 0:
            _LOGGER.info(
                "Enabled %d power limit entities based on options flow configuration",
                enabled_count,
            )

    async def _async_disable_power_limit_entities(self) -> None:
        """Disable power limit entities when CONF_LIMIT_POWER is disabled.

        Security:
            OWASP A01: Ensures entity access control follows configuration
            OWASP A05: Prevents unauthorized hardware access when feature disabled

        Performance:
            Efficient registry lookups with proper validation
        """
        ent_reg = er.async_get(self.hass)

        # Get SAXBatteryData instance from integration data
        integration_data = self.hass.data.get(DOMAIN, {}).get(
            self.config_entry.entry_id
        )

        if not integration_data:
            _LOGGER.error(
                "Integration data not found, cannot disable power limit entities"
            )
            return

        sax_data = integration_data.get("sax_data")
        if not sax_data:
            _LOGGER.error(
                "SAXBatteryData not found, cannot disable power limit entities"
            )
            return

        # Power limit items to disable
        power_limit_items = [
            item
            for item in MODBUS_BATTERY_POWER_LIMIT_ITEMS
            if item.name in [SAX_MAX_DISCHARGE, SAX_MAX_CHARGE]
        ]

        disabled_count = 0

        for item in power_limit_items:
            try:
                # Use SAXBatteryData method for unique_id generation (cluster entity)
                unique_id = sax_data.get_unique_id_for_item(
                    item,
                    battery_id=None,  # Cluster-wide entity
                )

                if not unique_id:
                    _LOGGER.warning(
                        "Could not generate unique_id for %s",
                        item.name,
                    )
                    continue

                # Find entity in registry
                entity_id = ent_reg.async_get_entity_id("number", DOMAIN, unique_id)

                if not entity_id:
                    _LOGGER.debug(
                        "Power limit entity %s not found in registry (unique_id: %s)",
                        item.name,
                        unique_id,
                    )
                    continue

                # Disable entity
                ent_reg.async_update_entity(
                    entity_id,
                    disabled_by=er.RegistryEntryDisabler.INTEGRATION,
                )
                disabled_count += 1

                _LOGGER.info(
                    "Disabled power limit entity %s (entity_id=%s) because CONF_LIMIT_POWER was set to False",
                    item.name,
                    entity_id,
                )

            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Failed to disable power limit entity %s: %s",
                    item.name,
                    err,
                )

        if disabled_count > 0:
            _LOGGER.info(
                "Disabled %d power limit entities based on options flow configuration",
                disabled_count,
            )

    async def _async_stop_power_manager(self) -> None:
        """Stop Power Manager when pilot feature is disabled.

        Security:
            OWASP A05: Proper resource cleanup prevents memory leaks

        Performance:
            Graceful shutdown of interval timers and config listeners
        """
        integration_data = self.hass.data.get(DOMAIN, {}).get(
            self.config_entry.entry_id
        )

        if not integration_data:
            _LOGGER.debug(
                "Integration data not found for entry %s",
                self.config_entry.entry_id,
            )
            return

        power_manager = integration_data.get("power_manager")
        if power_manager:
            await power_manager.async_stop()
            # Remove from integration data
            integration_data.pop("power_manager", None)
            _LOGGER.info(
                "Power manager stopped because CONF_CONTROL_POWER was set to False"
            )
        else:
            _LOGGER.debug("No power manager found to stop")

    async def _async_update_soc_manager_state(self, enabled: bool) -> None:
        """Update SOC Manager enabled state when CONF_LIMIT_POWER changes.

        Args:
            enabled: New enabled state for SOC Manager

        Security:
            OWASP A05: Validates coordinator state before updating
        """
        integration_data = self.hass.data.get(DOMAIN, {}).get(
            self.config_entry.entry_id
        )

        if not integration_data:
            _LOGGER.error("Integration data not found, cannot update SOC manager state")
            return

        coordinators = integration_data.get("coordinators", {})
        updated_count = 0

        for coordinator in coordinators.values():
            if hasattr(coordinator, "soc_manager") and coordinator.soc_manager:
                coordinator.soc_manager.enabled = enabled
                updated_count += 1
                _LOGGER.debug(
                    "Updated SOC manager for %s: enabled=%s",
                    coordinator.battery_id,
                    enabled,
                )

        if updated_count > 0:
            _LOGGER.info(
                "Updated %d SOC managers: enabled=%s (CONF_LIMIT_POWER changed)",
                updated_count,
                enabled,
            )

    async def _async_enable_sm_entities(self) -> None:
        """Enable SM device entities when smart meter is connected.

        Security:
            OWASP A01: Ensures entity access control follows configuration
        """
        await self._async_set_sm_entities_disabled_by(disabled_by=None)
        _LOGGER.info("Enabled SM entities because sm_connected was set to True")

    async def _async_disable_sm_entities(self) -> None:
        """Disable SM device entities when smart meter is not connected.

        Security:
            OWASP A01: Prevents access to unavailable hardware entities
        """
        await self._async_set_sm_entities_disabled_by(
            disabled_by=er.RegistryEntryDisabler.INTEGRATION
        )
        _LOGGER.info("Disabled SM entities because sm_connected was set to False")

    async def _async_set_sm_entities_disabled_by(
        self, disabled_by: er.RegistryEntryDisabler | None
    ) -> None:
        """Set disabled_by for all SM device entities.

        Args:
            disabled_by: Disabler to set, or None to enable
        """
        ent_reg = er.async_get(self.hass)
        updated_count = 0

        for entity_entry in er.async_entries_for_config_entry(
            ent_reg, self.config_entry.entry_id
        ):
            # SM entities have unique IDs containing "sax_sm_" prefix
            if entity_entry.unique_id and "_sm_" in entity_entry.unique_id:
                ent_reg.async_update_entity(
                    entity_entry.entity_id,
                    disabled_by=disabled_by,
                )
                updated_count += 1

        _LOGGER.debug(
            "Updated %d SM entities: disabled_by=%s",
            updated_count,
            disabled_by,
        )
