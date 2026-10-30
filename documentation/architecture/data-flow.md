# Data Flow

This document describes current runtime flows for monitoring, control writes, and safety enforcement.

## Monitoring Flow

```mermaid
flowchart LR
    HW[SAX Battery / Smart Meter] --> MODBUS[ModbusAPI]
    MODBUS --> PROVIDER[DataProvider]
    PROVIDER --> COORD[SAXBatteryCoordinator]
    COORD --> ENT[Entities]
    ENT --> UI[Home Assistant UI]
```

### Notes

- Legacy mode reads item values directly through item read path.
- SunSpec mode reads documented blocks and maps values back to stable entity keys.

## Control Write Flow

```mermaid
sequenceDiagram
    participant U as User
    participant E as Number Entity
    participant C as Coordinator
    participant Q as Write Queue
    participant M as ModbusAPI
    participant P as SunSpec Provider

    U->>E: set value
    E->>E: validate and apply constraints
    E->>C: enqueue write
    C->>Q: dequeue and process
    C->>M: write register(s)
    M-->>C: result
    alt SunSpec mode and write success
      C->>P: refresh_control_values
      P-->>C: updated control values
    end
    C-->>E: state update
```

## SunSpec Block Read Flow

```mermaid
sequenceDiagram
    participant C as Coordinator
    participant P as SunSpecDataProvider
    participant S as sunspec_client
    participant M as ModbusAPI

    C->>P: get_*_values(items)
    P->>P: map items to one logical block
    P->>S: read_sunspec_register_block
    S->>M: read_register_block
    M-->>S: raw block values
    S-->>P: block values
    P->>P: decode_sunspec_block_values
    P-->>C: normalized entity-key values
```

## SOC Protection Flow

```mermaid
flowchart TD
    C[Coordinator Update] --> SM[SOCManager check]
    SM --> PRE{enforcement prerequisites met?}
    PRE -->|no| END[No action]
    PRE -->|yes| LOW{combined SOC < min SOC?}
    LOW -->|no| END
    LOW -->|yes| ENF[Write max discharge limit]
    ENF --> END
```

## Diagnostics Flow

- Coordinator exposes provider diagnostics via diagnostics endpoint.
- SunSpec provider diagnostics include per-block and aggregate health.
- Optional smart meter block failures are tracked without declaring required session degradation.

Last updated: 2026-08-08
