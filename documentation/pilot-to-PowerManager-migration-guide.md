# Migration Guide: pilot.py to PowerManager

## Overview

The legacy `pilot.py` module has been deprecated in favor of the new `PowerManager` system. This guide will help you migrate your configuration to use the new system.

## Why Migrate?

The new PowerManager offers several advantages:

1. **Better Integration**: Uses Home Assistant number entities (`SAX_NOMINAL_POWER`, `SAX_NOMINAL_FACTOR`) instead of direct Modbus writes
2. **Improved Control**: Clear switch entities for solar charging and manual control modes
3. **SOC Protection**: Integrated SOC constraint management through `soc_manager.py`
4. **Performance**: Debounced grid monitoring with configurable intervals
5. **Security**: Enhanced input validation and error handling (OWASP compliance)

## Migration Steps

### Step 1: Verify Current Configuration

Check your current configuration in **Settings > Devices & Services > SAX Battery**:

```yaml
# Current configuration (pilot.py)
pilot_from_ha: true
power_sensor: sensor.smart_meter_power
pf_sensor: sensor.smart_meter_pf
enable_solar_charging: true
auto_pilot_interval: 60
```

## Automation example

### with pilot

```yml
automation:
  - alias: "Set Battery Manual Power"
    trigger:
      - platform: state
        entity_id: input_number.battery_power_target
    action:
      - service: sax_battery.set_manual_power
        data:
          power: "{{ states('input_number.battery_power_target') }}"
```

### with PowerManager

```yml
automation:
  - alias: "Set Battery Manual Power"
    trigger:
      - platform: state
        entity_id: input_number.battery_power_target
    action:
      # Enable manual control mode
      - service: switch.turn_on
        target:
          entity_id: switch.sax_battery_manual_control_switch
      # Set power via number entity
      - service: number.set_value
        target:
          entity_id: number.sax_battery_pilot_power
        data:
          value: "{{ states('input_number.battery_power_target') | float }}"
```

### Manual Control Based on Electricity Price

```yml
automation:
  - alias: "Charge Battery When Electricity Is Cheap"
    trigger:
      - platform: numeric_state
        entity_id: sensor.electricity_price
        below: 0.10
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.sax_battery_manual_control_switch
      - service: number.set_value
        target:
          entity_id: number.sax_battery_pilot_power
        data:
          value: -3000  # Charge at 3000W
  
  - alias: "Discharge Battery When Electricity Is Expensive"
    trigger:
      - platform: numeric_state
        entity_id: sensor.electricity_price
        above: 0.30
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.sax_battery_manual_control_switch
      - service: number.set_value
        target:
          entity_id: number.sax_battery_pilot_power
        data:
          value: 3000  # Discharge at 3000W
```

### SOC Protection

```yml
automation:
  - alias: "Protect Battery From Deep Discharge"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sax_battery_combined_soc
        below: 15
    action:
      - service: number.set_value
        target:
          entity_id: number.sax_battery_min_soc
        data:
          value: 20  # Increase minimum SOC to 20%
      - service: notify.notify
        data:
          message: "Battery SOC low - increasing minimum SOC protection"
```
