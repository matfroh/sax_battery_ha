# SAX Battery Home Assistant Component - pymodbus 3.9.2 Upgrade

## Summary of Changes

This document outlines the changes made to upgrade the SAX Battery Home Assistant component from pymodbus 3.7.4 to 3.9.2 compatibility, following the coordinator pattern from the solaredge-modbus-multi reference implementation.

## Key Architectural Changes

### 1. DataUpdateCoordinator Pattern
- **Added**: `coordinator.py` - Implements `SAXBatteryCoordinator` using Home Assistant's `DataUpdateCoordinator` pattern
- **Purpose**: Centralized data management with automatic refresh intervals and error handling
- **Benefits**: Better performance, reduced Modbus traffic, and consistent data across all entities

### 2. Async Modbus Hub
- **Added**: `hub.py` - New `SAXBatteryHub` class using `AsyncModbusTcpClient`
- **Key Features**:
  - AsyncModbusTcpClient for non-blocking operations
  - Parameter compatibility checking for pymodbus versions (slave vs device_id)
  - Proper connection management with locks
  - Enhanced error handling with specific exceptions

### 3. Updated Integration Setup
- **Modified**: `__init__.py` - Simplified to use coordinator pattern
- **Removed**: Old `SAXBatteryData` class and direct ModbusTcpClient usage
- **Added**: Hub initialization and coordinator setup

### 4. Entity Updates
- **Modified**: `sensor.py` - Sensors now inherit from `CoordinatorEntity`
- **Removed**: `should_poll=True` polling mechanism
- **Added**: Automatic updates through coordinator
- **Updated**: `switch.py` and `number.py` to use coordinator reference

## Technical Implementation Details

### pymodbus 3.9.2 Compatibility Features

1. **Parameter Compatibility Checking**:
   ```python
   sig = inspect.signature(self._client.read_holding_registers)
   if "device_id" in sig.parameters:
       # pymodbus 3.9.2+ uses device_id
       result = await self._client.read_holding_registers(
           address=address, count=count, device_id=slave
       )
   elif "slave" in sig.parameters:
       # older pymodbus uses slave
       result = await self._client.read_holding_registers(
           address=address, count=count, slave=slave
       )
   ```

2. **Async Client Management**:
   ```python
   self._client = AsyncModbusTcpClient(
       host=self._host,
       port=self._port,
       timeout=10,
       retry_on_empty=True,
   )
   ```

3. **Enhanced Error Handling**:
   ```python
   try:
       # Modbus operations
   except (ConnectionException, ModbusIOException) as e:
       self._connected = False
       raise HubConnectionError(f"Modbus communication error: {e}") from e
   ```

### Coordinator Pattern Implementation

1. **Data Update Coordinator**:
   ```python
   class SAXBatteryCoordinator(DataUpdateCoordinator):
       def __init__(self, hass: HomeAssistant, hub: SAXBatteryHub, scan_interval: int):
           super().__init__(
               hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=scan_interval)
           )
           self._hub = hub
   ```

2. **Entity Integration**:
   ```python
   class SAXBatterySensor(CoordinatorEntity, SensorEntity):
       def __init__(self, coordinator: SAXBatteryCoordinator, data_key: str):
           super().__init__(coordinator)
           # Entity implementation
   ```

## Files Modified/Created

### New Files:
1. **`coordinator.py`** - DataUpdateCoordinator implementation
2. **`hub.py`** - AsyncModbusTcpClient hub with pymodbus 3.9.2 compatibility

### Modified Files:
1. **`__init__.py`** - Simplified integration setup using coordinator
2. **`sensor.py`** - Updated to use CoordinatorEntity pattern
3. **`switch.py`** - Updated entity setup to use coordinator
4. **`number.py`** - Updated entity setup to use coordinator
5. **`requirements.txt`** - Already specified pymodbus==3.9.2

## Configuration Compatibility

The configuration remains the same - users don't need to reconfigure their existing setups. The component maintains backward compatibility with existing config entries while using the new architecture internally.

## Benefits of the Upgrade

1. **Performance**: Async operations prevent blocking the Home Assistant event loop
2. **Reliability**: Better error handling and connection management
3. **Efficiency**: Centralized data updates reduce Modbus traffic
4. **Maintainability**: Modern Home Assistant patterns make the code easier to maintain
5. **Future-proof**: Compatible with latest pymodbus releases

## Migration Path

Users can upgrade by:
1. Stopping Home Assistant
2. Replacing the component files
3. Restarting Home Assistant

The component will automatically use the new architecture without requiring configuration changes.

## Testing Recommendations

1. Verify connection establishment with SAX Battery system
2. Test data reading for all sensor types
3. Validate switch operations (if applicable)
4. Monitor logs for any connection or data update errors
5. Check entity availability and data freshness in Home Assistant

## Error Handling

The new implementation includes comprehensive error handling:
- Connection failures are logged and entities marked unavailable
- Modbus communication errors trigger reconnection attempts
- Individual sensor failures don't affect other sensors
- Coordinator retry logic handles temporary network issues

This upgrade provides a solid foundation for reliable SAX Battery integration with modern Home Assistant and pymodbus versions.
