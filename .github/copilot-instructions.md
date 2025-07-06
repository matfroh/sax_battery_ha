# Instructions for GitHub Copilot

This repository holds a custom integration of SAX battery for Home Assistant, a Python 3 based home
automation application.

## 🔋 SAX-power Home Battery System — Communication Architecture

The SAX-power energy storage solution ensures precise, intelligent power management across a multi-phase installation using structured communication protocols and a coordinated control hierarchy.
A customer system could have multiple battery units, each connected to a different grid phase (L1, L2, L3) for optimal load balancing and energy distribution. The

---

### 📡 Communication Interfaces

Each battery unit is equipped with the following:

#### Ethernet Port (Modbus TCP/IP)

- Allows remote monitoring, data acquisition, and system configuration
- Used to exchange live data and control signals with energy management systems

#### RS485 Port (Modbus RTU)

- Used for communication between the batteries and the smart meter
- Facilitates grid connection measurements for synchronized system behavior

---

### ⚙️ Smart Meter Integration

- A single smart meter is connected to all three grid phases: **L1, L2, and L3**
- Communicates via RS485 to all battery units
- Smart meter data is accessed through the battery units via Modbus TCP/IP
- Provides real-time measurements of:
  - Grid voltage and current per phase (L1, L2, L3)
  - Import/export power levels
  - Total energy consumption and production
  - Grid frequency, power factor, and other electrical parameters
- Acts as the reference point for system control and balancing logic

---

### 🧠 Master Battery Configuration and Data Polling

- **Battery A** is configured as the master unit
- The master battery is responsible for:
  - Power limit coordination for charging and discharging
  - **Smart meter data polling** - Only the master battery polls smart meter data
  - Sharing grid measurements with slave batteries via RS485 communication
- **Battery B and Battery C** act as slaves, following instructions from the master
- **Polling Strategy**:
  - Basic smart meter data (total power, frequency, etc.): Standard interval (5-10 seconds)
  - Phase-specific data (L1/L2/L3 voltages/currents): Lower frequency (30-60 seconds)
  - Battery-specific data: Standard interval for all batteries
- All communication coordination is based on **RS485 grid values** and shared logic via **Ethernet**

---

### 🔌 Power Phase Mapping

| Battery | Grid Phase | Role   |
| ------- | ---------- | ------ |
| A       | L1         | Master |
| B       | L2         | Slave  |
| C       | L3         | Slave  |

- Each battery is connected to a dedicated grid phase (L1, L2, or L3) to balance power flow
- Ensures equal load distribution and phase-specific control

---

### System Diagram

A visual representation includes:

- Separate **RS485** and **Ethernet** connections
- One unified smart meter with direct connection to all three grid phases (**L1/L2/L3**)
- Distinct power line routing

![](./assets/battery_cluster.png)

## Instructions for GitHub Copilot

This repository holds a custom integration for Home Assistant, a Python 3 based home
automation application.

- Python code must be compatible with Python 3.13
- Use the newest Python language features if possible:
  - Pattern matching
  - Type hints
  - f-strings for string formatting over `%` or `.format()`
  - Dataclasses
  - Walrus operator
- Code quality tools:
  - Formatting: Ruff
  - Linting: PyLint and Ruff
  - Type checking: MyPy
  - Testing: pytest with plain functions and fixtures
- Inline code documentation:
  - File headers should be short and concise:
    ```python
    """Integration for Peblar EV chargers."""
    ```
  - Every method and function needs a docstring:
    ```python
    async def async_setup_entry(hass: HomeAssistant, entry: PeblarConfigEntry) -> bool:
        """Set up Peblar from a config entry."""
        ...
    ```
- All code and comments and other text are written in American English
- Follow existing code style patterns as much as possible
- Core locations:
  - Shared constants: `homeassistant/const.py`, use them instead of hardcoding
    strings or creating duplicate integration constants.
  - Integration files:
    - Constants: `custom_components/{domain}/const.py`
    - Models: `custom_components/{domain}/models.py`
    - Coordinator: `custom_components/{domain}/coordinator.py`
    - Config flow: `custom_components/{domain}/config_flow.py`
    - Platform code: `custom_components/{domain}/{platform}.py`
- All external I/O operations must be async
- Async patterns:
  - Avoid sleeping in loops
  - Avoid awaiting in loops, gather instead
  - No blocking calls
- Polling:
  - Follow update coordinator pattern, when possible
  - Polling interval may not be configurable by the user
  - For local network polling, the minimum interval is 5 seconds
  - For cloud polling, the minimum interval is 60 seconds
- Error handling:
  - Use specific exceptions from `homeassistant.exceptions`
  - Setup failures:
    - Temporary: Raise `ConfigEntryNotReady`
    - Permanent: Use `ConfigEntryError`
- Logging:
  - Message format:
    - No periods at end
    - No integration names or domains (added automatically)
    - No sensitive data (keys, tokens, passwords), even when those are incorrect.
  - Be very restrictive on the use of logging info messages, use debug for
    anything which is not targeting the user.
  - Use lazy logging (no f-strings):
    ```python
    _LOGGER.debug("This is a log message with %s", variable)
    ```
- Entities:
  - Ensure unique IDs for state persistence:
    - Unique IDs should not contain values that are subject to user or network change.
    - An ID needs to be unique per platform, not per integration.
    - The ID does not have to contain the integration domain or platform.
    - Acceptable examples:
      - Serial number of a device
      - MAC address of a device formatted using `homeassistant.helpers.device_registry.format_mac`
        Do not obtain the MAC address through arp cache of local network access,
        only use the MAC address provided by discovery or the device itself.
      - Unique identifier that is physically printed on the device or burned into an EEPROM
    - Not acceptable examples:
      - IP Address
      - Device name
      - Hostname
      - URL
      - Email address
      - Username
    - For entities that are setup by a config entry, the config entry ID
      can be used as a last resort if no other Unique ID is available.
      For example: `f"{entry.entry_id}-battery"`
  - If the state value is unknown, use `None`
  - Do not use the `unavailable` string as a state value,
    implement the `available()` property method instead
  - Do not use the `unknown` string as a state value, use `None` instead
- Extra entity state attributes:
  - The keys of all state attributes should always be present
  - If the value is unknown, use `None`
  - Provide descriptive state attributes
- Testing:
  - Test location: `tests/components/{domain}/`
  - Use pytest fixtures from `tests.common`
  - Mock external dependencies
  - Use snapshots for complex data
  - Follow existing test patterns
