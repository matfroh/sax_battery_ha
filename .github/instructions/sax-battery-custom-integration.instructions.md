---
description: "Home Assistant specific integration patterns and requirements"
---

# Home Assistant Integration Patterns

## Core Locations

- Shared constants: `homeassistant/const.py`, use them instead of hardcoding strings or creating duplicate integration constants
- Integration files:
  - Constants: `custom_components/{domain}/const.py`
  - Models: `custom_components/{domain}/models.py`
  - Coordinator: `custom_components/{domain}/coordinator.py`
  - Config flow: `custom_components/{domain}/config_flow.py`
  - Platform code: `custom_components/{domain}/{platform}.py`

## Async Patterns

- All external I/O operations must be async
- Avoid sleeping in loops
- Avoid awaiting in loops, gather instead
- No blocking calls

## Polling Requirements

- Follow update coordinator pattern, when possible
- Polling interval may not be configurable by the user
- For local network polling, the minimum interval is 5 seconds
- For cloud polling, the minimum interval is 60 seconds

## Error Handling

- **Never catch blind `Exception`** - always use specific exception types:
  - `ModbusException` for Modbus communication errors
  - `OSError` for network/connection errors
  - `TimeoutError` for timeout situations
  - `ValueError`, `TypeError`, `KeyError` for data processing errors
  - `ConfigEntryNotReady`, `ConfigEntryError` for setup failures
- Use specific exceptions from `homeassistant.exceptions`
- Setup failures:
  - Temporary: Raise `ConfigEntryNotReady`
  - Permanent: Use `ConfigEntryError`

## Logging Standards

- Message format:
  - No periods at end
  - No integration names or domains (added automatically)
  - No sensitive data (keys, tokens, passwords), even when those are incorrect
- Be very restrictive on the use of logging info messages, use debug for anything which is not targeting the user
- Use lazy logging (no f-strings):

  ```python
  _LOGGER.debug("This is a log message with %s", variable)
  ```

## Entity Requirements

### Unique IDs

Ensure unique IDs for state persistence:

- Unique IDs should not contain values that are subject to user or network change
- An ID needs to be unique per platform, not per integration
- The ID does not have to contain the integration domain or platform

**Acceptable examples:**

- Serial number of a device
- MAC address of a device formatted using `homeassistant.helpers.device_registry.format_mac`
- Unique identifier that is physically printed on the device or burned into an EEPROM

**Not acceptable examples:**

- IP Address
- Device name
- Hostname
- URL
- Email address
- Username

**For entities that are setup by a config entry:** the config entry ID can be used as a last resort if no other Unique ID is available. For example: `f"{entry.entry_id}-battery"`

### State Values

- If the state value is unknown, use `None`
- Do not use the `unavailable` string as a state value, implement the `available()` property method instead
- Do not use the `unknown` string as a state value, use `None` instead

### Extra Entity State Attributes

- The keys of all state attributes should always be present
- If the value is unknown, use `None`
- Provide descriptive state attributes

## Entity Initialization Pattern

### Critical Rule: Follow Home Assistant Entity Initialization Patterns

**Before creating any entity class initialization:**

1. **Study existing entity patterns** in the Home Assistant codebase and this integration
2. **Use Home Assistant's built-in attribute system** instead of manual attribute assignment
3. **Follow the `_attr_*` pattern** for all entity attributes
4. **Never assume entity description structure** without proper type checking

### ✅ CORRECT Entity Initialization Pattern

```python
class SAXBatteryConfigNumber(CoordinatorEntity[SAXBatteryCoordinator], NumberEntity):
    """Implementation of a SAX Battery configuration number entity without ModbusItem."""

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

        # Generate unique ID using class name pattern
        if self._sax_item.name.startswith("sax_"):
            self._attr_unique_id = self._sax_item.name
        else:
            self._attr_unique_id = f"sax_{self._sax_item.name}"

        # Set entity description from modbus item if available
        if self._sax_item.entitydescription is not None:
            self.entity_description = self._sax_item.entitydescription  # type: ignore[assignment] # fmt: skip
```

### ❌ WRONG Entity Initialization Patterns

**DON'T manually set individual attributes:**

```python
# ❌ WRONG - Manual attribute assignment
self._attr_native_min_value = entity_desc.native_min_value or 0.0
self._attr_native_max_value = entity_desc.native_max_value or 100.0
self._attr_native_step = entity_desc.native_step or 1.0
```

**DON'T assume entity description types:**

```python
# ❌ WRONG - Assuming specific types without checking
if isinstance(self._modbus_item.entitydescription, NumberEntityDescription):
    # This may fail due to union types
```

### Entity Description Handling

```python
# ✅ CORRECT - Simple assignment, let HA handle the rest
if self._modbus_item.entitydescription is not None:
    self.entity_description = self._modbus_item.entitydescription

# ✅ CORRECT - Safe attribute access
if (hasattr(self, 'entity_description')
    and hasattr(self.entity_description, 'name')):
    # Use the attribute safely
```
