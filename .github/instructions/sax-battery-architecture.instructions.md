---
description: "SAX Battery System Communication Architecture and Technical Overview"
---

# 🔋 SAX-power Home Battery System — Communication Architecture

The SAX-power energy storage solution ensures precise, intelligent power management across a multi-phase installation using structured communication protocols and a coordinated control hierarchy.
A customer system could have multiple battery units, each connected to a different grid phase (L1, L2, L3) for optimal load balancing and energy distribution.

## 📡 Communication Interfaces

Each battery unit is equipped with the following:

### Ethernet Port (Modbus TCP/IP)

- Allows remote monitoring, data acquisition, and system configuration
- Used to exchange live data and control signals with energy management systems

### RS485 Port (Modbus RTU)

- Used for communication between the batteries and the smart meter
- Facilitates grid connection measurements for synchronized system behavior

## ⚙️ Smart Meter Integration

- A single smart meter is connected to all three grid phases: **L1, L2, and L3**
- Communicates via RS485 to all battery units
- Smart meter data is accessed through the battery units via Modbus TCP/IP
- Provides real-time measurements of:
  - Grid voltage and current per phase (L1, L2, L3)
  - Import/export power levels
  - Total energy consumption and production
  - Grid frequency, power factor, and other electrical parameters
- Acts as the reference point for system control and balancing logic

## 🧠 Master Battery Configuration and Data Polling

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
  - every battery unit polls its own data at the same interval using an individual coordinator
  - Redundant sensor values shall only be polled by the master battery
- All communication coordination is based on **RS485 grid values** and shared logic via **Ethernet**

## 🔌 Power Phase Mapping

| Battery | Grid Phase | Role   |
| ------- | ---------- | ------ |
| A       | L1         | Master |
| B       | L2         | Slave  |
| C       | L3         | Slave  |

- Each battery is connected to a dedicated grid phase (L1, L2, or L3) to balance power flow
- Ensures equal load distribution and phase-specific control

## System Diagram

A visual representation includes:

- Separate **RS485** and **Ethernet** connections
- One unified smart meter with direct connection to all three grid phases (**L1/L2/L3**)
- Distinct power line routing

![](./assets/battery_cluster.png)
