"""
backend/schemas/event.py

Pydantic schemas for Event and Notification endpoints.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from backend.models.event import EventType, EventStatus, RecurrenceType


# ── EventCreate ───────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title:          str
    description:    Optional[str] = None
    event_type:     EventType = EventType.meeting
    start_datetime: datetime
    end_datetime:   Optional[datetime] = None

    # Recurrence fields — all optional, default to non-recurring
    is_recurring:        bool                    = False
    recurrence_type:     RecurrenceType          = RecurrenceType.none
    recurrence_interval: int                     = 1
    recurrence_end_date: Optional[date]          = None

    @field_validator("start_datetime", "end_datetime", mode="before")
    @classmethod
    def must_be_aware(cls, v):
        """Accept naive datetimes but store everything as UTC-aware."""
        return v

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be blank")
        return v.strip()


# ── EventUpdate ───────────────────────────────────────────────────────────────

class EventUpdate(BaseModel):
    title:          Optional[str]        = None
    description:    Optional[str]        = None
    event_type:     Optional[EventType]  = None
    start_datetime: Optional[datetime]   = None
    end_datetime:   Optional[datetime]   = None
    status:         Optional[EventStatus] = None

    # Recurrence update fields
    is_recurring:        Optional[bool]            = None
    recurrence_type:     Optional[RecurrenceType]  = None
    recurrence_interval: Optional[int]             = None
    recurrence_end_date: Optional[date]            = None

    # Scope for recurring edits: "this" | "future" | "all"
    recurrence_edit_scope: Optional[str]           = None


# ── EventResponse ─────────────────────────────────────────────────────────────

class EventResponse(BaseModel):
    id:             int
    user_id:        int
    title:          str
    description:    Optional[str]
    event_type:     EventType
    start_datetime: datetime
    end_datetime:   Optional[datetime]
    status:         EventStatus
    created_at:     datetime
    updated_at:     datetime

    # Recurrence fields
    is_recurring:        bool             = False
    recurrence_type:     Optional[RecurrenceType] = None
    recurrence_interval: Optional[int]   = None
    recurrence_end_date: Optional[date]  = None
    parent_event_id:     Optional[int]   = None
    exception_date:      Optional[str]   = None

    # Virtual fields set by service layer for dynamically generated occurrences
    occurrence_date: Optional[str] = None  # "YYYY-MM-DD" — the occurrence this represents

    @field_validator("start_datetime", "end_datetime", "created_at", "updated_at", mode="after")
    @classmethod
    def ensure_timezone(cls, v: Optional[datetime]) -> Optional[datetime]:
        from datetime import timezone
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    model_config = {"from_attributes": True}


# ── NotificationResponse ──────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id:                int
    user_id:           int
    event_id:          int
    notification_time: datetime
    sent:              bool
    created_at:        datetime
    title:             Optional[str] = None
    body:              Optional[str] = None
    notification_type: Optional[str] = "event_reminder"
    is_read:           bool          = False

    model_config = {"from_attributes": True}


# ── Parse / Confirm ───────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v.strip()


class ConfirmRequest(BaseModel):
    """
    The frontend or Telegram sends back the parsed_data payload
    exactly as returned by POST /schedule/parse, plus the resolved
    start_datetime (ISO-8601, UTC recommended).
    """
    title:          str
    description:    Optional[str]  = None
    event_type:     EventType      = EventType.meeting
    start_datetime: datetime
    end_datetime:   Optional[datetime] = None

