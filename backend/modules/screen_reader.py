"""
Screen Reader Module
====================
Reads the Android screen using uiautomator2 (READ ONLY).
All actions are performed via ADB Executor (separate module).

Uses uiautomator2 to:
  - Detect which Instagram screen is showing
  - Find UI elements and their positions
  - Read text from screen
  - Check element states (liked/followed etc.)
"""

from __future__ import annotations

import uiautomator2 as u2
import time
import logging
from typing import Optional, Dict, Tuple, List
from enum import Enum

logger = logging.getLogger("ScreenReader")


class InstagramScreen(str, Enum):
    HOME = "home"
    REELS = "reels"
    EXPLORE = "explore"
    SEARCH = "search"
    PROFILE = "profile"
    PROFILE_OTHER = "profile_other"
    COMMENTS = "comments"
    POST_DETAIL = "post_detail"
    DIRECT_MESSAGES = "dm"
    LOGIN = "login"
    STORY = "story"
    UNKNOWN = "unknown"


class ScreenReader:
    """
    Reads the screen state using uiautomator2.
    ONLY reads — never performs actions.
    """

    INSTAGRAM_PACKAGE = "com.instagram.android"

    def __init__(self, serial: str):
        self.serial = serial
        self._device = None
        self._connected = False

    def connect(self):
        """Connect uiautomator2 to device."""
        try:
            self._device = u2.connect(self.serial)
            self._connected = True
            logger.info(f"👁️ ScreenReader connected to {self.serial}")
        except Exception as e:
            logger.error(f"ScreenReader connection failed: {e}")
            self._connected = False

    def disconnect(self):
        """Disconnect uiautomator2."""
        self._device = None
        self._connected = False

    @property
    def device(self):
        if not self._connected or not self._device:
            self.connect()
        return self._device

    # ══════════════════════════════════════════════
    #   SCREEN DETECTION
    # ══════════════════════════════════════════════

    def detect_current_screen(self) -> InstagramScreen:
        """
        Detect which Instagram screen is currently showing.
        Uses multiple signals for reliability.
        """
        try:
            d = self.device

            # Check if Instagram is even in foreground
            current = d.app_current()
            if self.INSTAGRAM_PACKAGE not in current.get("package", ""):
                return InstagramScreen.UNKNOWN

            # Check for comments overlay first (it appears on top)
            if self._is_comments_screen(d):
                return InstagramScreen.COMMENTS

            # Check for story viewer
            if self._is_story_screen(d):
                return InstagramScreen.STORY

            # Check bottom navigation to determine main screen
            # Instagram bottom tabs have content descriptions

            # Check for Reels
            if self._is_reels_screen(d):
                return InstagramScreen.REELS

            # Check for Explore/Search
            if self._is_explore_screen(d):
                return InstagramScreen.EXPLORE

            if self._is_search_screen(d):
                return InstagramScreen.SEARCH

            # Check for Profile
            if self._is_profile_screen(d):
                return InstagramScreen.PROFILE

            # Check for other user's profile
            if self._is_other_profile_screen(d):
                return InstagramScreen.PROFILE_OTHER

            # Check for Home feed
            if self._is_home_screen(d):
                return InstagramScreen.HOME

            # Check for Login
            if self._is_login_screen(d):
                return InstagramScreen.LOGIN

            return InstagramScreen.UNKNOWN

        except Exception as e:
            logger.error(f"Screen detection error: {e}")
            return InstagramScreen.UNKNOWN

    def _is_reels_screen(self, d) -> bool:
        """Check if we're on the Reels tab."""
        # Reels has the camera icon and music info at bottom
        # Also check if reels tab is selected
        try:
            # Check for reel-specific elements
            if d(descriptionContains="Reel").exists(timeout=0.5):
                return True
            if d(resourceIdMatches=".*reel.*").exists(timeout=0.3):
                return True
            # Check for like/comment/share column on right side (reels layout)
            if d(descriptionContains="Like").exists(timeout=0.3) and \
               d(descriptionContains="Comment").exists(timeout=0.3):
                # Could be reels or post - check if it's full screen
                if d(resourceIdMatches=".*clips.*|.*reel.*").exists(timeout=0.3):
                    return True
                # If like and comment exist vertically on right side = reels
                return True
        except:
            pass
        return False

    def _is_explore_screen(self, d) -> bool:
        """Check if we're on the Explore page."""
        try:
            if d(descriptionContains="Search and explore").exists(timeout=0.3):
                # Check if we're showing grid content (not search input)
                if not d(resourceIdMatches=".*search.*edit.*text.*").exists(timeout=0.3):
                    return True
        except:
            pass
        return False

    def _is_search_screen(self, d) -> bool:
        """Check if search bar is active/focused."""
        try:
            if d(resourceIdMatches=".*search.*edit.*text.*").exists(timeout=0.3):
                return True
            if d(textContains="Search").exists(timeout=0.3) and \
               d(resourceIdMatches=".*action_bar.*search.*").exists(timeout=0.3):
                return True
        except:
            pass
        return False

    def _is_home_screen(self, d) -> bool:
        """Check if we're on the Home feed."""
        try:
            # Home has the Instagram logo or camera icon at top
            if d(descriptionContains="Instagram").exists(timeout=0.3) or \
               d(descriptionContains="Camera").exists(timeout=0.3):
                return True
        except:
            pass
        return False

    def _is_profile_screen(self, d) -> bool:
        """Check if we're on own profile."""
        try:
            if d(descriptionContains="Profile").exists(timeout=0.3) and \
               d(textContains="Edit profile").exists(timeout=0.3):
                return True
        except:
            pass
        return False

    def _is_other_profile_screen(self, d) -> bool:
        """Check if we're on another user's profile."""
        try:
            if d(textContains="Follow").exists(timeout=0.3) or \
               d(textContains="Following").exists(timeout=0.3):
                if d(textContains="posts").exists(timeout=0.3) or \
                   d(textContains="followers").exists(timeout=0.3):
                    return True
        except:
            pass
        return False

    def _is_comments_screen(self, d) -> bool:
        """Check if comments section is open."""
        try:
            if d(textContains="Comments").exists(timeout=0.3) and \
               d(resourceIdMatches=".*comment.*").exists(timeout=0.3):
                return True
        except:
            pass
        return False

    def _is_story_screen(self, d) -> bool:
        """Check if viewing a story."""
        try:
            if d(resourceIdMatches=".*story.*|.*reel_viewer.*").exists(timeout=0.3):
                return True
        except:
            pass
        return False

    def _is_login_screen(self, d) -> bool:
        """Check if on login screen."""
        try:
            if d(textContains="Log in").exists(timeout=0.3) or \
               d(textContains="Sign up").exists(timeout=0.3):
                return True
        except:
            pass
        return False

    # ══════════════════════════════════════════════
    #   ELEMENT FINDING
    # ══════════════════════════════════════════════

    def find_element_bounds(self, **kwargs) -> Optional[Dict]:
        """
        Find an element and return its bounds.
        
        Returns dict with: left, top, right, bottom, center_x, center_y, width, height
        Or None if not found.
        
        Usage:
            bounds = reader.find_element_bounds(text="Follow")
            bounds = reader.find_element_bounds(descriptionContains="Like")
            bounds = reader.find_element_bounds(resourceId="com.instagram.android:id/...")
        """
        try:
            timeout = kwargs.pop("timeout", 1.0)
            element = self.device(**kwargs)
            if element.exists(timeout=timeout):
                info = element.info
                bounds = info["bounds"]
                left = bounds["left"]
                top = bounds["top"]
                right = bounds["right"]
                bottom = bounds["bottom"]
                return {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "center_x": (left + right) // 2,
                    "center_y": (top + bottom) // 2,
                    "width": right - left,
                    "height": bottom - top,
                }
            return None
        except Exception as e:
            logger.debug(f"Element not found: {e}")
            return None

    def find_element_center(self, **kwargs) -> Optional[Tuple[int, int]]:
        """Find element and return center (x, y) coordinates."""
        bounds = self.find_element_bounds(**kwargs)
        if bounds:
            return bounds["center_x"], bounds["center_y"]
        return None

    def element_exists(self, **kwargs) -> bool:
        """Check if an element exists on screen."""
        try:
            timeout = kwargs.pop("timeout", 0.5)
            return self.device(**kwargs).exists(timeout=timeout)
        except:
            return False

    # ══════════════════════════════════════════════
    #   INSTAGRAM-SPECIFIC ELEMENT FINDING
    # ══════════════════════════════════════════════

    def find_bottom_tab(self, tab_name: str) -> Optional[Tuple[int, int]]:
        """
        Find a bottom navigation tab.
        tab_name: "Home", "Search", "Reels", "Create", "Profile"
        """
        # Try by content description
        descriptions = {
            "Home": ["Home", "home"],
            "Search": ["Search and explore", "Search"],
            "Reels": ["Reels", "reels"],
            "Create": ["Create", "New post", "Camera"],
            "Profile": ["Profile", "profile"],
        }

        for desc in descriptions.get(tab_name, [tab_name]):
            pos = self.find_element_center(descriptionContains=desc, timeout=0.5)
            if pos:
                return pos

        return None

    def find_like_button(self) -> Optional[Tuple[int, int]]:
        """Find the Like button on current screen."""
        pos = self.find_element_center(descriptionContains="Like", timeout=0.5)
        if pos:
            return pos
        return None

    def find_comment_button(self) -> Optional[Tuple[int, int]]:
        """Find the Comment button."""
        pos = self.find_element_center(descriptionContains="Comment", timeout=0.5)
        if pos:
            return pos
        return None

    def find_follow_button(self) -> Optional[Tuple[int, int]]:
        """Find the Follow button on a profile."""
        # Try exact "Follow" text (not "Following" or "Follow back")
        pos = self.find_element_center(text="Follow", timeout=0.5)
        if pos:
            return pos
        return None

    def is_following(self) -> bool:
        """Check if already following on current profile."""
        return self.element_exists(text="Following", timeout=0.5) or \
               self.element_exists(text="Requested", timeout=0.3)

    def find_username_on_reel(self) -> Optional[Tuple[int, int]]:
        """Find the username overlay on a reel."""
        pos = self.find_element_center(
            resourceIdMatches=".*username.*|.*user_name.*|.*header_user.*",
            timeout=0.5
        )
        if pos:
            return pos
        # Fallback: try finding near bottom-left area
        pos = self.find_element_center(
            resourceIdMatches=".*text_user.*|.*owner.*",
            timeout=0.3
        )
        return pos

    def find_close_comments_button(self) -> Optional[Tuple[int, int]]:
        """Find button to close comments section."""
        # Try X button or close button
        pos = self.find_element_center(descriptionContains="Close", timeout=0.5)
        if pos:
            return pos
        pos = self.find_element_center(descriptionContains="Dismiss", timeout=0.3)
        return pos

    def find_back_button(self) -> Optional[Tuple[int, int]]:
        """Find the back/navigate-up button."""
        pos = self.find_element_center(descriptionContains="Back", timeout=0.5)
        if pos:
            return pos
        pos = self.find_element_center(descriptionContains="Navigate up", timeout=0.3)
        return pos

    def get_screen_size(self) -> Tuple[int, int]:
        """Get device screen size via uiautomator2."""
        try:
            info = self.device.info
            return info["displayWidth"], info["displayHeight"]
        except:
            return 1440, 3120  # fallback