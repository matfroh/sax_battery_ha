---
description: "Structured prompts for debugging and problem-solving in SAX Battery integration"
---

# Troubleshooting Prompts

## Connection Issues Prompt

```
Diagnose Modbus communication problems:

**Symptoms**: [Describe connection issues]
**Configuration**:
- Host: [IP address]
- Port: [Modbus port]
- Battery role: [master/slave]
- Network setup: [describe topology]

**Analysis checklist**:
1. Network connectivity (ping, telnet)
2. Modbus protocol compliance
3. Register address mapping
4. Timeout and retry settings
5. Multi-battery coordination conflicts
6. Error handling and logging

**Logs**: [Include relevant debug output]
```

## Entity State Issues Prompt

```
Debug entity state problems:

**Entity details**:
- Type: [sensor/number/switch]
- Name: [entity name]
- Unique ID: [unique identifier]
- Expected state: [what should show]
- Actual state: [what actually shows]

**Investigation steps**:
1. Coordinator data updates
2. Entity attribute mapping
3. Data type conversion
4. Availability logic
5. Update frequency
6. Multi-battery data conflicts

**Related logs**: [Include coordinator and entity logs]
```

## Performance Issues Prompt

```
Analyze performance bottlenecks:

**Performance symptoms**: [slow updates/high CPU/memory leaks]
**System context**:
- Number of batteries: [count]
- Update frequency: [seconds]
- Entity count: [total entities]
- Hardware specs: [if relevant]

**Profiling areas**:
1. Coordinator update cycles
2. Modbus communication efficiency
3. Entity processing overhead
4. Data structure optimization
5. Async operation patterns
6. Memory usage patterns

**Metrics**: [Include timing data if available]
```

## Configuration Problems Prompt

```
Resolve config flow and setup issues:

**Setup stage**: [discovery/user input/validation/creation]
**Configuration data**: [relevant config details]
**Error message**: [exact error text]

**Debugging focus**:
1. Config entry validation
2. Option handling
3. Migration logic
4. Default value assignment
5. Device discovery
6. Integration reload behavior

**Logs**: [Include config flow debug output]
```

## Multi-Battery Coordination Prompt

```
Debug master/slave battery coordination:

**System topology**:
- Master battery: [ID and phase]
- Slave batteries: [IDs and phases]
- Smart meter connection: [details]

**Coordination issue**: [describe problem]

**Analysis points**:
1. Master battery polling logic
2. Data sharing between coordinators
3. Phase-specific entity creation
4. Smart meter data distribution
5. RS485 vs Ethernet communication
6. Update synchronization

**System logs**: [Include multi-battery debug output]
```

## Integration Lifecycle Prompt

```
Debug Home Assistant integration lifecycle:

**Lifecycle stage**: [startup/reload/shutdown/update]
**Integration state**: [loaded/failed/updating]
**Error context**: [when does it occur]

**Investigation areas**:
1. Integration initialization
2. Platform setup sequence
3. Entity registration
4. Config entry management
5. Cleanup and disposal
6. Update coordinator lifecycle

**HA logs**: [Include Home Assistant core logs]
```
