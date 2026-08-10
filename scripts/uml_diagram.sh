#!/usr/bin/env bash
source "$VIRTUAL_ENV/bin/activate"
pyreverse -o png --output-directory documentation/ custom_components/sax_battery/ --project sax_battery --no-standalone
