---
description: "Testing patterns and guidelines for pytest and Home Assistant integration testing"
---

# Testing Guidelines

## Test Structure

### Test Location

- Test location: `tests/components/{domain}/`
- Use pytest fixtures from `tests.common`
- Mock external dependencies
- Use snapshots for complex data
- Follow existing test patterns

### When to Create New Fixtures

- If a mock is used across 3+ test files, add it to `conftest.py`
- Use descriptive fixture names with `mock_` prefix
- Document fixtures with proper docstrings

### Test File Structure

- Import only what's needed for the specific module under test
- Group related tests in classes with descriptive names
- Use fixture parameters instead of creating mocks in test methods

## Fixture Naming Rules

### Critical Rule: Unique Fixture Naming

- **Fixture Naming:**
  - All pytest fixture names must be unique within the test suite
  - Do not reuse fixture names across different scopes (module, class, function) to avoid PyLint `redefined-outer-name (W0621)` errors
  - If a fixture is reused or shared, use a descriptive and unique name (e.g., `mock_modbus_api_obj`, `mock_modbus_client_instance`)
  - When overriding a fixture for a specific test or class, always use a new name rather than shadowing an outer fixture
  - If a fixture is defined in `conftest.py`, do not redefine it in a test file with the same name—use a different name or import it directly

**Example:**

```python
# conftest.py
@pytest.fixture
def mock_modbus_api():
    ...

# test_modbusobject.py
@pytest.fixture
def mock_modbus_api_obj(mock_modbus_api):
    ...
```

- Always update references in test functions to use the unique fixture name

## Code Generation Rules

1. **Always suggest using existing fixtures** when generating tests
2. **Recommend adding new fixtures to conftest.py** if mocks are repeated
3. **Use pytest fixture dependency injection** pattern
4. **Avoid creating Mock() objects directly in test methods** when fixtures exist
5. **Follow all ruff linting rules** defined in `pyproject.toml`
6. **Sort imports properly** and remove unused imports
7. **Use specific exception handling** - never catch blind `Exception`
8. **import** statements should be at the top-level of a file

## Home Assistant Integration Testing Patterns

### Entity Testing

- Use `mock_hass` and `mock_coordinator` fixtures
- Test entity state updates and attribute changes
- Mock device registry and entity registry interactions

### Config Flow Testing

- Use `mock_modbus_api` for connection testing
- Test both successful and failed setup scenarios
- Mock user input validation

### Data Update Coordinator Testing

- Use `mock_modbus_api` for data fetching
- Test update intervals and error handling
- Mock network timeouts and connection failures

## Test Generation Verification

### Critical Rule: Always Verify Against Actual Implementation

When generating test files, you MUST:

1. **Read the actual implementation file first** before writing any tests
2. **Verify class constructors, method signatures, and return types** match the implementation
3. **Check import paths and class names** exist in the actual codebase
4. **Validate method parameters** - especially required vs optional parameters
5. **Confirm exception types** used in the actual implementation

### Before submitting test code

- [ ] All imported classes/functions exist in the specified modules
- [ ] Constructor calls match the actual required parameters (no defaults assumed)
- [ ] Method signatures match the implementation (async/sync, parameters, return types)
- [ ] Exception handling uses the same exception types as the implementation
- [ ] Test assertions match actual method behavior and return values

### Example Verification Process

```python
# ❌ WRONG - Assuming defaults exist
api = ModbusAPI()  # Error: constructor requires host, port, battery_id

# ✅ CORRECT - After checking actual implementation
api = ModbusAPI(host="192.168.1.100", port=502, battery_id="battery_a")
```

**If implementation doesn't match expectations:**

- Update tests to match actual implementation
- Do NOT assume or suggest changes to the implementation
- Use the actual method signatures, parameters, and behavior as-is

This rule prevents generating invalid tests that fail due to incorrect assumptions about the codebase structure.
