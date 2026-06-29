"""
backend/api/events.py

Event CRUD endpoints (all JWT-protected, user-scoped):

  POST   /events           — create a new event (auto-schedules notification)
  GET    /events           — list all events including recurring occurrences
  GET    /events/{id}      — get a single event
  PUT    /events/{id}      — update an event (partial update)
  DELETE /events/{id}      — delete an event (scope: this|future|all)
  GET    /events/stream    — SSE real-time stream (see sse.py)

All datetime fields in responses are UTC ISO 8601.
The frontend should convert to local time using the user's timezone from GET /auth/me.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.event import EventCreate, EventUpdate, EventResponse
from backend.schemas.response import ok
from backend.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["Events"])


# ── POST /events ──────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new scheduled event for the authenticated user.
    Automatically schedules a Telegram reminder notification.
    """
    event = EventService.create_event(
        user_id=current_user.id,
        payload=body,
        db=db,
        user=current_user,     # Pass user for auto-notification scheduling
    )
    return ok(EventResponse.model_validate(event).model_dump())


# ── GET /events ───────────────────────────────────────────────────────────────

@router.get("")
def list_events(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return all events belonging to the authenticated user,
    including dynamically generated occurrences of recurring events.
    """
    events = EventService.list_events(user_id=current_user.id, db=db)
    result = []
    for e in events:
        if isinstance(e, dict):
            # Dynamic recurring occurrence — already a dict
            result.append(e)
        else:
            result.append(EventResponse.model_validate(e).model_dump())
    return ok(result)


# ── GET /events/{event_id} ────────────────────────────────────────────────────

@router.get("/{event_id}")
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return a single event by ID (must belong to the authenticated user)."""
    event = EventService.get_event(
        user_id=current_user.id,
        event_id=event_id,
        db=db,
    )
    return ok(EventResponse.model_validate(event).model_dump())


# ── PUT /events/{event_id} ────────────────────────────────────────────────────

@router.put("/{event_id}")
def update_event(
    event_id: int,
    body: EventUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Partially update an event (only the provided fields are changed)."""
    event = EventService.update_event(
        user_id=current_user.id,
        event_id=event_id,
        payload=body,
        db=db,
    )
    return ok(EventResponse.model_validate(event).model_dump())


# ── DELETE /events/{event_id} ─────────────────────────────────────────────────

@router.delete("/{event_id}", status_code=status.HTTP_200_OK)
def delete_event(
    event_id: int,
    scope: str = Query("all", description="Deletion scope: 'this' | 'future' | 'all'"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an event permanently. For recurring events, use scope to control range."""
    EventService.delete_event(
        user_id=current_user.id,
        event_id=event_id,
        db=db,
        scope=scope,
    )
    return ok({"message": f"Event {event_id} deleted successfully."})


# ── POST /events/{id}/snooze ──────────────────────────────────────────────────

@router.post("/{event_id}/snooze")
def snooze_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Snooze an event by 10 minutes.
    """
    from datetime import timedelta
    from backend.services.notification_service import NotificationService
    
    event = EventService.get_event(user_id=current_user.id, event_id=event_id, db=db)
    
    new_start = event.start_datetime + timedelta(minutes=10)
    new_end = event.end_datetime + timedelta(minutes=10) if event.end_datetime else None
    
    # We update manually to bypass full validation payload for a quick action
    event.start_datetime = new_start
    event.end_datetime = new_end
    db.commit()
    db.refresh(event)
    
    NotificationService.schedule_event_notification(db, event, current_user)
    return ok(EventResponse.model_validate(event).model_dump())
