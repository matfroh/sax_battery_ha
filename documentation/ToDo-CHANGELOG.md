
### 4. Add changelog entry

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-10-07

### Added
- **PowerManager**: New state-based power management system
  - Replaces direct Modbus writes with Home Assistant number entities
  - Solar charging mode with grid sensor monitoring
  - Manual control mode with power setpoint
  - Integrated SOC constraint management
  - Debounced updates for improved performance
  - OWASP-compliant security hardening
- **Control Switches**: New mutually exclusive switches
  - `solar_charging_switch`: Enable/disable solar charging mode
  - `manual_control_switch`: Enable/disable manual control mode
- **Grid Power Sensor**: Required configuration for PowerManager
- **Migration Guide**: Comprehensive guide for migrating from pilot.py
- **Documentation**: Enhanced README and architecture documentation

### Changed
- **pilot.py**: Now deprecated with migration path to PowerManager
  - Added deprecation warnings throughout
  - Will be removed in v1.0.0
- **number.py**: Enhanced with power manager callbacks
  - Power manager notification on value changes
  - SOC constraints applied before writes
- **switch.py**: Enhanced control switch mutual exclusivity
  - Proper config entry updates
  - Comprehensive logging
- **config_flow.py**: Updated with grid power sensor configuration
  - Grid sensor required for PowerManager
  - Legacy sensors now optional
- **Performance**: Improved polling efficiency
  - Only polls enabled entities from entity registry
  - Debounced grid monitoring (10s default vs 60s legacy)
- **Security**: Enhanced input validation
  - OWASP A01: Access control for master battery only
  - OWASP A05: Resource protection and validation

### Deprecated
- **pilot.py**: Legacy pilot module deprecated
  - Use PowerManager with number entities instead
  - See MIGRATION_GUIDE.md for migration steps
- **Legacy sensor configuration**: `power_sensor` and `pf_sensor` now optional
  - Grid power sensor is the new requirement
- **Direct service calls**: Use number entity service calls instead

### Fixed
- SOC constraint application in number entities
- Power manager state synchronization
- Config entry update handling in switches
- Entity registry filtering performance

### Security
- Input validation for all sensor inputs (OWASP A05)
- Access control for power manager (OWASP A01)
- Proper resource cleanup on unload
- Secure configuration validation

### Performance
- Efficient entity registry queries
- Debounced grid power monitoring
- Non-blocking service calls
- Optimized polling strategy

## [0.2.0] - 2025-09-15

### Added
- Multi-battery support (up to 3 batteries)
- Master/slave battery coordination
- SOC manager for battery protection
- Entity registry integration

### Changed
- Improved coordinator architecture
- Enhanced configuration flow
- Better error handling

## [0.1.0] - 2025-08-01

### Added
- Initial release
- Basic battery monitoring
- Smart meter integration
- Modbus TCP communication

## Migration Notes

### v0.3.0 Migration

Users upgrading to v0.3.0 should:

1. Review [MIGRATION_GUIDE.md](documentation/MIGRATION_GUIDE.md)
2. Configure grid power sensor in integration settings
3. Update automations to use new control switches
4. Test PowerManager functionality before removing pilot.py dependencies

**Timeline**:
- v0.3.0: PowerManager introduced, pilot.py deprecated
- v0.4.0: Deprecation warnings enforced
- v1.0.0: pilot.py removed (planned Q1 2026)

[0.3.0]: https://github.com/matfroh/sax_battery_ha/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/matfroh/sax_battery_ha/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/matfroh/sax_battery_ha/releases/tag/v0.1.0
