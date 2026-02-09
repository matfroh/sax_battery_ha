# Data Flow Architecture

This document describes how data flows through the SAX Battery integration, from hardware polling to user interface updates and user actions back to hardware control.

## 🔄 Overview

Data flows through the SAX Battery integration in several distinct patterns:

1. **Monitoring Flow**: Hardware → Coordinator → Entities → UI
2. **Control Flow**: UI → Entities → Managers → Hardware  
3. **Protection Flow**: Managers → Constraint Checks → Hardware Limits
4. **Configuration Flow**: Config Flow → Storage → Runtime Initialization

## 📊 System Data Flow

```mermaid
sequenceDiagram
    participant UI as Home Assistant UI
    participant ENT as Platform Entities
    participant COORD as SAX Coordinator
    participant PM as Power Manager
    participant SM as SOC Manager
    participant API as Modbus API
    participant BAT as SAX Battery
    participant METER as Smart Meter

    Note over COORD,BAT: Monitoring Flow (Polling Cycle)
    
    COORD->>API: async_read_all_registers()
    API->>BAT: Modbus TCP read_holding_registers()
    BAT->>METER: RS485 smart meter data
    METER-->>BAT: Grid measurements
    BAT-->>API: Register data + smart meter
    API-->>COORD: Processed sensor values
    COORD->>ENT: Entity state updates
    ENT->>UI: State changes displayed
    
    Note over UI,BAT: Control Flow (User Action)
    
    UI->>ENT: User changes number entity
    ENT->>ENT: Validate input range
    ENT->>SM: Check SOC constraints
    SM-->>ENT: Constraint result
    ENT->>COORD: Write validated value
    COORD->>API: async_write_register()
    API->>BAT: Modbus TCP write_registers()
    BAT-->>API: Write confirmation
    API-->>COORD: Success/failure
    COORD-->>ENT: Write result
    ENT->>UI: State updated
```

## 🏗️ Detailed Data Flows

### 1. Monitoring Data Flow

#### Master Battery Polling Sequence

```mermaid
sequenceDiagram
    participant TIMER as Coordinator Timer
    participant COORD as Master Coordinator
    participant CB as Circuit Breaker  
    participant API as Modbus API
    participant MASTER as Master Battery
    participant METER as Smart Meter
    participant ENT as Platform Entities

    Note over TIMER,ENT: Every 15 seconds (Master Battery)
    
    TIMER->>COORD: Timer trigger (_async_update_data)
    COORD->>CB: check_circuit_state()
    alt Circuit CLOSED
        CB-->>COORD: Allow request
        COORD->>API: read_battery_registers()
        API->>MASTER: Read battery data (SOC, Power, etc.)
        MASTER-->>API: Battery register values
        
        COORD->>API: read_smart_meter_registers()
        API->>MASTER: Read smart meter data
        MASTER->>METER: RS485 query
        METER-->>MASTER: Grid measurements
        MASTER-->>API: Smart meter values
        API-->>COORD: Combined dataset
        
        COORD->>COORD: process_and_validate_data()
        COORD->>CB: record_success()
        COORD->>ENT: notify_state_update()
        ENT->>ENT: Update native_value properties
    else Circuit OPEN
        CB-->>COORD: Block request
        COORD->>COORD: Use cached data
        Note over COORD: Entity states marked unavailable
    end
```

#### Slave Battery Polling Sequence

```mermaid
sequenceDiagram 
    participant TIMER as Coordinator Timer
    participant COORD as Slave Coordinator
    participant API as Modbus API
    participant SLAVE as Slave Battery
    participant ENT as Platform Entities

    Note over TIMER,ENT: Every 30 seconds (Slave Battery)
    
    TIMER->>COORD: Timer trigger
    COORD->>API: read_battery_registers_only()
    API->>SLAVE: Individual battery data
    SLAVE-->>API: Battery register values
    API-->>COORD: Battery dataset
    COORD->>ENT: notify_state_update()
    ENT->>ENT: Update native_value properties
    
    Note over COORD,ENT: No smart meter data (master only)
```

### 2. Control Data Flow

#### Number Entity Value Change

```mermaid
sequenceDiagram
    participant USER as User
    participant UI as HA Frontend
    participant NUM as Number Entity
    participant SM as SOC Manager
    participant COORD as Coordinator
    participant API as Modbus API
    participant BAT as SAX Battery

    USER->>UI: Change power limit slider
    UI->>NUM: async_set_native_value(new_value)
    
    NUM->>NUM: Input validation
    alt Value out of range
        NUM-->>UI: HomeAssistantError
        UI-->>USER: Error message
    else Value valid
        NUM->>SM: check_discharge_allowed(new_value)
        
        alt SOC too low 
            SM->>SM: calculate_constrained_value()
            SM-->>NUM: ConstraintResult(constrained_value)
            NUM->>NUM: value = constrained_value
        else SOC acceptable
            SM-->>NUM: ConstraintResult(original_value)
        end
        
        NUM->>COORD: async_write_number_value()
        COORD->>API: write_registers(register, value)
        API->>BAT: Modbus TCP write
        
        alt Write successful
            BAT-->>API: Success response
            API-->>COORD: Write confirmed
            COORD-->>NUM: Success
            NUM->>NUM: Update _local_value cache
            NUM->>UI: State updated
            UI-->>USER: New value displayed
        else Write failed
            BAT-->>API: Error response
            API-->>COORD: ModbusException
            COORD-->>NUM: Write failed
            NUM-->>UI: HomeAssistantError  
            UI-->>USER: Error message
        end
    end
```

