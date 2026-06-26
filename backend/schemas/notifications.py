"""
backend/schemas/notifications.py

Request/Response schemas for the notification settings API.
"""
from typing import List, Optional
from pydantic import BaseModel, field_validator


class NotificationSettingsUpdate(BaseModel):
    notification_enabled: Optional[bool] = None
    reminder_minutes: Optional[int] = None
    briefing_enabled: Optional[bool] = None
    briefing_time: Optional[str] = None          # HH:MM format
    notification_categories: Optional[List[str]] = None
    timezone: Optional[str] = None

    @field_validator("reminder_minutes")
    @classmethod
    def validate_reminder_minutes(cls, v):
        if v is not None and (v < 0 or v > 1440):
            raise ValueError("reminder_minutes must be between 0 and 1440")
        return v

    @field_validator("briefing_time")
    @classmethod
    def validate_briefing_time(cls, v):
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("briefing_time must be in HH:MM format")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("briefing_time must be a valid time HH:MM")
        return v


class NotificationSettingsOut(BaseModel):
    notification_enabled: bool
    reminder_minutes: int
    briefing_enabled: bool
    briefing_time: str
    notification_categories: List[str]
    timezone: str
