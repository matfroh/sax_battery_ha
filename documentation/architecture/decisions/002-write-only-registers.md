# ADR-002: Write-Only Register State Strategy

Date: 2026-08-08
Status: Accepted

## Context

Some SAX control paths rely on write-focused behavior where immediate read-back is not always reliable for UI continuity. Users still need consistent control feedback and restart-resilient behavior.

## Decision

Keep a software-visible state strategy for writable controls and refresh control state through coordinator/provider flows.

### Implemented characteristics

- writes are serialized by coordinator queue
- successful writes update runtime values immediately
- SunSpec mode performs immediate control-block refresh after successful writes
- periodic control refresh keeps values synchronized over time

## Rationale

- prevents stale UI after control operations
- supports device-side changes and restart scenarios
- avoids relying on per-entity ad hoc readbacks

## Consequences

Positive:

- predictable operator experience
- single write/read orchestration path

Trade-off:

- requires control refresh telemetry and diagnostics to identify stale or failed refresh cycles

## Related

- [../modbus-communication.md](../modbus-communication.md)
- [../coordinator-pattern.md](../coordinator-pattern.md)
