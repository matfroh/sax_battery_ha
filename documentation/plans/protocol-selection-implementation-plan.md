# Protocol selection implementation plan

## Objective

Refactor the SAX Battery integration so protocol selection is explicit and configuration-driven instead of relying on automatic startup probing. The integration shall allow the user to choose the protocol type during setup or reconfiguration, verify SunSpec availability briefly when requested, and fall back to legacy mode if the check fails or times out.

## Scope

This work covers:

- config flow changes for protocol selection
- config entry data changes for persisted protocol settings
- startup/setup changes to use the configured protocol instead of automatic detection
- a lightweight SunSpec availability check with bounded timeout/retry behavior
- diagnostics and tests for the new flow

## Design summary

### New behavior

- Legacy is the default safe mode.
- The user can explicitly choose SunSpec during configuration.
- When SunSpec is selected, the integration performs one short availability check.
- If the check fails, the integration uses legacy mode and records the fallback.
- The integration no longer depends on the current repeated multi-probe detection sequence during normal startup.

## Implementation steps

### 1. Add protocol-related configuration constants

Update the integration constants to include:

- `CONF_PROTOCOL_MODE`
- `CONF_VERIFY_SUNSPEC`
- `CONF_EFFECTIVE_PROTOCOL_MODE`

Use clear values:

- `legacy`
- `sunspec`

### 2. Extend the config flow

Update the config flow so the user selects the protocol during setup.

#### Proposed flow

1. Keep the existing battery-count step.
2. Add a new protocol step after the initial setup step or after the control options step.
3. Present the following options:
   - Legacy
   - SunSpec
4. Add a checkbox:
   - "Verify SunSpec availability before enabling SunSpec"
5. Persist the selected values in the config entry data.

#### Reconfigure support

Also expose the same protocol options in the reconfigure flow so an existing installation can switch protocol modes later.

### 3. Persist protocol settings in the config entry

Store the following values in the config entry data:

- `protocol_mode`: chosen protocol
- `verify_sunspec`: whether to validate SunSpec availability
- `effective_protocol_mode`: resolved runtime mode after validation

The stored `effective_protocol_mode` should be updated during setup based on the validation result.

### 4. Replace automatic detection in setup

Refactor the startup path so it does not rely on the old multi-probe detection sequence during normal setup.

#### Current problem

The current logic uses repeated protocol probing and multiple retries, which adds delay and can be error-prone.

#### New approach

During setup:

1. Read the configured protocol mode from the config entry.
2. If the mode is `legacy`, use legacy directly.
3. If the mode is `sunspec` and `verify_sunspec` is enabled, run one short validation probe.
4. If validation succeeds, use SunSpec.
5. If validation fails or times out, log a fallback and use legacy.

### 5. Introduce a lightweight SunSpec validation helper

Replace the old detector with a simpler helper such as:

- `validate_sunspec_availability(modbus_api, battery_id)`

#### Requirements

- one short probe only
- at most one retry
- short timeout budget
- no repeated full probe chain
- return a boolean or a small result object with reason

### 6. Update coordinator initialization

Change the coordinator initialization path so it consumes the resolved effective mode from config rather than relying on runtime detection.

#### Expected result

- The coordinator receives `ProtocolMode.LEGACY` or `ProtocolMode.SUNSPEC` directly.
- The old detection path is no longer used in the normal startup flow.

### 7. Keep the legacy provider path intact

Do not change the current legacy behavior beyond the protocol selection integration.

Legacy installations should continue to work without requiring any migration steps.

### 8. Add diagnostics for the resolved mode

Expose the resolved protocol information in diagnostics so it is visible at runtime.

Recommended fields:

- `configured_protocol_mode`
- `effective_protocol_mode`
- `verify_sunspec`
- `protocol_validation_result`
- `protocol_validation_reason`

### 9. Add and update tests

Add tests for the new behavior:

#### Config flow tests

- legacy selection stores the expected config values
- SunSpec selection stores the expected config values
- reconfigure updates the protocol settings

#### Setup tests

- legacy config uses legacy mode without probing
- SunSpec config with successful validation uses SunSpec mode
- SunSpec config with failed validation falls back to legacy

#### Protocol helper tests

- successful validation returns success
- timeout returns failure
- shortened timeout/retry behavior is enforced

## Proposed file changes

### Constants

- [custom_components/sax_battery/const.py](custom_components/sax_battery/const.py)

### Config flow

- [custom_components/sax_battery/config_flow.py](custom_components/sax_battery/config_flow.py)

### Startup/setup

- [custom_components/sax_battery/__init__.py](custom_components/sax_battery/__init__.py)

### Coordinator / protocol handling

- [custom_components/sax_battery/coordinator.py](custom_components/sax_battery/coordinator.py)
- [custom_components/sax_battery/protocol_detector.py](custom_components/sax_battery/protocol_detector.py)
- [custom_components/sax_battery/protocol_mode.py](custom_components/sax_battery/protocol_mode.py)

### Diagnostics

- [custom_components/sax_battery/diagnostics.py](custom_components/sax_battery/diagnostics.py)

### Tests

- [tests/test_config_flow.py](tests/test_config_flow.py)
- [tests/test_init.py](tests/test_init.py)
- [tests/test_protocol_detector.py](tests/test_protocol_detector.py)

## Rollout order

1. Add config entry constants and config flow fields.
2. Persist protocol settings.
3. Introduce lightweight SunSpec validation helper.
4. Route setup through the new effective-mode selection.
5. Update diagnostics and tests.
6. Validate with the existing integration test suite.

## Acceptance criteria

- The user can select the protocol type during configuration.
- The integration no longer depends on automatic repeated detection during startup.
- SunSpec verification is optional and short.
- If SunSpec verification fails, the integration uses legacy mode.
- Existing legacy installs continue to work without manual changes.
- The test suite remains green after the refactor.

## Notes

This refactor should be implemented incrementally so that legacy behavior remains stable while the new config-driven path is introduced.
