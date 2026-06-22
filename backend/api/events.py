"""
backend/api/events.py

Event CRUD endpoints (all JWT-protected, user-scoped):

  POST   /events           — create a new event
  GET    /events           — list all events for the current user
  GET    /events/{id}      — get a single event
  PUT    /events/{id}      — update an event (partial update)
  DELETE /events/{id}      — delete an event
"""
from fastapi import APIRouter, Depends, status
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
    """Create a new scheduled event for the authenticated user."""
    event = EventService.create_event(
        user_id=current_user.id,
        payload=body,
        db=db,
    )
    return ok(EventResponse.model_validate(event).model_dump())


# ── GET /events ───────────────────────────────────────────────────────────────

@router.get("")
def list_events(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all events belonging to the authenticated user."""
    events = EventService.list_events(user_id=current_user.id, db=db)
    return ok([EventResponse.model_validate(e).model_dump() for e in events])


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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an event permanently."""
    EventService.delete_event(
        user_id=current_user.id,
        event_id=event_id,
        db=db,
    )
    return ok({"message": f"Event {event_id} deleted successfully."})
