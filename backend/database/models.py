import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean,
    Float, DateTime, Date, Time, ForeignKey, Enum, JSON,
    UniqueConstraint, Index, event
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


# ═══════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════

class DeviceStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class CloneStatus(str, enum.Enum):
    ACTIVE = "active"
    EMPTY = "empty"
    ERROR = "error"
    DISABLED = "disabled"
    INSTALLING = "installing"


class AccountState(str, enum.Enum):
    CREATED = "created"
    LOGGED_IN = "logged_in"
    WARMUP = "warmup"
    GROWING = "growing"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    RESTRICTED = "restricted"
    BANNED = "banned"
    PAUSED = "paused"
    ERROR = "error"
    LOGGED_OUT = "logged_out"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class ActionType(str, enum.Enum):
    LIKE = "like"
    UNLIKE = "unlike"
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    COMMENT = "comment"
    DM = "dm"
    VIEW_STORY = "view_story"
    VIEW_PROFILE = "view_profile"
    SEARCH_HASHTAG = "search_hashtag"
    SEARCH_USER = "search_user"
    SCROLL = "scroll"
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    SWITCH_CLONE = "switch_clone"
    BROWSE_FEED = "browse_feed"
    BROWSE_EXPLORE = "browse_explore"
    VIEW_REEL = "view_reel"
    SHARE = "share"
    SAVE_POST = "save_post"


