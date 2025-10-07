
### 3. Update README.md with PowerManager information

```markdown
# SAX Battery Home Assistant Integration

[![GitHub Release](https://img.shields.io/github/release/matfroh/sax_battery_ha.svg?style=for-the-badge)](https://github.com/matfroh/sax_battery_ha/releases)
[![License](https://img.shields.io/github/license/matfroh/sax_battery_ha.svg?style=for-the-badge)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

Home Assistant custom component for SAX Battery systems with advanced power management.

## Features

### Power Management (New in v0.3.0)

The integration now includes a modern **PowerManager** system that replaces the legacy pilot functionality:

- ✅ **State-Based Control**: Uses Home Assistant number entities instead of direct Modbus writes
- ✅ **Solar Charging Mode**: Automatically adjusts battery power based on grid sensor readings
- ✅ **Manual Control Mode**: Set battery power manually via number entity
- ✅ **SOC Protection**: Integrated SOC constraint management prevents battery damage
- ✅ **Mutual Exclusivity**: Only one control mode active at a time
- ✅ **Security-First**: OWASP-compliant input validation and error handling

### Multi-Battery Support

- Configure up to 3 batteries (L1, L2, L3 phases)
- Master/slave battery coordination
- Consolidated smart meter data (master battery only)
- Individual battery monitoring (SOC, power, temperature)

### Battery Monitoring

- Real-time SOC, power, voltage, current
- Temperature monitoring
- Cycle count tracking
- Energy statistics (produced/consumed)

### Smart Meter Integration

- Phase-specific power measurements (L1, L2, L3)
- Total power, voltage, current
- Grid frequency monitoring
- Power factor tracking

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/matfroh/sax_battery_ha`
6. Select category: "Integration"
7. Click "Add"
8. Find "SAX Battery" in the integration list and click "Install"
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from [releases page](https://github.com/matfroh/sax_battery_ha/releases)
2. Extract and copy `custom_components/sax_battery` to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to **Settings > Devices & Services**
2. Click **Add Integration**
3. Search for "SAX Battery"
4. Follow the configuration steps:
   - **Battery Count**: Number of batteries (1-3)
   - **Control Options**: Enable pilot mode and power limits
   - **Pilot Options**: Configure minimum SOC and update interval
   - **Sensors**: Select grid power sensor (required for PowerManager)
   - **Battery Config**: Enter IP addresses and ports for each battery

### PowerManager Configuration

The PowerManager is automatically enabled when `pilot_from_ha` is enabled in your configuration.

#### Required:
- **Grid Power Sensor**: Sensor measuring grid power (required for solar charging mode)

#### Optional:
- **Minimum SOC**: Discharge protection threshold (default: 10%)
- **Update Interval**: How often to check grid sensor (default: 10 seconds)
- **Solar Charging**: Enable automatic solar charging mode

### Control Entities

After setup, you'll have access to:

**Switch Entities** (mutually exclusive):
- `switch.sax_battery_solar_charging_switch` - Enable solar charging mode
- `switch.sax_battery_manual_control_switch` - Enable manual control mode

**Number Entities**:
- `number.sax_battery_pilot_power` - Manual power setpoint
- `number.sax_battery_nominal_power` - Current power setpoint
- `number.sax_battery_nominal_factor` - Power factor
- `number.sax_battery_max_charge` - Maximum charge power limit
- `number.sax_battery_max_discharge` - Maximum discharge power limit
- `number.sax_battery_min_soc` - Minimum SOC threshold

## Usage Examples

### Solar Charging Automation

```yaml
automation:
  - alias: "Enable Solar Charging During Day"
    trigger:
      - platform: sun
        event: sunrise
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.sax_battery_solar_charging_switch
  
  - alias: "Disable Solar Charging At Night"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.sax_battery_solar_charging_switch
