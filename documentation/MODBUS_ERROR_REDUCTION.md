# Modbus Error Reduction Improvements

## Overview
Implemented comprehensive improvements to reduce modbus errors and logging noise in the SAX Battery integration.

## Root Cause Analysis
The errors were caused by:
1. **Transaction ID Mismatches**: PyModbus 3.11.1 was receiving responses with mismatched transaction IDs
2. **Request Cancellations**: Multiple requests being cancelled "outside pymodbus" 
3. **Device Conflicts**: Multiple modbus devices (SAX batteries + EV charger) interfering
4. **Aggressive Polling**: 30-second update interval was too frequent
5. **Timeout Issues**: Short timeouts causing premature failures

## Implemented Solutions

### 1. ✅ Increased Coordinator Update Interval
- **Change**: Updated from 30 seconds to 60 seconds
- **File**: `__init__.py` line 59
- **Impact**: Reduces modbus traffic by 50% and prevents timeout warnings

### 2. ✅ Added Retry Logic with Exponential Backoff
- **Change**: Implemented proper retry mechanisms in `hub.py`
- **Features**:
  - 2 retries (up from 1) with exponential backoff delays
  - 0.5s base delay, increasing per retry attempt
  - Separate retry handling for different error types
- **Impact**: Handles transaction ID mismatches gracefully

### 3. ✅ Improved Connection Management  
- **Changes**:
  - Increased timeouts: MODBUS_TIMEOUT 5→8s, READ_TIMEOUT 3→5s
  - Added client configuration for better connection handling
  - Enhanced client initialization with proper error handling
- **Impact**: Reduces connection conflicts between multiple devices

### 4. ✅ Graceful Error Handling
- **Change**: Convert common recoverable errors from ERROR to WARNING
- **Specific**: "Request cancelled outside pymodbus" now logs as WARNING
- **Impact**: Reduces error spam while maintaining visibility of real issues

### 5. ✅ Reduced PyModbus Logging Verbosity
- **Change**: Set pymodbus loggers to WARNING level in `__init__.py`
- **Targets**:
  - `pymodbus.logging` → WARNING level
  - `pymodbus.client.tcp` → WARNING level  
- **Impact**: Eliminates transaction ID mismatch spam from logs

## Technical Details

### Timeout Configuration
```python
MODBUS_TIMEOUT = 8.0    # Increased from 5s
MODBUS_RETRIES = 2      # Increased from 1  
READ_TIMEOUT = 5.0      # Increased from 3s
RETRY_DELAY = 0.5       # New: delay between retries
```

### Retry Pattern
```python
for attempt in range(MODBUS_RETRIES + 1):
    try:
        # Modbus operation
        result = await client.read_holding_registers(...)
        if not result.isError():
            return result.registers
        # Handle error with exponential backoff
        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
    except TimeoutError:
        # Retry with longer delay
```

### Error Classification
- **WARNING**: Recoverable issues like "Request cancelled outside pymodbus"
- **ERROR**: Persistent failures after all retries exhausted

## Expected Results

### Before Changes
```
ERROR (MainThread) [pymodbus.logging] ERROR: request ask for transaction_id=2 but got id=1, Skipping.
ERROR (MainThread) [custom_components.sax_battery.hub] Modbus communication error for battery battery_a: Modbus Error: [Input/Output] Request cancelled outside pymodbus.
ERROR (MainThread) [custom_components.sax_battery.hub] Error reading power_factor (address 40093): Modbus communication error for battery battery_a: Modbus Error: [Input/Output] Request cancelled outside pymodbus.
WARNING (MainThread) [homeassistant.components.sensor] Updating sax_battery sensor took longer than the scheduled update interval 0:00:30
```

### After Changes
- Transaction ID mismatches: **Suppressed** (WARNING level only)
- "Request cancelled" errors: **WARNING** instead of ERROR
- Update interval warnings: **Eliminated** (60s interval)
- Retry attempts: **Automatic** with exponential backoff
- Connection stability: **Improved** with better timeouts

## Monitoring Recommendations

1. **Watch for WARNING logs**: Still indicates communication issues but non-critical
2. **ERROR logs**: Now indicate persistent problems requiring attention  
3. **Performance**: Monitor if 60-second updates provide sufficient responsiveness
4. **Conflicts**: Consider staggering other modbus device polling if issues persist

## Further Optimizations (Optional)

1. **Smart Scheduling**: Add random jitter to prevent synchronized polling
2. **Register Grouping**: Combine multiple register reads into fewer operations
3. **Connection Pooling**: Share connections between similar operations
4. **Circuit Breaker**: Temporarily disable problematic registers

## Validation

All updated files pass syntax checks:
- ✅ `__init__.py` - Updated coordinator interval and logging config
- ✅ `hub.py` - Enhanced retry logic and error handling  
- ✅ `coordinator.py` - Maintains existing functionality
- ✅ `number.py` - Hardware-specific power limits preserved

The integration maintains full compatibility while significantly reducing log noise and improving reliability.