class ErrorType(str, enum.Enum):
    ADB_DISCONNECT = "adb_disconnect"
    APP_CRASH = "app_crash"
    CLONE_ERROR = "clone_error"
    LOGIN_FAILED = "login_failed"
    SCREEN_NOT_RECOGNIZED = "screen_not_recognized"
    ACTION_BLOCKED = "action_blocked"
    RATE_LIMITED = "rate_limited"
    ACCOUNT_SUSPENDED = "account_suspended"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class CloneAccountAction(str, enum.Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    SWAP = "swap"
    AUTO_DETECTED = "auto_detected"


# ═══════════════════════════════════════════════════
# TABLE: devices
# ═══════════════════════════════════════════════════

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    serial = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    android_version = Column(String(50), nullable=True)
    screen_width = Column(Integer, nullable=True)
    screen_height = Column(Integer, nullable=True)
    screen_density = Column(Integer, nullable=True)
    touch_device_path = Column(String(255), nullable=True)
    touch_max_x = Column(Integer, nullable=True)
    touch_max_y = Column(Integer, nullable=True)
    touch_max_pressure = Column(Integer, nullable=True)

    # Touch event codes (auto-detected)
    touch_event_code_x = Column(Integer, nullable=True)          # Usually 53 (ABS_MT_POSITION_X)
    touch_event_code_y = Column(Integer, nullable=True)          # Usually 54 (ABS_MT_POSITION_Y)
    touch_event_code_pressure = Column(Integer, nullable=True)   # Usually 58 (ABS_MT_PRESSURE)
    touch_event_code_tracking = Column(Integer, nullable=True)   # Usually 57 (ABS_MT_TRACKING_ID)
    touch_event_code_touch_major = Column(Integer, nullable=True)# Usually 48 (ABS_MT_TOUCH_MAJOR)
    touch_event_code_slot = Column(Integer, nullable=True)       # Usually 47 (ABS_MT_SLOT)
    
    # Touch ranges
    touch_min_x = Column(Integer, default=0)
    touch_min_y = Column(Integer, default=0)
    touch_max_touch_major = Column(Integer, nullable=True)
    touch_min_pressure = Column(Integer, default=0)
    
    # Screen to touch coordinate mapping
    touch_scale_x = Column(Float, nullable=True)    # touch_max_x / screen_width
    touch_scale_y = Column(Float, nullable=True)    # touch_max_y / screen_height
    
    # Calibration status
    is_calibrated = Column(Boolean, default=False)
    calibrated_at = Column(DateTime, nullable=True)
    calibration_data = Column(JSON, nullable=True)   # Full raw calibration dump
    
    # ... rest of existing columns ...

    worker_pc = Column(String(255), nullable=True)
    usb_hub = Column(String(255), nullable=True)
    ip_address = Column(String(50), nullable=True)
    connection_type = Column(String(20), default="usb")  # usb or wifi
    status = Column(Enum(DeviceStatus), default=DeviceStatus.OFFLINE)
    total_clones = Column(Integer, default=0)
    battery_level = Column(Integer, nullable=True)
    storage_free_mb = Column(Integer, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    is_emulator = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    notes = Column(Text, nullable=True)

    # Relationships
    clones = relationship("Clone", back_populates="device", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="device")
    task_executions = relationship("TaskExecution", back_populates="device")
    error_logs = relationship("ErrorLog", back_populates="device")

    def __repr__(self):
        return f"<Device(id={self.id}, serial='{self.serial}', name='{self.name}', status='{self.status}')>"


# ═══════════════════════════════════════════════════
# TABLE: clones
# ═══════════════════════════════════════════════════

class Clone(Base):
    __tablename__ = "clones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    clone_index = Column(Integer, nullable=False)  # 0 = original, 1-19 = clones
    package_name = Column(String(500), nullable=False)  # com.instagram.android.clone_1
    clone_label = Column(String(255), nullable=True)
    is_original = Column(Boolean, default=False)

    # Current state
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL", name="fk_clone_account", use_alter=True), nullable=True)
    has_account = Column(Boolean, default=False)
    status = Column(Enum(CloneStatus), default=CloneStatus.EMPTY)

    # Health tracking
    is_installed = Column(Boolean, default=True)
    app_version = Column(String(50), nullable=True)
    last_opened = Column(DateTime, nullable=True)
    last_successful_task = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)
    consecutive_errors = Column(Integer, default=0)

    # Meta
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    notes = Column(Text, nullable=True)

    # Unique constraint: one clone index per device
    __table_args__ = (
        UniqueConstraint("device_id", "clone_index", name="uq_device_clone_index"),
        UniqueConstraint("device_id", "package_name", name="uq_device_package"),
    )

    # Relationships
    device = relationship("Device", back_populates="clones")
    current_account = relationship("Account", foreign_keys=[account_id], uselist=False)
    clone_account_history = relationship("CloneAccountHistory", back_populates="clone")
    task_executions = relationship("TaskExecution", back_populates="clone")

    def __repr__(self):
        return f"<Clone(id={self.id}, device_id={self.device_id}, index={self.clone_index}, package='{self.package_name}')>"


# ═══════════════════════════════════════════════════
# TABLE: accounts
# ═══════════════════════════════════════════════════

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False)
    password_encrypted = Column(String(500), nullable=True)
    email = Column(String(255), nullable=True)
    phone_number = Column(String(50), nullable=True)
    full_name = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    profile_pic_url = Column(Text, nullable=True)

    # Location (which device/clone this account lives in)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    clone_id = Column(Integer, ForeignKey("clones.id", ondelete="SET NULL", name="fk_account_clone", use_alter=True), nullable=True)

    # ── STATE TRACKING ──
    state = Column(Enum(AccountState), default=AccountState.CREATED)
    state_changed_at = Column(DateTime, default=func.now())
    previous_state = Column(Enum(AccountState), nullable=True)

    # ── TIMELINE ──
    first_login_at = Column(DateTime, nullable=True)
    account_age_days = Column(Integer, default=0)
    warmup_days = Column(Integer, default=2)
    growing_days = Column(Integer, default=5)
    warmup_until = Column(DateTime, nullable=True)
    growing_until = Column(DateTime, nullable=True)

    # ── DAILY COUNTERS ──
    likes_today = Column(Integer, default=0)
    follows_today = Column(Integer, default=0)
    unfollows_today = Column(Integer, default=0)
    comments_today = Column(Integer, default=0)
    dms_today = Column(Integer, default=0)
    stories_viewed_today = Column(Integer, default=0)
    searches_today = Column(Integer, default=0)
    last_counter_reset = Column(Date, default=date.today)

    # ── HOURLY COUNTERS ──
    likes_this_hour = Column(Integer, default=0)
    follows_this_hour = Column(Integer, default=0)
    comments_this_hour = Column(Integer, default=0)
    last_hourly_reset = Column(DateTime, default=func.now())

    # ── LIFETIME TOTALS ──
    total_likes = Column(BigInteger, default=0)
    total_follows = Column(BigInteger, default=0)
    total_unfollows = Column(BigInteger, default=0)
    total_comments = Column(BigInteger, default=0)
    total_dms = Column(BigInteger, default=0)
    total_stories_viewed = Column(BigInteger, default=0)
    total_sessions = Column(BigInteger, default=0)

    # ── INSTAGRAM METRICS ──
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    last_metrics_update = Column(DateTime, nullable=True)

    # ── SAFETY TRACKING ──
    last_action_at = Column(DateTime, nullable=True)
    last_session_at = Column(DateTime, nullable=True)
    last_session_duration_min = Column(Integer, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)
    restriction_count = Column(Integer, default=0)
    last_restriction_at = Column(DateTime, nullable=True)
    is_action_blocked = Column(Boolean, default=False)
    risk_score = Column(Integer, default=0)  # 0-100

    # ── CONFIG ──
    max_likes_per_day = Column(Integer, default=200)
    max_follows_per_day = Column(Integer, default=100)
    max_unfollows_per_day = Column(Integer, default=100)
    max_comments_per_day = Column(Integer, default=50)
    max_dms_per_day = Column(Integer, default=30)
    delay_multiplier = Column(Float, default=1.0)
    proxy = Column(String(255), nullable=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)

    # ── TASK ASSIGNMENT ──
    current_task_execution_id = Column(Integer, nullable=True)
    task_template_id = Column(Integer, ForeignKey("task_templates.id", ondelete="SET NULL"), nullable=True)

    # ── META ──
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    notes = Column(Text, nullable=True)

    # Relationships
    device = relationship("Device", back_populates="accounts")
    current_clone = relationship("Clone", foreign_keys=[clone_id], uselist=False)
    state_history = relationship("AccountStateHistory", back_populates="account", cascade="all, delete-orphan")
    task_executions = relationship("TaskExecution", back_populates="account")
    action_logs = relationship("ActionLog", back_populates="account")
    metrics_history = relationship("AccountMetricsHistory", back_populates="account", cascade="all, delete-orphan")
    clone_history = relationship("CloneAccountHistory", back_populates="account")
    follow_tracking = relationship("FollowTracking", back_populates="account", cascade="all, delete-orphan")
    assigned_template = relationship("TaskTemplate", foreign_keys=[task_template_id])
    schedule = relationship("Schedule", foreign_keys=[schedule_id])
    error_logs = relationship("ErrorLog", back_populates="account")

    def __repr__(self):
        return f"<Account(id={self.id}, username='{self.username}', state='{self.state}')>"


