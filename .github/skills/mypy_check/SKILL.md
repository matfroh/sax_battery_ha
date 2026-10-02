---
name: mypy_check
description: Run static type checks for the SAX battery integration using the repository script.
---

Use this skill when you want to validate Python typing.

## Command

```bash
source "$VIRTUAL_ENV/bin/activate"
./scripts/run_mypy.sh
```

## Expected outcome

- MyPy reports no errors

## If it fails

- Address type errors in the reported files
- Re-run until clean
