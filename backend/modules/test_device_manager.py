"""
Test the Device Manager.

Usage:
  cd ~/Hell/sentinel
  source venv/bin/activate
  python3 backend/modules/test_device_manager.py
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    print("")
    print("=" * 55)
    print("   📱 Device Manager Test")
    print("=" * 55)

    from backend.modules.device_manager import DeviceManager

    # Create manager
    manager = DeviceManager()

    # ── Test 1: Scan for devices ──
    print("\n── TEST 1: Scan for devices ──")
    devices = manager.scan()
    print(f"   Found {len(devices)} device(s)")

    if not devices:
        print("   ❌ No devices found. Is emulator running?")
        return

    # ── Test 2: Print status ──
    print("\n── TEST 2: Device status ──")
    manager.print_status()

    # ── Test 3: Get device info ──
    print("\n── TEST 3: Device info ──")
    for serial in devices:
        info = manager.get_device_info(serial)
        if info:
            print(f"\n   📱 {serial}:")
            print(f"      DB ID: {info['db_id']}")
            print(f"      Screen: {info['screen']}")
            print(f"      Emulator: {info['is_emulator']}")
            print(f"      Touch mode: {info['touch_mode']}")
            print(f"      Total clones: {info['total_clones']}")
            print(f"      Clone packages:")
            for pkg in info['clone_packages']:
                marker = "⭐" if pkg == "com.instagram.android" else "  "
                print(f"         {marker} {pkg}")

    # ── Test 4: Get executor and test ──
    print("\n── TEST 4: Get executor and test tap ──")
    first_serial = list(devices.keys())[0]
    executor = manager.get_executor(first_serial)

    if executor:
        print(f"   ✅ Got executor for {first_serial}")
        print(f"   Mode: {executor.mode.value}")
        print("   Sending test tap to center of screen...")
        cx = executor.config.screen_width // 2
        cy = executor.config.screen_height // 2
        executor.tap(cx, cy)
        print("   ✅ Tap sent! Check emulator.")
    else:
        print(f"   ❌ No executor for {first_serial}")

    # ── Test 5: Health check ──
    print("\n── TEST 5: Health check ──")
    for serial in devices:
        health = manager.check_device_health(serial)
        print(f"\n   📊 {serial}:")
        print(f"      ADB connected: {health['adb_connected']}")
        print(f"      Screen on: {health['screen_on']}")
        print(f"      Battery: {health['battery_level']}%")
        print(f"      Free storage: {health['storage_free_mb']}MB")
        print(f"      Current app: {health['current_app']}")

    # ── Test 6: Summary ──
    print("\n── TEST 6: Full summary (JSON) ──")
    summary = manager.get_summary()
    print(json.dumps(summary, indent=4, default=str))

    # ── Test 7: Verify database ──
    print("\n── TEST 7: Verify database ──")
    from backend.database.connection import db_manager
    from backend.database.models import Device, Clone

    session = db_manager.get_session()
    try:
        db_devices = session.query(Device).all()
        print(f"   Devices in DB: {len(db_devices)}")

        for dev in db_devices:
            clones = session.query(Clone).filter_by(device_id=dev.id).all()
            print(f"\n   📱 Device: {dev.serial} (ID: {dev.id})")
            print(f"      Status: {dev.status}")
            print(f"      Calibrated: {dev.is_calibrated}")
            print(f"      Clones in DB: {len(clones)}")

            for clone in clones:
                account_info = f"→ account #{clone.account_id}" if clone.account_id else "empty"
                original = " ⭐ ORIGINAL" if clone.is_original else ""
                print(f"      [{clone.clone_index}] {clone.package_name} ({clone.status.value}) {account_info}{original}")

    finally:
        session.close()

    # Done
    print(f"\n{'=' * 55}")
    print("   🎉 Device Manager Test Complete!")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()