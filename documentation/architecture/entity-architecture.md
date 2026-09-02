# Entity Architecture

The integration uses item-driven entity creation with coordinator-backed state.

## Entity Foundations

- `SAXItem`: virtual/calculated/config entities
- `ModbusItem`: hardware-backed entities with register metadata

These item definitions are consumed by sensor, number, and switch platforms.

## Entity Data Sources

| Entity Type | Backing | Value Source |
| --- | --- | --- |
| Hardware sensor/number | ModbusItem | coordinator data from provider/modbus |
| Calculated sensor | SAXItem | coordinator-calculated values |
| Config number/switch | SAXItem | coordinator/config runtime state |

## Unique ID Rules

Unique IDs are generated via model utility functions in [custom_components/sax_battery/models.py](../../custom_components/sax_battery/models.py), not by hardcoded string templates in entity classes.

Scope patterns:

- Cluster entities: one instance across integration
- Per-battery entities: one instance per configured battery

## SunSpec Mapping Behavior

- SunSpec provider resolves legacy entity keys to canonical SunSpec item mappings.
- Duplicate SunSpec aliases are normalized via canonical item resolution.
- Entities remain stable while protocol mode changes internally.

## Number Entity Considerations

- Power/limit numbers pass through coordinator write queue.
- SOC constraints can override requested discharge-related values.
- Write-only behavior uses cached/local state patterns for UI continuity.

## Availability Model

- Coordinator update success drives hardware-backed availability.
- Optional SunSpec smart meter block failure affects only impacted entities.
- Required-block degradation is visible in diagnostics and coordinator state behavior.

Last updated: 2026-08-08
