"""
Account Manager Module
======================
Manages Instagram account lifecycle.

Responsibilities:
  - Create/register new accounts in database
  - State machine transitions (warmup → growing → active, etc.)
  - Daily/hourly counter management
  - Rate limit checking
  - Account-clone linking
  - Metrics tracking
  - Auto-detection of new accounts

Usage:
  acct_mgr = AccountManager()
  account = acct_mgr.register_account("user123", clone_id=5, device_id=1)
  acct_mgr.transition_state(account.id, AccountState.WARMUP)
  can_like = acct_mgr.can_perform_action(account.id, "like")
  acct_mgr.record_action(account.id, "like")
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple

from backend.database.connection import db_manager
from backend.database.models import (
    Account, AccountState, AccountStateHistory,
    Clone, CloneStatus, CloneAccountHistory, CloneAccountAction,
    ActionLog, ActionType, AccountMetricsHistory,
    TaskTemplate, FollowTracking, ErrorLog, ErrorType,
)

logger = logging.getLogger("AccountManager")


class AccountManager:
    """
    Manages the complete lifecycle of Instagram accounts.
    
    Handles:
      - Registration & discovery
      - State transitions
      - Action counting & rate limits
      - Counter resets (daily/hourly)
      - Account-clone linking
      - Metrics snapshots
    """

    # ── Default limits per state ──
    STATE_LIMITS = {
        AccountState.WARMUP: {
            "max_likes": 15,
            "max_follows": 3,
            "max_unfollows": 0,
            "max_comments": 0,
            "max_dms": 0,
            "max_stories": 5,
            "max_searches": 5,
            "sessions_per_day": 2,
            "delay_multiplier": 2.0,
        },
        AccountState.GROWING: {
            "max_likes": 50,
            "max_follows": 20,
            "max_unfollows": 10,
            "max_comments": 5,
            "max_dms": 3,
            "max_stories": 15,
            "max_searches": 10,
            "sessions_per_day": 3,
            "delay_multiplier": 1.5,
        },
        AccountState.ACTIVE: {
            "max_likes": 200,
            "max_follows": 100,
            "max_unfollows": 100,
            "max_comments": 50,
            "max_dms": 30,
            "max_stories": 50,
            "max_searches": 30,
            "sessions_per_day": 5,
            "delay_multiplier": 1.0,
        },
        AccountState.COOLDOWN: {
            "max_likes": 0,
            "max_follows": 0,
            "max_unfollows": 0,
            "max_comments": 0,
            "max_dms": 0,
            "max_stories": 3,
            "max_searches": 2,
            "sessions_per_day": 1,
            "delay_multiplier": 3.0,
        },
        AccountState.RESTRICTED: {
            "max_likes": 0,
            "max_follows": 0,
            "max_unfollows": 0,
            "max_comments": 0,
            "max_dms": 0,
            "max_stories": 0,
            "max_searches": 0,
            "sessions_per_day": 0,
            "delay_multiplier": 5.0,
        },
    }

    # ── Hourly limits (applied on top of daily) ──
    HOURLY_LIMITS = {
        "likes": 30,
        "follows": 15,
        "comments": 10,
    }

    # ══════════════════════════════════════════════
    #   ACCOUNT REGISTRATION
    # ══════════════════════════════════════════════

    def register_account(
        self,
        username: str,
        clone_id: Optional[int] = None,
        device_id: Optional[int] = None,
        email: Optional[str] = None,
        phone_number: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Optional[Account]:
        """
        Register a new account or return existing one.
        Sets initial state to LOGGED_IN and starts warmup timer.
        """
        session = db_manager.get_session()
        try:
            # Check if account already exists
            existing = session.query(Account).filter_by(username=username).first()
            if existing:
                logger.info(f"   📋 Account @{username} already exists (ID: {existing.id})")

                # Update clone/device if provided
                if clone_id and existing.clone_id != clone_id:
                    existing.clone_id = clone_id
                if device_id and existing.device_id != device_id:
                    existing.device_id = device_id

                session.commit()

                # Load all attributes before detaching from session
                session.refresh(existing)
                session.expunge(existing)
                return existing

            # Create new account
            now = datetime.now()
            account = Account(
                username=username,
                password_encrypted=password,
                email=email,
                phone_number=phone_number,
                clone_id=clone_id,
                device_id=device_id,
                state=AccountState.LOGGED_IN,
                state_changed_at=now,
                first_login_at=now,
                account_age_days=0,
                warmup_until=now + timedelta(days=2),
                growing_until=now + timedelta(days=7),
                last_counter_reset=date.today(),
                last_hourly_reset=now,
            )
            session.add(account)
            session.flush()  # Get ID

            # Record state history
            history = AccountStateHistory(
                account_id=account.id,
                from_state=None,
                to_state=AccountState.LOGGED_IN,
                reason="account_registered",
                triggered_by="system",
            )
            session.add(history)

            # Link to clone if provided
            if clone_id:
                clone = session.query(Clone).filter_by(id=clone_id).first()
                if clone:
                    clone.account_id = account.id
                    clone.has_account = True
                    clone.status = CloneStatus.ACTIVE

                    # Record clone-account history
                    clone_history = CloneAccountHistory(
                        clone_id=clone_id,
                        account_id=account.id,
                        action=CloneAccountAction.LOGIN,
                        logged_in_at=now,
                        reason="initial_registration",
                    )
                    session.add(clone_history)

            session.commit()
            logger.info(f"   ✅ Account @{username} registered (ID: {account.id})")

            # Auto-transition to WARMUP
            self._transition_state(
                account.id, AccountState.WARMUP,
                reason="auto_warmup_start",
                triggered_by="system",
                session=session,
            )

            # Load all attributes before detaching from session
            session.refresh(account)
            session.expunge(account)
            return account

        except Exception as e:
            session.rollback()
            logger.error(f"   ❌ Failed to register account @{username}: {e}")
            return None
        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   STATE MACHINE
    # ══════════════════════════════════════════════

    def get_account(self, account_id: int) -> Optional[Account]:
        """Get account by ID."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if account:
                session.expunge(account)
            return account
        finally:
            session.close()

    def get_account_by_username(self, username: str) -> Optional[Account]:
        """Get account by username."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(username=username).first()
            if account:
                session.expunge(account)
            return account
        finally:
            session.close()

    def get_account_state(self, account_id: int) -> Optional[AccountState]:
        """Get current state of an account."""
        account = self.get_account(account_id)
        if account:
            return account.state
        return None

    def transition_state(
        self,
        account_id: int,
        new_state: AccountState,
        reason: str = "",
        triggered_by: str = "system",
    ) -> bool:
        """
        Transition account to a new state.
        Records the transition in history.
        """
        session = db_manager.get_session()
        try:
            return self._transition_state(
                account_id, new_state, reason, triggered_by, session
            )
        finally:
            session.close()

    def _transition_state(
        self,
        account_id: int,
        new_state: AccountState,
        reason: str,
        triggered_by: str,
        session,
    ) -> bool:
        """Internal state transition with existing session."""
        account = session.query(Account).filter_by(id=account_id).first()
        if not account:
            logger.error(f"Account #{account_id} not found")
            return False

        old_state = account.state

        # Validate transition
        if not self._is_valid_transition(old_state, new_state):
            logger.warning(
                f"   ⚠️  Invalid transition: {old_state} → {new_state} "
                f"for account #{account_id}"
            )
            # Allow it anyway but log warning

        # Update account
        account.previous_state = old_state
        account.state = new_state
        account.state_changed_at = datetime.now()

        # Set cooldown timer if entering cooldown
        if new_state == AccountState.COOLDOWN:
            hours = 6 + (account.restriction_count or 0) * 2  # Longer cooldown each time
            account.cooldown_until = datetime.now() + timedelta(hours=hours)

        if new_state == AccountState.RESTRICTED:
            account.restriction_count = (account.restriction_count or 0) + 1
            account.last_restriction_at = datetime.now()
            account.cooldown_until = datetime.now() + timedelta(hours=24)

        if new_state == AccountState.BANNED:
            account.is_action_blocked = True

        # Record history
        history = AccountStateHistory(
            account_id=account_id,
            from_state=old_state,
            to_state=new_state,
            reason=reason,
            triggered_by=triggered_by,
        )
        session.add(history)
        session.commit()

        logger.info(f"   🔄 Account #{account_id} @{account.username}: {old_state} → {new_state} ({reason})")
        return True

    def _is_valid_transition(self, from_state: AccountState, to_state: AccountState) -> bool:
        """Check if a state transition is logically valid."""
        valid_transitions = {
            AccountState.CREATED: [AccountState.LOGGED_IN, AccountState.ERROR],
            AccountState.LOGGED_IN: [AccountState.WARMUP, AccountState.ERROR, AccountState.PAUSED],
            AccountState.WARMUP: [AccountState.GROWING, AccountState.COOLDOWN, AccountState.RESTRICTED, AccountState.BANNED, AccountState.PAUSED, AccountState.ERROR],
            AccountState.GROWING: [AccountState.ACTIVE, AccountState.COOLDOWN, AccountState.RESTRICTED, AccountState.BANNED, AccountState.PAUSED, AccountState.ERROR],
            AccountState.ACTIVE: [AccountState.COOLDOWN, AccountState.RESTRICTED, AccountState.BANNED, AccountState.PAUSED, AccountState.ERROR],
            AccountState.COOLDOWN: [AccountState.WARMUP, AccountState.GROWING, AccountState.ACTIVE, AccountState.RESTRICTED, AccountState.BANNED, AccountState.PAUSED, AccountState.ERROR],
            AccountState.RESTRICTED: [AccountState.COOLDOWN, AccountState.ACTIVE, AccountState.GROWING, AccountState.BANNED, AccountState.PAUSED, AccountState.ERROR],
            AccountState.PAUSED: [AccountState.WARMUP, AccountState.GROWING, AccountState.ACTIVE, AccountState.COOLDOWN, AccountState.ERROR],
            AccountState.ERROR: [AccountState.WARMUP, AccountState.GROWING, AccountState.ACTIVE, AccountState.PAUSED, AccountState.LOGGED_OUT],
            AccountState.BANNED: [AccountState.LOGGED_OUT],
            AccountState.LOGGED_OUT: [AccountState.LOGGED_IN],
        }

        allowed = valid_transitions.get(from_state, [])
        return to_state in allowed

    # ══════════════════════════════════════════════
    #   AUTO STATE CHECKS
    # ══════════════════════════════════════════════

    def check_auto_transitions(self, account_id: int) -> Optional[AccountState]:
        """
        Check if an account should automatically transition.
        Called before each task execution.
        
        Returns new state if transition happened, None otherwise.
        """
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return None

            now = datetime.now()
            current = account.state

            # WARMUP → GROWING (warmup period expired)
            if current == AccountState.WARMUP and account.warmup_until:
                if now >= account.warmup_until:
                    self._transition_state(
                        account_id, AccountState.GROWING,
                        "warmup_period_complete", "system", session
                    )
                    return AccountState.GROWING

            # GROWING → ACTIVE (growing period expired)
            if current == AccountState.GROWING and account.growing_until:
                if now >= account.growing_until:
                    self._transition_state(
                        account_id, AccountState.ACTIVE,
                        "growing_period_complete", "system", session
                    )
                    return AccountState.ACTIVE

            # COOLDOWN → previous state (cooldown expired)
            if current == AccountState.COOLDOWN and account.cooldown_until:
                if now >= account.cooldown_until:
                    # Return to previous state or ACTIVE
                    resume_state = account.previous_state or AccountState.ACTIVE
                    if resume_state in (AccountState.COOLDOWN, AccountState.RESTRICTED, AccountState.BANNED):
                        resume_state = AccountState.ACTIVE
                    self._transition_state(
                        account_id, resume_state,
                        "cooldown_expired", "system", session
                    )
                    return resume_state

            # RESTRICTED → COOLDOWN (restriction expired)
            if current == AccountState.RESTRICTED and account.cooldown_until:
                if now >= account.cooldown_until:
                    self._transition_state(
                        account_id, AccountState.COOLDOWN,
                        "restriction_expired_entering_cooldown", "system", session
                    )
                    return AccountState.COOLDOWN

            # Update account age
            if account.first_login_at:
                age = (now - account.first_login_at).days
                if age != account.account_age_days:
                    account.account_age_days = age
                    session.commit()

            return None

        except Exception as e:
            session.rollback()
            logger.error(f"Auto transition check failed for #{account_id}: {e}")
            return None
        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   COUNTER MANAGEMENT
    # ══════════════════════════════════════════════

    def reset_daily_counters_if_needed(self, account_id: int):
        """Reset daily counters if it's a new day."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return

            today = date.today()
            if account.last_counter_reset != today:
                account.likes_today = 0
                account.follows_today = 0
                account.unfollows_today = 0
                account.comments_today = 0
                account.dms_today = 0
                account.stories_viewed_today = 0
                account.searches_today = 0
                account.last_counter_reset = today
                session.commit()
                logger.info(f"   🔄 Daily counters reset for @{account.username}")

        except Exception as e:
            session.rollback()
            logger.error(f"Counter reset failed: {e}")
        finally:
            session.close()

    def reset_hourly_counters_if_needed(self, account_id: int):
        """Reset hourly counters if an hour has passed."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return

            now = datetime.now()
            if account.last_hourly_reset:
                elapsed = (now - account.last_hourly_reset).total_seconds()
                if elapsed >= 3600:  # 1 hour
                    account.likes_this_hour = 0
                    account.follows_this_hour = 0
                    account.comments_this_hour = 0
                    account.last_hourly_reset = now
                    session.commit()

        except Exception as e:
            session.rollback()
        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   RATE LIMIT CHECKING
    # ══════════════════════════════════════════════

    def can_perform_action(self, account_id: int, action_type: str) -> Tuple[bool, str]:
        """
        Check if an account can perform a specific action.
        
        Returns:
            (can_do: bool, reason: str)
        """
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return False, "account_not_found"

            # Check state allows actions
            if account.state in (
                AccountState.BANNED, AccountState.PAUSED,
                AccountState.ERROR, AccountState.LOGGED_OUT,
                AccountState.CREATED
            ):
                return False, f"account_state_{account.state.value}"

            if account.is_action_blocked:
                return False, "action_blocked"

            # Check cooldown
            if account.cooldown_until and datetime.now() < account.cooldown_until:
                return False, "in_cooldown"

            # Get limits for current state
            state_limits = self.STATE_LIMITS.get(account.state, self.STATE_LIMITS[AccountState.ACTIVE])

            # Reset counters if needed
            self.reset_daily_counters_if_needed(account_id)
            self.reset_hourly_counters_if_needed(account_id)

            # Reload after potential reset
            session.refresh(account)

            # Check daily limits
            daily_checks = {
                "like": ("likes_today", state_limits.get("max_likes", 200), account.max_likes_per_day),
                "follow": ("follows_today", state_limits.get("max_follows", 100), account.max_follows_per_day),
                "unfollow": ("unfollows_today", state_limits.get("max_unfollows", 100), account.max_unfollows_per_day),
                "comment": ("comments_today", state_limits.get("max_comments", 50), account.max_comments_per_day),
                "dm": ("dms_today", state_limits.get("max_dms", 30), account.max_dms_per_day),
                "view_story": ("stories_viewed_today", state_limits.get("max_stories", 50), 999),
                "search": ("searches_today", state_limits.get("max_searches", 30), 999),
            }

            if action_type in daily_checks:
                field, state_limit, account_limit = daily_checks[action_type]
                current_count = getattr(account, field, 0) or 0
                effective_limit = min(state_limit, account_limit)

                if current_count >= effective_limit:
                    return False, f"daily_limit_reached_{action_type}"

            # Check hourly limits
            hourly_checks = {
                "like": ("likes_this_hour", self.HOURLY_LIMITS.get("likes", 30)),
                "follow": ("follows_this_hour", self.HOURLY_LIMITS.get("follows", 15)),
                "comment": ("comments_this_hour", self.HOURLY_LIMITS.get("comments", 10)),
            }

            if action_type in hourly_checks:
                field, limit = hourly_checks[action_type]
                current = getattr(account, field, 0) or 0
                if current >= limit:
                    return False, f"hourly_limit_reached_{action_type}"

            return True, "ok"

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return False, f"error: {e}"
        finally:
            session.close()

    def get_remaining_actions(self, account_id: int) -> Dict:
        """Get how many actions an account can still perform today."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return {}

            self.reset_daily_counters_if_needed(account_id)
            session.refresh(account)

            state_limits = self.STATE_LIMITS.get(account.state, self.STATE_LIMITS[AccountState.ACTIVE])

            return {
                "likes": min(state_limits.get("max_likes", 200), account.max_likes_per_day) - (account.likes_today or 0),
                "follows": min(state_limits.get("max_follows", 100), account.max_follows_per_day) - (account.follows_today or 0),
                "unfollows": min(state_limits.get("max_unfollows", 100), account.max_unfollows_per_day) - (account.unfollows_today or 0),
                "comments": min(state_limits.get("max_comments", 50), account.max_comments_per_day) - (account.comments_today or 0),
                "dms": min(state_limits.get("max_dms", 30), account.max_dms_per_day) - (account.dms_today or 0),
                "stories": state_limits.get("max_stories", 50) - (account.stories_viewed_today or 0),
            }

        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   ACTION RECORDING
    # ══════════════════════════════════════════════

    def record_action(
        self,
        account_id: int,
        action_type: str,
        success: bool = True,
        target_user: Optional[str] = None,
        target_hashtag: Optional[str] = None,
        target_post_id: Optional[str] = None,
        action_data: Optional[Dict] = None,
        task_execution_id: Optional[int] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> Optional[int]:
        """
        Record an action performed by an account.
        Updates counters and creates action log entry.
        
        Returns action_log ID if successful.
        """
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return None

            # Map string action type to enum
            action_enum = self._str_to_action_type(action_type)

            # Create action log
            log = ActionLog(
                account_id=account_id,
                device_id=account.device_id,
                task_execution_id=task_execution_id,
                action_type=action_enum,
                target_user=target_user,
                target_post_id=target_post_id,
                target_hashtag=target_hashtag,
                action_data=action_data,
                success=success,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            session.add(log)

            # Update counters if successful
            if success:
                counter_map = {
                    "like": ("likes_today", "likes_this_hour", "total_likes"),
                    "follow": ("follows_today", "follows_this_hour", "total_follows"),
                    "unfollow": ("unfollows_today", None, "total_unfollows"),
                    "comment": ("comments_today", "comments_this_hour", "total_comments"),
                    "dm": ("dms_today", None, "total_dms"),
                    "view_story": ("stories_viewed_today", None, "total_stories_viewed"),
                    "search_hashtag": ("searches_today", None, None),
                    "search_user": ("searches_today", None, None),
                }

                if action_type in counter_map:
                    daily_field, hourly_field, total_field = counter_map[action_type]

                    if daily_field:
                        current = getattr(account, daily_field, 0) or 0
                        setattr(account, daily_field, current + 1)

                    if hourly_field:
                        current = getattr(account, hourly_field, 0) or 0
                        setattr(account, hourly_field, current + 1)

                    if total_field:
                        current = getattr(account, total_field, 0) or 0
                        setattr(account, total_field, current + 1)

                account.last_action_at = datetime.now()

                # Track follows for later unfollowing
                if action_type == "follow" and target_user:
                    follow = FollowTracking(
                        account_id=account_id,
                        followed_username=target_user,
                        follow_source=target_hashtag or "unknown",
                    )
                    session.add(follow)

                # Track unfollows
                if action_type == "unfollow" and target_user:
                    existing_follow = session.query(FollowTracking).filter_by(
                        account_id=account_id,
                        followed_username=target_user,
                        unfollowed_at=None,
                    ).first()
                    if existing_follow:
                        existing_follow.unfollowed_at = datetime.now()

            # Update risk score on failure
            if not success and action_type in ("like", "follow", "comment", "dm"):
                account.risk_score = min(100, (account.risk_score or 0) + 5)

                # Auto-cooldown if risk is high
                if (account.risk_score or 0) >= 50:
                    self._transition_state(
                        account_id, AccountState.COOLDOWN,
                        "high_risk_score", "safety", session,
                    )

            session.flush()
            action_id = log.id
            session.commit()

            return action_id

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record action: {e}")
            return None
        finally:
            session.close()

    def _str_to_action_type(self, action: str) -> ActionType:
        """Convert string to ActionType enum."""
        mapping = {
            "like": ActionType.LIKE,
            "unlike": ActionType.UNLIKE,
            "follow": ActionType.FOLLOW,
            "unfollow": ActionType.UNFOLLOW,
            "comment": ActionType.COMMENT,
            "dm": ActionType.DM,
            "view_story": ActionType.VIEW_STORY,
            "view_profile": ActionType.VIEW_PROFILE,
            "search_hashtag": ActionType.SEARCH_HASHTAG,
            "search_user": ActionType.SEARCH_USER,
            "scroll": ActionType.SCROLL,
            "open_app": ActionType.OPEN_APP,
            "close_app": ActionType.CLOSE_APP,
            "switch_clone": ActionType.SWITCH_CLONE,
            "browse_feed": ActionType.BROWSE_FEED,
            "browse_explore": ActionType.BROWSE_EXPLORE,
            "view_reel": ActionType.VIEW_REEL,
            "share": ActionType.SHARE,
            "save_post": ActionType.SAVE_POST,
        }
        return mapping.get(action, ActionType.LIKE)

    # ══════════════════════════════════════════════
    #   SESSION TRACKING
    # ══════════════════════════════════════════════

    def start_session(self, account_id: int):
        """Mark the start of a bot session for an account."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if account:
                account.last_session_at = datetime.now()
                account.total_sessions = (account.total_sessions or 0) + 1
                session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()

    def end_session(self, account_id: int, duration_minutes: int):
        """Mark the end of a bot session."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if account:
                account.last_session_duration_min = duration_minutes
                session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   METRICS
    # ══════════════════════════════════════════════

    def update_metrics(
        self,
        account_id: int,
        followers: Optional[int] = None,
        following: Optional[int] = None,
        posts: Optional[int] = None,
    ):
        """Update account metrics and save snapshot to history."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return

            if followers is not None:
                account.followers_count = followers
            if following is not None:
                account.following_count = following
            if posts is not None:
                account.posts_count = posts

            account.last_metrics_update = datetime.now()

            # Save snapshot
            snapshot = AccountMetricsHistory(
                account_id=account_id,
                followers_count=followers or account.followers_count or 0,
                following_count=following or account.following_count or 0,
                posts_count=posts or account.posts_count or 0,
            )
            session.add(snapshot)
            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Metrics update failed: {e}")
        finally:
            session.close()

    # ══════════════════════════════════════════════
    #   BULK OPERATIONS
    # ══════════════════════════════════════════════

    def get_all_accounts(self, state: Optional[AccountState] = None) -> List[Dict]:
        """Get all accounts, optionally filtered by state."""
        session = db_manager.get_session()
        try:
            query = session.query(Account)
            if state:
                query = query.filter_by(state=state)
            accounts = query.order_by(Account.id).all()

            return [
                {
                    "id": a.id,
                    "username": a.username,
                    "state": a.state.value if a.state else "unknown",
                    "device_id": a.device_id,
                    "clone_id": a.clone_id,
                    "account_age_days": a.account_age_days,
                    "likes_today": a.likes_today or 0,
                    "follows_today": a.follows_today or 0,
                    "total_likes": a.total_likes or 0,
                    "total_follows": a.total_follows or 0,
                    "followers_count": a.followers_count or 0,
                    "risk_score": a.risk_score or 0,
                    "last_action_at": a.last_action_at.isoformat() if a.last_action_at else None,
                }
                for a in accounts
            ]
        finally:
            session.close()

    def get_accounts_needing_action(self) -> List[Dict]:
        """Get accounts that are ready for automation (not paused/banned/cooling)."""
        session = db_manager.get_session()
        try:
            active_states = [
                AccountState.WARMUP,
                AccountState.GROWING,
                AccountState.ACTIVE,
            ]
            accounts = (
                session.query(Account)
                .filter(Account.state.in_(active_states))
                .filter(Account.is_action_blocked == False)
                .order_by(Account.last_action_at.asc().nullsfirst())
                .all()
            )

            return [
                {
                    "id": a.id,
                    "username": a.username,
                    "state": a.state.value,
                    "device_id": a.device_id,
                    "clone_id": a.clone_id,
                    "remaining": self.get_remaining_actions(a.id),
                }
                for a in accounts
            ]
        finally:
            session.close()

    def get_account_summary(self, account_id: int) -> Optional[Dict]:
        """Get a comprehensive summary of an account."""
        session = db_manager.get_session()
        try:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                return None

            return {
                "id": account.id,
                "username": account.username,
                "state": account.state.value if account.state else "unknown",
                "state_changed_at": account.state_changed_at.isoformat() if account.state_changed_at else None,
                "age_days": account.account_age_days or 0,
                "device_id": account.device_id,
                "clone_id": account.clone_id,
                "today": {
                    "likes": account.likes_today or 0,
                    "follows": account.follows_today or 0,
                    "unfollows": account.unfollows_today or 0,
                    "comments": account.comments_today or 0,
                    "dms": account.dms_today or 0,
                    "stories": account.stories_viewed_today or 0,
                },
                "totals": {
                    "likes": account.total_likes or 0,
                    "follows": account.total_follows or 0,
                    "unfollows": account.total_unfollows or 0,
                    "comments": account.total_comments or 0,
                    "dms": account.total_dms or 0,
                    "sessions": account.total_sessions or 0,
                },
                "metrics": {
                    "followers": account.followers_count or 0,
                    "following": account.following_count or 0,
                    "posts": account.posts_count or 0,
                },
                "safety": {
                    "risk_score": account.risk_score or 0,
                    "restriction_count": account.restriction_count or 0,
                    "is_blocked": account.is_action_blocked or False,
                    "cooldown_until": account.cooldown_until.isoformat() if account.cooldown_until else None,
                },
                "remaining": self.get_remaining_actions(account_id),
            }
        finally:
            session.close()
