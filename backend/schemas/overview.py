"""
backend/schemas/overview.py

Pydantic schemas for GET /overview response.
"""
from typing import List

from pydantic import BaseModel

from backend.schemas.event import EventResponse, NotificationResponse


class OverviewResponse(BaseModel):
    today_events:            List[EventResponse]
    tasks_due:               List[EventResponse]
    upcoming_notifications:  List[NotificationResponse]
