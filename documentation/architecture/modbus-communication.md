# Modbus Communication

This document reflects the current transport and protocol behavior implemented by the integration.

## Protocol Modes

- Legacy mode: Unit-ID 64, item-based reads
- SunSpec mode: Unit-ID 100 (preferred) or Unit-ID 40 compatibility probe

Detection flow is implemented in [custom_components/sax_battery/protocol_detector.py](../../custom_components/sax_battery/protocol_detector.py).

## Communication Layers

```mermaid
graph LR
    COORD[SAXBatteryCoordinator] --> PROVIDER[DataProvider]
    PROVIDER --> API[ModbusAPI]
    API --> PM[PyModbus Client]
    PM --> HW[SAX Battery]
```

## SunSpec Register Block Policy

| Name | Range | Required |
| --- | --- | --- |
| device_metadata | 40000-40014 | Yes |
| battery_sensor_data | 40015-40046 | Yes |
| battery_controls | 40047-40053 | Yes |
| smartmeter_data | 40054-40094 | No |
| battery_states | 40095-40114 | Yes |

Block definitions are centralized in [custom_components/sax_battery/sunspec_map.py](../../custom_components/sax_battery/sunspec_map.py).

## Read Path

- Legacy: `item.async_read_value()` per enabled item.
- SunSpec: block reads via `read_sunspec_register_block` and centralized decoding.
- SunSpec realtime path does not fall back to direct per-item register reads for unmapped items.

## Write Path

- Writes are serialized by coordinator write queue.
- Number writes call Modbus API register writes through coordinator methods.
- SunSpec mode refreshes control block values after successful writes.
- Periodic control refresh keeps cached control state synchronized even without writes.

## Failure and Retry Behavior

- SunSpec block reads use bounded retries for transient failures.
- Coordinator applies circuit-breaker protection and structured `UpdateFailed` signaling.

## Observability

- Provider block diagnostics include last success, last error, cached register count.
- Aggregate health fields distinguish required-block degradation from optional smart meter unavailability.

Last updated: 2026-08-08
