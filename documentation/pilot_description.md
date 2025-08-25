# Former implementation description of the `SAXBatteryPilot` class and how it interacts with Home Assistant components:

---

## **What is `SAXBatteryPilot`?**

`SAXBatteryPilot` is a **service class** that manages the "pilot" logic for the SAX Battery system within a Home Assistant integration. Its purpose is to automatically (or manually) control the battery's power setpoint (charge/discharge), considering real-time sensor data, configuration options, and system constraints such as minimum state-of-charge (SOC).

---

## **How Does It Work?**

### **Initialization**

- When `async_setup_pilot` is called, it:
  - Checks if pilot mode is enabled (`CONF_PILOT_FROM_HA`).
  - Instantiates the `SAXBatteryPilot` class, passing Home Assistant's `hass` object and integration state.
  - Registers two Home Assistant entities:
    - `SAXBatteryPilotPowerEntity`: Shows and can override the calculated battery power.
    - `SAXBatterySolarChargingSwitch`: Allows toggling solar charging on/off.
  - Starts the pilot logic by scheduling periodic updates.

---

### **Main Responsibilities of `SAXBatteryPilot`**

1. **Periodic Update Loop**
   - Uses Home Assistant's `async_track_time_interval` to call `_async_update_pilot` every `update_interval` seconds.
   - Registers a config update listener to react to configuration changes.

2. **Pilot Power Calculation**
   - Reads current power and power factor from Home Assistant sensor entities.
   - Sums up priority device consumption.
   - Reads current battery power and state-of-charge (SOC).
   - Calculates a `target_power` based on power flows, priorities, and constraints.
   - Applies SOC constraints:
     - Prevents charging if SOC is at or above 100%.
     - Prevents discharging if SOC is below the configured minimum.
   - Writes the calculated power (and power factor) to the battery via Modbus, using an executor job.

3. **Manual Control**
   - If `CONF_MANUAL_CONTROL` is set, skips automatic calculations and only checks SOC constraints on the user-set power value.
   - Manual power can be set via the `SAXBatteryPilotPowerEntity` number entity.

4. **Solar Charging Switch**
   - Responds to `SAXBatterySolarChargingSwitch` on/off.
   - If off, sends a power command of zero to the battery.

---

## **How It Uses Home Assistant Components**

### **Entities and Sensors**

- **NumberEntity (`SAXBatteryPilotPowerEntity`)**
  - Exposes the current calculated power as a number entity.
  - Allows the user to override the pilot's calculated value (manual mode).
  - Handles min/max/range and icon based on power direction.
- **SwitchEntity (`SAXBatterySolarChargingSwitch`)**
  - Exposes a switch entity for enabling/disabling solar charging.
  - Toggling this switch invokes `set_solar_charging` on the pilot.

### **State Reading**

- Reads sensor states from Home Assistant using `hass.states.get(entity_id)`:
  - Power sensor (total home power)
  - Power factor sensor
  - Priority device sensors (list of entity_ids)
  - Battery combined power and SOC

### **Event Tracking**

- Uses `async_track_time_interval` to schedule periodic updates.
- Registers a config entry update listener to react to integration config changes.

### **Service Calls / Modbus**

- Sends commands to the battery hardware using the Modbus client (outside Home Assistant's normal service call mechanism, but integrated via the Home Assistant event loop).

---

## **Summary Table**

| Component                  | Usage in `SAXBatteryPilot`                                             |
|----------------------------|-------------------------------------------------------------------------|
| `HomeAssistant` object     | Core for accessing entities, state, event loop, and scheduling updates. |
| `NumberEntity`             | Exposes/overrides calculated power.                                     |
| `SwitchEntity`             | Toggles solar charging logic.                                           |
| `hass.states.get()`        | Reads sensor states (power, PF, SOC, etc.).                             |
| `async_track_time_interval`| Schedules regular pilot updates.                                        |
| Config Entry Listener      | Reacts to integration option changes.                                   |

---

## **In Practice**

- **Automatic mode:** The pilot continuously calculates the optimal power setpoint for the battery based on live energy flows, priorities, and battery SOC, sending the command to the battery hardware.
- **Manual mode:** The pilot enforces SOC constraints on the user-set power value, but does not recalculate automatically.
- **Entities:** Exposed entities let users monitor and override the pilot’s behavior from the Home Assistant UI.

---

**In short:**  
`SAXBatteryPilot` is the "brain" of the battery logic, tightly integrated with Home Assistant for sensor readings, state tracking, configuration, and exposing control/monitoring entities to the user.
