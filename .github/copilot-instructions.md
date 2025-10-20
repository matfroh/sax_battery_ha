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

### Write-Only Register Handling

SAX Battery hardware has write-only registers (41-44) that cannot be read back:
- **Register 41**: max_discharge (W)
- **Register 42**: max_charge (W)
- **Register 43**: nominal_power (W) - Pilot control
- **Register 44**: nominal_factor (0-100%) - Pilot control

**Implementation Requirements:**
- Values stored in `_local_value` cache for UI display
- Cached values persisted across restarts via entity states
- Restored during startup via `_restore_write_only_register_values()`
- SOC constraints enforced after value restoration
- Hardware writes coordinated with UI state updates

**State Restoration Flow:**
```
HA Restart
    ↓
1. Create coordinators, first refresh (gets SOC)
    ↓
2. Entity initialization with cached values
    ↓
3. EVENT_HOMEASSISTANT_STARTED
    ↓
4. Restore write-only values from entity states
    ↓
5. Check SOC constraints using SAX_COMBINED_SOC
    ↓
6. Enforce hardware limits if needed (write 0W)
    ↓
7. Update entity UI state to match hardware
```

### SOC Constraint Enforcement

- Uses `SAX_COMBINED_SOC` for multi-battery protection
- Master coordinator enforces discharge limits
- Constraints applied silently (no user errors)
- Hardware writes coordinated with UI state updates
- `check_and_enforce_discharge_limit()` writes directly to master's `SAX_MAX_DISCHARGE` entity

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

### Runtime Data Storage

- **Use ConfigEntry.runtime_data**: Store non-persistent runtime data
  ```python
  type SAXBatteryConfigEntry = ConfigEntry[dict[str, SAXBatteryCoordinator]]

  async def async_setup_entry(hass: HomeAssistant, entry: SAXBatteryConfigEntry) -> bool:
      coordinators = {}  # Dictionary of battery_id -> coordinator
      entry.runtime_data = coordinators
  ```

### Async Patterns

- All external I/O operations must be async
- No blocking calls, no sleeping in loops
- Use `gather()` instead of awaiting in loops
- Follow update coordinator pattern

**Data Update Coordinator Pattern:**
```python
class SAXBatteryCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        client: SAXBatteryClient,
        config_entry: ConfigEntry
    ) -> None:
        # Interval determined by battery role and connection type
        if client.is_master:
            update_interval = timedelta(seconds=5)  # Master polls smart meter
        else:
            update_interval = timedelta(seconds=30)  # Slave batteries

        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=config_entry,  # ✅ Pass config_entry - recommended pattern
        )
        self.client = client

    async def _async_update_data(self):
        try:
            return await self.client.fetch_data()
        except ModbusException as err:
            raise UpdateFailed(f"Modbus communication error: {err}") from err
        except OSError as err:
            raise UpdateFailed(f"Network error: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(f"Request timeout: {err}") from err
```

**Key Points:**
- Always pass `config_entry` parameter to coordinator (Home Assistant Core recommended pattern)
- Use `UpdateFailed` for API errors
- Use `ConfigEntryAuthFailed` for authentication issues
- Master coordinator has faster update interval for smart meter polling

### Polling Requirements

- **Polling intervals are NOT user-configurable**: Never add scan_interval, update_interval, or polling frequency options to config flows or config entries
- **Integration determines intervals**: Set `update_interval` programmatically based on integration logic, not user input
- **SAX Battery Polling Strategy**:
  - Master Battery: 5-10s for basic smart meter data, 30-60s for phase-specific data
  - Slave Batteries: Standard coordinator interval (30s)
  - Individual battery data: Standard interval

```python
# ✅ GOOD: Integration-determined polling
update_interval = timedelta(seconds=5 if client.is_master else 30)

# ❌ BAD: User-configurable intervals
# In config flow
vol.Optional("scan_interval", default=60): cv.positive_int  # ❌ Not allowed

# In coordinator
update_interval = timedelta(minutes=entry.data.get("scan_interval", 1))  # ❌ Not allowed
```

**Minimum Intervals** (Home Assistant Core requirement):
- Local network: 5 seconds minimum
- Cloud services: 60 seconds minimum

**Parallel Updates**: Specify number of concurrent updates:
```python
PARALLEL_UPDATES = 1  # Serialize updates to prevent overwhelming device
# OR
PARALLEL_UPDATES = 0  # Unlimited (for coordinator-based or read-only)
```

### Error Handling

