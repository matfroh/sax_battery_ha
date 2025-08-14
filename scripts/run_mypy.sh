#!/usr/bin/env bash
source "$VIRTUAL_ENV/bin/activate"

# python3 -m pip install --upgrade pip
# python3 -m pip install mypy==1.17.1
# Run your standardized mypy invocation, e.g.
mypy custom_components/sax_battery/ tests/ --explicit-package-bases --show-error-codes
