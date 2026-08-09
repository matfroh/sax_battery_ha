# GitHub Copilot Instructions for SAX Battery Integration

This repository is a Home Assistant custom integration for SAX-power batteries. The active work on this branch is SunSpec protocol support, but the integration still retains the legacy protocol path.

## What matters most

- Start with [README.md](../README.md) and the docs in [documentation/](../documentation/) for product and architecture context.
- Follow the normal Home Assistant pattern of config flow -> coordinator -> entity platforms.
- Prefer async, coordinator-based code and avoid blocking I/O.
- Use specific Modbus and connection exceptions rather than broad catch blocks.

## Architecture snapshot

- Protocol handling: [custom_components/sax_battery/protocol_detector.py](../custom_components/sax_battery/protocol_detector.py) and [custom_components/sax_battery/protocol_mode.py](../custom_components/sax_battery/protocol_mode.py)
- SunSpec implementation: [custom_components/sax_battery/sunspec_client.py](../custom_components/sax_battery/sunspec_client.py), [custom_components/sax_battery/const_sunspec.py](../custom_components/sax_battery/const_sunspec.py)
- Legacy implementation: [custom_components/sax_battery/const_legacy.py](../custom_components/sax_battery/const_legacy.py)
- Core runtime flow: [custom_components/sax_battery/coordinator.py](../custom_components/sax_battery/coordinator.py), [custom_components/sax_battery/items.py](../custom_components/sax_battery/items.py), [custom_components/sax_battery/number.py](../custom_components/sax_battery/number.py), [custom_components/sax_battery/sensor.py](../custom_components/sax_battery/sensor.py), [custom_components/sax_battery/switch.py](../custom_components/sax_battery/switch.py)

## Repository-specific conventions

- Use the existing helper for entity unique IDs; do not hardcode entity IDs or unique IDs.
- Preserve the distinction between virtual/config entities and hardware-backed entities.
- For write-only Modbus registers, keep the local cached value in sync with the UI and restore it on startup when appropriate.
- Do not add user-configurable polling intervals.
- Keep log messages concise and avoid logging sensitive data.
- Use specific exceptions such as `ModbusException`, `OSError`, `TimeoutError`, `ValueError`, and `ConfigEntryNotReady`.

## Validation commands

Run these from the repository root after activating the existing virtual environment:

```bash
source "$VIRTUAL_ENV/bin/activate"
./scripts/run_tests.sh
./scripts/run_ruff.sh
./scripts/run_mypy.sh
```

## Testing guidance

- Add or update tests under [tests/](../tests/).
- Focus on protocol detection, coordinator behavior, config flow, and entity state restoration.
- For protocol-related work, cover both legacy and SunSpec paths when practical.

## Security and quality

- Keep secrets out of code; prefer config entry data or environment values over hardcoded credentials.
- Follow Home Assistant patterns, especially coordinator-based updates and entity availability handling.
- Prefer minimal, readable changes over broad refactors.