- **Specific exceptions only**: `ModbusException` (Modbus), `OSError` (network), `TimeoutError` (timeouts)
- **Setup failures**: `ConfigEntryNotReady` (temporary), `ConfigEntryError` (permanent)
- **Service errors**: `ServiceValidationError` (user input), `HomeAssistantError` (device communication)
- **Keep try blocks minimal**: Only wrap code that can throw exceptions, process data outside try block

**SAX Battery Exception Handling Pattern** (stricter than HA Core):
```python
# ✅ SAX Battery: Specific Modbus exceptions
try:
    data = await device.get_data()
except ModbusException as err:
    raise UpdateFailed(f"Modbus communication error: {err}") from err
except OSError as err:
    raise UpdateFailed(f"Network error: {err}") from err
except TimeoutError as err:
    raise UpdateFailed(f"Request timeout: {err}") from err

# ℹ️ Home Assistant Core: Bare exceptions allowed in config flows
async def async_step_user(self, user_input=None):
    try:
        await self._test_connection(user_input)
    except Exception:  # Allowed in HA Core config flows
        errors["base"] = "unknown"

# ✅ SAX Battery: Specific exceptions even in config flows (OWASP compliant)
async def async_step_user(self, user_input=None):
    try:
        await self._test_connection(user_input)
    except ModbusException:
        errors["base"] = "cannot_connect"
    except TimeoutError:
        errors["base"] = "timeout"
    except OSError:
        errors["base"] = "network_error"
```

**Why SAX Battery Uses Specific Exceptions:**
- **Security (OWASP A03)**: Prevents information leakage through error messages
- **Debugging**: Specific exceptions provide better troubleshooting context
- **Hardware Integration**: Modbus hardware has specific failure modes requiring distinct handling
- **Battery Protection**: Different error types trigger different safety responses

**Data Processing Pattern:**
```python
# ❌ BAD: Too much code in try block
try:
    data = await device.get_data()  # Can throw
    processed = data.get("value", 0) * 100  # ❌ Processing in try block
    self._attr_native_value = processed
except DeviceError:
    _LOGGER.error("Failed to get data")

# ✅ GOOD: Minimal try block, process outside
try:
    data = await device.get_data()  # Only what can throw
except DeviceError:
    _LOGGER.error("Failed to get data")
    return

# ✅ Process data outside try block
processed = data.get("value", 0) * 100
self._attr_native_value = processed
```

### Logging Standards

- No periods at end of messages
- No integration names/domains (auto-added)
- No sensitive data in logs
- Use lazy logging: `_LOGGER.debug("Message with %s", variable)`
- Restrict info messages - use debug for non-user content

**Log Levels:**
- **debug**: Non-user-facing messages, detailed troubleshooting
- **info**: User-relevant events (device connected, constraint enforced)
- **warning**: Recoverable issues (SOC constraint triggered, connection retry)
- **error**: Failures requiring attention (setup failed, Modbus error)

### Entity Requirements

#### Unique IDs (Critical)

**Acceptable**: Serial numbers, MAC addresses (formatted), device EEPROM IDs
**Not acceptable**: IP addresses, device names, hostnames, URLs, usernames
**Fallback**: Use `f"{entry.entry_id}-battery"` only if no other option

#### Unique ID Generation (Critical Rule)

**Always use `get_unique_id_for_item()` utility function** for entity unique ID generation. Never hardcode unique IDs.

```python
from .utils import get_unique_id_for_item

# ✅ GOOD: Use utility function for SAX Battery
unique_id = get_unique_id_for_item(
    coordinator.hass,
    coordinator.config_entry.entry_id,
    SAX_MAX_DISCHARGE,
)

# ❌ BAD: Hardcoded unique_id
unique_id = "max_discharge"  # Never do this

# ❌ BAD: Manual string formatting
unique_id = f"sax_{item_name}"  # Don't bypass utility function
```

**ℹ️ Note on Home Assistant Core Patterns:**
Home Assistant Core integrations may use simpler patterns like `self._attr_unique_id = f"{device_id}_temperature"`. However, SAX Battery uses centralized utility function for:
- Consistent unique ID generation across integration
- Multi-battery vs cluster-wide entity differentiation
- Entity registry lookup reliability
- Stability across Home Assistant restarts
- Single location for unique ID pattern changes

**Unique ID Patterns:**
- **Cluster entities** (system-wide): Generated with `battery_id=None`
  - Examples: `sax_combined_soc`, `sax_cluster_max_discharge`
