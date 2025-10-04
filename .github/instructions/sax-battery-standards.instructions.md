---
description: "Python coding standards and Home Assistant integration patterns"
---

# Python Coding Standards

## General Python Requirements

- Python code must be compatible with Python 3.13
- Use the newest Python language features if possible:
  - Pattern matching
  - Type hints
  - f-strings for string formatting over `%` or `.format()`
  - Dataclasses
  - Walrus operator

## Code Quality Tools

- Formatting: Ruff
- Linting: PyLint and Ruff
- Type checking: MyPy
- Testing: pytest with plain functions and fixtures

## Linting Rules Compliance

**Follow linting rules from `pyproject.toml`** - All code generation must adhere to the configured ruff rules including:

- **Import sorting** (I001): Always sort imports alphabetically and group them properly
- **Exception handling** (BLE001): Never catch blind `Exception` - use specific exception types
- **Import cleanup** (F401): Remove unused imports immediately
- **Security** (S): Follow security best practices (avoid `eval`, sanitize inputs)
- **Complexity** (C901): Keep functions simple and readable
- All other rules defined in `pyproject.toml` under `[tool.ruff]` and `[tool.ruff.lint]`

## Documentation Standards

### Inline Code Documentation

- File headers should be short and concise:

  ```python
  """Integration for SAX Battery systems."""
  ```

- Every method and function needs a docstring:

  ```python
  async def async_setup_entry(hass: HomeAssistant, entry: SAXConfigEntry) -> bool:
      """Set up SAX Battery from a config entry."""
      ...
  ```

## Import Management

- Always sort imports alphabetically within their groups
- Group imports: standard library, third-party, local imports
- Remove unused imports immediately (F401 violations)
- Use specific imports rather than wildcard imports
- Import order example:

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

## Security Considerations

- Avoid `eval()` function - use `ast.literal_eval()` or safe alternatives
- Validate and sanitize all user inputs
- Use parameterized queries for database operations
- Never log sensitive information

## Language and Style

- All code and comments and other text are written in American English
- Follow existing code style patterns as much as possible
