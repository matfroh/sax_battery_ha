# ADR-001: Coordinator Pattern for Runtime Control

Date: 2026-08-08
Status: Accepted

## Context

The integration manages multiple batteries, mixed protocol modes, queued writes, safety constraints, and periodic updates. A single consistent runtime pattern is required to keep entity state coherent and resilient during communication failures.

## Decision

Use one `DataUpdateCoordinator` per configured battery as the integration runtime control plane.

### Implemented characteristics

- role-based update interval:
  - master: 15 seconds
  - slave: 30 seconds
- provider abstraction per protocol mode
- centralized write queue serialization
- circuit-breaker pre-check and failure tracking
- coordinator telemetry and diagnostics fields

## Rationale

- aligns with Home Assistant recommended polling model
- isolates battery-level failures
- keeps entity updates synchronized to coordinator cache
- simplifies integration-wide diagnostics and testing

## Consequences

Positive:

- clear ownership of polling and write orchestration
- stable place for SunSpec cadence logic and metadata seeding
- improved observability and fault isolation

Trade-off:

- additional coordinator complexity compared with direct entity polling

## Related

- [../coordinator-pattern.md](../coordinator-pattern.md)
- [003-circuit-breaker.md](003-circuit-breaker.md)
