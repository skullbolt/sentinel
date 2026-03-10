"""
Quick test script for auto-calibration.

Usage:
  cd ~/instagram-automation
  source venv/bin/activate
  python3 -m backend.modules.test_calibration
"""

import sys
import os
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def get_connected_devices():
    """Get list of connected ADB devices"""
    result = subprocess.run(
        ['adb', 'devices'],
        capture_output=True,
        text=True
    )
    devices = []
    for line in result.stdout.strip().split('\n')[1:]:
        if '\tdevice' in line:
            serial = line.split('\t')[0]
            devices.append(serial)
    return devices


def main():
    print("=" * 50)
    print("  Device Auto-Calibration Test")
    print("=" * 50)
    print()

    # Find connected devices
    print("1. Scanning for connected devices...")
    devices = get_connected_devices()

    if not devices:
        print("   ❌ No devices found!")
        print("   Make sure emulator is running or phone is connected")
        print("   Run: adb devices")
        sys.exit(1)

    print(f"   Found {len(devices)} device(s):")
    for d in devices:
        print(f"   → {d}")

    # Calibrate each device
    print()
    for serial in devices:
        print(f"\n2. Calibrating: {serial}")
        print("-" * 40)

        from backend.modules.device_calibrator import auto_calibrate_device
        result = auto_calibrate_device(serial)

        if result.get('success'):
            print(f"\n   ✅ CALIBRATION SUCCESSFUL!")
            print(f"   → Database ID: {result.get('device_db_id', 'N/A')}")
            print(f"\n   Full calibration data:")
            print(json.dumps(result, indent=4, default=str))
        else:
            print(f"\n   ❌ CALIBRATION FAILED!")
            print(f"   → Error: {result.get('error', 'Unknown')}")

    # Verify in database
    print(f"\n{'=' * 50}")
    print("3. Verifying database...")

    from backend.database.connection import db_manager
    from backend.database.models import Device

    session = db_manager.get_session()
    try:
        all_devices = session.query(Device).all()
        print(f"   Devices in database: {len(all_devices)}")
        for dev in all_devices:
            print(f"\n   📱 Device ID: {dev.id}")
            print(f"      Serial: {dev.serial}")
            print(f"      Name: {dev.name}")
            print(f"      Model: {dev.model}")
            print(f"      Screen: {dev.screen_width}x{dev.screen_height}")
            print(f"      Touch device: {dev.touch_device_path}")
            print(f"      Touch X range: {dev.touch_min_x}-{dev.touch_max_x}")
            print(f"      Touch Y range: {dev.touch_min_y}-{dev.touch_max_y}")
            print(f"      Pressure range: {dev.touch_min_pressure}-{dev.touch_max_pressure}")
            print(f"      Scale: X={dev.touch_scale_x}, Y={dev.touch_scale_y}")
            print(f"      Calibrated: {dev.is_calibrated}")
            print(f"      Emulator: {dev.is_emulator}")
    finally:
        session.close()

    print(f"\n{'=' * 50}")
    print("  🎉 Done!")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()