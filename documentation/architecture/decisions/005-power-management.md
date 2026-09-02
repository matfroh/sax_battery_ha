# ADR-005: Coordinator-Centric Power Management

Date: 2026-08-08
Status: Accepted

## Context

Power control behavior must combine user mode selections, smart meter awareness, and safety constraints while remaining consistent with coordinator-owned write orchestration.

## Decision

Keep power management on top of master coordinator state and write APIs, with explicit mode state handling.

### Implemented characteristics

- runtime mode tracking (`PV` and `grid` charging flows)
- smart meter connected and balanced loading branches
- coordinator interval aligned update cycle
- coordinator write routing for control operations

## Rationale

- avoids duplicated hardware write logic outside coordinator
- keeps control operations observable and testable
- aligns power behavior with SOC constraints and diagnostics flow

## Consequences

Positive:

- coherent runtime behavior for control updates
- simpler safety integration with SOC manager

Trade-off:

- power-manager correctness depends on coordinator health and availability

## Related

- [../power-management.md](../power-management.md)
- [001-coordinator-pattern.md](001-coordinator-pattern.md)
