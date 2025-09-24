---
description: "Prompt templates for consistent code generation following project standards"
---

# Code Generation Prompts

## Entity Creation Prompt

```
Generate a new Home Assistant entity for the SAX Battery integration following these requirements:

1. **Entity Type**: [sensor/number/switch/etc.]
2. **Purpose**: [Brief description of entity function]
3. **Data Source**: [ModbusItem/SAXItem/calculated]
4. **Platform Patterns**: Follow existing patterns in custom_components/sax_battery/[platform].py
5. **Requirements**:
   - Use proper unique ID generation
   - Follow entity initialization patterns
   - Include comprehensive docstrings
   - Generate corresponding unit tests
   - Comply with all ruff linting rules
   - Use type hints and modern Python features

**Context**: This entity will be part of a multi-battery system with master/slave coordination.
```

## Test Generation Prompt

```
Generate comprehensive unit tests for the following class/method:

**Target**: [Class/Method name and file path]

**Requirements**:
1. Read the actual implementation first
2. Verify all method signatures and parameters
3. Use unique pytest fixture names (avoid shadowing)
4. Mock external dependencies appropriately
5. Test both success and failure scenarios
6. Follow existing test patterns in tests/
7. Include edge cases and error conditions
8. Use proper assertions for entity behavior

**Fixtures to use**: [List existing fixtures if applicable]
```

## Code Review Prompt

```
Review the following code for:

**Security**: OWASP compliance, input validation, secret management
**Performance**: Algorithmic efficiency, resource usage, caching opportunities
**Standards**: Ruff compliance, exception handling, import organization
**Patterns**: Home Assistant entity patterns, async/await usage
**Testing**: Test coverage, fixture usage, mock appropriateness

**Code to review**: [Paste code here]

Focus on actionable improvements and specific violations.
```

## Debugging Prompt

```
Help troubleshoot this issue in the SAX Battery integration:

**Problem**: [Describe the issue]
**Context**: Multi-battery system with Modbus TCP/IP communication
**Error logs**: [Include relevant log output]
**Expected behavior**: [What should happen]

**Analysis needed**:
1. System architecture considerations
2. Modbus communication patterns
3. Home Assistant integration constraints
4. Multi-coordinator coordination issues
5. Suggested debugging steps
```

## Refactoring Prompt

```
Refactor this code to improve:

**Target areas**: [performance/security/maintainability/patterns]
**Current code**: [Paste existing code]

**Requirements**:
- Maintain existing functionality
- Follow Home Assistant patterns
- Apply security best practices
- Improve performance where possible
- Add comprehensive tests for changes
- Update documentation as needed

**Constraints**: Must work with existing multi-battery architecture
```
