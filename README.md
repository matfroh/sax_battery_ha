# Home Assistant integration for SAX-power batteries

[![GitHub Release][releases-shield]][releases]
[![HACS][hacs-shield]][hacs]
[![License][license-shield]](LICENSE)

Monitor and control SAX-power battery systems from Home Assistant. The integration communicates locally with the battery over Modbus TCP and supports one to three batteries.

## Features

- Battery state of charge, power, voltage, current, temperature, and energy data
- Combined battery state of charge and energy statistics
- Optional SAX smart-meter telemetry for ADW200 and ADL400 installations
- Legacy Modbus and SunSpec protocol modes
- Optional Home Assistant power setpoint control
- Minimum and maximum charging state-of-charge limits
- Grid charge/discharge control with a selectable direction
- Diagnostics for coordinator, Modbus, and connection health

## Requirements

- Home Assistant with custom integrations enabled
- One to three SAX battery units reachable from Home Assistant over Modbus TCP
- The battery IP address or hostname and Modbus port (normally `502`)
- For power control, the relevant battery registers must be writable. Confirm access with your SAX installer or support before enabling control.

The battery's own smart meter is connected to the battery system, typically over RS485. Home Assistant connects to the battery over the local network; it does not connect directly to the meter.

## Installation

### Marketplace

1. In home assistant, open **Marketplace** and select the menu to add a custom repository.
2. Add `https://github.com/matfroh/sax_battery_ha` with category **Integration**.
3. Install **SAX Battery** and restart Home Assistant.

### Manual

1. Download the latest release from [GitHub Releases][releases].
2. Copy content of `custom_components/sax_battery` into `<config_dir>/custom_components/sax_battery`.
3. Restart Home Assistant.

## Configuration

In Home Assistant, go to **Settings → Devices & services → Add integration** and search for **SAX Battery**.

The setup flow asks for the following:

1. **Battery count:** Select one to three batteries. Battery A is the default master for a single-battery installation. For multiple batteries, select the master that coordinates the system.
2. **Control options:** Choose whether to enable power setpoint control and power limits.
3. **Smart meter and balancing:** If power control is enabled, select the meter type:
   - **ADW200 / ADL400:** Uses the SAX meter connected to the battery. No external Home Assistant power sensor is required for balancing.
   - **Other Modbus Smart Meter:** Select an external grid power sensor. Positive readings mean grid import; negative readings mean export. This sensor is required for this mode when Home Assistant power control is enabled.
   - **None:** No meter-based balancing is configured; only explicit setpoint control is available.
4. **Protocol:** Choose Legacy or SunSpec. The optional verification setting performs an initial SunSpec availability check.
5. **Battery connection:** Enter each battery's IP address or hostname and port. Use port `502` unless your installation specifies another port.

The external power sensor and balanced-loading options apply to **Other Modbus Smart Meter**. ADW200/ADL400 balancing uses the meter data reported by the battery.

## Devices and Entities

The integration creates entities on these devices:

- **SAX BESS A/B/C:** Per-battery measurements such as SOC, power, temperature, and battery state.
- **SAX BMS:** Combined values, configuration status, control switches, and control numbers.
- **SAX SM:** Smart-meter measurements when ADW200/ADL400 is selected. In the Legacy implementation, the balancing calculation uses the battery-side `Power Smartmeter` reading; the SAX SM device provides additional meter telemetry.

Home Assistant may prefix entity IDs with the assigned area or device name. Use the entity picker instead of assuming an entity ID from an example.

### Configuration status

The BMS device includes read-only binary sensors:

- **BMS Power Control Configured**
- **BMS Power Limits Configured**

They report whether the corresponding integration options are enabled. Automations can use them as conditions. They do not verify that firmware permissions or register writes are working.

## Power Control

Power setpoints use the convention **positive = discharge** and **negative = charge**.

### Power control and limits

- **Power setpoint control** uses Legacy registers 41/42. The displayed setpoint and factor are write-only register values maintained locally by the integration.
- **Max charge** and **Max discharge** use Legacy registers 44 and 43 respectively. They limit battery power per battery; they do not cap total household consumption.
- Legacy power control enforces the absolute per-battery hardware limits and configured minimum and maximum charging SOC.
- Registers 43/44 are Legacy controls. SunSpec exposes Model 123 setpoint controls instead; it does not expose equivalent writable max-charge/max-discharge numbers.

### PV balancing

