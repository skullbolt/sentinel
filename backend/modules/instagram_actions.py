"""
Instagram Actions Module
========================
Instagram-specific navigation and interaction.
Combines ScreenReader (eyes) and ADBExecutor (hands).

TERMINOLOGY:
  Home Feed = main feed (posts/reels from followed accounts)
  Explore   = discover page (grid of trending/suggested content)
  Reels     = short video feed (TikTok-style vertical scroll)
"""

from __future__ import annotations

import time
import random
import logging
from typing import Optional, Tuple

from backend.modules.adb_executor import ADBExecutor
from backend.modules.screen_reader import ScreenReader, InstagramScreen

logger = logging.getLogger("InstagramActions")


class InstagramActions:
    """
    High-level Instagram interactions.
    Uses ScreenReader to SEE and ADBExecutor to ACT.
    """

    INSTAGRAM_PACKAGE = "com.instagram.android"

    def __init__(self, executor: ADBExecutor, reader: ScreenReader):
        self.executor = executor
        self.reader = reader
        self.screen_width = executor.config.screen_width
        self.screen_height = executor.config.screen_height

    # ══════════════════════════════════════════════
    #   POSITION HELPERS
    # ══════════════════════════════════════════════

    def _pos(self, x_pct: float, y_pct: float) -> Tuple[int, int]:
        """Convert percentage position to pixel coordinates."""
        return int(self.screen_width * x_pct), int(self.screen_height * y_pct)

    def _bottom_tab_positions(self):
        """Get approximate positions of 5 bottom nav tabs."""
        y = int(self.screen_height * 0.97)
        w = self.screen_width
        return {
            "home": (int(w * 0.10), y),
            "explore": (int(w * 0.30), y),
            "reels": (int(w * 0.50), y),
            "create": (int(w * 0.70), y),
            "profile": (int(w * 0.90), y),
        }

    # ══════════════════════════════════════════════
    #   APP MANAGEMENT
    # ══════════════════════════════════════════════

    def open_instagram(self, package: str = None) -> bool:
        """Open Instagram and wait for it to load."""
        pkg = package or self.INSTAGRAM_PACKAGE
        logger.info(f"📱 Opening Instagram: {pkg}")
        self.executor.open_app(pkg)
        time.sleep(random.uniform(3, 5))

        for attempt in range(3):
            if self.executor.is_app_running(pkg):
                logger.info("   ✅ Instagram is open")
                time.sleep(random.uniform(1, 2))
                return True
            time.sleep(2)

        logger.error("   ❌ Instagram failed to open")
        return False

    def close_instagram(self, package: str = None):
        """Close Instagram."""
        pkg = package or self.INSTAGRAM_PACKAGE
        logger.info("📱 Closing Instagram")
        self.executor.close_app(pkg)
        time.sleep(random.uniform(0.5, 1.5))

    def is_instagram_open(self, package: str = None) -> bool:
        """Check if Instagram is in foreground."""
        pkg = package or self.INSTAGRAM_PACKAGE
        return self.executor.is_app_running(pkg)

    # ══════════════════════════════════════════════
    #   NAVIGATION
    # ══════════════════════════════════════════════

    def go_to_reels(self) -> bool:
        """Navigate to the Reels tab."""
        logger.info("   🎬 Navigating to Reels")

        pos = self.reader.find_bottom_tab("Reels")
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=80, element_height=80)
        else:
            tabs = self._bottom_tab_positions()
            x, y = tabs["reels"]
            self.executor.tap(x, y, element_width=80, element_height=80)

        time.sleep(random.uniform(1.5, 3.0))

        # Sometimes need a second tap
        pos = self.reader.find_bottom_tab("Reels")
        if pos:
            pass  # Already on reels
        else:
            tabs = self._bottom_tab_positions()
            x, y = tabs["reels"]
            self.executor.tap(x, y, element_width=80, element_height=80)
            time.sleep(1)

        logger.info("   ✅ On Reels")
        return True

    def go_to_home_feed(self) -> bool:
        """Navigate to the Home Feed (main feed with posts from followed accounts)."""
        logger.info("   🏠 Navigating to Home Feed")

        pos = self.reader.find_bottom_tab("Home")
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=80, element_height=80)
        else:
            tabs = self._bottom_tab_positions()
            x, y = tabs["home"]
            self.executor.tap(x, y, element_width=80, element_height=80)

        time.sleep(random.uniform(1.5, 2.5))
        logger.info("   ✅ On Home Feed")
        return True

    def go_to_explore(self) -> bool:
        """Navigate to the Explore page (trending/suggested content grid)."""
        logger.info("   🔍 Navigating to Explore")

        pos = self.reader.find_bottom_tab("Search")
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=80, element_height=80)
        else:
            tabs = self._bottom_tab_positions()
            x, y = tabs["explore"]
            self.executor.tap(x, y, element_width=80, element_height=80)

        time.sleep(random.uniform(1.5, 3.0))
        logger.info("   ✅ On Explore")
        return True

    def go_back(self) -> bool:
        """Press back / navigate back."""
        pos = self.reader.find_back_button()
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=60, element_height=60)
        else:
            self.executor.press_back()
        time.sleep(random.uniform(0.8, 1.5))
        return True

    # ══════════════════════════════════════════════
    #   REEL INTERACTIONS
    # ══════════════════════════════════════════════

    def scroll_to_next_reel(self):
        """Swipe up to next reel."""
        self.executor.scroll_up()
        time.sleep(random.uniform(0.3, 0.8))

    def watch_current_reel(self, duration_seconds: float = None):
        """
        Watch current reel for random duration.
        
        Human viewing pattern:
          40% — Quick scroll (0.5-2s)
          35% — Partial watch (3-8s)
          17% — Full watch (10-20s)
           8% — Extended watch (20-35s)
        """
        if duration_seconds is None:
            roll = random.random()
            if roll < 0.40:
                duration_seconds = random.uniform(0.5, 2.0)
            elif roll < 0.75:
                duration_seconds = random.uniform(3.0, 8.0)
            elif roll < 0.92:
                duration_seconds = random.uniform(10.0, 20.0)
            else:
                duration_seconds = random.uniform(20.0, 35.0)

        logger.debug(f"   👀 Watching reel for {duration_seconds:.1f}s")
        time.sleep(duration_seconds)

    def like_current_content(self) -> bool:
        """Double-tap to like current reel or post."""
        logger.info("   ❤️ Liking content (double tap)")
        cx = self.screen_width // 2
        cy = int(self.screen_height * 0.45)
        self.executor.double_tap(cx, cy, element_width=300, element_height=300)
        time.sleep(random.uniform(0.5, 1.5))
        return True

    def open_reel_comments(self) -> bool:
        """Open comments section of current reel."""
        logger.info("   💬 Opening comments")

        pos = self.reader.find_comment_button()
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=60, element_height=60)
        else:
            x = int(self.screen_width * 0.93)
            y = int(self.screen_height * 0.55)
            self.executor.tap(x, y, element_width=60, element_height=60)

        time.sleep(random.uniform(1.5, 3.0))
        return True

    def scroll_comments(self, scroll_count: int = None):
        """Scroll through comments section."""
        if scroll_count is None:
            scroll_count = random.randint(2, 6)

        logger.info(f"   💬 Scrolling comments ({scroll_count} scrolls)")
        for i in range(scroll_count):
            self.executor.scroll_up()
            time.sleep(random.uniform(1.0, 3.0))

    def close_comments(self):
        """Close comments section."""
        logger.info("   💬 Closing comments")

        pos = self.reader.find_close_comments_button()
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=60, element_height=60)
        else:
            # Swipe down to close
            self.executor.swipe(
                self.screen_width // 2,
                int(self.screen_height * 0.3),
                self.screen_width // 2,
                int(self.screen_height * 0.8),
                random.randint(200, 400),
            )

        time.sleep(random.uniform(0.8, 1.5))

    def open_reel_user_profile(self) -> bool:
        """Tap on username on current reel to open profile."""
        logger.info("   👤 Opening reel user's profile")

        pos = self.reader.find_username_on_reel()
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=200, element_height=40)
        else:
            x = int(self.screen_width * 0.15)
            y = int(self.screen_height * 0.87)
            self.executor.tap(x, y, element_width=200, element_height=40)

        time.sleep(random.uniform(2.0, 4.0))
        return True

    def scroll_profile(self, scroll_count: int = None):
        """Scroll through a user's profile."""
        if scroll_count is None:
            scroll_count = random.randint(2, 5)

        logger.info(f"   👤 Scrolling profile ({scroll_count} scrolls)")
        for i in range(scroll_count):
            self.executor.scroll_up()
            time.sleep(random.uniform(1.0, 3.0))

    def follow_user(self) -> bool:
        """Follow user on currently visible profile."""
        logger.info("   ➕ Following user")

        if self.reader.is_following():
            logger.info("   Already following, skipping")
            return False

        pos = self.reader.find_follow_button()
        if pos:
            self.executor.tap(pos[0], pos[1], element_width=150, element_height=50)
            time.sleep(random.uniform(1.0, 2.0))
            logger.info("   ✅ Followed!")
            return True
        else:
            logger.warning("   ⚠️ Follow button not found")
            return False

    def refresh_reels_feed(self):
        """Pull down to refresh reels feed."""
        logger.info("   🔄 Refreshing reels feed")
        # Pull down gesture (swipe from top to bottom)
        self.executor.swipe(
            self.screen_width // 2 + random.randint(-50, 50),
            int(self.screen_height * 0.15),
            self.screen_width // 2 + random.randint(-50, 50),
            int(self.screen_height * 0.75),
            random.randint(300, 600),
        )
        time.sleep(random.uniform(2.0, 4.0))

    # ══════════════════════════════════════════════
    #   HOME FEED INTERACTIONS
    # ══════════════════════════════════════════════

    def scroll_home_feed(self):
        """Scroll through the home feed."""
        self.executor.scroll_up()
        time.sleep(random.uniform(1.5, 4.0))

        # Sometimes pause longer (reading a post)
        if random.random() < 0.20:
            time.sleep(random.uniform(2.0, 6.0))

    def tap_home_feed_post(self):
        """Tap on a post/reel in the home feed to view it fullscreen."""
        logger.info("   📱 Tapping on a feed post")

        # Posts are roughly in center column, variable Y
        x = self.screen_width // 2 + random.randint(-100, 100)
        y = int(self.screen_height * random.uniform(0.30, 0.60))

        self.executor.tap(x, y, element_width=int(self.screen_width * 0.8), element_height=300)
        time.sleep(random.uniform(2, 4))

    def watch_home_feed_content(self, duration: float = None):
        """Watch a post/reel opened from home feed."""
        if duration is None:
            duration = random.uniform(3, 15)
        logger.debug(f"   👀 Watching home feed content for {duration:.1f}s")
        time.sleep(duration)

    def refresh_home_feed(self):
        """Pull down to refresh home feed."""
        logger.info("   🔄 Refreshing home feed")
        self.executor.swipe(
            self.screen_width // 2 + random.randint(-50, 50),
            int(self.screen_height * 0.15),
            self.screen_width // 2 + random.randint(-50, 50),
            int(self.screen_height * 0.75),
            random.randint(300, 600),
        )
        time.sleep(random.uniform(2.0, 4.0))

    # ══════════════════════════════════════════════
    #   EXPLORE PAGE INTERACTIONS
    # ══════════════════════════════════════════════

    def scroll_explore(self):
        """Scroll through explore grid."""
        self.executor.scroll_up()
        time.sleep(random.uniform(1.5, 4.0))

        if random.random() < 0.15:
            time.sleep(random.uniform(2.0, 5.0))

    def tap_explore_content(self):
        """Tap on a random post/reel in the explore grid."""
        col = random.randint(0, 2)
        row = random.randint(0, 2)

        x = int(self.screen_width * (0.17 + col * 0.33))
        y = int(self.screen_height * (0.15 + row * 0.20))

        logger.info(f"   🔍 Tapping explore content at ({x}, {y})")
        self.executor.tap(x, y, element_width=int(self.screen_width * 0.3), element_height=150)
        time.sleep(random.uniform(2, 4))

    def watch_explore_content(self, duration: float = None):
        """Watch content opened from explore page."""
        if duration is None:
            duration = random.uniform(3, 12)
        logger.debug(f"   👀 Watching explore content for {duration:.1f}s")
        time.sleep(duration)

    # ══════════════════════════════════════════════
    #   ERROR RECOVERY
    # ══════════════════════════════════════════════

    def dismiss_popups(self):
        """Try to dismiss any popups/dialogs."""
        dismiss_texts = [
            "Not Now", "Not now", "Cancel", "Dismiss",
            "Close", "OK", "Got It", "Maybe Later",
            "Skip", "No Thanks", "No thanks",
        ]

        for text in dismiss_texts:
            if self.reader.element_exists(text=text, timeout=0.2):
                pos = self.reader.find_element_center(text=text, timeout=0.3)
                if pos:
                    logger.info(f"   🚫 Dismissing popup: '{text}'")
                    self.executor.tap(pos[0], pos[1], element_width=150, element_height=50)
                    time.sleep(random.uniform(0.5, 1.0))
                    return True
        return False

    def ensure_instagram_open(self, package: str = None) -> bool:
        """Make sure Instagram is open, reopen if needed."""
        pkg = package or self.INSTAGRAM_PACKAGE
        if not self.executor.is_app_running(pkg):
            logger.warning("   ⚠️ Instagram not in foreground, reopening...")
            return self.open_instagram(pkg)
        return True