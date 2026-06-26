"""
backend/api/overview.py

Dashboard overview endpoint:

  GET /overview — returns today's events, tasks due, and upcoming notifications
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.repositories.event_repository import EventRepository, NotificationRepository
from backend.schemas.event import EventResponse, NotificationResponse
from backend.schemas.response import ok

router = APIRouter(prefix="/overview", tags=["Overview"])


@router.get("")
def get_overview(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Returns a complete dashboard snapshot for the authenticated user:
      - today_events:           all events scheduled for today (UTC)
      - tasks_due:              task-type events due today
      - upcoming_notifications: next 10 unsent notifications
    """
    today_events = EventRepository.get_today_for_user(db, current_user.id, current_user.timezone)
    tasks_due    = EventRepository.get_tasks_due_today(db, current_user.id, current_user.timezone)
    upcoming     = NotificationRepository.get_upcoming_for_user(db, current_user.id, limit=10)

    return ok({
        "today_events": [
            EventResponse.model_validate(e).model_dump() for e in today_events
        ],
        "tasks_due": [
            EventResponse.model_validate(t).model_dump() for t in tasks_due
        ],
        "upcoming_notifications": [
            NotificationResponse.model_validate(n).model_dump() for n in upcoming
        ],
    })
