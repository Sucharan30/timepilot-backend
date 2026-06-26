"""
backend/models/user.py

User model — the central identity entity.
"""
from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phone_number  = Column(String(20), unique=True, nullable=False, index=True)
    full_name     = Column(String(150), nullable=True)
    is_active     = Column(Boolean, default=True, nullable=False)
    is_verified   = Column(Boolean, default=False, nullable=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Timezone & Notification Preferences ──────────────────────────────────
    # IANA timezone string, e.g. "Asia/Kolkata", "America/New_York"
    timezone              = Column(String(100), nullable=False, server_default="Asia/Kolkata")
    # HH:MM string for daily briefing time in the user's local timezone
    briefing_time         = Column(String(5), nullable=False, server_default="07:00")
    # Master switch for all Telegram notifications
    notification_enabled  = Column(Boolean, nullable=False, server_default="1")
    # How many minutes before an event the reminder fires
    reminder_minutes      = Column(Integer, nullable=False, server_default="15")
    # Whether to send the daily briefing message
    briefing_enabled      = Column(Boolean, nullable=False, server_default="1")
    # Comma-separated list of enabled notification categories
    # e.g. "meeting,appointment,task,class,deadline,reminder"
    notification_categories = Column(String(255), nullable=False,
                                     server_default="meeting,appointment,task,class,deadline,reminder")

    # ── Relationships ─────────────────────────────────────────────────────────
    sessions         = relationship("UserSession",    back_populates="user", cascade="all, delete-orphan")
    telegram_account = relationship("TelegramAccount", back_populates="user", uselist=False, cascade="all, delete-orphan")
    events           = relationship("Event",          back_populates="user", cascade="all, delete-orphan")
    notifications    = relationship("Notification",   back_populates="user", cascade="all, delete-orphan")
    expenses         = relationship("Expense",        back_populates="user", cascade="all, delete-orphan")
    budgets          = relationship("Budget",         back_populates="user", cascade="all, delete-orphan")
    activity_logs    = relationship("ActivityLog",    back_populates="user", cascade="all, delete-orphan")
    recommendations  = relationship("Recommendation", back_populates="user", cascade="all, delete-orphan")
    ai_insights      = relationship("AIInsight",      back_populates="user", cascade="all, delete-orphan")
    streaks          = relationship("Streak",         back_populates="user", cascade="all, delete-orphan")
    saving_goals     = relationship("SavingGoal",     back_populates="user", cascade="all, delete-orphan")
    rewards          = relationship("Reward",         back_populates="user", cascade="all, delete-orphan")