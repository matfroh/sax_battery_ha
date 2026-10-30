# ADR-004: SOC Protection Enforcement Path

Date: 2026-08-08
Status: Accepted

## Context

The integration must prevent unsafe discharge behavior when combined SOC falls below configured minimum values.

## Decision

Enforce SOC protection through `SOCManager` using guarded prerequisite checks and master-context write enforcement.

### Implemented characteristics

- checks include enabled state, data availability, and master context
- combined SOC threshold comparison determines enforcement action
- discharge limit enforcement targets max-discharge control path
- behavior is integrated into coordinator update lifecycle

## Rationale

- safety-first behavior without requiring user intervention
- centralized logic with clear diagnostics surface

## Consequences

Positive:

- consistent battery protection behavior
- reduced chance of accidental deep-discharge control commands

Trade-off:

- protection behavior adds implicit constraints during normal control actions

## Related

- [../soc-constraints.md](../soc-constraints.md)
- [005-power-management.md](005-power-management.md)
