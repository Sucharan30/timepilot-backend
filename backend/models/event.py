"""
backend/models/event.py

Event model — represents any schedulable item:
  meeting, appointment, class, task, reminder, deadline, study.
  
Recurring events:
  - is_recurring / recurrence_type / recurrence_interval / recurrence_end_date
    store the RULE (like Google Calendar's RRULE).
  - Occurrences are generated DYNAMICALLY by the service layer.
  - parent_event_id is only set on EXCEPTION events (edited single occurrences).
"""
import enum

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
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
    study       = "study"


class EventStatus(str, enum.Enum):
    scheduled  = "scheduled"
    completed  = "completed"
    cancelled  = "cancelled"


class RecurrenceType(str, enum.Enum):
    none    = "none"
    daily   = "daily"
    weekly  = "weekly"
    monthly = "monthly"
    yearly  = "yearly"
    custom  = "custom"


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

    # ── Recurrence Rule (stored on the MASTER event only) ─────────────────────
    # Generate occurrences dynamically in the service layer.
    is_recurring         = Column(Boolean, nullable=False, default=False)
    recurrence_type      = Column(Enum(RecurrenceType), nullable=True, default=RecurrenceType.none)
    recurrence_interval  = Column(Integer, nullable=True, default=1)   # every N days/weeks/months
    recurrence_end_date  = Column(Date, nullable=True)                  # last occurrence date

    # Set ONLY on exception events (edited single occurrence) — points to master
    parent_event_id      = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    # Stores the original start date of the replaced occurrence (ISO date string)
    exception_date       = Column(String(10), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    user          = relationship("User", back_populates="events")
    notifications = relationship("Notification", back_populates="event", cascade="all, delete-orphan")
    exceptions    = relationship("Event", foreign_keys=[parent_event_id])

