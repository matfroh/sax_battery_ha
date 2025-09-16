#!/usr/bin/env bash
source "$VIRTUAL_ENV/bin/activate"

# Run your standardized mypy invocation, e.g.
mypy custom_components/sax_battery/ tests/ --explicit-package-bases --show-error-codes
