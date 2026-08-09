---
name: tests_check
description: Run the integration test suite and coverage using the repository test script.
---

Use this skill when you want to validate behavior with tests.

## Command

```bash
source "$VIRTUAL_ENV/bin/activate"
./scripts/run_tests.sh
```

## Expected outcome

- Pytest test run passes
- Coverage report is generated

## If it fails

- Review failing tests and tracebacks
- Fix regressions
- Re-run until green
