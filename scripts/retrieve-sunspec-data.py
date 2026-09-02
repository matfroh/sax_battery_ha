#!/usr/bin/env python3
"""Retrieve SunSpec data from a device over Modbus TCP."""
from sunspec2.modbus import client

DEFAULT_IPADDR = "192.168.178.90"
DEFAULT_IPPORT = "502"
DEFAULT_SLAVE_ID = "40"


def prompt_with_default(prompt_text: str, default_value: str) -> str:
    """Ask the user for a value, falling back to a default if they just hit Enter."""
    user_input = input(f"{prompt_text} [{default_value}]: ").strip()
    return user_input or default_value

def trace_logger(msg: str) -> None:
    """Log Modbus trace messages to the console."""
    print(f"[MODBUS TRACE] {msg}") # noqa: T201

def main() -> None:
    """Get models and data from Sunspec device."""
    ipaddr = prompt_with_default("Enter IP address", DEFAULT_IPADDR)
    ipport = prompt_with_default("Enter IP port", DEFAULT_IPPORT)
    slave_id = prompt_with_default("Enter slave ID", DEFAULT_SLAVE_ID)

    # cast numeric inputs (input() always returns str)
    try:
        ipport_value : int = int(ipport)
        slave_id_value: int = int(slave_id)
    except ValueError:
        print("Invalid port or slave ID, must be an integer.") # noqa: T201
        return

    # create a SunSpec client instance
    device = client.SunSpecModbusClientDeviceTCP(
        slave_id=slave_id_value, ipaddr=ipaddr, ipport=ipport_value, timeout=5, trace_func=trace_logger
    )

    #try:
    # device.connect()
    # device model discovery process
    device.scan()
    #except Exception as e: #noqa: BLE001
    #    print(f"Connection/scan failed: {e}") # noqa: T201
#        return

    # Determine which models are present in the device
    for model_id, model in device.models.items():
        print(model_id, model) # noqa: T201
    # read device common model data
    # device.common[0].read()
    # print(f"Manufacturer: {device.common.Mn}") # noqa: T201
    device.close()

if __name__ == "__main__":
    main()
