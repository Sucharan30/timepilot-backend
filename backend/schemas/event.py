"""
backend/schemas/event.py

Pydantic schemas for Event and Notification endpoints.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from backend.models.event import EventType, EventStatus


# ── EventCreate ───────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title:          str
    description:    Optional[str] = None
    event_type:     EventType = EventType.meeting
    start_datetime: datetime
    end_datetime:   Optional[datetime] = None

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

    model_config = {"from_attributes": True}


# ── NotificationResponse ──────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id:                int
    user_id:           int
    event_id:          int
    notification_time: datetime
    sent:              bool
    created_at:        datetime

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
