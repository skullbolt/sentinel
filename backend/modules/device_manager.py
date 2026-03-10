"""
Device Manager Module
=====================
Central management of all connected Android devices.

Responsibilities:
  - Scan for connected ADB devices
  - Auto-calibrate new devices
  - Create and cache executor instances
  - Track device health and status
  - Detect installed clones per device
  - Register everything in database
  - Provide ready-to-use executors

Usage:
  manager = DeviceManager()
  manager.scan()                          # find all devices
  executor = manager.get_executor("emulator-5554")  # get executor
  executor.tap(540, 1200)                 # use it
"""

from __future__ import annotations

import subprocess
import time
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.modules.device_calibrator import DeviceCalibrator, auto_calibrate_device
from backend.modules.adb_executor import ADBExecutor, DeviceConfig, create_executor_from_db
from backend.database.connection import db_manager
from backend.database.models import Device, Clone, CloneStatus, DeviceStatus

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DeviceManager")


class ManagedDevice:
    """Represents a single connected device with all its components"""

    def __init__(
        self,
        serial: str,
        db_id: int,
        executor: ADBExecutor,
        config: DeviceConfig,
    ):
        self.serial = serial
        self.db_id = db_id
        self.executor = executor
        self.config = config
        self.status = "online"
        self.last_heartbeat = datetime.now()
        self.clone_packages: List[str] = []
        self.total_clones = 0
        self.error_count = 0
        self.consecutive_errors = 0

    def __repr__(self):
        return (
            f"<ManagedDevice serial='{self.serial}' "
            f"db_id={self.db_id} status='{self.status}' "
            f"clones={self.total_clones}>"
        )


