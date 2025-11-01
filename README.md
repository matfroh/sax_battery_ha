# Home Assistant AddOn to manage 1 or more SAX batteries

This is a custom component for Home Assistant to manage one or multiple SAX batteries.

> [!IMPORTANT]  
**Work in Progress**  
This battery management system (pilot functions) is being developed to control charging and discharging limits, calculate appropriate power levels, and allow Home Assistant to manage the battery behavior.  
Several configuration options are available, depending on which registers you have permission to write to.  
Refer to the documentation to learn how to enable register writing.

## Installation

Follow these steps to set up the SAX Battery integration in Home Assistant:

- **Install the Integration**
  - Use [HACS](https://hacs.xyz/docs/setup/download): Go to `HACS > Integrations > Explore & Add Repositories`, search for "sax battery", and add `https://github.com/matfroh/sax_battery_ha` as a custom repository.
  - Or manually copy the files to HA `/custom_components/sax_battery/` directory.

- **Restart Home Assistant**
  - After adding the files, restart Home Assistant to load the integration.

## Configuration Steps

1. **Add the Integration**

    - In Home Assistant, go to "Settings" → "Devices & Services", click "+", and search for "SAX battery".
    - Activate the integration.

2. **Select Number of Batteries**

    *Choose how many batteries you want to configure (1–3).*
    <img src="https://github.com/matfroh/sax_battery_ha/blob/main/assets/step1.png" width="600" alt="Select Number of Batteries">

4. **Select Control Options**

    *Choose if you want to enable "Pilot from Home Assistant" and/or "Limit Power".*
    <img src="https://github.com/matfroh/sax_battery_ha/blob/main/assets/step2.png" width="600" alt="Select Control Options">

  > [!IMPORTANT]
  > You need to have register 41, 42, 43, 44 writable for full control.
  > Contact SAX Power customer service and request write access for control registers e.g. 41, 42 (limit charge/discharge power)
  >
  > [SAX Power Customer service ticket](https://sax-power.net/kontakt/kundenservice/)

4. **Configure Pilot Options** *(only if "Pilot from HA" is enabled)*

    *Set minimum SOC, auto pilot interval, and enable solar charging.*
    <img src="https://github.com/matfroh/sax_battery_ha/blob/main/assets/step3.png" width="600" alt="Configure Pilot Options">

  > [!IMPORTANT]
  > Power limiter to charge or discharge works but the device does not allow reading that value, so by default, slider is set to maximum and unless there is an error, the value passed is taken as working.

  > [!WARNING] 
  > Battery steering:
  > Setup all necessary protection to avoid deep discharge (bringing battery to SOC 0%) as this might damage your battery system. Recommendation is to start setting thresholds for discharge at 15% to avoid battery to go below 10%.

5. **Configure Sensors** *(only if "Pilot from HA" is enabled)*

    *Select power and power factor sensors.*
    <img src="https://github.com/matfroh/sax_battery_ha/blob/main/assets/step4.png" width="600" alt="Configure Sensors">

6. **Configure Priority Devices**

    *Optionally select devices (e.g., EV charger, heat pump) that should have priority over battery usage.*
    <img src="https://github.com/matfroh/sax_battery_ha/blob/main/assets/step5.png" width="600" alt="Configure Priority Devices">

7. **Configure Battery Connection**

    - *Enter IP and port for each battery.*
    - *Select the master battery if more than one.*
    <img src="https://github.com/matfroh/sax_battery_ha/blob/main/assets/step6.png" width="600" alt="Configure Battery Connection">

8. **Review and Finish**

    *Confirm your settings and finish the setup.*
    <img src="https://github.com/matfroh/sax_battery_ha/blob/main/assets/step7.png" width="600" alt="Review and Finish">

After restart, your sensors should immediately appear and give you current values

> [!Note]
>
> - If upgrading from a previous version, clear your browser cache or use private mode to see updated explanations.
> - Not selecting any feature will still install all the sensors of the battery.
> - If you have multiple batteries, you can set only the master battery and read/steer it, but you will lack detailed sensors for the system.

## Advanced: Manual Control

*Use the pilot mode to manually set charging/discharging values.*
![Advanced: Manual Control](assets/saxpilot.png)
