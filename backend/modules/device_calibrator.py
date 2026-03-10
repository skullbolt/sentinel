"""
Auto-calibration module.
Detects touchscreen device, coordinate ranges,
event codes, and screen info for any connected device.
Saves everything to database.
"""

import subprocess
import re
import json
from datetime import datetime
from typing import Dict, Optional, Tuple


class DeviceCalibrator:
    """Automatically calibrates a connected Android device"""

    # Standard Linux input event codes
    EVENT_CODES = {
        "ABS_MT_SLOT": 0x2f,           # 47
        "ABS_MT_TOUCH_MAJOR": 0x30,    # 48
        "ABS_MT_TOUCH_MINOR": 0x31,    # 49
        "ABS_MT_WIDTH_MAJOR": 0x32,    # 50
        "ABS_MT_WIDTH_MINOR": 0x33,    # 51
        "ABS_MT_ORIENTATION": 0x34,    # 52
        "ABS_MT_POSITION_X": 0x35,    # 53
        "ABS_MT_POSITION_Y": 0x36,    # 54
        "ABS_MT_TRACKING_ID": 0x39,   # 57
        "ABS_MT_PRESSURE": 0x3a,      # 58
    }

    def __init__(self, serial: str):
        self.serial = serial

    def _run_adb(self, command: str) -> str:
        """Run an ADB command and return output"""
        full_cmd = f"adb -s {self.serial} shell {command}"
        try:
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return ""
        except Exception as e:
            print(f"ADB command failed: {e}")
            return ""

    def _run_adb_host(self, command: str) -> str:
        """Run an ADB host command (not shell)"""
        full_cmd = f"adb -s {self.serial} {command}"
        try:
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout.strip()
        except Exception as e:
            print(f"ADB command failed: {e}")
            return ""

    # ─── SCREEN INFO ─────────────────────────────

    def get_screen_resolution(self) -> Tuple[int, int]:
        """Get screen width and height"""
        output = self._run_adb("wm size")
        # Output: "Physical size: 1080x2400"
        match = re.search(r'(\d+)x(\d+)', output)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            return width, height
        return 0, 0

    def get_screen_density(self) -> int:
        """Get screen density (DPI)"""
        output = self._run_adb("wm density")
        # Output: "Physical density: 420"
        match = re.search(r'(\d+)', output)
        if match:
            return int(match.group(1))
        return 0

    def get_device_model(self) -> str:
        """Get device model name"""
        return self._run_adb("getprop ro.product.model")

    def get_android_version(self) -> str:
        """Get Android version"""
        return self._run_adb("getprop ro.build.version.release")

    def get_device_name(self) -> str:
        """Get device brand + model"""
        brand = self._run_adb("getprop ro.product.brand")
        model = self._run_adb("getprop ro.product.model")
        return f"{brand} {model}".strip()

    def is_emulator(self) -> bool:
        """Check if device is an emulator"""
        fingerprint = self._run_adb("getprop ro.build.fingerprint")
        hardware = self._run_adb("getprop ro.hardware")
        emulator_indicators = [
            "generic", "emulator", "sdk", "vbox",
            "goldfish", "ranchu", "android-studio"
        ]
        combined = f"{fingerprint} {hardware}".lower()
        return any(ind in combined for ind in emulator_indicators)

    # ─── TOUCH DEVICE DETECTION ──────────────────

    def detect_touch_device(self) -> Dict:
        """
        Parse 'getevent -pl' to find touchscreen device
        and extract all event codes and ranges.
        
        This is the CORE calibration function.
        """
        output = self._run_adb("getevent -pl")

        if not output:
            return {"error": "Could not get event device list"}

        # Parse device blocks
        devices = self._parse_getevent_output(output)

        # Find the touchscreen device
        touch_device = None
        for device in devices:
            if self._is_touchscreen(device):
                touch_device = device
                break

        if not touch_device:
            return {"error": "No touchscreen device found"}

        return touch_device

    def _parse_getevent_output(self, output: str) -> list:
        """Parse the raw getevent -pl output into structured data"""
        devices = []
        current_device = None
        current_abs_code = None

        for line in output.split('\n'):
            line = line.rstrip()

            # New device: "add device 1: /dev/input/event0"
            device_match = re.match(r'add device \d+:\s+(/dev/input/event\d+)', line)
            if device_match:
                if current_device:
                    devices.append(current_device)
                current_device = {
                    'path': device_match.group(1),
                    'name': '',
                    'events': {},
                    'abs_info': {},
                }
                continue

            if current_device is None:
                continue

            # Device name: '  name:     "..."'
            name_match = re.match(r'\s+name:\s+"(.+)"', line)
            if name_match:
                current_device['name'] = name_match.group(1)
                continue

            # ABS code line: "    ABS (0003): ABS_MT_POSITION_X  ..."
            # or individual: "      ABS_MT_POSITION_X : value 0, min 0, max 1079..."
            abs_match = re.match(
                r'\s+(ABS_MT_\w+|ABS_\w+)\s*:\s*value\s+(\d+),\s*min\s+(\d+),\s*max\s+(\d+)',
                line
            )
            if abs_match:
                code_name = abs_match.group(1)
                current_device['abs_info'][code_name] = {
                    'value': int(abs_match.group(2)),
                    'min': int(abs_match.group(3)),
                    'max': int(abs_match.group(4)),
                }
                continue

            # Hex format: "    0035  : value 0, min 0, max 1079..."
            hex_abs_match = re.match(
                r'\s+([0-9a-fA-F]{4})\s*:\s*value\s+(\d+),\s*min\s+(\d+),\s*max\s+(\d+)',
                line
            )
            if hex_abs_match:
                code_hex = int(hex_abs_match.group(1), 16)
                code_name = self._hex_to_abs_name(code_hex)
                current_device['abs_info'][code_name] = {
                    'value': int(hex_abs_match.group(2)),
                    'min': int(hex_abs_match.group(3)),
                    'max': int(hex_abs_match.group(4)),
                }
                continue

        # Don't forget the last device
        if current_device:
            devices.append(current_device)

        return devices

    def _hex_to_abs_name(self, code: int) -> str:
        """Convert hex event code to human-readable name"""
        reverse_map = {v: k for k, v in self.EVENT_CODES.items()}
        return reverse_map.get(code, f"UNKNOWN_0x{code:04x}")

    def _is_touchscreen(self, device: Dict) -> bool:
        """Check if a device is a touchscreen based on its capabilities"""
        name = device.get('name', '').lower()
        abs_info = device.get('abs_info', {})

        # Check by name
        touch_names = ['touch', 'touchscreen', 'input', 'ts', 'ft5x', 'goodix', 'synaptics']
        name_match = any(tn in name for tn in touch_names)

        # Check by having required multitouch axes
        has_x = 'ABS_MT_POSITION_X' in abs_info
        has_y = 'ABS_MT_POSITION_Y' in abs_info

        return (name_match or has_x) and has_y

    # ─── FULL CALIBRATION ────────────────────────

    def calibrate(self) -> Dict:
        """
        Run full calibration and return all data.
        This is the main function to call.
        """
        print(f"🔧 Calibrating device: {self.serial}")

        result = {
            'serial': self.serial,
            'success': False,
            'timestamp': datetime.now().isoformat(),
        }

        # Screen info
        print("   📱 Getting screen info...")
        width, height = self.get_screen_resolution()
        density = self.get_screen_density()
        model = self.get_device_model()
        android_ver = self.get_android_version()
        device_name = self.get_device_name()
        is_emu = self.is_emulator()

        result['screen'] = {
            'width': width,
            'height': height,
            'density': density,
        }
        result['device'] = {
            'model': model,
            'android_version': android_ver,
            'name': device_name,
            'is_emulator': is_emu,
        }

        print(f"   → Screen: {width}x{height} @ {density}dpi")
        print(f"   → Model: {device_name}")
        print(f"   → Android: {android_ver}")
        print(f"   → Emulator: {is_emu}")

        # Touch device detection
        print("   🖐️ Detecting touchscreen device...")
        touch = self.detect_touch_device()

        if 'error' in touch:
            print(f"   ❌ {touch['error']}")
            result['error'] = touch['error']
            return result

        abs_info = touch.get('abs_info', {})
        result['touch'] = {
            'device_path': touch['path'],
            'device_name': touch['name'],
            'abs_info': abs_info,
        }

        print(f"   → Touch device: {touch['path']}")
        print(f"   → Touch name: {touch['name']}")

        # Extract specific values
        x_info = abs_info.get('ABS_MT_POSITION_X', {})
        y_info = abs_info.get('ABS_MT_POSITION_Y', {})
        pressure_info = abs_info.get('ABS_MT_PRESSURE', {})
        tracking_info = abs_info.get('ABS_MT_TRACKING_ID', {})
        touch_major_info = abs_info.get('ABS_MT_TOUCH_MAJOR', {})
        slot_info = abs_info.get('ABS_MT_SLOT', {})

        result['ranges'] = {
            'x_min': x_info.get('min', 0),
            'x_max': x_info.get('max', width),
            'y_min': y_info.get('min', 0),
            'y_max': y_info.get('max', height),
            'pressure_min': pressure_info.get('min', 0),
            'pressure_max': pressure_info.get('max', 255),
            'touch_major_max': touch_major_info.get('max', 0),
            'tracking_id_max': tracking_info.get('max', 65535),
        }

        # Calculate scale factors
        if width > 0 and x_info.get('max', 0) > 0:
            result['scale'] = {
                'x': x_info['max'] / width,
                'y': y_info.get('max', height) / height,
            }
        else:
            result['scale'] = {'x': 1.0, 'y': 1.0}

        # Event codes
        result['event_codes'] = {
            'x': self.EVENT_CODES.get('ABS_MT_POSITION_X', 53),
            'y': self.EVENT_CODES.get('ABS_MT_POSITION_Y', 54),
            'pressure': self.EVENT_CODES.get('ABS_MT_PRESSURE', 58),
            'tracking_id': self.EVENT_CODES.get('ABS_MT_TRACKING_ID', 57),
            'touch_major': self.EVENT_CODES.get('ABS_MT_TOUCH_MAJOR', 48),
            'slot': self.EVENT_CODES.get('ABS_MT_SLOT', 47),
        }

        print(f"   → X range: {result['ranges']['x_min']}-{result['ranges']['x_max']}")
        print(f"   → Y range: {result['ranges']['y_min']}-{result['ranges']['y_max']}")
        print(f"   → Pressure range: {result['ranges']['pressure_min']}-{result['ranges']['pressure_max']}")
        print(f"   → Scale X: {result['scale']['x']:.4f}")
        print(f"   → Scale Y: {result['scale']['y']:.4f}")

        result['success'] = True
        print("   ✅ Calibration complete!")

        return result

    # ─── SAVE TO DATABASE ────────────────────────

    def save_to_database(self, calibration_data: Dict, session) -> 'Device':
        """Save calibration data to devices table"""
        from backend.database.models import Device

        # Check if device already exists
        device = session.query(Device).filter_by(serial=self.serial).first()

        if device is None:
            device = Device(serial=self.serial)
            session.add(device)
            print(f"   📝 New device record created: {self.serial}")
        else:
            print(f"   📝 Updating existing device: {self.serial}")

        # Update device info
        dev_info = calibration_data.get('device', {})
        screen = calibration_data.get('screen', {})
        touch = calibration_data.get('touch', {})
        ranges = calibration_data.get('ranges', {})
        scale = calibration_data.get('scale', {})
        codes = calibration_data.get('event_codes', {})

        device.name = dev_info.get('name', device.name)
        device.model = dev_info.get('model', device.model)
        device.android_version = dev_info.get('android_version', device.android_version)
        device.is_emulator = dev_info.get('is_emulator', False)

        device.screen_width = screen.get('width', 0)
        device.screen_height = screen.get('height', 0)
        device.screen_density = screen.get('density', 0)

        device.touch_device_path = touch.get('device_path', '')
        device.touch_max_x = ranges.get('x_max', 0)
        device.touch_max_y = ranges.get('y_max', 0)
        device.touch_min_x = ranges.get('x_min', 0)
        device.touch_min_y = ranges.get('y_min', 0)
        device.touch_max_pressure = ranges.get('pressure_max', 255)
        device.touch_min_pressure = ranges.get('pressure_min', 0)
        device.touch_max_touch_major = ranges.get('touch_major_max', 0)

        device.touch_event_code_x = codes.get('x', 53)
        device.touch_event_code_y = codes.get('y', 54)
        device.touch_event_code_pressure = codes.get('pressure', 58)
        device.touch_event_code_tracking = codes.get('tracking_id', 57)
        device.touch_event_code_touch_major = codes.get('touch_major', 48)
        device.touch_event_code_slot = codes.get('slot', 47)

        device.touch_scale_x = scale.get('x', 1.0)
        device.touch_scale_y = scale.get('y', 1.0)

        device.is_calibrated = calibration_data.get('success', False)
        device.calibrated_at = datetime.now()
        device.calibration_data = calibration_data  # Store full raw data as JSON

        device.status = 'online'
        device.last_heartbeat = datetime.now()

        session.commit()
        print(f"   ✅ Device saved to database (ID: {device.id})")

        return device


def auto_calibrate_device(serial: str) -> Dict:
    """
    One-function call to calibrate and save.
    Use this when a new device is detected.
    """
    from backend.database.connection import db_manager

    calibrator = DeviceCalibrator(serial)
    data = calibrator.calibrate()

    if data.get('success'):
        session = db_manager.get_session()
        try:
            device = calibrator.save_to_database(data, session)
            data['device_db_id'] = device.id
        except Exception as e:
            session.rollback()
            print(f"   ❌ Failed to save to database: {e}")
            data['db_error'] = str(e)
        finally:
            session.close()

    return data