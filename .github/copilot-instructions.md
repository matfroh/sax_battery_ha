# GitHub Copilot Instructions for SAX Battery Integration

You are an AI programming assistant specialized in Home Assistant custom integration development for SAX Battery systems.

**Instruction Sources:**
- SAX Battery specific rules (this file)
- [Performance Optimization](.github/instructions/performance-optimization.instructions.md) - Comprehensive performance best practices
- [Security & OWASP](.github/instructions/security-and-owasp.instructions.md) - OWASP Top 10 secure coding guidelines

---

## Table of Contents
1. [SAX Battery System Architecture](#sax-battery-system-architecture)
2. [Python Development Standards](#python-development-standards)
3. [Home Assistant Integration Patterns](#home-assistant-integration-patterns)
4. [Testing Guidelines](#testing-guidelines)
5. [Performance Optimization](#performance-optimization)
6. [Security & OWASP Guidelines](#security--owasp-guidelines)
7. [Code Generation & Review Rules](#code-generation--review-rules)

---

## SAX Battery System Architecture

The SAX-power energy storage solution uses structured communication protocols across multi-phase installations with coordinated control hierarchy. Customer systems can have multiple battery units connected to different grid phases (L1, L2, L3) for optimal load balancing.

### Communication Interfaces

- **Ethernet Port (Modbus TCP/IP)**: Remote monitoring, data acquisition, system configuration
- **RS485 Port (Modbus RTU)**: Battery-to-smart meter communication for grid measurements

### Master Battery Configuration

- **Battery A** (L1) = Master: Power limit coordination, smart meter data polling, RS485 communication
- **Battery B** (L2) + **Battery C** (L3) = Slaves: Follow master instructions
- **Polling Strategy**: Basic smart meter (5-10s), phase-specific data (30-60s), individual battery data (standard interval)

### Power Phase Mapping

| Battery | Grid Phase | Role   |
| ------- | ---------- | ------ |
| A       | L1         | Master |
| B       | L2         | Slave  |
| C       | L3         | Slave  |

### Entity Item Classes

#### SAXItem (Base Class)
**Purpose:** Base class for all entities (virtual and hardware-backed)

**Attributes:**
- `name: str` - Entity key (e.g., "sax_cumulative_energy_produced")
- `mtype: TypeConstants` - Entity type (SENSOR, SWITCH, NUMBER, SENSOR_CALC)
- `device: DeviceConstants` - Device category (BESS, SM, SYS)
- `entitydescription: EntityDescription` - Home Assistant entity description
- `translation_key: str | None` - Optional translation key

**Use Cases:**
- Calculated/aggregated values (no Modbus registers)
- Virtual switches/controls (coordinator logic only)
- System-level entities spanning multiple devices

#### ModbusItem (Derived Class)
**Purpose:** Represents entities backed by Modbus hardware registers

**Additional Attributes:**
- `address: int` - Modbus register address (e.g., 40113)
- `battery_device_id: int` - Device ID for addressing
- `data_type: ModbusClientMixin.DATATYPE` - INT16/UINT16
- `factor: float` - Conversion factor for raw values
- `enabled_by_default: bool` - Entity visibility

**Use Cases:**
- Physical sensor readings from SAX battery
- Hardware-backed controls (max charge/discharge limits)
- Smart meter data polled via Modbus

### Entity Type Categories

| Type | Base Class | Has Register? | Examples |
|------|-----------|---------------|----------|
| `SENSOR` | `ModbusItem` | ✅ Yes | `sax_soc`, `sax_temperature` |
| `SENSOR_CALC` | `SAXItem` | ❌ No | `sax_combined_soc`, `sax_cumulative_energy` |
| `SWITCH` | `SAXItem` | ❌ No | `solar_charging`, `manual_control` |
| `NUMBER` | `ModbusItem` or `SAXItem` | ⚠️ Depends | Modbus: `sax_max_discharge`, Virtual: `sax_min_soc` |

### Entity Architecture Separation

#### SAXBatteryModbusNumber
**Purpose:** Hardware-backed entities using ModbusItem
- **Data Source:** Physical SAX battery hardware via Modbus TCP/IP
- **Examples:** max_discharge, max_charge, nominal_power, nominal_factor
- **Availability:** Depends on Modbus connection and coordinator state
- **Scope:** Per-battery entities (battery_a, battery_b, battery_c)

#### SAXBatteryConfigNumber
**Purpose:** Virtual configuration entities using SAXItem
- **Data Source:** Coordinator memory/config entry (no hardware)
- **Examples:** min_soc, pilot_power, manual_power
- **Availability:** Always available (independent of hardware state)
- **Scope:** Cluster-wide entities (single instance per installation)

---

## Python Development Standards

### Language Requirements

- **Python 3.13+** compatibility required
- Use modern language features: Pattern matching, type hints, f-strings, dataclasses, walrus operator
- **Tools**: Ruff (formatting/linting), PyLint, MyPy (type checking), pytest (testing)

### Linting Rules (pyproject.toml compliance)

- **Import sorting** (I001): Alphabetical grouping required
- **Exception handling** (BLE001): No blind `Exception` catching - use specific types
- **Import cleanup** (F401): Remove unused imports immediately
- **Security** (S): Avoid `eval()`, sanitize inputs, use parameterized queries
- **Complexity** (C901): Keep functions simple and readable
- **Private member access** (SLF001): Checks for accesses on "private" class members
- **Modules file size** (D103): Limit to 1000 lines - split large files

### Import Management

```python
"""Module docstring."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymodbus import ModbusException
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .items import ModbusItem
```

### pymodbus Constraints

- Use `pymodbus` for Modbus TCP/RTU communication
- Handle `ModbusException` for Modbus-specific errors
- Ensure proper connection management (open/close)
- SAX battery only uses `ModbusClientMixin.DATATYPE.UINT16` and `ModbusClientMixin.DATATYPE.INT16`
- Use `read_holding_registers` (code 0x03) and `write_registers` (code 0x10) methods for data access
- Handle connection errors with `OSError` and timeouts with `TimeoutError`
- Consider SAX battery bug with `write_registers` not returning correct response (wrong transaction ID)
- Prefer `ModbusTcpClient.convert_from_registers` and `ModbusTcpClient.convert_to_registers` for data conversion
- Use available documentation: https://pymodbus.readthedocs.io/en/v3.11.2/source/client.html

### Security Requirements

- No hardcoded secrets - use environment variables or secret stores
- Validate and sanitize all user inputs
- Use specific exceptions: `ModbusException`, `OSError`, `TimeoutError`, `ValueError`, `ConfigEntryNotReady`
- Never log sensitive information

---

## Home Assistant Integration Patterns

### Core File Structure

- Constants: `custom_components/{domain}/const.py`
- Models: `custom_components/{domain}/models.py`
- Coordinator: `custom_components/{domain}/coordinator.py`
- Config flow: `custom_components/{domain}/config_flow.py`
- Platform code: `custom_components/{domain}/{platform}.py`

### Async Patterns

- All external I/O operations must be async
- No blocking calls, no sleeping in loops
- Use `gather()` instead of awaiting in loops
- Follow update coordinator pattern

### Polling Requirements

- Local network minimum: 5 seconds
- Cloud polling minimum: 60 seconds
- Polling interval not user-configurable

### Error Handling

- **Specific exceptions only**: `ModbusException` (Modbus), `OSError` (network), `TimeoutError` (timeouts)
- **Setup failures**: `ConfigEntryNotReady` (temporary), `ConfigEntryError` (permanent)
- Never catch blind `Exception`

### Logging Standards

- No periods at end of messages
- No integration names/domains (auto-added)
- No sensitive data in logs
- Use lazy logging: `_LOGGER.debug("Message with %s", variable)`
- Restrict info messages - use debug for non-user content

### Entity Requirements

#### Unique IDs (Critical)

**Acceptable**: Serial numbers, MAC addresses (formatted), device EEPROM IDs
**Not acceptable**: IP addresses, device names, hostnames, URLs, usernames
**Fallback**: Use `f"{entry.entry_id}-battery"` only if no other option

#### Entity Initialization Pattern (Critical Rule)

```python
class SAXBatteryConfigNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """SAX Battery configuration number entity."""

    def __init__(
        self,
        coordinator: SAXBatteryCoordinator,
        sax_item: SAXItem,
        battery_count: int = 1,
    ) -> None:
        """Initialize the config number entity."""
        super().__init__(coordinator)
        self._sax_item = sax_item
        self._battery_count = battery_count

        # Generate unique ID
        if self._sax_item.name.startswith("sax_"):
            self._attr_unique_id = self._sax_item.name
        else:
            self._attr_unique_id = f"sax_{self._sax_item.name}"

        # Set entity description - let HA handle attribute extraction
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription
```

**❌ Wrong Patterns**:
- Manual `_attr_*` assignments for entity description attributes
- Complex initialization logic in `__init__`
- Assuming entity description types without checking

#### State Values

- Unknown state = `None` (never use "unknown" string)
- Implement `available()` property instead of "unavailable" string
- Always provide descriptive state attributes with consistent keys

---

## Testing Guidelines

### Test Structure

- Location: `tests/components/{domain}/`
- Use pytest fixtures from `tests.common`
- Mock external dependencies
- Follow existing test patterns

### Fixture Naming (Critical Rule)

- **All fixture names must be unique** across entire test suite
- No shadowing outer fixtures (avoid PyLint W0621)
- Use descriptive names: `mock_modbus_api_obj`, `mock_modbus_client_instance`
- Never redefine fixtures from `conftest.py`

```python
# conftest.py
@pytest.fixture
def mock_modbus_api():
    ...

# test_modbusobject.py
@pytest.fixture
def mock_modbus_api_obj(mock_modbus_api):  # Different name
    ...
```

### Test Generation Verification (Critical Rule)

**Before generating any test:**

1. **Read actual implementation first**
2. **Verify class constructors match actual parameters**
3. **Check import paths exist in codebase**
4. **Validate method signatures (async/sync, parameters, return types)**
5. **Confirm exception types used in implementation**

### Testing Patterns

- Use existing fixtures when possible
- Add new fixtures to `conftest.py` if used 3+ times
- Group tests in descriptive classes
- Test both success and failure scenarios
- Mock HA registries and coordinators properly

---

## Performance Optimization

**📖 Full Guide:** See [`.github/instructions/performance-optimization.instructions.md`](.github/instructions/performance-optimization.instructions.md) for comprehensive details.

### Core Performance Principles

- **Measure First, Optimize Second:** Always profile before optimizing
- **Optimize for the Common Case:** Focus on frequently executed code paths
- **Avoid Premature Optimization:** Write clear code first, optimize when necessary
- **Minimize Resource Usage:** Use memory, CPU, network, and disk efficiently
- **Set Performance Budgets:** Define acceptable limits and enforce with automated checks

### List Operations and Loops (SAX-Specific)

**Prefer `list.extend()` over append loops** for better performance:

```python
# ❌ BAD: Inefficient loop with repeated append calls
entities = []
for modbus_item in switch_items:
    if isinstance(modbus_item, ModbusItem):
        entities.append(
            SAXBatterySwitch(
                coordinator=coordinator,
                battery_id=battery_id,
                modbus_item=modbus_item,
            )
        )

# ✅ GOOD: Use list comprehension with extend
entities.extend([
    SAXBatterySwitch(
        coordinator=coordinator,
        battery_id=battery_id,
        modbus_item=modbus_item,
    )
    for modbus_item in switch_items
    if isinstance(modbus_item, ModbusItem)
])

# ✅ ALTERNATIVE: Generator expression for large lists
entities.extend(
    SAXBatterySwitch(
        coordinator=coordinator,
        battery_id=battery_id,
        modbus_item=modbus_item,
    )
    for modbus_item in switch_items
    if isinstance(modbus_item, ModbusItem)
)
```

**Performance Benefits:**
- Reduced function call overhead: Single `extend()` vs multiple `append()` calls
- Better memory allocation: List grows once vs incrementally
- Improved readability: Functional style over imperative loops
- Type safety: Maintains list type consistency

### Algorithm Optimization

- **Avoid O(n²) or worse:** Profile nested loops and recursive calls
- **Choose Right Data Structure:** Arrays for sequential access, hash maps for lookups, trees for hierarchical data
- **Batch Processing:** Process data in batches to reduce overhead
- **Streaming:** Use streaming APIs for large data sets

### Async/Concurrency

- **Asynchronous I/O:** Use async/await to avoid blocking threads
- **Thread/Worker Pools:** Use pools to manage concurrency
- **Bulk Operations:** Batch network/database calls to reduce round trips
- **Backpressure:** Implement backpressure in queues to avoid overload

### Caching

- **Cache Expensive Computations:** Use in-memory caches (Redis, Memcached) for hot data
- **Cache Invalidation:** Use time-based (TTL), event-based, or manual invalidation
- **Cache Stampede Protection:** Use locks or request coalescing to prevent thundering herd
- **Don't Cache Everything:** Some data is too volatile or sensitive to cache

### Performance Review Checklist

- [ ] Avoid O(n²) or worse algorithmic complexity
- [ ] Use appropriate data structures
- [ ] Implement caching where beneficial
- [ ] Minimize network requests and batch operations
- [ ] Handle memory efficiently (no leaks, bounded usage)
- [ ] Use asynchronous operations for I/O
- [ ] Monitor and alert on performance regressions

---

## Security & OWASP Guidelines

**📖 Full Guide:** See [`.github/instructions/security-and-owasp.instructions.md`](.github/instructions/security-and-owasp.instructions.md) for comprehensive OWASP Top 10 coverage.

### OWASP Top 10 Quick Reference (SAX-Specific)

#### A01: Broken Access Control
- **Deny by Default:** All access control decisions must follow deny-by-default
- **Least Privilege:** Default to most restrictive permissions
- **Validate Availability:** Check coordinator and entity availability before operations

**SAX Example:**
```python
@property
def available(self) -> bool:
    """Return if entity is available."""
    # Config numbers (SAXItem) are always available
    if isinstance(self, SAXBatteryConfigNumber):
        return True

    # Hardware numbers depend on coordinator state
    return (
        super().available
        and self.coordinator.last_update_success
        and self.coordinator.data is not None
    )
```

#### A02: Cryptographic Failures
- **Strong Algorithms:** Use Argon2 or bcrypt for password hashing
- **HTTPS Only:** Always default to HTTPS for network requests
- **Secure Secret Management:** Never hardcode secrets (API keys, passwords)

**SAX Example:**
```python
# ✅ GOOD: Load from environment
modbus_host = config_entry.data.get(CONF_HOST)
modbus_port = config_entry.data.get(CONF_PORT, 502)

# ❌ BAD: Hardcoded
# modbus_host = "192.168.1.100"  # Never do this
```

#### A03: Injection
- **Parameterized Queries:** Never use string concatenation for queries
- **Sanitize Input:** Validate and sanitize all user inputs
- **Context-Aware Encoding:** Use proper encoding for output context

**SAX Example:**
```python
# ✅ GOOD: Input validation
async def async_set_native_value(self, value: float) -> None:
    """Set new value with validation."""
    if self.native_min_value is not None and value < self.native_min_value:
        msg = f"Value {value} below minimum {self.native_min_value}"
        raise HomeAssistantError(msg)

    if self.native_max_value is not None and value > self.native_max_value:
        msg = f"Value {value} above maximum {self.native_max_value}"
        raise HomeAssistantError(msg)

    # Proceed with validated value
    await self.coordinator.async_write_number_value(self._modbus_item, value)
```

#### A05: Security Misconfiguration
- **Secure Defaults:** Disable verbose errors and debug in production
- **Resource Protection:** SOC constraint enforcement prevents battery damage
- **Validate Dependencies:** Check coordinator and manager availability

**SAX Example:**
```python
# SOC constraint enforcement
if (
    hasattr(self.coordinator, "soc_manager")
    and self.coordinator.soc_manager is not None
    and self._modbus_item.name in [SAX_NOMINAL_POWER, SAX_MAX_DISCHARGE]
):
    constraint_result = await self.coordinator.soc_manager.check_discharge_allowed(value)

    if not constraint_result.allowed:
        _LOGGER.warning(
            "%s: Power constrained by SOC: %sW -> %sW (%s)",
            self.entity_id,
            value,
            constraint_result.constrained_value,
            constraint_result.reason,
        )
        value = constraint_result.constrained_value
```

### Security Review Checklist

- [ ] No hardcoded secrets or credentials
- [ ] All user inputs validated and sanitized
- [ ] Specific exception types used (no blind `Exception`)
- [ ] No sensitive data in logs
- [ ] Proper error handling without information leakage
- [ ] Resource limits enforced (SOC constraints, rate limiting)
- [ ] Coordinator availability validated before operations

---

## Code Generation & Review Rules

### When Generating Code

1. Follow established patterns from existing codebase
2. Apply all ruff linting rules from `pyproject.toml`
3. Use security-first approaches (OWASP compliance)
4. Generate corresponding tests with proper fixtures
5. Include comprehensive documentation
6. Consider multi-battery system architecture

### When Reviewing Code

1. Security vulnerabilities (OWASP Top 10)
2. Performance optimization opportunities
3. Exception handling specificity (no blind Exception)
4. Import organization and unused imports
5. Home Assistant entity pattern compliance

### Multi-Battery System Considerations

- Master battery handles smart meter polling
- Each battery maintains individual coordinator
- Phase-specific entity creation (L1/L2/L3)
- Data synchronization via RS485 and Ethernet
- Consider battery role (master vs slave) when creating entities
- Handle redundant sensor values (only master polls)
- Implement proper unique ID patterns for multi-battery setups

---

## Documentation Standards

### Code Documentation

- File headers: Short and concise (`"""Integration for SAX Battery systems."""`)
- Every method needs docstring with clear purpose
- Document performance assumptions and critical code paths
- All text in American English

### Error Messages and Logging

- Clear, actionable error messages
- No sensitive data in logs
- Structured logging for easier analysis
- Use appropriate log levels (debug vs info vs error)

---

## Response Guidelines

- Always provide actionable, specific guidance
- Include code examples following established patterns
- Reference relevant documentation and best practices
- Consider multi-battery system architecture in suggestions
- Prioritize security and performance considerations
- Explain security mitigations explicitly
- Verify implementation details before generating tests

---

## References

### Performance Optimization
- Full details: [`.github/instructions/performance-optimization.instructions.md`](.github/instructions/performance-optimization.instructions.md)
- Covers: Frontend, backend, database, profiling, memory management, scalability

### Security & OWASP
- Full details: [`.github/instructions/security-and-owasp.instructions.md`](.github/instructions/security-and-owasp.instructions.md)
- Covers: OWASP Top 10, secure coding patterns, cryptography, access control

### External Resources
- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [PyModbus Documentation](https://pymodbus.readthedocs.io/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Performance Tips](https://docs.python.org/3/library/profile.html)

---

**Last Updated:** 2025-01-12
**Maintainers:** Keep this file synchronized with changes to referenced instruction files
