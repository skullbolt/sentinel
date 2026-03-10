"""
Debug script to find why sendevent isn't working on emulator.
Tests multiple approaches from simplest to most complex.
"""

import sys
import os
import subprocess
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

SERIAL = "emulator-5554"


def run_adb(cmd):
    """Run ADB command and show output"""
    full = f"adb -s {SERIAL} shell {cmd}"
    result = subprocess.run(full, shell=True, capture_output=True, text=True, timeout=10)
    if result.stdout.strip():
        print(f"   stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        print(f"   stderr: {result.stderr.strip()}")
    return result


def main():
    print("")
    print("=" * 60)
    print("   🔍 Touch Debug Script")
    print("=" * 60)

    # ─── TEST 1: Basic input tap (should definitely work) ────
    print("\n" + "─" * 60)
    print("TEST 1: adb shell input tap 720 1560")
    print("   This uses Android's InputManager (not sendevent)")
    print("   👆 WATCH EMULATOR — you should see a tap")
    input("   Press ENTER to send tap...")

    run_adb("input tap 720 1560")
    print("   Did you see a tap on the emulator? (yes/no)")
    test1 = input("   → ").strip().lower()

    # ─── TEST 2: input swipe (simulates tap with duration) ───
    print("\n" + "─" * 60)
    print("TEST 2: adb shell input swipe 720 1560 721 1561 100")
    print("   This simulates a tap using swipe with duration")
    print("   👆 WATCH EMULATOR")
    input("   Press ENTER to send tap...")

    run_adb("input swipe 720 1560 721 1561 100")
    print("   Did you see a tap? (yes/no)")
    test2 = input("   → ").strip().lower()

    # ─── TEST 3: Find correct touch device ───────────────────
    print("\n" + "─" * 60)
    print("TEST 3: Finding all input devices with touch capability")

    result = subprocess.run(
        f"adb -s {SERIAL} shell getevent -pl",
        shell=True, capture_output=True, text=True, timeout=10
    )

    # Parse all devices that have ABS_MT_POSITION_X
    import re
    output = result.stdout
    current_device = None
    touch_devices = []

    for line in output.split('\n'):
        device_match = re.match(r'add device \d+:\s+(/dev/input/event\d+)', line)
        if device_match:
            current_device = device_match.group(1)

        name_match = re.match(r'\s+name:\s+"(.+)"', line)
        if name_match and current_device:
            name = name_match.group(1)
            if current_device:
                pass  # just tracking

        if current_device and 'ABS_MT_POSITION_X' in line:
            touch_devices.append(current_device)

    print(f"   Found {len(touch_devices)} touch-capable devices:")
    for td in touch_devices:
        print(f"      → {td}")

    # ─── TEST 4: Try sendevent on EACH touch device ──────────
    print("\n" + "─" * 60)
    print("TEST 4: Testing sendevent on each touch device")
    print("   We'll try a simple tap using sendevent on each device")

    for device_path in touch_devices:
        print(f"\n   Testing: {device_path}")
        print("   👆 WATCH EMULATOR")
        input(f"   Press ENTER to test {device_path}...")

        # Method A: Simple sendevent sequence
        print(f"   Sending touch events to {device_path}...")

        commands = [
            # Touch down
            f"sendevent {device_path} 3 57 0",        # ABS_MT_TRACKING_ID = 0
            f"sendevent {device_path} 3 53 16383",    # ABS_MT_POSITION_X (middle of 0-32767)
            f"sendevent {device_path} 3 54 16383",    # ABS_MT_POSITION_Y (middle of 0-32767)
            f"sendevent {device_path} 3 58 200",      # ABS_MT_PRESSURE
            f"sendevent {device_path} 3 48 5",        # ABS_MT_TOUCH_MAJOR
            f"sendevent {device_path} 0 0 0",         # SYN_REPORT
        ]

        for cmd in commands:
            run_adb(cmd)

        time.sleep(0.1)

        # Touch up
        commands_up = [
            f"sendevent {device_path} 3 57 4294967295",  # ABS_MT_TRACKING_ID = -1 (as unsigned)
            f"sendevent {device_path} 0 0 0",             # SYN_REPORT
        ]

        for cmd in commands_up:
            run_adb(cmd)

        print(f"   Did you see a tap from {device_path}? (yes/no/maybe)")
        result_str = input("   → ").strip().lower()

        if result_str == "yes":
            print(f"\n   ✅ FOUND WORKING DEVICE: {device_path}")
            print(f"   Using unsigned -1 (4294967295) for tracking ID")
            break

    # ─── TEST 5: Try with BTN_TOUCH event ────────────────────
    print("\n" + "─" * 60)
    print("TEST 5: Testing with BTN_TOUCH event added")
    print("   Some emulators need BTN_TOUCH (EV_KEY code 330)")
    print("   👆 WATCH EMULATOR")

    device_path = touch_devices[0] if touch_devices else "/dev/input/event11"
    input(f"   Press ENTER to test {device_path} with BTN_TOUCH...")

    # Touch down with BTN_TOUCH
    cmds = [
        f"sendevent {device_path} 3 47 0",           # ABS_MT_SLOT = 0
        f"sendevent {device_path} 3 57 100",         # ABS_MT_TRACKING_ID
        f"sendevent {device_path} 1 330 1",          # EV_KEY BTN_TOUCH DOWN
        f"sendevent {device_path} 3 53 16383",       # X
        f"sendevent {device_path} 3 54 16383",       # Y
        f"sendevent {device_path} 3 58 200",         # Pressure
        f"sendevent {device_path} 3 48 5",           # Touch major
        f"sendevent {device_path} 0 0 0",            # SYN_REPORT
    ]

    for cmd in cmds:
        run_adb(cmd)

    time.sleep(0.15)

    # Touch up
    cmds_up = [
        f"sendevent {device_path} 3 57 4294967295",  # Tracking ID = -1
        f"sendevent {device_path} 1 330 0",           # BTN_TOUCH UP
        f"sendevent {device_path} 0 0 0",             # SYN_REPORT
    ]

    for cmd in cmds_up:
        run_adb(cmd)

    print("   Did you see a tap? (yes/no)")
    test5 = input("   → ").strip().lower()

    # ─── TEST 6: Try batch command ───────────────────────────
    print("\n" + "─" * 60)
    print("TEST 6: Testing BATCH sendevent (all in one shell call)")
    print("   👆 WATCH EMULATOR")
    input("   Press ENTER to test...")

    batch_cmd = (
        f"sendevent {device_path} 3 47 0 && "
        f"sendevent {device_path} 3 57 200 && "
        f"sendevent {device_path} 1 330 1 && "
        f"sendevent {device_path} 3 53 16383 && "
        f"sendevent {device_path} 3 54 16383 && "
        f"sendevent {device_path} 3 58 200 && "
        f"sendevent {device_path} 3 48 5 && "
        f"sendevent {device_path} 0 0 0 && "
        f"sleep 0.1 && "
        f"sendevent {device_path} 3 57 4294967295 && "
        f"sendevent {device_path} 1 330 0 && "
        f"sendevent {device_path} 0 0 0"
    )

    subprocess.run(
        f'adb -s {SERIAL} shell "{batch_cmd}"',
        shell=True, capture_output=True,
    )

    print("   Did you see a tap? (yes/no)")
    test6 = input("   → ").strip().lower()

    # ─── TEST 7: Use 'input' with touchscreen source ────────
    print("\n" + "─" * 60)
    print("TEST 7: Using 'input touchscreen tap' explicitly")
    input("   Press ENTER to test...")

    run_adb("input touchscreen tap 720 1560")

    print("   Did you see a tap? (yes/no)")
    test7 = input("   → ").strip().lower()

    # ─── SUMMARY ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("   SUMMARY")
    print("=" * 60)
    print(f"   TEST 1 (input tap):           {test1}")
    print(f"   TEST 2 (input swipe):         {test2}")
    print(f"   TEST 5 (sendevent+BTN_TOUCH): {test5}")
    print(f"   TEST 6 (batch sendevent):     {test6}")
    print(f"   TEST 7 (input touchscreen):   {test7}")
    print("")

    if test1 == "yes" and test5 != "yes" and test6 != "yes":
        print("   CONCLUSION: sendevent doesn't work on this emulator")
        print("   but 'input tap' works fine.")
        print("")
        print("   SOLUTION: Use 'input swipe' for the emulator")
        print("   (still good — has duration, better than plain 'input tap')")
        print("   Switch to sendevent when on REAL phone.")
        print("")
        print("   I'll update adb_executor.py with a DUAL MODE:")
        print("   → Emulator: uses 'input swipe' (works)")
        print("   → Real phone: uses sendevent (undetectable)")

    elif test5 == "yes" or test6 == "yes":
        print("   CONCLUSION: sendevent WORKS with BTN_TOUCH event!")
        print("   I'll update adb_executor.py to include BTN_TOUCH.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()