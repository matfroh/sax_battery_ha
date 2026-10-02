#!/usr/bin/env python3
"""Verify expected SunSpec models and selected values over Modbus TCP.

sax-power supported models:
model 1: common (All SunSpec compliant devices must include this as the first model)
model 103: inverter_three_phase (Inverter Three Phase)
model 123: controls (Specific device controls)
model 203: ac_meter_abcn (Wye-connect three phase meter)
model 802: battery (Battery Base Model)

documentation: https://github.com/sunspec/pysunspec2#full-example-of-a-device-interaction
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from typing import Any

# Import sunspec2 to find its installation path
import sunspec2
from sunspec2.modbus import client

# Modbus Connection Defaults from SAX Power Documentation
DEFAULT_IPADDR = "192.168.178.90"
DEFAULT_IPPORT = 502
DEFAULT_SLAVE_ID = 100


# Dynamically resolve the absolute subfolder relative to this file
SCRIPT_DIR = Path(__file__).resolve().parent
# Folder containing custom JSON configurations
FOLDER_PATH = SCRIPT_DIR / "sax_models"


def deploy_custom_models(src_folder: Path) -> None:
    """Locate the active sunspec2 package and inject custom SAX models into its internal JSON directory."""
    if not os.path.exists(src_folder):  # noqa:  PTH110
        print(f"Error: Model directory '{src_folder}' not found.", file=sys.stderr)  # noqa: T201
        sys.exit(2)

    # Find where sunspec2 is installed in the current environment
    sunspec_base_dir = os.path.dirname(sunspec2.__file__)  # noqa: PTH120
    target_json_dir = os.path.join(sunspec_base_dir, "models", "json")  # noqa: PTH118

    if not os.path.exists(target_json_dir):  # noqa: PTH110
        print(  # noqa: T201
            f"Error: Target sunspec2 JSON path not found at {target_json_dir}",
            file=sys.stderr,
        )
        sys.exit(2)

    # Copy files across
    for file_name in os.listdir(src_folder):  # noqa: PTH208
        if file_name.endswith(".json"):
            src_file = os.path.join(src_folder, file_name)  # noqa: PTH118
            dest_file = os.path.join(target_json_dir, file_name)  # noqa: PTH118
            try:
                # Copy file to package site-packages directory
                shutil.copy2(src_file, dest_file)
            except Exception as e:  # noqa: BLE001
                print(  # noqa: T201
                    f"Failed to deploy model file {file_name} to runtime: {e}",
                    file=sys.stderr,
                )
                sys.exit(2)


def prompt_with_default(prompt_text: str, default_value: str) -> str:
    """Prompt the user for input, providing a default value if no input is given."""
    user_input = input(f"{prompt_text} [{default_value}]: ").strip()
    return user_input or default_value


def trace_logger(message: str) -> None:
    """Log a Modbus trace message."""
    print(f"[MODBUS TRACE] {message}")  # noqa: T201


def verify_model(
    device_obj: Any, attribute_name: str, model_id: int, fields: list[str]
) -> None:
    """Read the first instance of an expected model and print selected fields."""
    models = getattr(device_obj, attribute_name, None)
    if not models:
        raise RuntimeError(
            f"Required SunSpec model {model_id} ({attribute_name}) is missing."
        )

    model = models[0]
    model.read()

    print(f"Model {model_id} ({attribute_name}) verified:")  # noqa: T201
    for field in fields:
        # Check computed values (.cvalue) so scale factors are handled automatically
        point = getattr(model, field, None)
        if point is not None:
            print(f"  {field}: {point.cvalue} {getattr(point, 'units', '')}")  # noqa: T201
        else:
            print(f"  {field}: <field unavailable>")  # noqa: T201


def main() -> int:
    """Main entry point for the script.

    Prompts the user for connection details, connects to the SunSpec device over Modbus TCP,
    verifies the presence of required models, and prints selected fields.

    Returns:
        int: Exit code (0 for success, 1 for verification failure, 2 for input errors).
    """
    # Deploy files directly into the active package environment
    deploy_custom_models(FOLDER_PATH)

    ipaddr = prompt_with_default("Enter IP address", DEFAULT_IPADDR)

    try:
        ipport = int(prompt_with_default("Enter IP port", str(DEFAULT_IPPORT)))
        slave_id = int(prompt_with_default("Enter slave ID", str(DEFAULT_SLAVE_ID)))
    except ValueError:
        print("Port and slave ID must be integers.", file=sys.stderr)  # noqa: T201
        return 2

    if not 1 <= ipport <= 65535:
        print("Port must be between 1 and 65535.", file=sys.stderr)  # noqa: T201
        return 2

    if not 0 <= slave_id <= 247:
        print("Slave ID must be between 0 and 247.", file=sys.stderr)  # noqa: T201
        return 2

    device_obj = client.SunSpecModbusClientDeviceTCP(
        slave_id=slave_id,
        ipaddr=ipaddr,
        ipport=ipport,
        timeout=5,
        trace_func=trace_logger,
    )

    try:
        device_obj.connect()
        device_obj.scan()

        print("\nDiscovered models:")  # noqa: T201
        for model_id, model in device_obj.models.items():
            print(f"  {model_id}: {model}")  # noqa: T201

        print("\n--- Verifying Data Points ---")  # noqa: T201
        # Fixed point fields to match the exact point IDs within your custom files!
        verify_model(device_obj, "common", 1, ["Mn", "Md", "Vr_Master", "Vr_Gateway"])
        verify_model(device_obj, "inverter", 103, ["W", "Hz", "St"])
        verify_model(device_obj, "controls", 123, ["Mode", "Conn_Win_Pct"])
        verify_model(device_obj, "meter", 203, ["W", "A", "Hz"])
        verify_model(device_obj, "battery", 802, ["SoC", "W_Max_Rtg", "St"])

        print("\nSunSpec firmware verification passed.")  # noqa: T201
        return 0  # noqa: TRY300
    except Exception as error:  # noqa: BLE001
        print(f"\nSunSpec firmware verification failed: {error}", file=sys.stderr)  # noqa: T201
        return 1
    finally:
        device_obj.close()


if __name__ == "__main__":
    raise SystemExit(main())
