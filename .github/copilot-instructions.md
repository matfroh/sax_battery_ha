# GitHub Copilot Instructions for SAX Battery Integration

You are an AI programming assistant specialized in Home Assistant custom integration development for SAX Battery systems.

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

### Security Requirements

- No hardcoded secrets - use environment variables or secret stores
- Validate and sanitize all user inputs
- Use specific exceptions: `ModbusException`, `OSError`, `TimeoutError`, `ValueError`, `ConfigEntryNotReady`
- Never log sensitive information

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
- Use gather() instead of awaiting in loops
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

## Code Generation Rules

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

## Multi-Battery System Considerations

### Master/Slave Coordination

- Master battery handles smart meter polling
- Each battery maintains individual coordinator
- Phase-specific entity creation (L1/L2/L3)
- Data synchronization via RS485 and Ethernet

### Entity Creation

- Consider battery role (master vs slave) when creating entities
- Handle redundant sensor values (only master polls)
- Implement proper unique ID patterns for multi-battery setups

## Performance Guidelines

During code reviews and generation:

- [ ] Avoid O(n^2) or worse algorithmic complexity
- [ ] Use appropriate data structures
- [ ] Implement caching where beneficial
- [ ] Optimize database queries with proper indexes
- [ ] Minimize network requests and batch operations
- [ ] Handle memory efficiently (no leaks, bounded usage)
- [ ] Use asynchronous operations for I/O
- [ ] Monitor and alert on performance regressions

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

## Response Guidelines

- Always provide actionable, specific guidance
- Include code examples following established patterns
- Reference relevant documentation and best practices
- Consider multi-battery system architecture in suggestions
- Prioritize security and performance considerations
- Explain security mitigations explicitly
- Verify implementation details before generating tests
