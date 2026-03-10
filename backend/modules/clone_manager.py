"""
Clone Manager Module
====================
Manages Instagram clone cycling on each device.

Responsibilities:
  - Open/close specific clones by package name
  - Cycle through all clones on a device
  - Track which clone is currently active
  - Handle clone switching with proper cleanup
  - Detect if clone is working or crashed
  - Register clone status in database

Usage:
  clone_mgr = CloneManager(executor, device_id)
  clone_mgr.open_clone("com.instagram.android")
  clone_mgr.close_current_clone()
  clone_mgr.cycle_all_clones(callback=do_task)
"""

from __future__ import annotations

import time
import random
import logging
from datetime import datetime
from typing import List, Optional, Callable, Dict

from backend.modules.adb_executor import ADBExecutor
from backend.database.connection import db_manager
from backend.database.models import Clone, CloneStatus, Account, AccountState

logger = logging.getLogger("CloneManager")


class CloneManager:
    """
    Manages clone switching and cycling on a single device.
    Each device gets its own CloneManager instance.
    """

    INSTAGRAM_ORIGINAL = "com.instagram.android"

    def __init__(self, executor: ADBExecutor, device_id: int):
        self.executor = executor
        self.device_id = device_id
        self.serial = executor.serial
        self.current_clone_package: Optional[str] = None
        self.current_clone_id: Optional[int] = None
        self._clone_list: List[Dict] = []

    # ══════════════════════════════════════════════
    #   CLONE LIST MANAGEMENT
    # ══════════════════════════════════════════════

    def load_clones_from_db(self) -> List[Dict]:
        """
        Load all clones for this device from database.
        Returns list of clone info dicts sorted by clone_index.
        """
        session = db_manager.get_session()
        try:
            clones = (
                session.query(Clone)
                .filter_by(device_id=self.device_id, is_installed=True)
                .order_by(Clone.clone_index)
                .all()
            )

            self._clone_list = []
            for c in clones:
                self._clone_list.append({
                    "id": c.id,
                    "clone_index": c.clone_index,
                    "package_name": c.package_name,
                    "clone_label": c.clone_label,
                    "is_original": c.is_original,
                    "has_account": c.has_account,
                    "account_id": c.account_id,
                    "status": c.status.value if c.status else "unknown",
                })

            logger.info(f"📦 Loaded {len(self._clone_list)} clones for device {self.serial}")
            return self._clone_list

        finally:
            session.close()

    def get_clone_list(self) -> List[Dict]:
        """Get cached clone list. Loads from DB if empty."""
        if not self._clone_list:
            self.load_clones_from_db()
        return self._clone_list

    def get_active_clones(self) -> List[Dict]:
        """Get only clones that have accounts and are active."""
        return [
            c for c in self.get_clone_list()
            if c["has_account"] and c["status"] == "active"
        ]

    def get_clone_by_package(self, package_name: str) -> Optional[Dict]:
        """Find a clone by its package name."""
        for c in self.get_clone_list():
            if c["package_name"] == package_name:
                return c
        return None

    def get_clone_by_index(self, index: int) -> Optional[Dict]:
        """Find a clone by its index."""
        for c in self.get_clone_list():
            if c["clone_index"] == index:
                return c
        return None

    # ══════════════════════════════════════════════
    #   OPEN / CLOSE CLONES
    # ══════════════════════════════════════════════

    def open_clone(self, package_name: str, wait_seconds: float = 4.0) -> bool:
        """
        Open a specific Instagram clone.
        
        Args:
            package_name: The clone's package name
            wait_seconds: How long to wait for app to load
            
        Returns:
            True if clone opened successfully
        """
        logger.info(f"📱 Opening clone: {package_name}")

        # Close current clone first if one is open
        if self.current_clone_package and self.current_clone_package != package_name:
            self.close_current_clone()
            # Wait between closing and opening (human-like)
            time.sleep(random.uniform(1.0, 3.0))

        # Open the app
        self.executor.open_app(package_name)

        # Wait for app to load
        load_wait = wait_seconds + random.uniform(-0.5, 1.5)
        time.sleep(max(2.0, load_wait))

        # Verify it opened
        current_app = self.executor.get_current_app()
        if package_name in current_app:
            self.current_clone_package = package_name
            clone_info = self.get_clone_by_package(package_name)
            if clone_info:
                self.current_clone_id = clone_info["id"]

            # Update database
            self._update_clone_last_opened(package_name)

            logger.info(f"   ✅ Clone opened: {package_name}")
            return True
        else:
            logger.warning(f"   ⚠️  Expected {package_name}, got {current_app}")
            # Try one more time
            time.sleep(2)
            current_app = self.executor.get_current_app()
            if package_name in current_app:
                self.current_clone_package = package_name
                clone_info = self.get_clone_by_package(package_name)
                if clone_info:
                    self.current_clone_id = clone_info["id"]
                self._update_clone_last_opened(package_name)
                logger.info(f"   ✅ Clone opened (delayed): {package_name}")
                return True

            logger.error(f"   ❌ Clone failed to open: {package_name}")
            self._increment_clone_error(package_name, f"Failed to open. Got: {current_app}")
            return False

    def close_current_clone(self, wait_after: float = 1.0):
        """Close the currently open clone."""
        if self.current_clone_package:
            logger.info(f"   🔒 Closing clone: {self.current_clone_package}")
            self.executor.close_app(self.current_clone_package)
            time.sleep(wait_after + random.uniform(0, 0.5))

            self.current_clone_package = None
            self.current_clone_id = None

    def close_clone(self, package_name: str, wait_after: float = 1.0):
        """Close a specific clone by package name."""
        logger.info(f"   🔒 Closing: {package_name}")
        self.executor.close_app(package_name)
        time.sleep(wait_after + random.uniform(0, 0.5))

        if self.current_clone_package == package_name:
            self.current_clone_package = None
            self.current_clone_id = None

    def close_all_clones(self):
        """Close all Instagram clones on the device."""
        logger.info(f"🔒 Closing all clones on {self.serial}")
        for clone in self.get_clone_list():
            self.executor.close_app(clone["package_name"])
            time.sleep(0.3)
        self.current_clone_package = None
        self.current_clone_id = None

    # ══════════════════════════════════════════════
    #   CLONE CYCLING
    # ══════════════════════════════════════════════

    def cycle_all_clones(
        self,
        callback: Optional[Callable[[str, int, Optional[int]], None]] = None,
        only_active: bool = True,
        delay_between_clones_min: float = 30.0,
        delay_between_clones_max: float = 120.0,
        shuffle: bool = False,
    ) -> Dict:
        """
        Cycle through all clones on this device.
        Opens each clone, calls the callback, then moves to next.
        
        Args:
            callback: Function called for each clone
                      callback(package_name, clone_db_id, account_id)
            only_active: If True, skip clones without accounts
            delay_between_clones_min: Min seconds between clone switches
            delay_between_clones_max: Max seconds between clone switches
            shuffle: Randomize clone order
            
        Returns:
            Summary dict with results
        """
        # Refresh clone list
        self.load_clones_from_db()

        if only_active:
            clones = self.get_active_clones()
        else:
            clones = self.get_clone_list()

        if not clones:
            logger.warning(f"No {'active ' if only_active else ''}clones to cycle on {self.serial}")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        if shuffle:
            random.shuffle(clones)

        logger.info(f"🔄 Starting clone cycle: {len(clones)} clones on {self.serial}")

        results = {
            "total": len(clones),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

        for i, clone in enumerate(clones):
            package = clone["package_name"]
            clone_id = clone["id"]
            account_id = clone.get("account_id")
            label = clone.get("clone_label", package)

            logger.info(f"\n   ── Clone {i + 1}/{len(clones)}: {label} ──")

            # Open clone
            opened = self.open_clone(package)

            if not opened:
                results["failed"] += 1
                results["details"].append({
                    "package": package,
                    "status": "failed_to_open",
                })
                continue

            # Execute callback
            if callback:
                try:
                    callback(package, clone_id, account_id)
                    results["success"] += 1
                    results["details"].append({
                        "package": package,
                        "status": "success",
                    })

                    # Reset consecutive errors on success
                    self._reset_clone_errors(package)

                except Exception as e:
                    logger.error(f"   ❌ Callback error on {package}: {e}")
                    results["failed"] += 1
                    results["details"].append({
                        "package": package,
                        "status": "callback_error",
                        "error": str(e),
                    })
                    self._increment_clone_error(package, str(e))
            else:
                results["success"] += 1
                results["details"].append({
                    "package": package,
                    "status": "opened_no_callback",
                })

            # Close clone
            self.close_current_clone()

            # Wait between clones (human-like)
            if i < len(clones) - 1:
                delay = random.uniform(delay_between_clones_min, delay_between_clones_max)
                logger.info(f"   ⏳ Waiting {delay:.0f}s before next clone...")
                time.sleep(delay)

        logger.info(f"\n🔄 Clone cycle complete: "
                     f"{results['success']} success, "
                     f"{results['failed']} failed, "
                     f"{results['skipped']} skipped")

        return results

    # ══════════════════════════════════════════════
    #   CLONE STATE CHECKS
    # ══════════════════════════════════════════════

    def is_clone_open(self, package_name: str) -> bool:
        """Check if a specific clone is currently in foreground."""
        current = self.executor.get_current_app()
        return package_name in current

    def get_current_clone(self) -> Optional[str]:
        """Get the currently open clone package name."""
        return self.current_clone_package

    def get_current_clone_id(self) -> Optional[int]:
        """Get the database ID of the currently open clone."""
        return self.current_clone_id

    # ══════════════════════════════════════════════
    #   DATABASE UPDATES
    # ══════════════════════════════════════════════

    def _update_clone_last_opened(self, package_name: str):
        """Update the last_opened timestamp for a clone."""
        session = db_manager.get_session()
        try:
            clone = session.query(Clone).filter_by(
                device_id=self.device_id,
                package_name=package_name,
            ).first()
            if clone:
                clone.last_opened = datetime.now()
                clone.consecutive_errors = 0
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update clone last_opened: {e}")
        finally:
            session.close()

    def _increment_clone_error(self, package_name: str, error_msg: str):
        """Increment error count for a clone."""
        session = db_manager.get_session()
        try:
            clone = session.query(Clone).filter_by(
                device_id=self.device_id,
                package_name=package_name,
            ).first()
            if clone:
                clone.error_count = (clone.error_count or 0) + 1
                clone.consecutive_errors = (clone.consecutive_errors or 0) + 1
                clone.last_error = error_msg
                clone.updated_at = datetime.now()

                # Auto-disable clone after too many consecutive errors
                if clone.consecutive_errors >= 5:
                    clone.status = CloneStatus.ERROR
                    logger.warning(f"   ⚠️  Clone {package_name} disabled after 5 consecutive errors")

                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update clone error: {e}")
        finally:
            session.close()

    def _reset_clone_errors(self, package_name: str):
        """Reset consecutive error count on success."""
        session = db_manager.get_session()
        try:
            clone = session.query(Clone).filter_by(
                device_id=self.device_id,
                package_name=package_name,
            ).first()
            if clone:
                clone.consecutive_errors = 0
                clone.last_successful_task = datetime.now()
                if clone.status == CloneStatus.ERROR:
                    clone.status = CloneStatus.ACTIVE
                session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()

    def link_account_to_clone(self, package_name: str, account_id: int):
        """Link an account to a clone in the database."""
        session = db_manager.get_session()
        try:
            clone = session.query(Clone).filter_by(
                device_id=self.device_id,
                package_name=package_name,
            ).first()

            if clone:
                # Unlink previous account if any
                old_account_id = clone.account_id

                clone.account_id = account_id
                clone.has_account = True
                clone.status = CloneStatus.ACTIVE

                # Update account's clone reference
                account = session.query(Account).filter_by(id=account_id).first()
                if account:
                    account.clone_id = clone.id
                    account.device_id = self.device_id

                session.commit()
                logger.info(f"   🔗 Linked account #{account_id} to clone {package_name}")

                # Refresh clone list cache
                self.load_clones_from_db()

                return True

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to link account to clone: {e}")
        finally:
            session.close()

        return False

    def unlink_account_from_clone(self, package_name: str):
        """Unlink account from a clone."""
        session = db_manager.get_session()
        try:
            clone = session.query(Clone).filter_by(
                device_id=self.device_id,
                package_name=package_name,
            ).first()

            if clone:
                old_account_id = clone.account_id
                clone.account_id = None
                clone.has_account = False
                clone.status = CloneStatus.EMPTY

                # Update account's clone reference
                if old_account_id:
                    account = session.query(Account).filter_by(id=old_account_id).first()
                    if account:
                        account.clone_id = None

                session.commit()
                logger.info(f"   🔓 Unlinked account from clone {package_name}")

                self.load_clones_from_db()
                return True

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to unlink account from clone: {e}")
        finally:
            session.close()

        return False