Turn on **Charging from PV** to enable the configured PV/balancing behavior. With ADW200/ADL400, the integration uses the SAX meter reading. With **Other Modbus Smart Meter**, it uses the configured external grid power sensor; positive means import and negative means export.

For SunSpec, the battery performs smart-meter zero balancing in its own control mode.

### Grid power charge/discharge

The **Grid Power Charge/Discharge** switch enables grid mode. **Grid Power Mode** selects **Charge** (default) or **Discharge**. In Legacy mode, the requested power uses the configured max-charge or max-discharge number. SunSpec has no writable equivalent to Legacy registers 43/44, so its grid-mode request uses the hardware/reference-power ceiling instead. Both modes also apply SOC limits.

When the applicable SOC boundary is reached, grid mode stops and the integration returns to balanced operation. Grid mode starts **off** after a Home Assistant restart. The PV switch restores its previous state when Home Assistant has a saved state for it.

## Automations

Use the Home Assistant entity picker to select the BMS configuration-status binary sensor as an automation condition. For example, check **BMS Power Control Configured** before an automation writes a power setpoint or limit. This distinguishes what is configured from the current PV or grid operating mode.

Set power limits with the corresponding number entities. For Legacy control, the power manager applies the configured limit to its balancing requests, checks SOC limits, and refreshes write-only setpoints periodically because the battery does not report those values back.

When SOC reaches the minimum, **Max discharge** is set to 0 W. When it reaches **Maximum SOC**, **Max charge** is set to 0 W. Once SOC returns inside the configured range, an automation or user must set the relevant limit to a nonzero value to enable that direction again; it is not restored automatically.

## Protocols

- **Legacy:** Uses SAX-specific Modbus registers, including the write-only setpoint and limit registers where enabled.
- **SunSpec:** Reads SunSpec models and uses Model 123 for writable power control. Meter zero balancing is handled by the battery in its SunSpec operating mode.

Supported behavior depends on the battery firmware and writable register access. If a control option is enabled but the hardware refuses writes, check the integration logs and confirm permissions with your installer.

## Troubleshooting

### Cannot connect

- Confirm Home Assistant and the battery are on a network that permits communication between them.
- Verify the IP address/hostname and Modbus TCP port.
- Check that another Modbus client is not interfering with the connection.
- Reload the integration and inspect **Settings → System → Logs** for `custom_components.sax_battery` messages.

### Power setpoint stays at zero or does not respond

- Confirm **Power Control Configured** is on and the required registers are writable.
- Check the battery's combined SOC against the configured minimum SOC and maximum charging SOC.
- Check the configured max-charge/max-discharge limits and selected smart-meter type.
- For **Other Modbus Smart Meter**, verify the selected sensor exists, is available, reports watts, and uses positive for import and negative for export.
- For ADW200/ADL400 in Legacy mode, check the battery-side `Power Smartmeter` entity and its availability.

A zero setpoint may be intentional when an SOC or power limit blocks the requested direction.

### Grid switch is off after restart

This is intentional: grid charge/discharge mode is not automatically resumed after Home Assistant restarts. The selected Grid Power Mode (Charge or Discharge) is retained.

### PV switch state after restart

The PV switch restores from Home Assistant's saved entity state. If the entity was newly created, disabled, or had no saved state, turn it on once in the UI.

### Diagnostics

1. Open **Settings → Devices & services → SAX Battery**.
2. Download diagnostics from the integration menu.
3. Include the relevant log excerpt and battery firmware/protocol details when reporting an issue. Remove sensitive network information before sharing.

## Removing the integration

1. Remove **SAX Battery** from **Settings → Devices & services**.
2. Restart Home Assistant.
3. For a manual installation, remove `<config_dir>/custom_components/sax_battery/` and restart again.

Do not delete Home Assistant's entire entity registry to remove this integration; that registry also contains entities from other integrations.

## Support and contributions

- Report bugs or request features at [GitHub Issues][issues].
- See [GitHub Discussions](https://github.com/matfroh/sax_battery_ha/discussions) for questions.
- Contributions should include tests and pass the repository's Ruff, MyPy, and test scripts.

## License

MIT. See [LICENSE](LICENSE).

[releases-shield]: https://img.shields.io/github/v/release/matfroh/sax_battery_ha?style=flat-square
[releases]: https://github.com/matfroh/sax_battery_ha/releases
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square
[hacs]: https://github.com/hacs/integration
[license-shield]: https://img.shields.io/github/license/matfroh/sax_battery_ha?style=flat-square
[issues]: https://github.com/matfroh/sax_battery_ha/issues