class DeviceManager:
    """
    Central manager for all connected Android devices.
    
    This is the SINGLE ENTRY POINT for device operations.
    All other modules go through DeviceManager to get executors.
    """

    # Instagram package names
    INSTAGRAM_ORIGINAL = "com.instagram.android"

    def __init__(self):
        self.devices: Dict[str, ManagedDevice] = {}
        self._lock = threading.Lock()
        self._health_thread: Optional[threading.Thread] = None
        self._running = False

    # ══════════════════════════════════════════════
    #   DEVICE SCANNING
    # ══════════════════════════════════════════════

    def get_adb_devices(self) -> List[str]:
        """Get list of device serials from 'adb devices'"""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            serials = []
            for line in result.stdout.strip().split("\n")[1:]:
                if "\tdevice" in line:
                    serial = line.split("\t")[0]
                    serials.append(serial)
            return serials
        except Exception as e:
            logger.error(f"Failed to get ADB devices: {e}")
            return []

    def scan(self) -> Dict[str, ManagedDevice]:
        """
        Scan for all connected devices.
        - Finds new devices → calibrate and register
        - Finds known devices → load from DB
        - Detects disconnected devices → mark offline
        
        Returns dict of all online devices.
        """
        logger.info("🔍 Scanning for connected devices...")
        connected_serials = self.get_adb_devices()

        if not connected_serials:
            logger.warning("   No devices found via ADB")
            return self.devices

        logger.info(f"   Found {len(connected_serials)} device(s): {connected_serials}")

        # Process each connected device
        for serial in connected_serials:
            if serial in self.devices and self.devices[serial].status == "online":
                # Already managed and online — just update heartbeat
                self.devices[serial].last_heartbeat = datetime.now()
                logger.info(f"   ✅ {serial}: already managed")
                continue

            # New or reconnected device
            try:
                managed = self._initialize_device(serial)
                if managed:
                    self.devices[serial] = managed
                    logger.info(f"   ✅ {serial}: initialized (DB ID: {managed.db_id})")
            except Exception as e:
                logger.error(f"   ❌ {serial}: initialization failed: {e}")

        # Mark disconnected devices as offline
        for serial in list(self.devices.keys()):
            if serial not in connected_serials:
                self.devices[serial].status = "offline"
                self._update_device_status(serial, DeviceStatus.OFFLINE)
                logger.info(f"   ⚠️  {serial}: marked offline (disconnected)")

        online_count = sum(1 for d in self.devices.values() if d.status == "online")
        logger.info(f"   📱 Total: {len(self.devices)} devices, {online_count} online")

        return self.devices

    def _initialize_device(self, serial: str) -> Optional[ManagedDevice]:
        """
        Initialize a single device:
        1. Check if calibrated in DB
        2. If not, run auto-calibration
        3. Create executor
        4. Detect clones
        5. Return ManagedDevice
        """
        session = db_manager.get_session()
        try:
            # Check database for existing device
            device_row = session.query(Device).filter_by(serial=serial).first()

            if device_row and device_row.is_calibrated:
                logger.info(f"   📂 {serial}: loading from database")
            else:
                logger.info(f"   🔧 {serial}: calibrating (first time)...")
                cal_result = auto_calibrate_device(serial)
                if not cal_result.get("success"):
                    logger.error(f"   ❌ {serial}: calibration failed: {cal_result.get('error')}")
                    return None
                # Reload from DB after calibration
                device_row = session.query(Device).filter_by(serial=serial).first()

            if not device_row:
                logger.error(f"   ❌ {serial}: device not found in DB after calibration")
                return None

            # Create executor
            config = DeviceConfig.from_database(device_row)
            executor = ADBExecutor(config)

            # Detect clones
            clone_packages = self._detect_instagram_clones(serial)
            total_clones = len(clone_packages)

            # Register clones in database
            self._register_clones(device_row.id, clone_packages, session)

            # Update device record
            device_row.status = DeviceStatus.ONLINE
            device_row.last_heartbeat = datetime.now()
            device_row.total_clones = total_clones
            session.commit()

            # Create managed device
            managed = ManagedDevice(
                serial=serial,
                db_id=device_row.id,
                executor=executor,
                config=config,
            )
            managed.clone_packages = clone_packages
            managed.total_clones = total_clones

            logger.info(f"   → Mode: {executor.mode.value}")
            logger.info(f"   → Screen: {config.screen_width}x{config.screen_height}")
            logger.info(f"   → Clones: {total_clones} ({len(clone_packages)} Instagram packages)")

            return managed

        except Exception as e:
            session.rollback()
            logger.error(f"   ❌ {serial}: error during initialization: {e}")
            raise
        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   CLONE DETECTION
    # ══════════════════════════════════════════════

    def _detect_instagram_clones(self, serial: str) -> List[str]:
        """
        Detect all Instagram packages on a device.
        This includes the original and all App Cloner clones.
        
        App Cloner typically creates packages like:
          com.instagram.android          ← original
          com.instagram.android.clone1   ← clone
          com.instagram.android_clone2   ← clone (different naming)
          
        We detect ALL packages containing 'instagram'.
        """
        try:
            result = subprocess.run(
                f'adb -s {serial} shell pm list packages',
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
            )

            packages = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.startswith("package:"):
                    package = line.replace("package:", "").strip()
                    # Check if it's an Instagram package
                    if "instagram" in package.lower():
                        packages.append(package)

            # Sort: original first, then clones
            packages.sort(key=lambda p: (p != self.INSTAGRAM_ORIGINAL, p))

            return packages

        except Exception as e:
            logger.error(f"Failed to detect clones on {serial}: {e}")
            return []

    def _register_clones(
        self,
        device_id: int,
        clone_packages: List[str],
        session,
    ):
        """Register detected clones in the database"""
        for index, package in enumerate(clone_packages):
            # Check if clone already exists
            existing = session.query(Clone).filter_by(
                device_id=device_id,
                package_name=package,
            ).first()

            if existing:
                # Update existing clone
                existing.is_installed = True
                existing.status = CloneStatus.ACTIVE if existing.has_account else CloneStatus.EMPTY
                existing.updated_at = datetime.now()
            else:
                # Create new clone record
                is_original = (package == self.INSTAGRAM_ORIGINAL)
                clone = Clone(
                    device_id=device_id,
                    clone_index=index,
                    package_name=package,
                    clone_label=f"{'Original' if is_original else f'Clone {index}'}",
                    is_original=is_original,
                    is_installed=True,
                    has_account=False,
                    status=CloneStatus.EMPTY,
                )
                session.add(clone)
                logger.info(f"      📦 Registered: {package} ({'original' if is_original else f'clone {index}'})")

        # Mark uninstalled clones
        all_db_clones = session.query(Clone).filter_by(device_id=device_id).all()
        for db_clone in all_db_clones:
            if db_clone.package_name not in clone_packages:
                db_clone.is_installed = False
                db_clone.status = CloneStatus.DISABLED

        session.flush()

    # ══════════════════════════════════════════════
    #   DEVICE ACCESS
    # ══════════════════════════════════════════════

    def get_device(self, serial: str) -> Optional[ManagedDevice]:
        """Get a managed device by serial number."""
        device = self.devices.get(serial)
        if device and device.status == "online":
            return device
        return None

    def get_executor(self, serial: str) -> Optional[ADBExecutor]:
        """Get executor for a specific device."""
        device = self.get_device(serial)
        if device:
            return device.executor
        return None

    def get_all_online_devices(self) -> List[ManagedDevice]:
        """Get all online devices."""
        return [d for d in self.devices.values() if d.status == "online"]

    def get_all_devices(self) -> List[ManagedDevice]:
        """Get all devices (online and offline)."""
        return list(self.devices.values())

    def get_device_clones(self, serial: str) -> List[str]:
        """Get list of Instagram clone packages on a device."""
        device = self.get_device(serial)
        if device:
            return device.clone_packages
        return []

    def get_device_info(self, serial: str) -> Optional[Dict]:
        """Get device info as a dictionary."""
        device = self.get_device(serial)
        if not device:
            return None

        return {
            "serial": device.serial,
            "db_id": device.db_id,
            "status": device.status,
            "screen": f"{device.config.screen_width}x{device.config.screen_height}",
            "is_emulator": device.config.is_emulator,
            "touch_mode": device.executor.mode.value,
            "total_clones": device.total_clones,
            "clone_packages": device.clone_packages,
            "last_heartbeat": device.last_heartbeat.isoformat(),
            "error_count": device.error_count,
        }

    # ══════════════════════════════════════════════
    #   DEVICE STATUS UPDATES
    # ══════════════════════════════════════════════

    def _update_device_status(self, serial: str, status: DeviceStatus):
        """Update device status in database."""
        session = db_manager.get_session()
        try:
            device = session.query(Device).filter_by(serial=serial).first()
            if device:
                device.status = status
                device.last_heartbeat = datetime.now()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update device status: {e}")
        finally:
            session.close()

    def _update_heartbeat(self, serial: str):
        """Update device heartbeat in database."""
        session = db_manager.get_session()
        try:
            device = session.query(Device).filter_by(serial=serial).first()
            if device:
                device.last_heartbeat = datetime.now()
                session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   HEALTH MONITORING
    # ══════════════════════════════════════════════

    def check_device_health(self, serial: str) -> Dict:
        """
        Check health of a specific device.
        Returns health info dict.
        """
        health = {
            "serial": serial,
            "adb_connected": False,
            "screen_on": False,
            "battery_level": None,
            "storage_free_mb": None,
            "current_app": None,
        }

        try:
            # Check ADB connection
            connected = serial in self.get_adb_devices()
            health["adb_connected"] = connected

            if not connected:
                return health

            device = self.get_device(serial)
            if not device:
                return health

            executor = device.executor

            # Check screen
            health["screen_on"] = executor.is_screen_on()

            # Get battery level
            result = subprocess.run(
                f'adb -s {serial} shell dumpsys battery | grep level',
                shell=True, capture_output=True, text=True, timeout=5,
            )
            if result.stdout:
                import re
                match = re.search(r'level:\s*(\d+)', result.stdout)
                if match:
                    health["battery_level"] = int(match.group(1))

            # Get free storage
            result = subprocess.run(
                f'adb -s {serial} shell df /data | tail -1',
                shell=True, capture_output=True, text=True, timeout=5,
            )
            if result.stdout:
                parts = result.stdout.split()
                if len(parts) >= 4:
                    try:
                        # Available space (in 1K blocks)
                        free_kb = int(parts[3])
                        health["storage_free_mb"] = free_kb // 1024
                    except (ValueError, IndexError):
                        pass

            # Get current app
            health["current_app"] = executor.get_current_app()

            # Update database
            session = db_manager.get_session()
            try:
                db_device = session.query(Device).filter_by(serial=serial).first()
                if db_device:
                    db_device.battery_level = health["battery_level"]
                    db_device.storage_free_mb = health["storage_free_mb"]
                    db_device.last_heartbeat = datetime.now()
                    session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()

        except Exception as e:
            logger.error(f"Health check failed for {serial}: {e}")

        return health

    def check_all_devices_health(self) -> List[Dict]:
        """Run health check on all managed devices."""
        results = []
        for serial in list(self.devices.keys()):
            health = self.check_device_health(serial)
            results.append(health)
        return results

    # ══════════════════════════════════════════════
    #   HEALTH MONITORING THREAD
    # ══════════════════════════════════════════════

    def start_health_monitor(self, interval_seconds: int = 60):
        """Start background health monitoring thread."""
        if self._running:
            logger.warning("Health monitor already running")
            return

        self._running = True
        self._health_thread = threading.Thread(
            target=self._health_monitor_loop,
            args=(interval_seconds,),
            daemon=True,
        )
        self._health_thread.start()
        logger.info(f"🏥 Health monitor started (every {interval_seconds}s)")

    def stop_health_monitor(self):
        """Stop the health monitoring thread."""
        self._running = False
        if self._health_thread:
            self._health_thread.join(timeout=10)
        logger.info("🏥 Health monitor stopped")

    def _health_monitor_loop(self, interval: int):
        """Background loop for health monitoring."""
        while self._running:
            try:
                # Re-scan for new/disconnected devices
                self.scan()

                # Check health of all devices
                for serial, device in list(self.devices.items()):
                    if device.status == "online":
                        health = self.check_device_health(serial)
                        if not health["adb_connected"]:
                            device.status = "offline"
                            device.consecutive_errors += 1
                            self._update_device_status(serial, DeviceStatus.OFFLINE)
                            logger.warning(f"📱 {serial}: went offline")
                        else:
                            device.consecutive_errors = 0
                            device.last_heartbeat = datetime.now()

                        # Log battery warnings
                        if health["battery_level"] and health["battery_level"] < 20:
                            logger.warning(
                                f"🔋 {serial}: low battery ({health['battery_level']}%)"
                            )

                        # Log storage warnings
                        if health["storage_free_mb"] and health["storage_free_mb"] < 500:
                            logger.warning(
                                f"💾 {serial}: low storage ({health['storage_free_mb']}MB free)"
                            )

            except Exception as e:
                logger.error(f"Health monitor error: {e}")

            # Sleep in small intervals so we can stop quickly
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

    # ══════════════════════════════════════════════
    #   WIFI ADB CONNECTION
    # ══════════════════════════════════════════════

    def connect_wifi(self, ip: str, port: int = 5555) -> bool:
        """Connect to a device over WiFi ADB."""
        try:
            # First enable tcpip on the device (if connected via USB)
            subprocess.run(
                f"adb tcpip {port}",
                shell=True, capture_output=True, timeout=5,
            )
            time.sleep(1)

            # Connect
            result = subprocess.run(
                f"adb connect {ip}:{port}",
                shell=True, capture_output=True, text=True, timeout=10,
            )

            if "connected" in result.stdout.lower():
                logger.info(f"✅ WiFi connected: {ip}:{port}")
                # Initialize the device
                serial = f"{ip}:{port}"
                time.sleep(2)
                self.scan()
                return True
            else:
                logger.error(f"❌ WiFi connection failed: {result.stdout}")
                return False

        except Exception as e:
            logger.error(f"WiFi connection error: {e}")
            return False

    def disconnect_wifi(self, ip: str, port: int = 5555) -> bool:
        """Disconnect a WiFi ADB device."""
        try:
            result = subprocess.run(
                f"adb disconnect {ip}:{port}",
                shell=True, capture_output=True, text=True, timeout=5,
            )
            serial = f"{ip}:{port}"
            if serial in self.devices:
                self.devices[serial].status = "offline"
                self._update_device_status(serial, DeviceStatus.OFFLINE)
            return True
        except Exception as e:
            logger.error(f"WiFi disconnect error: {e}")
            return False

    # ══════════════════════════════════════════════
    #   SUMMARY / REPORTING
    # ══════════════════════════════════════════════

    def get_summary(self) -> Dict:
        """Get a summary of all managed devices."""
        online = [d for d in self.devices.values() if d.status == "online"]
        offline = [d for d in self.devices.values() if d.status == "offline"]
        total_clones = sum(d.total_clones for d in online)

        return {
            "total_devices": len(self.devices),
            "online": len(online),
            "offline": len(offline),
            "total_clones": total_clones,
            "devices": [
                {
                    "serial": d.serial,
                    "db_id": d.db_id,
                    "status": d.status,
                    "clones": d.total_clones,
                    "mode": d.executor.mode.value,
                    "is_emulator": d.config.is_emulator,
                    "last_heartbeat": d.last_heartbeat.isoformat(),
                }
                for d in self.devices.values()
            ],
        }

    def print_status(self):
        """Print a nice status overview to console."""
        summary = self.get_summary()

        print("")
        print("╔══════════════════════════════════════════════╗")
        print("║          📱 DEVICE MANAGER STATUS            ║")
        print("╠══════════════════════════════════════════════╣")
        print(f"║  Total devices:  {summary['total_devices']:<27} ║")
        print(f"║  Online:         {summary['online']:<27} ║")
        print(f"║  Offline:        {summary['offline']:<27} ║")
        print(f"║  Total clones:   {summary['total_clones']:<27} ║")
        print("╠══════════════════════════════════════════════╣")

        for d in summary["devices"]:
            status_icon = "🟢" if d["status"] == "online" else "🔴"
            emu = "📟" if d["is_emulator"] else "📱"
            print(f"║  {status_icon} {emu} {d['serial']:<25}     ║")
            print(f"║     DB ID: {d['db_id']}  |  Clones: {d['clones']}  |  Mode: {d['mode']:<12} ║")

        print("╚══════════════════════════════════════════════╝")
        print("")