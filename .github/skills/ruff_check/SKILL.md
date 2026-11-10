---
name: ruff_check
description: Run formatting and lint checks for the SAX battery integration using the repository script.
---

Use this skill when you want to validate formatting and linting.

## Command

```bash
source "$VIRTUAL_ENV/bin/activate"
./scripts/run_ruff.sh
```

## Expected outcome

- `ruff format --check` passes
- `ruff check` passes

## If it fails

- Fix formatting first
- Fix lint violations next
- Re-run the command until clean
