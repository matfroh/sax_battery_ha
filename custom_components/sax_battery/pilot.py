"""Battery pilot service for SAX Battery integration."""
import logging
import asyncio
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.components.number import NumberEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    UnitOfPower,
    PERCENTAGE,
    STATE_ON,
    STATE_OFF,
)
from .const import (
    DOMAIN,
    CONF_POWER_SENSOR,
    CONF_PF_SENSOR,
    CONF_MIN_SOC,
    CONF_PRIORITY_DEVICES,
    CONF_PILOT_FROM_HA,
    CONF_AUTO_PILOT_INTERVAL,
    CONF_ENABLE_SOLAR_CHARGING,
    DEFAULT_MIN_SOC,
    DEFAULT_AUTO_PILOT_INTERVAL,
    SAX_SOC,
    SAX_COMBINED_POWER,
    CONF_MANUAL_CONTROL
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_pilot(hass: HomeAssistant, entry_id: str):
    """Set up the SAX Battery pilot service."""
    sax_data = hass.data[DOMAIN][entry_id]
    
    # Check if pilot mode is enabled
    if not sax_data.entry.data.get(CONF_PILOT_FROM_HA, False):
        _LOGGER.debug("Battery pilot mode is disabled, skipping setup")
        return

    # Create battery pilot instance
    pilot = SAXBatteryPilot(hass, sax_data)
    
    # Store pilot instance
    sax_data.pilot = pilot
    
    # Create entities
    component = EntityComponent(_LOGGER, f"{DOMAIN}_pilot", hass)
    entities = [
        SAXBatteryPilotPowerEntity(pilot),
        SAXBatterySolarChargingSwitch(pilot)
    ]
    
    await component.async_add_entities(entities)
    
    # Start automatic pilot service
    await pilot.async_start()
    return True



class SAXBatteryPilot:
    """Manages automatic battery pilot calculations and control."""
    
    def __init__(self, hass, sax_data):
        """Initialize the battery pilot."""
        self.hass = hass
        self.sax_data = sax_data
        self.entry = sax_data.entry
        self.battery_count = len(sax_data.batteries)
        
        # Configuration values
        self._update_config_values()
        self.power_sensor_entity_id = self.entry.data.get(CONF_POWER_SENSOR)
        self.pf_sensor_entity_id = self.entry.data.get(CONF_PF_SENSOR)
        self.priority_devices = self.entry.data.get(CONF_PRIORITY_DEVICES, [])
        self.min_soc = self.entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self.update_interval = self.entry.data.get(CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL)
        self.solar_charging_enabled = self.entry.data.get(CONF_ENABLE_SOLAR_CHARGING, True)
        
        # Calculated values
        self.calculated_power = 0
        self.max_discharge_power = self.battery_count * 3600
        self.max_charge_power = self.battery_count * 4500
        
        # Modbus
        self.master_battery = sax_data.master_battery
        
        # Track state
        self._remove_interval_update = None
        self._remove_config_update = None
        self._running = False
    
    def _update_config_values(self):
        """Update configuration values from entry data."""
        self.power_sensor_entity_id = self.entry.data.get(CONF_POWER_SENSOR)
        self.pf_sensor_entity_id = self.entry.data.get(CONF_PF_SENSOR)
        self.priority_devices = self.entry.data.get(CONF_PRIORITY_DEVICES, [])
        self.min_soc = self.entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self.update_interval = self.entry.data.get(CONF_AUTO_PILOT_INTERVAL, DEFAULT_AUTO_PILOT_INTERVAL)
        self.solar_charging_enabled = self.entry.data.get(CONF_ENABLE_SOLAR_CHARGING, True)
        _LOGGER.debug(f"Updated config values - min_soc: {self.min_soc}%, update_interval: {self.update_interval}s")

    
    async def async_start(self):
        """Start the pilot service."""
        if self._running:
            return
            
        self._running = True
        self._remove_interval_update = async_track_time_interval(
            self.hass,
            self._async_update_pilot,
            timedelta(seconds=self.update_interval)
        )
          
        # Add listener for config entry updates
        self._remove_config_update = self.entry.add_update_listener(self._async_config_updated)
   
        
        # Do initial calculation
        await self._async_update_pilot(None)
        
        _LOGGER.info(f"SAX Battery pilot started with {self.update_interval}s interval")
     
    async def _async_config_updated(self, hass, entry):
        """Handle config entry updates."""
        self.entry = entry
        self._update_config_values()
        # Apply new configuration immediately
        await self._async_update_pilot(None)
        _LOGGER.info("SAX Battery pilot configuration updated")
          
    async def async_stop(self):
        """Stop the pilot service."""
        if not self._running:
            return
            
        if self._remove_interval_update is not None:
            self._remove_interval_update()
            self._remove_interval_update = None
            
        if self._remove_config_update is not None:
            self._remove_config_update()
            self._remove_config_update = None
            
        self._running = False
        _LOGGER.info("SAX Battery pilot stopped")
        
    async def _async_update_pilot(self, now=None):
        """Update the pilot calculations and send to battery."""
        try:
            # Check if in manual mode
            if self.entry.data.get(CONF_MANUAL_CONTROL, False):
                # Skip automatic calculations in manual mode
                _LOGGER.debug(f"Manual control mode active - Current power setting: {self.calculated_power}W")
      
                # Check SOC constraints for the current manual power setting
                _LOGGER.debug(f"Checking SOC constraints for manual power: {self.calculated_power}W")
                constrained_power = await self._apply_soc_constraints(self.calculated_power)
                if constrained_power != self.calculated_power:
                    _LOGGER.info(f"Manual power needs adjustment from {self.calculated_power}W to {constrained_power}W due to SOC constraints")
                    # Update the power setting if constraints changed it
                    await self._send_power_command(constrained_power, 1.0)
                    self.calculated_power = constrained_power
                    _LOGGER.info(f"Manual power adjusted to {constrained_power}W due to SOC constraints")
                else:
                    _LOGGER.debug(f"No SOC constraint adjustments needed for manual power {self.calculated_power}W")
                return
            
            # Get current power sensor state
            power_state = self.hass.states.get(self.power_sensor_entity_id)
            if power_state is None:
                _LOGGER.warning(f"Power sensor {self.power_sensor_entity_id} not found")
                return
                
            if power_state.state in (None, "unknown", "unavailable"):
                _LOGGER.warning(f"Power sensor {self.power_sensor_entity_id} state is {power_state.state}")
                return
                
            try:
                total_power = float(power_state.state)
            except (ValueError, TypeError) as err:
                _LOGGER.error(f"Could not convert power sensor state '{power_state.state}' to float: {err}")
                return
                
            # Get current PF value
            pf_state = self.hass.states.get(self.pf_sensor_entity_id)
            if pf_state is None:
                _LOGGER.warning(f"PF sensor {self.pf_sensor_entity_id} not found")
                return
                
            if pf_state.state in (None, "unknown", "unavailable"):
                _LOGGER.warning(f"PF sensor {self.pf_sensor_entity_id} state is {pf_state.state}")
                return
                
            try:
                power_factor = float(pf_state.state)
            except (ValueError, TypeError) as err:
                _LOGGER.error(f"Could not convert PF sensor state '{pf_state.state}' to float: {err}")
                return
            
            # Get priority device power consumption
            priority_power = 0
            for device_id in self.priority_devices:
                device_state = self.hass.states.get(device_id)
                if device_state is not None:
                    try:
                        priority_power += float(device_state.state)
                    except (ValueError, TypeError):
                        _LOGGER.warning(f"Could not convert state of {device_id} to number")
            
            # Get current battery power
            battery_power_state = self.hass.states.get(f"sensor.battery_combined_power")
            battery_power = 0
            if battery_power_state is not None:
                try:
                    if battery_power_state.state not in (None, "unknown", "unavailable"):
                        battery_power = float(battery_power_state.state)
                    else:
                        _LOGGER.debug(f"Battery power state is {battery_power_state.state}")
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(f"Could not convert battery power '{battery_power_state.state}' to number: {err}") 
                               
            # Calculate target power
#            net_power = total_power - battery_power
            # Calculate target power
#            if total_power < 0 and priority_power >= 50:
#                net_power = total_power + priority_power - battery_power
#            elif (total_power < 0 and priority_power < 50) or total_power > 0:
#                net_power = total_power - battery_power
#            target_power = -net_power  # Negative because we want to offset consumption

#            _LOGGER.debug(f"Starting calculation with total_power={total_power}, priority_power={priority_power}, battery_power={battery_power}")
#            
#            if total_power < 0 and priority_power >= 50:
#                _LOGGER.debug(f"Condition met: total_power < 0 and priority_power >= 50")
#                net_power = total_power + priority_power - battery_power
#                _LOGGER.debug(f"Calculated net_power = {total_power} + {priority_power} - {battery_power} = {net_power}")
#            elif (total_power < 0 and priority_power < 50) or total_power > 0:
#                _LOGGER.debug(f"Condition met: (total_power < 0 and priority_power < 50) or total_power > 0")
#                net_power = total_power - battery_power
#                _LOGGER.debug(f"Calculated net_power = {total_power} - {battery_power} = {net_power}")
            _LOGGER.debug(f"Starting calculation with total_power={total_power}, priority_power={priority_power}, battery_power={battery_power}")
            
            if priority_power > 50:
                _LOGGER.debug(f"Condition met: priority_power > 50 ({priority_power} > 50)")
                net_power = 0
                _LOGGER.debug(f"Set net_power = 0")
            else:
                _LOGGER.debug(f"Condition met: priority_power <= 50 ({priority_power} <= 50)")
                net_power = total_power - battery_power
                _LOGGER.debug(f"Calculated net_power = {total_power} - {battery_power} = {net_power}")
            
            _LOGGER.debug(f"Final net_power value: {net_power}")

            target_power = -net_power
            _LOGGER.debug(f"Final net_power value: {target_power}")


            
            # Apply limits
            target_power = max(-self.max_discharge_power, min(self.max_charge_power, target_power))
            
            # Check battery SOC constraints
            master_soc = self.master_battery.data.get(SAX_SOC, 0)
        
            # Apply SOC constraints before the "Update calculated power" line (line ~221)
            _LOGGER.debug(f"Pre-constraint target power: {target_power}W")
            target_power = await self._apply_soc_constraints(target_power)
            _LOGGER.debug(f"Post-constraint target power: {target_power}W")

                            
            # Update calculated power
            self.calculated_power = target_power
            
            # Send to battery if solar charging is enabled
            if self.solar_charging_enabled:
                await self._send_power_command(target_power, power_factor)
            else:
                await self._send_power_command(0, power_factor)
                
            _LOGGER.debug(f"Updated battery pilot: target power = {target_power}W, PF = {power_factor}")
            
        except Exception as err:
            _LOGGER.error(f"Error in battery pilot update: {err}")
    
    async def _apply_soc_constraints(self, power_value):
        """Apply SOC constraints to a power value."""
        # Get current battery SOC
        master_soc = self.master_battery.data.get(SAX_SOC, 0)
        self.min_soc = self.entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)

        # Log the input values
        _LOGGER.debug(f"Applying SOC constraints - Current SOC: {master_soc}%, Min SOC: {self.min_soc}%, Power: {power_value}W")

        # Apply constraints
        original_value = power_value
        
        # Don't discharge below min SOC
        if master_soc < self.min_soc and power_value > 0:
            power_value = 0
            _LOGGER.debug(f"Battery SOC at minimum ({master_soc}%), preventing discharge")
            
        # Don't charge above 100%
        if master_soc >= 100 and power_value < 0:
            power_value = 0
            _LOGGER.debug("Battery SOC at maximum (100%), preventing charge")
               
         # Log if any change was made
        if original_value != power_value:
            _LOGGER.info(f"SOC constraint applied: changed power from {original_value}W to {power_value}W")
        else:
            _LOGGER.debug(f"SOC constraint check: no change needed to power value {power_value}W")
        
            
        return power_value
        
    
    async def set_solar_charging(self, enabled):
        """Enable or disable solar charging."""
        self.solar_charging_enabled = enabled
        
        if enabled:
            # Recalculate and send current value
            await self._async_update_pilot()
        else:
            # Send 0 to stop charging from solar
            await self._send_power_command(0, 1.0)
            
        _LOGGER.info(f"Solar charging {'enabled' if enabled else 'disabled'}")

    async def set_manual_power(self, power_value):
        """Set a manual power value."""
        # Apply SOC constraints
        power_value = await self._apply_soc_constraints(power_value)
                  
        # Send the power command with a default power factor of 1.0
        await self._send_power_command(power_value, 1.0)
        self.calculated_power = power_value
        _LOGGER.info(f"Manual power set to {power_value}W")
    
    async def _apply_manual_power_with_constraints(self):
        """Apply the stored manual power value with current SOC constraints."""
        if not hasattr(self, '_requested_manual_power'):
            return
            
        power_value = self._requested_manual_power        
                    
        # Apply SOC constraints
        master_soc = self.master_battery.data.get(SAX_SOC, 0)
        
        # Don't discharge below min SOC
        if master_soc <= self.min_soc and power_value < 0:
            adjusted_power = 0
            _LOGGER.debug(f"Battery SOC at minimum ({master_soc}%), preventing manual discharge")
        
        # Don't charge above 100%
        elif master_soc >= 100 and power_value > 0:
            adjusted_power = 0
            _LOGGER.debug("Battery SOC at maximum (100%), preventing manual charge")
        else:
            adjusted_power = power_value

        # Send the power command with a default power factor of 1.0
        await self._send_power_command(power_value, 1.0)
        self.calculated_power = power_value
        
        if adjusted_power != power_value:
            _LOGGER.info(f"Manual power set to {power_value}W")

    
    async def _send_power_command(self, power, power_factor):
        """Send power command to battery via Modbus."""
        try:
            # Get Modbus client for master battery
            client = self.master_battery._data_manager.modbus_clients.get(
                self.master_battery.battery_id
            )
            
            if client is None:
                _LOGGER.error(f"No Modbus client found for battery {self.master_battery.battery_id}")
                return
                    
            # Check if client is connected
            if not hasattr(client, 'is_socket_open') or not client.is_socket_open():
                _LOGGER.error("Modbus client socket not open, attempting to reconnect")
                try:
                    client.connect()
                    _LOGGER.info("Reconnected to Modbus device")
                except Exception as connect_err:
                    _LOGGER.error(f"Failed to reconnect: {connect_err}")
                    return
            
            # Convert power to integer for Modbus
            power_int = int(power) & 0xFFFF
            
            # Convert PF to integer (assuming PF is a small decimal like 0.95)
            # Scale PF by 1000 to preserve precision
            pf_int = int(power_factor * 10) & 0xFFFF
            
            # Prepare data for writing both registers at once
            values = [power_int, pf_int]
            
            # Set slave ID
            slave_id = 64
            
            _LOGGER.debug(f"Sending combined command: Power={power_int}, PF={pf_int} to registers 41-42 with slave={slave_id}")
            
            # Use write_registers with slave parameter, similar to your working switch implementation
            result = await self.hass.async_add_executor_job(
                lambda: client.write_registers(
                    41,  # Starting register (power control)
                    values,
                    slave=slave_id
                )
            )
            
            if hasattr(result, 'isError') and result.isError():
                _LOGGER.error(f"Error sending combined power and PF command: {result}")
            else:
                _LOGGER.debug(f"Successfully sent combined power and PF command")
                
        except Exception as err:
            _LOGGER.error(f"Failed to send power command: {err}", exc_info=True)