- **Per-battery entities**: Generated with specific `battery_id`
  - Examples: `battery_a_soc`, `battery_a_temperature`

**Entity Registry Lookups:**
```python
# ✅ GOOD: Use generated unique_id for lookups (SAX Battery)
from homeassistant.helpers import entity_registry as er
from .utils import get_unique_id_for_item

ent_reg = er.async_get(hass)
unique_id = get_unique_id_for_item(
    hass,
    entry.entry_id,
    SAX_MAX_DISCHARGE,
)

# Type guard: Validate unique_id is not None before entity lookup
if not unique_id:
    _LOGGER.warning("Could not generate unique_id for %s", SAX_MAX_DISCHARGE)
    return

entity_id = ent_reg.async_get_entity_id("number", DOMAIN, unique_id)

# ❌ BAD: Hardcoded lookup
entity_id = ent_reg.async_get_entity_id("number", DOMAIN, "max_discharge")
```

**Type Safety for Entity Lookups:**
```python
# ✅ GOOD: Type guard before using unique_id
unique_id = get_unique_id_for_item(hass, entry_id, item_name)
if not unique_id:
    _LOGGER.warning("Could not generate unique_id for %s", item_name)
    return

# Now safe to use with async_get_entity_id (expects str, not str | None)
entity_id = ent_reg.async_get_entity_id("number", DOMAIN, unique_id)

# ✅ GOOD: Validate config_entry exists before accessing .entry_id
if not coordinator.config_entry:
    _LOGGER.error("Coordinator has no config entry")
    return

unique_id = get_unique_id_for_item(
    hass,
    coordinator.config_entry.entry_id,  # Now safe - validated above
    item_name,
)
```

#### Entity Initialization Pattern (Critical Rule)

Home Assistant entities require `_attr_has_entity_name = True` for proper entity naming.

```python
class SAXBatteryConfigNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """SAX Battery configuration number entity."""

    _attr_has_entity_name = True

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
- Hardcoded unique_id strings: `self._attr_unique_id = "max_discharge"`
- Manual string formatting without prefix check: `self._attr_unique_id = f"sax_{name}"`
- Bypassing utility function for "simple" cases
- Manual `_attr_*` assignments for entity description attributes
- Complex initialization logic in `__init__`
- Assuming entity description types without checking

#### Entity Descriptions

Lambda functions are often used in EntityDescription for value transformation. When lambdas exceed line length, wrap in parentheses for readability:

```python
# ❌ BAD: Lambda exceeds line length
SensorEntityDescription(
    key="temperature",
    name="Temperature",
    value_fn=lambda data: round(data["temp_value"] * 1.8 + 32, 1) if data.get("temp_value") is not None else None,
)

# ✅ GOOD: Parenthesis on same line as lambda, multiline expression
SensorEntityDescription(
    key="temperature",
    name="Temperature",
    value_fn=lambda data: (
        round(data["temp_value"] * 1.8 + 32, 1)
        if data.get("temp_value") is not None
        else None
    ),
)
```

#### State Values

- Unknown state = `None` (never use "unknown" string)
- Implement `available()` property instead of "unavailable" string
- Always provide descriptive state attributes with consistent keys

**Entity Availability Pattern:**
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

### Configuration Flow

- **UI Setup Required**: All integrations must support configuration via UI
- **Manifest**: Set `"config_flow": true` in `manifest.json`
- **Data Storage**:
  - Connection-critical config: Store in `ConfigEntry.data`
  - Non-critical settings: Store in `ConfigEntry.options`
- **Validation**: Always validate user input before creating entries
- **Config Entry Naming**:
  - ❌ Do NOT allow users to set config entry names in config flows
  - Names are automatically generated or can be customized later in UI
- **Connection Testing**: Test device/service connection during config flow
- **Duplicate Prevention**: Prevent duplicate configurations using unique ID or unique data matching

---

## Testing Requirements

- **Location**: `tests/`
- **Coverage Requirement**: Above 95% test coverage for all modules
- **Best Practices**:
  - Use pytest fixtures from `conftest.py`
  - Mock all external dependencies
  - Use snapshots for complex data structures
  - Follow existing test patterns

### Config Flow Testing
- **100% Coverage Required**: All config flow paths must be tested
- **Test Scenarios**:
  - All flow initiation methods (user, discovery, import)
  - Successful configuration paths
  - Error recovery scenarios
  - Prevention of duplicate entries
  - Flow completion after errors

## Testing Guidelines

### Test Structure

- Location: `tests/components/{domain}/`
- Use pytest fixtures from `tests.common` and integration-specific fixtures
- Mock external dependencies - never make real network calls or access hardware
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
    """Fixture for ModbusAPI mock."""
    ...

# test_modbusobject.py
@pytest.fixture
def mock_modbus_api_obj(mock_modbus_api):  # ✅ Different name, uses parent
    """Fixture for ModbusItem object with mocked API."""
    ...
```