# ═══════════════════════════════════════════════════
# TABLE: account_state_history
# ═══════════════════════════════════════════════════

class AccountStateHistory(Base):
    __tablename__ = "account_state_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    from_state = Column(Enum(AccountState), nullable=True)
    to_state = Column(Enum(AccountState), nullable=False)
    reason = Column(String(500), nullable=True)
    triggered_by = Column(String(100), default="system")  # system / admin / safety
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # Index for fast lookups
    __table_args__ = (
        Index("idx_state_history_account", "account_id"),
        Index("idx_state_history_created", "created_at"),
    )

    # Relationships
    account = relationship("Account", back_populates="state_history")

    def __repr__(self):
        return f"<StateHistory(account={self.account_id}, {self.from_state}→{self.to_state})>"


# ═══════════════════════════════════════════════════
# TABLE: task_templates
# ═══════════════════════════════════════════════════

class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(100), nullable=False)
    applicable_states = Column(JSON, default=list)  # ["warmup", "growing", "active"]
    config = Column(JSON, default=dict)
    # config example:
    # {
    #   "hashtags": ["travel", "food"],
    #   "max_likes": 50,
    #   "max_follows": 20,
    #   "delay_min": 30,
    #   "delay_max": 120,
    #   "comments": ["Nice!", "Great!"],
    #   "session_duration_min": 15,
    #   "session_duration_max": 45,
    # }
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    task_executions = relationship("TaskExecution", back_populates="template")

    def __repr__(self):
        return f"<TaskTemplate(id={self.id}, name='{self.name}', type='{self.task_type}')>"


# ═══════════════════════════════════════════════════
# TABLE: task_executions
# ═══════════════════════════════════════════════════