class SAXBatteryPilotPowerEntity(NumberEntity):
    """Entity showing current calculated pilot power."""
    
    def __init__(self, pilot):
        """Initialize the entity."""
        self._pilot = pilot
        self._attr_unique_id = f"{DOMAIN}_pilot_power_{self._pilot.sax_data.device_id}"
        self._attr_name = "Battery Pilot Power"
        self._attr_native_min_value = -self._pilot.max_discharge_power
        self._attr_native_max_value = self._pilot.max_charge_power
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_should_poll = True
        self._attr_mode = "box"
        
        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._pilot.sax_data.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }
    
    @property
    def native_value(self):
        """Return the current calculated power."""
        return self._pilot.calculated_power
    
    @property
    def icon(self):
        """Return the icon to use for the entity."""
        if self._pilot.calculated_power > 0:
            return "mdi:battery-charging"
        elif self._pilot.calculated_power < 0:
            return "mdi:battery-minus"
        return "mdi:battery"
    
    async def async_set_native_value(self, value: float) -> None:
        """Handle manual override of calculated power."""
        await self._pilot._send_power_command(value, 1.0)
        self._pilot.calculated_power = value


class SAXBatterySolarChargingSwitch(SwitchEntity):
    """Switch to enable/disable solar charging."""
    
    def __init__(self, pilot):
        """Initialize the switch."""
        self._pilot = pilot
        self._attr_unique_id = f"{DOMAIN}_solar_charging_{self._pilot.sax_data.device_id}"
        self._attr_name = "Solar Charging"
        
        # Add device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._pilot.sax_data.device_id)},
            "name": "SAX Battery System",
            "manufacturer": "SAX",
            "model": "SAX Battery",
            "sw_version": "1.0",
        }
    
    @property
    def is_on(self):
        """Return true if solar charging is enabled."""
        return self._pilot.solar_charging_enabled
    
    @property
    def icon(self):
        """Return the icon to use for the switch."""
        return "mdi:solar-power" if self.is_on else "mdi:solar-power-off"
    
    async def async_turn_on(self, **kwargs):
        """Turn on solar charging."""
        await self._pilot.set_solar_charging(True)
    
    async def async_turn_off(self, **kwargs):
        """Turn off solar charging."""
        await self._pilot.set_solar_charging(False)