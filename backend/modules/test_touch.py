"""
Test the DUAL MODE touch engine.
Watch your emulator screen!

Usage:
  cd ~/Hell/sentinel
  source venv/bin/activate
  python3 backend/modules/test_touch.py
"""

import sys
import os
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    print("")
    print("=" * 55)
    print("   🖐️  Touch Engine Test (DUAL MODE)")
    print("   Watch your emulator screen!")
    print("=" * 55)

    from backend.modules.adb_executor import create_executor_from_db

    try:
        executor = create_executor_from_db("emulator-5554")
    except ValueError as e:
        print(f"   ❌ {e}")
        return

    print(f"\n   Device: {executor.serial}")
    print(f"   Screen: {executor.config.screen_width}x{executor.config.screen_height}")
    print(f"   Mode: {executor.mode.value}")
    print(f"   Emulator: {executor.config.is_emulator}")

    w = executor.config.screen_width
    h = executor.config.screen_height
    cx = w // 2
    cy = h // 2

    # ── Test 1: Wake screen ──
    print("\n── TEST 1: Wake screen ──")
    executor.wake_screen()
    time.sleep(1)
    print("   ✅ Done")

    # ── Test 2: Single tap center ──
    print("\n── TEST 2: Single tap (center) ──")
    print("   👆 Watch emulator!")
    time.sleep(1)
    executor.tap(cx, cy)
    print("   ✅ Tap sent")
    time.sleep(2)

    # ── Test 3: Multiple taps ──
    print("\n── TEST 3: Multiple taps (5 locations) ──")
    taps = [
        (w // 4, h // 4, "top-left"),
        (3 * w // 4, h // 4, "top-right"),
        (cx, cy, "center"),
        (w // 4, 3 * h // 4, "bottom-left"),
        (3 * w // 4, 3 * h // 4, "bottom-right"),
    ]
    for x, y, label in taps:
        print(f"   → {label} ({x}, {y})")
        executor.tap(x, y)
        time.sleep(1.5)
    print("   ✅ All taps sent")
    time.sleep(1)

    # ── Test 4: Scroll up ──
    print("\n── TEST 4: Scroll UP ──")
    executor.scroll_up()
    print("   ✅ Scrolled up")
    time.sleep(2)

    # ── Test 5: Scroll down ──
    print("\n── TEST 5: Scroll DOWN ──")
    executor.scroll_down()
    print("   ✅ Scrolled down")
    time.sleep(2)

    # ── Test 6: Swipe left to right ──
    print("\n── TEST 6: Swipe (left → right) ──")
    executor.swipe(w // 4, cy, 3 * w // 4, cy, 400)
    print("   ✅ Swiped")
    time.sleep(2)

    # ── Test 7: Double tap ──
    print("\n── TEST 7: Double tap (center) ──")
    executor.double_tap(cx, cy)
    print("   ✅ Double tap sent")
    time.sleep(2)

    # ── Test 8: Long press ──
    print("\n── TEST 8: Long press (center, ~1 second) ──")
    executor.long_press(cx, cy, hold_ms=1000)
    print("   ✅ Long press sent")
    time.sleep(2)

    # ── Test 9: Press back ──
    print("\n── TEST 9: Back button ──")
    executor.press_back()
    print("   ✅ Back pressed")
    time.sleep(1)

    # ── Test 10: Press home ──
    print("\n── TEST 10: Home button ──")
    executor.press_home()
    print("   ✅ Home pressed")
    time.sleep(1)

    # ── Test 11: Open Instagram ──
    print("\n── TEST 11: Open Instagram ──")
    executor.open_app("com.instagram.android")
    time.sleep(4)
    current = executor.get_current_app()
    if "instagram" in current.lower():
        print("   ✅ Instagram opened!")

        # Scroll through feed
        print("\n── TEST 12: Scroll Instagram feed (3 times) ──")
        for i in range(3):
            print(f"   → Scroll {i + 1}/3")
            executor.scroll_up()
            time.sleep(random.uniform(2.0, 4.0))
        print("   ✅ Feed scrolled!")

        # Double tap to like (center of post area)
        print("\n── TEST 13: Double tap to like a post ──")
        post_center_y = int(h * 0.4)
        executor.double_tap(cx, post_center_y)
        print("   ✅ Double tap sent (may have liked a post!)")
        time.sleep(2)

    else:
        print(f"   ⚠️  Instagram not found. Got: {current}")

    # Close Instagram
    print("\n── TEST 14: Close Instagram ──")
    executor.close_app("com.instagram.android")
    print("   ✅ Closed")
    time.sleep(1)

    # ── Test 15: Type text ──
    print("\n── TEST 15: Open Chrome and type text ──")
    executor.open_app("com.android.chrome")
    time.sleep(3)

    # Tap on URL bar (approximate position)
    url_bar_y = int(h * 0.05)
    executor.tap(cx, url_bar_y, element_width=w, element_height=80)
    time.sleep(2)

    print("   Typing 'hello world'...")
    executor.type_text("hello world", human_like=True)
    print("   ✅ Text typed!")
    time.sleep(2)

    executor.close_app("com.android.chrome")

    # ── Test 16: Screenshot ──
    print("\n── TEST 16: Take screenshot ──")
    screenshot_path = os.path.join(
        os.path.dirname(__file__), "..", "screenshots", "test_dual_mode.png"
    )
    img = executor.take_screenshot(screenshot_path)
    if img:
        print(f"   ✅ Screenshot saved ({len(img)} bytes)")
        print(f"   Path: {screenshot_path}")
    else:
        print("   ❌ Screenshot failed")

    # Done
    print(f"\n{'=' * 55}")
    print(f"   🎉 ALL TESTS COMPLETE!")
    print(f"")
    print(f"   Mode used: {executor.mode.value}")
    print(f"")
    if executor.mode.value == "input_swipe":
        print(f"   Using 'input swipe' mode (emulator)")
        print(f"   On real phone, will auto-switch to")
        print(f"   sendevent mode (kernel-level, undetectable)")
    else:
        print(f"   Using sendevent mode (kernel-level)")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()