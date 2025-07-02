#!/usr/bin/env bash
source .venv/bin/activate
ruff format --check custom_components/sax_battery/
ruff check custom_components/sax_battery/