#### Switch Entity Toggle

```mermaid
sequenceDiagram
    participant USER as User
    participant UI as HA Frontend 
    participant SW as Switch Entity
    participant PM as Power Manager
    participant COORD as Coordinator

    USER->>UI: Toggle solar charging switch
    UI->>SW: async_turn_on()
    
    SW->>PM: enable_solar_charging()
    PM->>PM: disable_other_modes()
    PM->>COORD: Update mode state
    
    alt Mode change successful
        COORD-->>PM: Success
        PM-->>SW: Mode enabled
        SW->>SW: _is_on = True
        SW->>UI: State updated
        UI-->>USER: Switch on
    else Mode change failed
        COORD-->>PM: Error
        PM-->>SW: Mode change failed
        SW-->>UI: HomeAssistantError
        UI-->>USER: Error message
    end
```

### 3. Protection Data Flow

#### SOC Constraint Enforcement

```mermaid
sequenceDiagram
    participant TIMER as Background Timer
    participant SM as SOC Manager
    participant COORD as Master Coordinator
    participant ER as Entity Registry
    participant NUM as Max Discharge Entity
    participant API as Modbus API
    participant BAT as Master Battery

    Note over TIMER,BAT: Periodic SOC monitoring
    
    TIMER->>SM: check_and_enforce_discharge_limit()
    SM->>COORD: Get combined SOC
    COORD-->>SM: Current SOC value
    
    alt SOC < minimum_threshold
        SM->>SM: Log constraint warning
        SM->>ER: async_get_entity_id(SAX_MAX_DISCHARGE)
        ER-->>SM: Entity ID found
        SM->>NUM: Set native value to 0W
        NUM->>COORD: async_write_number_value() 
        COORD->>API: write_registers(register_41, 0)
        API->>BAT: Disable discharge
        BAT-->>API: Write confirmed
        SM->>SM: Log protection applied
    else SOC >= threshold
        SM->>SM: No constraint needed
        Note over SM: Existing limits maintained
    end
```

### 4. Circuit Breaker Flow

#### Failure Detection and Recovery

```mermaid
sequenceDiagram
    participant COORD as Coordinator
    participant CB as Circuit Breaker
    participant API as Modbus API
    participant BAT as SAX Battery
    participant TIMER as Recovery Timer

    Note over COORD,BAT: Normal Operation
    
    COORD->>CB: call(modbus_operation)
    CB->>API: Forward request
    API->>BAT: Modbus TCP
    
    alt Communication Success
        BAT-->>API: Response
        API-->>CB: Success result
        CB->>CB: reset_failure_count()
        CB-->>COORD: Return result
    else Communication Failure
        BAT-->>API: Timeout/Error
        API-->>CB: ModbusException
        CB->>CB: increment_failure_count()
        
        alt failure_count < threshold
            CB-->>COORD: Return error
        else failure_count >= threshold
            CB->>CB: open_circuit()
            CB-->>COORD: CircuitOpenError
            CB->>TIMER: Schedule recovery attempt
            
            Note over CB,TIMER: Circuit OPEN - Block requests
            
            TIMER->>CB: cooldown_expired()
            CB->>CB: set_half_open()
            COORD->>CB: Next request attempt
            CB->>API: Test request
            
            alt Test Success 
                API-->>CB: Success
                CB->>CB: close_circuit()
                CB-->>COORD: Normal operation resumed
            else Test Failure
                API-->>CB: Still failing
                CB->>CB: open_circuit()
                CB->>TIMER: Schedule next attempt  
            end
        end
    end
```

## 📈 Data Processing Pipeline

### 1. Raw Data Acquisition

```python
# Coordinator polling cycle
async def _async_update_data(self) -> dict[str, Any]:
    """Fetch and process sensor data from SAX Battery."""
    
    # 1. Read raw register values
    raw_data = {}
    for item in self.modbus_items:
        raw_value = await self.modbus_api.read_value(item)
        raw_data[item.address] = raw_value
    
    # 2. Apply scaling factors and conversions
    processed_data = {}
    for item in self.modbus_items:
        if raw_data[item.address] is not None:
            processed_data[item.name] = raw_data[item.address] * item.factor
    
    # 3. Calculate derived values
    if SAX_SOC in processed_data:
        processed_data[SAX_COMBINED_SOC] = self._calculate_combined_soc()
    
    return processed_data
```

