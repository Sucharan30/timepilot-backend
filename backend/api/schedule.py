"""
backend/api/schedule.py

Natural-language scheduling flow:

  POST /schedule/parse    — Gemini parses a free-text message into structured data
  POST /schedule/confirm  — User confirms parsed event → saved to DB
  GET  /schedule/today    — Returns today's events for the authenticated user
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.event import (
    ParseRequest,
    ConfirmRequest,
    EventResponse,
)
from backend.schemas.response import ok
from backend.services.gemini_schedule_parser import gemini_parser
from backend.services.event_service import EventService

router = APIRouter(prefix="/schedule", tags=["Schedule"])


# ── POST /schedule/parse ──────────────────────────────────────────────────────

@router.post("/parse")
def parse_schedule(
    body: ParseRequest,
    current_user=Depends(get_current_user),
):
    """
    Send a free-text message to Gemini and receive structured event data.
    Does NOT save anything to the database.
    The client should display the parsed result to the user for confirmation,
    then call POST /schedule/confirm.
    """
    parsed_data = gemini_parser.parse(body.message)
    return ok({"parsed_data": parsed_data})


# ── POST /schedule/confirm ────────────────────────────────────────────────────

@router.post("/confirm", status_code=status.HTTP_201_CREATED)
def confirm_schedule(
    body: ConfirmRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Confirm and save a previously parsed event to the database.
    The client passes back the parsed_data (with resolved start_datetime).
    Only after this call is the event persisted.
    """
    from backend.schemas.event import EventCreate  # local import to avoid circular refs

    payload = EventCreate(
        title=body.title,
        description=body.description,
        event_type=body.event_type,
        start_datetime=body.start_datetime,
        end_datetime=body.end_datetime,
    )
    event = EventService.create_event(
        user_id=current_user.id,
        payload=payload,
        db=db,
    )
    return ok(EventResponse.model_validate(event).model_dump())


# ── GET /schedule/today ───────────────────────────────────────────────────────

@router.get("/today")
def today_schedule(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all scheduled events for today (UTC) for the authenticated user."""
    events = EventService.get_today_events(user_id=current_user.id, db=db)
    return ok({"events": [EventResponse.model_validate(e).model_dump() for e in events]})