### Fixture Location and Scope (Critical Rule)

**Centralize fixtures in `conftest.py` for reusability and consistency:**

- **All reusable fixtures go in `conftest.py`**: Use `tests/conftest.py` for integration-wide fixtures
- **Test-specific fixtures use unique names**: If a test needs a specialized version of a `conftest.py` fixture, create a new fixture with a descriptive name that extends or modifies the base fixture
- **Never duplicate fixture names**: Shadowing fixtures from `conftest.py` in test files causes confusing behavior and breaks other tests
- **Document fixture dependencies**: Clearly comment which fixtures depend on others

**Pattern for Test-Specific Fixture Customization:**

```python
# tests/conftest.py
@pytest.fixture
def mock_soc_manager() -> SOCManager:
    """Create a properly configured SOCManager for testing.

    Returns real SOCManager instance with mocked dependencies.
    Security:
        OWASP A05: Validates manager has required attributes for testing
    """
    # Create mock coordinator with required attributes
    mock_coordinator = MagicMock()
    mock_coordinator.data = {}

    # Create mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.services.async_call = AsyncMock(return_value=None)

    # Mock entity registry for entity ID lookups
    mock_entity_registry = MagicMock()
    mock_entity_registry.async_get_entity_id = MagicMock(return_value="number.test_entity")
    mock_hass.data = {
        "entity_registry": mock_entity_registry
    }

    mock_coordinator.hass = mock_hass

    # Create mock config_entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry_123"
    mock_coordinator.config_entry = mock_entry

    # Create mock SAXBatteryData with get_unique_id_for_item
    mock_sax_data = MagicMock()
    mock_sax_data.get_unique_id_for_item = MagicMock(return_value=None)
    mock_coordinator.sax_data = mock_sax_data

    # Create REAL SOCManager instance with mocked dependencies
    manager = SOCManager(
        coordinator=mock_coordinator,
        min_soc=20.0,
        enabled=True,
    )

    return manager


# tests/test_soc_manager.py
class TestCheckAndEnforceDischargeLimit:
    """Test check_and_enforce_discharge_limit method."""

    @patch("homeassistant.helpers.entity_platform.async_get_current_platform")
    @patch("homeassistant.helpers.entity_registry.async_get")
    async def test_enforce_writes_to_entity(
        self,
        mock_entity_registry,
        mock_get_platform,
        mock_soc_manager,  # ✅ Use fixture from conftest.py
    ) -> None:
        """Test enforcement writes to SAX_MAX_DISCHARGE entity.

        Security:
            OWASP A05: Validates proper constraint enforcement
        """
        # ✅ Customize the fixture for this specific test
        mock_soc_manager.coordinator.data = {SAX_COMBINED_SOC: 8.0}
        mock_soc_manager.coordinator.sax_data.get_unique_id_for_item.return_value = (
            "sax_cluster_max_discharge"
        )

        # ✅ Mock additional test-specific dependencies
        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get_entity_id.return_value = "number.sax_max_discharge"
        mock_entity_registry.return_value = mock_ent_reg

        # Execute test
        result = await mock_soc_manager.check_and_enforce_discharge_limit()

        # Verify behavior
        assert result is True
```

**When to Create Test-Specific Fixtures:**

```python
# ✅ GOOD: Test needs significantly different setup
@pytest.fixture
def mock_soc_manager_disabled(mock_soc_manager) -> SOCManager:
    """SOC manager with enforcement disabled for specific tests."""
    mock_soc_manager.enabled = False
    return mock_soc_manager

# ✅ GOOD: Test needs different data setup
@pytest.fixture
def mock_soc_manager_low_soc(mock_soc_manager) -> SOCManager:
    """SOC manager with critically low SOC for boundary tests."""
    mock_soc_manager.coordinator.data = {SAX_COMBINED_SOC: 5.0}
    return mock_soc_manager

# ❌ BAD: Shadowing conftest.py fixture
@pytest.fixture
def mock_soc_manager():  # ❌ Duplicates conftest.py fixture name
    """This breaks other tests that depend on the base fixture."""
    ...
```

