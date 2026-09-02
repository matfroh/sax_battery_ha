# ADR-003: Circuit Breaker for Communication Resilience

Date: 2026-08-08
Status: Accepted

## Context

Modbus communication can fail transiently or for extended periods. Repeated unbounded retries can degrade both Home Assistant and device behavior.

## Decision

Use a circuit-breaker guard in coordinator update flow.

### Implemented characteristics

- pre-update breaker check before polling
- failure recording on communication and full-batch failure conditions
- success recording and cycle telemetry after healthy updates
- coordinator-level diagnostics exposure

## Rationale

- protects system from repeated high-frequency failures
- provides predictable degraded behavior
- improves troubleshooting via explicit breaker state metrics

## Consequences

Positive:

- better runtime stability during outages
- fewer cascading failures

Trade-off:

- slightly more complex update lifecycle and diagnostics interpretation

## Related

- [../coordinator-pattern.md](../coordinator-pattern.md)
