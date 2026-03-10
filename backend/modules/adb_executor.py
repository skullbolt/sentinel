"""
ADB Executor Module — DUAL MODE
================================
Mode 1: INPUT_SWIPE — uses 'adb shell input swipe' 
        Works on ALL devices including emulators.
        Has duration control and coordinate humanization.

Mode 2: SENDEVENT — uses raw kernel-level touch events
        Works on real phones with proper permissions.
        Full pressure curves, touch major, micro-drift.
        Undetectable by apps.

The executor auto-detects which mode to use,
or you can force a specific mode.
"""

from __future__ import annotations

import subprocess
import re
import time
import random
import math
from enum import Enum
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from backend.modules.humanizer import Humanizer, TouchSequence, TouchPoint


class TouchMode(str, Enum):
    INPUT_SWIPE = "input_swipe"    # Works everywhere
    SENDEVENT = "sendevent"        # Kernel level, needs permissions
    AUTO = "auto"                  # Auto-detect best mode


@dataclass
class DeviceConfig:
    """Calibration data for a specific device"""
    serial: str
    screen_width: int
    screen_height: int
    touch_device_path: str
    touch_max_x: int
    touch_max_y: int
    touch_min_x: int = 0
    touch_min_y: int = 0
    touch_max_pressure: int = 1024
    touch_min_pressure: int = 0
    touch_max_touch_major: int = 10
    scale_x: float = 1.0
    scale_y: float = 1.0
    event_code_x: int = 0x35
    event_code_y: int = 0x36
    event_code_pressure: int = 0x3a
    event_code_tracking: int = 0x39
    event_code_touch_major: int = 0x30
    event_code_slot: int = 0x2f
    is_emulator: bool = False

    @classmethod
    def from_database(cls, device_row) -> DeviceConfig:
        """Create config from a Device database row"""
        return cls(
            serial=device_row.serial,
            screen_width=device_row.screen_width or 1080,
            screen_height=device_row.screen_height or 2400,
            touch_device_path=device_row.touch_device_path or "/dev/input/event2",
            touch_max_x=device_row.touch_max_x or 32767,
            touch_max_y=device_row.touch_max_y or 32767,
            touch_min_x=device_row.touch_min_x or 0,
            touch_min_y=device_row.touch_min_y or 0,
            touch_max_pressure=device_row.touch_max_pressure or 1024,
            touch_min_pressure=device_row.touch_min_pressure or 0,
            touch_max_touch_major=device_row.touch_max_touch_major or 10,
            scale_x=device_row.touch_scale_x or 1.0,
            scale_y=device_row.touch_scale_y or 1.0,
            event_code_x=device_row.touch_event_code_x or 0x35,
            event_code_y=device_row.touch_event_code_y or 0x36,
            event_code_pressure=device_row.touch_event_code_pressure or 0x3a,
            event_code_tracking=device_row.touch_event_code_tracking or 0x39,
            event_code_touch_major=device_row.touch_event_code_touch_major or 0x30,
            event_code_slot=device_row.touch_event_code_slot or 0x2f,
            is_emulator=device_row.is_emulator or False,
        )