class TaskExecution(Base):
    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    clone_id = Column(Integer, ForeignKey("clones.id", ondelete="SET NULL"), nullable=True)
    task_template_id = Column(Integer, ForeignKey("task_templates.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    progress = Column(Integer, default=0)  # 0-100
    actions_completed = Column(Integer, default=0)
    actions_target = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    result_summary = Column(JSON, default=dict)
    # result_summary example: {"likes": 15, "follows": 5, "comments": 3}
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # Index for fast lookups
    __table_args__ = (
        Index("idx_task_exec_account", "account_id"),
        Index("idx_task_exec_status", "status"),
        Index("idx_task_exec_created", "created_at"),
    )

    # Relationships
    account = relationship("Account", back_populates="task_executions")
    device = relationship("Device", back_populates="task_executions")
    clone = relationship("Clone", back_populates="task_executions")
    template = relationship("TaskTemplate", back_populates="task_executions")
    action_logs = relationship("ActionLog", back_populates="task_execution", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TaskExecution(id={self.id}, account={self.account_id}, status='{self.status}')>"


# ═══════════════════════════════════════════════════
# TABLE: action_logs
# ═══════════════════════════════════════════════════

class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    task_execution_id = Column(Integer, ForeignKey("task_executions.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(Enum(ActionType), nullable=False)
    target_user = Column(String(255), nullable=True)
    target_post_id = Column(String(255), nullable=True)
    target_hashtag = Column(String(255), nullable=True)
    action_data = Column(JSON, nullable=True)
    # action_data example: {"comment_text": "nice!", "was_private": false}
    success = Column(Boolean, default=True)
    error_message = Column(String(500), nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # How long the action took
    created_at = Column(DateTime, default=func.now())

    # Indexes for fast queries (this table will have MILLIONS of rows)
    __table_args__ = (
        Index("idx_action_account", "account_id"),
        Index("idx_action_type", "action_type"),
        Index("idx_action_created", "created_at"),
        Index("idx_action_account_type", "account_id", "action_type"),
        Index("idx_action_account_date", "account_id", "created_at"),
    )

    # Relationships
    account = relationship("Account", back_populates="action_logs")
    task_execution = relationship("TaskExecution", back_populates="action_logs")

    def __repr__(self):
        return f"<ActionLog(id={self.id}, account={self.account_id}, type='{self.action_type}', success={self.success})>"


# ═══════════════════════════════════════════════════
# TABLE: account_metrics_history
# ═══════════════════════════════════════════════════

class AccountMetricsHistory(Base):
    __tablename__ = "account_metrics_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    recorded_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_metrics_account", "account_id"),
        Index("idx_metrics_recorded", "recorded_at"),
    )

    # Relationships
    account = relationship("Account", back_populates="metrics_history")

    def __repr__(self):
        return f"<Metrics(account={self.account_id}, followers={self.followers_count}, at={self.recorded_at})>"


# ═══════════════════════════════════════════════════
# TABLE: clone_account_history
# ═══════════════════════════════════════════════════

class CloneAccountHistory(Base):
    __tablename__ = "clone_account_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clone_id = Column(Integer, ForeignKey("clones.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    action = Column(Enum(CloneAccountAction), nullable=False)
    logged_in_at = Column(DateTime, nullable=True)
    logged_out_at = Column(DateTime, nullable=True)
    reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_clone_history_clone", "clone_id"),
        Index("idx_clone_history_account", "account_id"),
    )

    # Relationships
    clone = relationship("Clone", back_populates="clone_account_history")
    account = relationship("Account", back_populates="clone_history")

    def __repr__(self):
        return f"<CloneHistory(clone={self.clone_id}, account={self.account_id}, action='{self.action}')>"


# ═══════════════════════════════════════════════════
# TABLE: follow_tracking
# ═══════════════════════════════════════════════════

class FollowTracking(Base):
    __tablename__ = "follow_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    followed_username = Column(String(255), nullable=False)
    followed_at = Column(DateTime, default=func.now())
    unfollowed_at = Column(DateTime, nullable=True)
    follow_source = Column(String(255), nullable=True)  # "hashtag:travel" or "explore" or "suggested"
    followed_back = Column(Boolean, nullable=True)  # null = unknown
    checked_followback_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_follow_account", "account_id"),
        Index("idx_follow_username", "followed_username"),
        Index("idx_follow_unfollowed", "account_id", "unfollowed_at"),
    )

    # Relationships
    account = relationship("Account", back_populates="follow_tracking")

    def __repr__(self):
        return f"<Follow(account={self.account_id}, followed='{self.followed_username}')>"


# ═══════════════════════════════════════════════════
# TABLE: schedules
# ═══════════════════════════════════════════════════

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    active_hours_start = Column(Time, nullable=True)  # 08:00
    active_hours_end = Column(Time, nullable=True)    # 22:00
    active_days = Column(JSON, default=[1, 2, 3, 4, 5, 6, 7])  # 1=Mon, 7=Sun
    sessions_per_day = Column(Integer, default=4)
    session_min_minutes = Column(Integer, default=15)
    session_max_minutes = Column(Integer, default=45)
    break_min_minutes = Column(Integer, default=60)
    break_max_minutes = Column(Integer, default=240)
    timezone = Column(String(50), default="UTC")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Schedule(id={self.id}, name='{self.name}')>"


# ═══════════════════════════════════════════════════
# TABLE: error_logs
# ═══════════════════════════════════════════════════

class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    clone_id = Column(Integer, ForeignKey("clones.id", ondelete="SET NULL"), nullable=True)
    task_execution_id = Column(Integer, ForeignKey("task_executions.id", ondelete="SET NULL"), nullable=True)
    error_type = Column(Enum(ErrorType), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_error_device", "device_id"),
        Index("idx_error_account", "account_id"),
        Index("idx_error_type", "error_type"),
        Index("idx_error_resolved", "resolved"),
        Index("idx_error_created", "created_at"),
    )

    # Relationships
    device = relationship("Device", back_populates="error_logs")
    account = relationship("Account", back_populates="error_logs")

    def __repr__(self):
        return f"<ErrorLog(id={self.id}, type='{self.error_type}', resolved={self.resolved})>"