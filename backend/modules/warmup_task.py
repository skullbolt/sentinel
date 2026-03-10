"""
Warmup Task Module
==================
Automates the first 3 days of account warmup.

DAILY STRUCTURE:
  Total active: 25-35 minutes
  Split into sessions: 5-12 minutes each
  Gaps between sessions: 2-5 minutes (app closed)

TIME DISTRIBUTION:
  70% — Reels (primary activity)
  25% — Home Feed (scroll posts/reels from followed accounts)
   5% — Explore Page (browse trending content)

REELS BEHAVIOR:
  - Watch reels at variable speed (human pattern)
  - Like 2-4 reels per batch of 10
  - Sometimes open comments → scroll → close
  - Sometimes open user profile → scroll → back
  - Sometimes refresh the reel feed
  - Follow exactly 1 account per day at random time
  - Sometimes navigate: Reels → Home Feed → Reels

HOME FEED BEHAVIOR:
  - Scroll through posts and reels
  - Sometimes tap on a post/reel to view fullscreen
  - Sometimes like content
  - Sometimes refresh feed

EXPLORE PAGE BEHAVIOR:
  - Scroll through grid content
  - Sometimes tap on a post/reel to view it
  - Watch briefly then close and go back
"""

from __future__ import annotations

import time
import random
import logging
from datetime import datetime
from typing import Dict

from backend.modules.adb_executor import ADBExecutor
from backend.modules.screen_reader import ScreenReader
from backend.modules.instagram_actions import InstagramActions
from backend.modules.account_manager import AccountManager

logger = logging.getLogger("WarmupTask")