### 2. Entity State Updates

```python
# Entity value retrieval  
@property
def native_value(self) -> float | None:
    """Get current sensor value from coordinator data."""
    if self.coordinator.data is None:
        return None
    
    # Direct register value for hardware entities
    if isinstance(self._item, ModbusItem):
        return self.coordinator.data.get(self._item.name)
    
    # Calculated value for virtual entities
    elif isinstance(self._item, SAXItem):
        return self._calculate_value(self.coordinator.data)
```

### 3. User Input Processing

```python
# Number entity value setting
async def async_set_native_value(self, value: float) -> None:
    """Process user input with validation and constraints."""
    
    # Step 1: Input validation
    if not self._validate_range(value):
        raise HomeAssistantError(f"Value {value} out of range")
    
    # Step 2: Apply SOC constraints
    if self.coordinator.soc_manager:
        constraint_result = await self.coordinator.soc_manager.check_discharge_allowed(value)
        if not constraint_result.allowed:
            _LOGGER.warning("Power limited by SOC: %sW -> %sW", value, constraint_result.constrained_value)
            value = constraint_result.constrained_value
    
    # Step 3: Write to hardware
    await self.coordinator.async_write_number_value(self._modbus_item, value)
    
    # Step 4: Cache for write-only registers
    self._local_value = value
    self.async_write_ha_state()
```

## 🔗 Data Dependencies

### Inter-Component Data Flow

```mermaid
graph TD
    subgraph "Data Sources"
        BATTERY[SAX Battery Hardware]
        METER[Smart Meter]
        CONFIG[Config Entry]
    end
    
    subgraph "Processing Layer"
        API[Modbus API]
        COORD[Coordinator]
        CB[Circuit Breaker]
    end
    
    subgraph "Business Logic"
        SM[SOC Manager]
        PM[Power Manager]
    end
    
    subgraph "Entities"
        SENS[Sensors]
        NUM[Numbers] 
        SW[Switches]
    end
    
    subgraph "User Interface"
        UI[HA Frontend]
        AUTO[Automations]
    end

    BATTERY --> API
    METER --> BATTERY
    CONFIG --> COORD
    API --> COORD
    CB --> API
    COORD --> SM
    COORD --> PM
    COORD --> SENS
    COORD --> NUM
    COORD --> SW
    SM --> NUM
    PM --> SW
    SENS --> UI
    NUM --> UI
    SW --> UI
    AUTO --> NUM
    AUTO --> SW
```

### Data Synchronization Points

1. **Coordinator Timer**: Periodic data refresh from hardware
2. **Entity Updates**: State synchronization when coordinator data changes
3. **User Actions**: Immediate validation and hardware writes
4. **Constraint Enforcement**: Background SOC monitoring and limit application
5. **Circuit Breaker**: Failure detection and recovery coordination

## ⚡ Performance Characteristics

### Polling Intervals

- **Master Battery**: 15 seconds (includes smart meter data)
- **Slave Batteries**: 30 seconds (battery data only)  
- **SOC Monitoring**: Every coordinator update cycle
- **Circuit Breaker Recovery**: 60 seconds during outages

### Data Caching Strategy

- **Coordinator Data**: Cached between polling cycles
- **Write-Only Values**: Locally cached in entities with state restoration
- **Circuit Breaker**: Cached decisions to avoid redundant calls
- **Entity Registry**: Cached lookups for performance

### Error Handling Flow

```mermaid
graph TD
    REQUEST[User/Timer Request] --> VALIDATE[Input Validation]
    VALIDATE --> |Valid| CIRCUIT[Circuit Breaker Check]
    VALIDATE --> |Invalid| ERROR1[Input Error]
    
    CIRCUIT --> |Open| ERROR2[Circuit Open Error]
    CIRCUIT --> |Closed/Half-Open| MODBUS[Modbus Operation]
    
    MODBUS --> |Success| UPDATE[Update State]
    MODBUS --> |Timeout| CB_FAIL[Record Circuit Failure]
    MODBUS --> |Protocol Error| CB_FAIL
    MODBUS --> |Connection Error| CB_FAIL
    
    CB_FAIL --> THRESHOLD{Failure Threshold?}
    THRESHOLD --> |Below| RETRY[Return Error, Allow Retry]
    THRESHOLD --> |Exceeded| OPEN_CB[Open Circuit Breaker]
    
    UPDATE --> SUCCESS[Operation Complete]
    ERROR1 --> USER_ERROR[Show User Error]
    ERROR2 --> FALLBACK[Use Cached Data]
    OPEN_CB --> SCHEDULE[Schedule Recovery]
```

---

**Next**: [Modbus Communication](modbus-communication.md)  
**See Also**: [Components](components.md), [Multi-Battery System](multi-battery-system.md)
