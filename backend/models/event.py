"""
backend/models/event.py

Event model — represents any schedulable item:
  meeting, appointment, class, task, reminder, deadline.
"""
import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class EventType(str, enum.Enum):
    meeting     = "meeting"
    appointment = "appointment"
    class_      = "class"
    task        = "task"
    reminder    = "reminder"
    deadline    = "deadline"


class EventStatus(str, enum.Enum):
    scheduled  = "scheduled"
    completed  = "completed"
    cancelled  = "cancelled"


class Event(Base):
    __tablename__ = "events"

    id             = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title          = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    event_type     = Column(Enum(EventType), nullable=False, default=EventType.meeting)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime   = Column(DateTime(timezone=True), nullable=True)
    status         = Column(Enum(EventStatus), nullable=False, default=EventStatus.scheduled)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user          = relationship("User", back_populates="events")
    notifications = relationship("Notification", back_populates="event", cascade="all, delete-orphan")