class WarmupTask:
    """
    Runs warmup automation for one account for one day.
    Call run() to execute the full day's warmup.
    """

    def __init__(
        self,
        executor: ADBExecutor,
        reader: ScreenReader,
        account_manager: AccountManager,
        account_id: int,
        instagram_package: str = "com.instagram.android",
    ):
        self.executor = executor
        self.reader = reader
        self.account_manager = account_manager
        self.account_id = account_id
        self.instagram_package = instagram_package
        self.actions = InstagramActions(executor, reader)

        # Day tracking
        self.reels_seen = 0
        self.reels_liked = 0
        self.home_posts_seen = 0
        self.home_posts_liked = 0
        self.explore_posts_seen = 0
        self.followed_today = False
        self.session_count = 0
        self.total_active_seconds = 0

        # Config (can be overridden for testing)
        self.total_day_minutes_min = 25
        self.total_day_minutes_max = 35
        self.session_minutes_min = 5
        self.session_minutes_max = 12
        self.gap_minutes_min = 2
        self.gap_minutes_max = 5

    def run(self) -> Dict:
        """
        Run the full warmup for one day.
        Returns summary of what was done.
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🌅 Starting warmup day for account #{self.account_id}")
        logger.info(f"{'='*60}")

        # Check account state
        self.account_manager.check_auto_transitions(self.account_id)
        can_act, reason = self.account_manager.can_perform_action(self.account_id, "like")
        if not can_act and reason != "ok":
            if "banned" in reason or "paused" in reason:
                logger.warning(f"   ⚠️ Skipping: {reason}")
                return {"status": "skipped", "reason": reason}

        # Reset counters
        self.account_manager.reset_daily_counters_if_needed(self.account_id)
        self.account_manager.start_session(self.account_id)
        day_start = datetime.now()

        # Calculate today's total active time
        total_target_seconds = random.uniform(
            self.total_day_minutes_min * 60,
            self.total_day_minutes_max * 60,
        )

        logger.info(f"   Target active time: {total_target_seconds / 60:.1f} minutes")

        try:
            while self.total_active_seconds < total_target_seconds:
                remaining = total_target_seconds - self.total_active_seconds
                session_max = min(self.session_minutes_max * 60, remaining)
                session_min = min(self.session_minutes_min * 60, session_max)

                if session_min < 60:
                    break

                session_duration = random.uniform(session_min, session_max)
                self.session_count += 1

                logger.info(f"\n{'─'*50}")
                logger.info(f"📍 Session {self.session_count} ({session_duration / 60:.1f} min)")
                logger.info(f"{'─'*50}")

                self._run_session(session_duration)
                self.total_active_seconds += session_duration

                remaining_after = total_target_seconds - self.total_active_seconds
                if remaining_after < 60:
                    break

                # Gap between sessions — app closed
                gap = random.uniform(
                    self.gap_minutes_min * 60,
                    self.gap_minutes_max * 60,
                )
                logger.info(f"\n   ⏸️ Gap: closing app for {gap / 60:.1f} minutes")
                self.actions.close_instagram(self.instagram_package)
                time.sleep(gap)

        except Exception as e:
            logger.error(f"❌ Warmup error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.actions.close_instagram(self.instagram_package)
            total_minutes = int((datetime.now() - day_start).total_seconds() / 60)
            self.account_manager.end_session(self.account_id, total_minutes)

        # Summary
        summary = {
            "status": "completed",
            "account_id": self.account_id,
            "sessions": self.session_count,
            "total_active_minutes": round(self.total_active_seconds / 60, 1),
            "reels_seen": self.reels_seen,
            "reels_liked": self.reels_liked,
            "home_posts_seen": self.home_posts_seen,
            "home_posts_liked": self.home_posts_liked,
            "explore_posts_seen": self.explore_posts_seen,
            "followed": self.followed_today,
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"🌙 Warmup day complete for account #{self.account_id}")
        logger.info(f"   Sessions:        {summary['sessions']}")
        logger.info(f"   Active time:     {summary['total_active_minutes']} min")
        logger.info(f"   Reels seen:      {summary['reels_seen']}")
        logger.info(f"   Reels liked:     {summary['reels_liked']}")
        logger.info(f"   Home posts seen: {summary['home_posts_seen']}")
        logger.info(f"   Home posts liked:{summary['home_posts_liked']}")
        logger.info(f"   Explore seen:    {summary['explore_posts_seen']}")
        logger.info(f"   Followed:        {summary['followed']}")
        logger.info(f"{'='*60}\n")

        return summary

    def _run_session(self, duration_seconds: float):
        """Run a single session within the day."""
        session_start = time.time()

        # Open Instagram
        if not self.actions.open_instagram(self.instagram_package):
            logger.error("   Failed to open Instagram")
            return

        time.sleep(random.uniform(1, 2))
        self.actions.dismiss_popups()

        # Start each session from Home Feed (natural — that's where IG opens)
        # Then navigate to activity
        time.sleep(random.uniform(1, 3))

        while (time.time() - session_start) < duration_seconds:
            remaining = duration_seconds - (time.time() - session_start)
            if remaining < 15:
                break

            activity = self._pick_activity()

            try:
                if activity == "reels":
                    reel_time = min(remaining, random.uniform(40, 150))
                    self._browse_reels(reel_time)

                elif activity == "home_feed":
                    feed_time = min(remaining, random.uniform(25, 80))
                    self._browse_home_feed(feed_time)

                elif activity == "explore":
                    explore_time = min(remaining, random.uniform(20, 50))
                    self._browse_explore(explore_time)

            except Exception as e:
                logger.warning(f"   ⚠️ Activity error: {e}")
                self.actions.ensure_instagram_open(self.instagram_package)
                self.actions.dismiss_popups()
                time.sleep(random.uniform(1, 2))

    def _pick_activity(self) -> str:
        """
        Pick next activity based on weighted distribution.
        70% reels, 25% home feed, 5% explore
        """
        roll = random.random()
        if roll < 0.70:
            return "reels"
        elif roll < 0.95:
            return "home_feed"
        else:
            return "explore"

    # ══════════════════════════════════════════════
    #   BROWSE REELS
    # ══════════════════════════════════════════════

    def _browse_reels(self, duration_seconds: float):
        """Browse reels with natural random interactions."""
        logger.info(f"   🎬 Browsing reels for {duration_seconds:.0f}s")

        # Sometimes go to home feed first, then reels (natural navigation)
        if random.random() < 0.25:
            logger.info("   🏠→🎬 Going Home first, then Reels")
            self.actions.go_to_home_feed()
            time.sleep(random.uniform(1, 3))
            # Scroll home briefly
            for _ in range(random.randint(1, 3)):
                self.actions.scroll_home_feed()
            self.actions.go_to_reels()
        else:
            self.actions.go_to_reels()

        time.sleep(random.uniform(1, 2))

        start = time.time()
        reels_in_batch = 0
        likes_in_batch = 0

        while (time.time() - start) < duration_seconds:
            remaining = duration_seconds - (time.time() - start)
            if remaining < 5:
                break

            # Watch current reel
            self.actions.watch_current_reel()
            self.reels_seen += 1
            reels_in_batch += 1

            # ── RANDOM LIKE (2-4 per 10 reels = 20-40%) ──
            if reels_in_batch <= 10:
                like_rate = random.uniform(0.20, 0.40)
                if random.random() < like_rate and likes_in_batch < 4:
                    can_like, _ = self.account_manager.can_perform_action(
                        self.account_id, "like"
                    )
                    if can_like:
                        self.actions.like_current_content()
                        self.account_manager.record_action(
                            self.account_id, "like",
                            success=True,
                            action_data={"source": "reels"},
                        )
                        self.reels_liked += 1
                        likes_in_batch += 1
            else:
                reels_in_batch = 0
                likes_in_batch = 0

            # ── RANDOM: Open comments (8%) ──
            if random.random() < 0.08 and remaining > 15:
                self.actions.open_reel_comments()
                self.actions.scroll_comments()
                self.actions.close_comments()
                time.sleep(random.uniform(0.5, 1.5))

            # ── RANDOM: Open user profile (6%) ──
            if random.random() < 0.06 and remaining > 20:
                self.actions.open_reel_user_profile()
                time.sleep(random.uniform(1.5, 3.0))

                # Follow decision (1 per day max, random timing)
                if not self.followed_today and random.random() < 0.15:
                    can_follow, _ = self.account_manager.can_perform_action(
                        self.account_id, "follow"
                    )
                    if can_follow:
                        success = self.actions.follow_user()
                        if success:
                            self.account_manager.record_action(
                                self.account_id, "follow",
                                success=True,
                                action_data={"source": "reels_profile"},
                            )
                            self.followed_today = True

                self.actions.scroll_profile(random.randint(1, 3))
                self.actions.go_back()
                time.sleep(random.uniform(1, 2))

                # May need double back press
                if not self.actions.is_instagram_open(self.instagram_package):
                    self.actions.ensure_instagram_open(self.instagram_package)
                else:
                    screen = self.reader.detect_current_screen()
                    if screen != InstagramScreen.REELS:
                        self.actions.go_back()
                        time.sleep(1)

            # ── RANDOM: Refresh reels feed (4%) ──
            if random.random() < 0.04 and remaining > 10:
                self.actions.refresh_reels_feed()

            # Scroll to next reel
            self.actions.scroll_to_next_reel()
            time.sleep(random.uniform(0.3, 1.0))

    # ══════════════════════════════════════════════
    #   BROWSE HOME FEED
    # ══════════════════════════════════════════════

    def _browse_home_feed(self, duration_seconds: float):
        """Browse home feed with natural interactions."""
        logger.info(f"   🏠 Browsing home feed for {duration_seconds:.0f}s")

        self.actions.go_to_home_feed()
        time.sleep(random.uniform(1, 2))

        start = time.time()

        while (time.time() - start) < duration_seconds:
            remaining = duration_seconds - (time.time() - start)
            if remaining < 5:
                break

            # Scroll feed
            self.actions.scroll_home_feed()
            self.home_posts_seen += 1

            # ── RANDOM: Tap on a post/reel to view fullscreen (12%) ──
            if random.random() < 0.12 and remaining > 10:
                self.actions.tap_home_feed_post()
                self.actions.watch_home_feed_content()

                # Sometimes like the fullscreen content (30% when opened)
                if random.random() < 0.30:
                    can_like, _ = self.account_manager.can_perform_action(
                        self.account_id, "like"
                    )
                    if can_like:
                        self.actions.like_current_content()
                        self.account_manager.record_action(
                            self.account_id, "like",
                            success=True,
                            action_data={"source": "home_feed"},
                        )
                        self.home_posts_liked += 1

                # Go back from fullscreen
                self.actions.go_back()
                time.sleep(random.uniform(0.5, 1.5))

            # ── RANDOM: Like directly in feed (8%) ──
            elif random.random() < 0.08:
                can_like, _ = self.account_manager.can_perform_action(
                    self.account_id, "like"
                )
                if can_like:
                    self.actions.like_current_content()
                    self.account_manager.record_action(
                        self.account_id, "like",
                        success=True,
                        action_data={"source": "home_feed_scroll"},
                    )
                    self.home_posts_liked += 1

            # ── RANDOM: Refresh home feed (5%) ──
            if random.random() < 0.05 and remaining > 10:
                self.actions.refresh_home_feed()

    # ══════════════════════════════════════════════
    #   BROWSE EXPLORE PAGE
    # ══════════════════════════════════════════════

    def _browse_explore(self, duration_seconds: float):
        """Browse explore page with natural interactions."""
        logger.info(f"   🔍 Browsing explore for {duration_seconds:.0f}s")

        self.actions.go_to_explore()
        time.sleep(random.uniform(1, 2))

        start = time.time()

        while (time.time() - start) < duration_seconds:
            remaining = duration_seconds - (time.time() - start)
            if remaining < 5:
                break

            # Scroll explore grid
            self.actions.scroll_explore()
            self.explore_posts_seen += 1

            # ── RANDOM: Tap on content to view (15%) ──
            if random.random() < 0.15 and remaining > 10:
                self.actions.tap_explore_content()
                self.actions.watch_explore_content()

                # Sometimes like it (20% when opened)
                if random.random() < 0.20:
                    can_like, _ = self.account_manager.can_perform_action(
                        self.account_id, "like"
                    )
                    if can_like:
                        self.actions.like_current_content()
                        self.account_manager.record_action(
                            self.account_id, "like",
                            success=True,
                            action_data={"source": "explore"},
                        )

                # Go back to explore grid
                self.actions.go_back()
                time.sleep(random.uniform(0.5, 1.5))


# Need this import for screen detection in reels browsing
from backend.modules.screen_reader import InstagramScreen