**Fixture Organization Checklist:**

- [ ] All fixtures used in 3+ test files are in `conftest.py`
- [ ] Test-specific fixtures have unique, descriptive names
- [ ] No fixture name conflicts between `conftest.py` and test files
- [ ] Fixture dependencies are documented with docstrings
- [ ] Test-specific fixtures extend base fixtures via parameters
- [ ] Complex fixture setup is centralized to avoid duplication

**Benefits of This Approach:**

✅ **Consistency**: All tests use the same base fixture setup from `conftest.py`
✅ **Maintainability**: Fixture changes propagate to all tests automatically
✅ **Type Safety**: IDEs can track fixture dependencies and detect conflicts
✅ **Test Isolation**: Tests remain independent while sharing infrastructure
✅ **No Breaking Changes**: Adding test-specific fixtures doesn't break existing tests
✅ **OWASP A05 Compliance**: Centralized security validations in fixtures

### Testing Home Assistant Data Access

**Critical Rule**: Never access `hass.data` directly in tests - always use proper integration setup and fixtures.

```python
# ❌ BAD: Accessing hass.data directly
def test_coordinator(hass):
    coordinator = hass.data[DOMAIN][entry.entry_id]  # Never do this
    assert coordinator.data

# ✅ GOOD: Use proper integration setup
@pytest.fixture
async def init_integration(hass, mock_config_entry, mock_api):
    """Set up the integration for testing."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry

async def test_coordinator(hass, init_integration):
    """Test coordinator through proper setup."""
    state = hass.states.get("sensor.my_sensor")  # ✅ Access through state machine
    assert state.state == "42"
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
- Use snapshot testing for complex entity states

**Modern Integration Fixture Setup:**
```python
@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        title="SAX Battery A",
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 502},
        unique_id="battery_a_serial_12345",
    )

@pytest.fixture
def mock_modbus_api() -> Generator[MagicMock]:
    """Return a mocked Modbus API."""
    with patch(
        "homeassistant.components.sax_battery.ModbusAPI",
        autospec=True
    ) as api_mock:
        api = api_mock.return_value
        api.async_read_value.return_value = 50.0  # Mock SOC value
        yield api

@pytest.fixture
def platforms() -> list[Platform]:
    """Fixture to specify platforms to test."""
    return [Platform.SENSOR, Platform.NUMBER]

@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_modbus_api: MagicMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the integration for testing."""
    mock_config_entry.add_to_hass(hass)

    with patch("homeassistant.components.sax_battery.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    return mock_config_entry
```

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

- **Cache Expensive Computations:** Use in-memory caches for hot data
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
6. Type safety (mypy compliance)

### Multi-Battery System Considerations

- Master battery handles smart meter polling
- Each battery maintains individual coordinator
- Phase-specific entity creation (L1/L2/L3)
- Data synchronization via RS485 and Ethernet
- Consider battery role (master vs slave) when creating entities
- Handle redundant sensor values (only master polls)
- Implement proper unique ID patterns for multi-battery setups

### Code Review Checklist for Performance

- [ ] Are there any obvious algorithmic inefficiencies (O(n²) or worse)?
- [ ] Are data structures appropriate for their use?
- [ ] Are there unnecessary computations or repeated work?
- [ ] Is caching used where appropriate, and is invalidation handled correctly?
- [ ] Are large payloads paginated, streamed, or chunked?
- [ ] Are there any memory leaks or unbounded resource usage?
- [ ] Are network requests minimized, batched, and retried on failure?
- [ ] Are there any blocking operations in hot paths?
- [ ] Is logging in hot paths minimized and structured?
- [ ] Are performance-critical code paths documented and tested?

---

## Documentation Standards

### Code Documentation

- File headers: Short and concise (`"""Integration for SAX Battery systems."""`)
- Every method needs docstring with clear purpose
- Document performance assumptions and critical code paths
- All text in American English
- Use sentence case for titles and messages

### Writing Style Guidelines
- **Tone**: Friendly and informative
- **Perspective**: Use second-person ("you" and "your") for user-facing messages
- **Inclusivity**: Use objective, non-discriminatory language
- **Clarity**: Write for non-native English speakers
- **Formatting in Messages**:
  - Use backticks for: file paths, filenames, variable names, field entries
  - Use sentence case for titles and messages
  - Avoid abbreviations when possible

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
- Use type guards to satisfy mypy type checking

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

**Last Updated:** 2025-01-13
**Maintainers:** Keep this file synchronized with changes to referenced instruction files