class ADBExecutor:
    """
    Sends human-like touch events to Android device via ADB.
    
    DUAL MODE:
      - input_swipe: for emulators and devices without root
      - sendevent: for real phones (kernel-level, undetectable)
    """

    EV_SYN = 0x00
    EV_KEY = 0x01
    EV_ABS = 0x03
    SYN_REPORT = 0x00
    BTN_TOUCH = 330

    def __init__(self, config: DeviceConfig, mode: TouchMode = TouchMode.AUTO):
        self.config = config
        self.serial = config.serial
        self.dev = config.touch_device_path
        self.humanizer = Humanizer(
            pressure_max=config.touch_max_pressure,
            touch_major_max=config.touch_max_touch_major,
        )
        self._tracking_id = 0

        # Determine touch mode
        if mode == TouchMode.AUTO:
            self.mode = self._detect_mode()
        else:
            self.mode = mode

    def _detect_mode(self) -> TouchMode:
        """Auto-detect whether sendevent works on this device"""
        if self.config.is_emulator:
            return TouchMode.INPUT_SWIPE

        # Try sendevent — check if permission denied
        result = subprocess.run(
            f'adb -s {self.serial} shell "sendevent {self.dev} 0 0 0"',
            shell=True, capture_output=True, text=True, timeout=5,
        )

        if "permission denied" in result.stderr.lower():
            return TouchMode.INPUT_SWIPE
        else:
            return TouchMode.SENDEVENT

    # ══════════════════════════════════════════════
    #   INPUT_SWIPE MODE
    #   Uses: adb shell input swipe x1 y1 x2 y2 duration
    #   Works on: ALL devices
    # ══════════════════════════════════════════════

    def _input_tap(self, x: int, y: int, duration_ms: int = 80):
        """
        Tap using 'input swipe' with a tiny movement and duration.
        
        'input swipe x1 y1 x2 y2 duration' with nearly same
        start and end point = tap with duration.
        This is MUCH better than 'input tap' which has 0ms duration.
        """
        # Slight offset for end point (1-2 pixels, like a real finger)
        end_x = x + random.randint(-2, 2)
        end_y = y + random.randint(-2, 2)

        subprocess.run(
            f'adb -s {self.serial} shell input swipe {x} {y} {end_x} {end_y} {duration_ms}',
            shell=True, capture_output=True,
        )

    def _input_swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """Swipe using 'input swipe' command."""
        subprocess.run(
            f'adb -s {self.serial} shell input swipe {x1} {y1} {x2} {y2} {duration_ms}',
            shell=True, capture_output=True,
        )

    # ══════════════════════════════════════════════
    #   SENDEVENT MODE
    #   Uses: raw kernel-level touch events
    #   Works on: real phones with ADB permission
    # ══════════════════════════════════════════════

    def pixel_to_touch(self, pixel_x: int, pixel_y: int) -> Tuple[int, int]:
        """Convert screen pixel coordinates to touch device coordinates."""
        touch_x = int(pixel_x * self.config.scale_x)
        touch_y = int(pixel_y * self.config.scale_y)
        touch_x = max(self.config.touch_min_x, min(self.config.touch_max_x, touch_x))
        touch_y = max(self.config.touch_min_y, min(self.config.touch_max_y, touch_y))
        return touch_x, touch_y

    def _sendevent_batch(self, events: List[Tuple[int, int, int]]):
        """Send multiple sendevent commands in one ADB shell session."""
        if not events:
            return
        commands = []
        for event_type, code, value in events:
            commands.append(f"sendevent {self.dev} {event_type} {code} {value}")
        full_cmd = " && ".join(commands)
        subprocess.run(
            f'adb -s {self.serial} shell "{full_cmd}"',
            shell=True, capture_output=True,
        )

    def _next_tracking_id(self) -> int:
        """Get next tracking ID for a new touch"""
        self._tracking_id = (self._tracking_id + 1) % 65535
        return self._tracking_id

    def _touch_down_sendevent(self, touch_x: int, touch_y: int, pressure: int, touch_major: int):
        """Send finger-down events via sendevent"""
        tracking_id = self._next_tracking_id()
        events = [
            (self.EV_ABS, self.config.event_code_slot, 0),
            (self.EV_ABS, self.config.event_code_tracking, tracking_id),
            (self.EV_KEY, self.BTN_TOUCH, 1),
            (self.EV_ABS, self.config.event_code_x, touch_x),
            (self.EV_ABS, self.config.event_code_y, touch_y),
            (self.EV_ABS, self.config.event_code_pressure, pressure),
        ]
        if self.config.touch_max_touch_major > 0:
            events.append((self.EV_ABS, self.config.event_code_touch_major, touch_major))
        events.append((self.EV_SYN, self.SYN_REPORT, 0))
        self._sendevent_batch(events)

    def _touch_move_sendevent(self, touch_x: int, touch_y: int, pressure: int, touch_major: int):
        """Send finger-move events via sendevent"""
        events = [
            (self.EV_ABS, self.config.event_code_x, touch_x),
            (self.EV_ABS, self.config.event_code_y, touch_y),
            (self.EV_ABS, self.config.event_code_pressure, pressure),
        ]
        if self.config.touch_max_touch_major > 0:
            events.append((self.EV_ABS, self.config.event_code_touch_major, touch_major))
        events.append((self.EV_SYN, self.SYN_REPORT, 0))
        self._sendevent_batch(events)

    def _touch_up_sendevent(self):
        """Send finger-up events via sendevent"""
        events = [
            (self.EV_ABS, self.config.event_code_tracking, 4294967295),  # -1 unsigned
            (self.EV_KEY, self.BTN_TOUCH, 0),
            (self.EV_SYN, self.SYN_REPORT, 0),
        ]
        self._sendevent_batch(events)

    def _execute_sequence_sendevent(self, sequence: TouchSequence):
        """Execute a touch sequence using sendevent"""
        if not sequence.points:
            return

        points = sequence.points
        first = points[0]
        tx, ty = self.pixel_to_touch(first.x, first.y)
        self._touch_down_sendevent(tx, ty, first.pressure, first.touch_major)

        for i in range(1, len(points)):
            point = points[i]
            dt = (points[i].timestamp_ms - points[i - 1].timestamp_ms) / 1000.0
            if dt > 0:
                time.sleep(dt)
            tx, ty = self.pixel_to_touch(point.x, point.y)
            self._touch_move_sendevent(tx, ty, point.pressure, point.touch_major)

        self._touch_up_sendevent()

    # ══════════════════════════════════════════════
    #   PUBLIC API: TAP
    # ══════════════════════════════════════════════

    def tap(
        self,
        x: int,
        y: int,
        element_width: int = 100,
        element_height: int = 60,
    ):
        """
        Perform a human-like tap at pixel coordinates (x, y).
        Automatically uses the correct mode.
        """
        if self.mode == TouchMode.SENDEVENT:
            sequence = self.humanizer.generate_tap(x, y, element_width, element_height)
            self._execute_sequence_sendevent(sequence)
        else:
            # INPUT_SWIPE mode
            hx, hy = self.humanizer.humanize_coordinates(x, y, element_width, element_height)
            duration = random.randint(50, 130)
            self._input_tap(hx, hy, duration)

    def double_tap(
        self,
        x: int,
        y: int,
        element_width: int = 200,
        element_height: int = 200,
    ):
        """Perform a human-like double tap."""
        if self.mode == TouchMode.SENDEVENT:
            tap1, tap2 = self.humanizer.generate_double_tap(x, y, element_width, element_height)
            self._execute_sequence_sendevent(tap1)
            gap = self.humanizer.get_action_delay("double_tap_gap")
            time.sleep(gap)
            self._execute_sequence_sendevent(tap2)
        else:
            # INPUT_SWIPE mode
            hx1, hy1 = self.humanizer.humanize_coordinates(x, y, element_width, element_height)
            duration1 = random.randint(40, 90)
            self._input_tap(hx1, hy1, duration1)

            gap = random.uniform(0.08, 0.2)
            time.sleep(gap)

            hx2, hy2 = self.humanizer.humanize_coordinates(
                x + random.randint(-5, 5),
                y + random.randint(-5, 5),
                element_width, element_height
            )
            duration2 = random.randint(40, 90)
            self._input_tap(hx2, hy2, duration2)

    def long_press(
        self,
        x: int,
        y: int,
        hold_ms: float = 800,
        element_width: int = 100,
        element_height: int = 60,
    ):
        """Perform a human-like long press."""
        if self.mode == TouchMode.SENDEVENT:
            sequence = self.humanizer.generate_long_press(
                x, y, hold_ms, element_width, element_height
            )
            self._execute_sequence_sendevent(sequence)
        else:
            # INPUT_SWIPE mode — swipe from point to nearly same point with long duration
            hx, hy = self.humanizer.humanize_coordinates(x, y, element_width, element_height)
            end_x = hx + random.randint(-3, 3)
            end_y = hy + random.randint(-3, 3)
            hold = int(hold_ms + random.uniform(-100, 200))
            self._input_swipe(hx, hy, end_x, end_y, hold)

    # ══════════════════════════════════════════════
    #   PUBLIC API: SWIPE / SCROLL
    # ══════════════════════════════════════════════

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: float = None,
    ):
        """Perform a human-like swipe."""
        if self.mode == TouchMode.SENDEVENT:
            sequence = self.humanizer.generate_swipe(
                start_x, start_y, end_x, end_y, duration_ms
            )
            self._execute_sequence_sendevent(sequence)
        else:
            # INPUT_SWIPE mode with humanization
            # Add slight randomness to start/end
            sx = start_x + random.randint(-5, 5)
            sy = start_y + random.randint(-5, 5)
            ex = end_x + random.randint(-5, 5)
            ey = end_y + random.randint(-5, 5)

            if duration_ms is None:
                distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
                duration_ms = max(200, min(800, distance * 0.5 + random.uniform(-50, 100)))

            self._input_swipe(sx, sy, ex, ey, int(duration_ms))

    def scroll_up(self):
        """Scroll content up (finger swipes upward)."""
        if self.mode == TouchMode.SENDEVENT:
            sequence = self.humanizer.generate_scroll(
                self.config.screen_width, self.config.screen_height, "up"
            )
            self._execute_sequence_sendevent(sequence)
        else:
            w = self.config.screen_width
            h = self.config.screen_height
            sx = w // 2 + random.randint(-80, 80)
            sy = random.randint(int(h * 0.55), int(h * 0.75))
            ex = sx + random.randint(-20, 20)
            ey = random.randint(int(h * 0.2), int(h * 0.35))
            duration = random.randint(250, 600)
            self._input_swipe(sx, sy, ex, ey, duration)

    def scroll_down(self):
        """Scroll content down (finger swipes downward)."""
        if self.mode == TouchMode.SENDEVENT:
            sequence = self.humanizer.generate_scroll(
                self.config.screen_width, self.config.screen_height, "down"
            )
            self._execute_sequence_sendevent(sequence)
        else:
            w = self.config.screen_width
            h = self.config.screen_height
            sx = w // 2 + random.randint(-80, 80)
            sy = random.randint(int(h * 0.25), int(h * 0.4))
            ex = sx + random.randint(-20, 20)
            ey = random.randint(int(h * 0.65), int(h * 0.8))
            duration = random.randint(250, 600)
            self._input_swipe(sx, sy, ex, ey, duration)

    # ══════════════════════════════════════════════
    #   PUBLIC API: TEXT INPUT
    # ══════════════════════════════════════════════

    def type_text(self, text: str, human_like: bool = True):
        """Type text on the device."""
        if not text:
            return
        if human_like:
            for char in text:
                escaped = self._escape_for_adb(char)
                if escaped:
                    subprocess.run(
                        f'adb -s {self.serial} shell input text "{escaped}"',
                        shell=True, capture_output=True,
                    )
                    delay = self.humanizer.get_typing_delay()
                    time.sleep(delay)
        else:
            escaped = self._escape_for_adb(text)
            subprocess.run(
                f'adb -s {self.serial} shell input text "{escaped}"',
                shell=True, capture_output=True,
            )

    def _escape_for_adb(self, text: str) -> str:
        """Escape special characters for ADB shell"""
        special = ['\\', '"', "'", '`', '$', '!', '&', '|', ';',
                   '(', ')', '<', '>', '{', '}', '[', ']', ' ',
                   '#', '~', '?', '*']
        result = []
        for char in text:
            if char in special:
                result.append(f'\\{char}')
            elif char == '\n':
                continue
            else:
                result.append(char)
        return ''.join(result)

    def clear_text_field(self, max_chars: int = 50):
        """Clear a text field by selecting all and deleting."""
        subprocess.run(
            f'adb -s {self.serial} shell input keyevent KEYCODE_MOVE_HOME',
            shell=True, capture_output=True,
        )
        time.sleep(0.1)
        subprocess.run(
            f'adb -s {self.serial} shell input keyevent --longpress KEYCODE_MOVE_END',
            shell=True, capture_output=True,
        )
        time.sleep(0.1)
        subprocess.run(
            f'adb -s {self.serial} shell input keyevent KEYCODE_DEL',
            shell=True, capture_output=True,
        )
        time.sleep(0.2)

    # ══════════════════════════════════════════════
    #   PUBLIC API: KEY EVENTS
    # ══════════════════════════════════════════════

    def press_back(self):
        subprocess.run(
            f'adb -s {self.serial} shell input keyevent KEYCODE_BACK',
            shell=True, capture_output=True,
        )

    def press_home(self):
        subprocess.run(
            f'adb -s {self.serial} shell input keyevent KEYCODE_HOME',
            shell=True, capture_output=True,
        )

    def press_recent_apps(self):
        subprocess.run(
            f'adb -s {self.serial} shell input keyevent KEYCODE_APP_SWITCH',
            shell=True, capture_output=True,
        )

    def press_enter(self):
        subprocess.run(
            f'adb -s {self.serial} shell input keyevent KEYCODE_ENTER',
            shell=True, capture_output=True,
        )

    # ══════════════════════════════════════════════
    #   PUBLIC API: APP MANAGEMENT
    # ══════════════════════════════════════════════

    def open_app(self, package_name: str):
        subprocess.run(
            f'adb -s {self.serial} shell monkey -p {package_name} '
            f'-c android.intent.category.LAUNCHER 1',
            shell=True, capture_output=True,
        )

    def close_app(self, package_name: str):
        subprocess.run(
            f'adb -s {self.serial} shell am force-stop {package_name}',
            shell=True, capture_output=True,
        )

    def get_current_app(self) -> str:
        """Get the currently running app package name."""
        # Try multiple methods — different Android versions use different fields

        # Method 1: dumpsys window (most reliable across versions)
        result = subprocess.run(
            f'adb -s {self.serial} shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp"',
            shell=True, capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.strip()
        if output:
            package = self._parse_package_from_dumpsys(output)
            if package:
                return package

        # Method 2: dumpsys activity (fallback)
        result = subprocess.run(
            f'adb -s {self.serial} shell dumpsys activity activities '
            f'| grep -E "mResumedActivity|topResumedActivity|mFocusedActivity"',
            shell=True, capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.strip()
        if output:
            package = self._parse_package_from_dumpsys(output)
            if package:
                return package

        return ""
    
    def _parse_package_from_dumpsys(self, output: str) -> str:
        """Parse package name from dumpsys output."""
        import re
        # Match patterns like:
        #   com.instagram.android/.activity.MainTabActivity
        #   com.instagram.android/com.instagram.android.activity.MainTabActivity
        match = re.search(r'([\w.]+)/([\w.]+)', output)
        if match:
            return match.group(1)
        return ""

    def is_app_running(self, package_name: str) -> bool:
        current = self.get_current_app()
        return package_name in current

    def is_screen_on(self) -> bool:
        result = subprocess.run(
            f'adb -s {self.serial} shell dumpsys power | grep "Display Power"',
            shell=True, capture_output=True, text=True,
        )
        return "ON" in result.stdout.upper()

    def wake_screen(self):
        if not self.is_screen_on():
            subprocess.run(
                f'adb -s {self.serial} shell input keyevent KEYCODE_WAKEUP',
                shell=True, capture_output=True,
            )
            time.sleep(0.5)
            self.swipe(
                self.config.screen_width // 2,
                int(self.config.screen_height * 0.8),
                self.config.screen_width // 2,
                int(self.config.screen_height * 0.3),
                300,
            )
            time.sleep(0.5)

    # ══════════════════════════════════════════════
    #   PUBLIC API: SCREENSHOT
    # ══════════════════════════════════════════════

    def take_screenshot(self, save_path: str = None) -> bytes:
        result = subprocess.run(
            f'adb -s {self.serial} exec-out screencap -p',
            shell=True, capture_output=True,
        )
        if save_path and result.stdout:
            import os
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(result.stdout)
        return result.stdout

    # ══════════════════════════════════════════════
    #   PUBLIC API: WAIT
    # ══════════════════════════════════════════════

    def wait(self, action_type: str = "general"):
        delay = self.humanizer.get_action_delay(action_type)
        time.sleep(delay)

    def wait_seconds(self, min_sec: float, max_sec: float):
        time.sleep(random.uniform(min_sec, max_sec))


def create_executor_from_db(serial: str) -> ADBExecutor:
    """Create an ADBExecutor using calibration data from the database."""
    from backend.database.connection import db_manager
    from backend.database.models import Device

    session = db_manager.get_session()
    try:
        device = session.query(Device).filter_by(serial=serial).first()
        if device is None:
            raise ValueError(f"Device {serial} not found in database. Run calibration first.")
        if not device.is_calibrated:
            raise ValueError(f"Device {serial} is not calibrated. Run calibration first.")

        config = DeviceConfig.from_database(device)
        return ADBExecutor(config)
    finally:
        session.close()