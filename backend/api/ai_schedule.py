"""
backend/api/ai_schedule.py

AI Schedule Negotiation endpoints:

  POST /ai/schedule/negotiate  — Gemini suggests optimal schedule for tasks + free window
  POST /ai/schedule/confirm    — Saves the accepted suggested schedule as real events

Flow: User Request → Gemini Suggestion → Frontend Preview → Accept → Save
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.core.config import get_settings
from backend.core.dependencies import get_db, get_current_user
from backend.repositories.event_repository import EventRepository
from backend.models.event import EventType
from backend.schemas.response import ok
from backend.services.notification_service import NotificationService
from backend.services.timezone_service import TimezoneService

router = APIRouter(prefix="/ai/schedule", tags=["AI Schedule"])
settings = get_settings()


class TaskItem(BaseModel):
    name: str
    duration_minutes: int = 60


class NegotiateRequest(BaseModel):
    tasks: List[TaskItem]
    free_start: str   # ISO datetime string (local time)
    free_end: str     # ISO datetime string (local time)
    date: Optional[str] = None  # "YYYY-MM-DD", defaults to today


class SuggestedEvent(BaseModel):
    title: str
    description: Optional[str] = None
    start_datetime: str
    end_datetime: str
    event_type: str = "meeting"


class ConfirmScheduleRequest(BaseModel):
    events: List[SuggestedEvent]


@router.post("/negotiate")
def negotiate_schedule(
    body: NegotiateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Use Gemini to suggest an optimal schedule for the given tasks within the free window.
    Returns suggested events — NOT saved until /ai/schedule/confirm is called.
    """
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured.")

    try:
        from backend.models.event import Event, EventStatus
        from dateutil.parser import parse as parse_date
        start_dt = parse_date(body.free_start)
        end_dt = parse_date(body.free_end)

        # Fetch existing events in this window to avoid conflicts
        existing_events = db.query(Event).filter(
            Event.user_id == current_user.id,
            Event.status != EventStatus.cancelled,
            Event.end_datetime > start_dt,
            Event.start_datetime < end_dt
        ).all()

        context_str = ""
        if existing_events:
            context_str = "\n".join([f"- {e.title} ({e.start_datetime.strftime('%H:%M')} to {e.end_datetime.strftime('%H:%M')})" for e in existing_events if e.end_datetime])
            context_str = f"\nCRITICAL: The user already has the following events scheduled during this window:\n{context_str}\nDO NOT schedule new tasks overlapping with these existing events!"

        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=(
                "You are an intelligent scheduling assistant. "
                "Create an optimal schedule fitting all tasks into the free time window. "
                "Include short breaks between tasks. "
                "Return ONLY a JSON array of scheduled events with: title, description, "
                "start_datetime (ISO 8601), end_datetime (ISO 8601), event_type. "
                "Do NOT add any markdown formatting."
            )
        )

        tasks_str = "\n".join([f"- {t.name} ({t.duration_minutes} min)" for t in body.tasks])
        prompt = f"""
Free time window: {body.free_start} to {body.free_end}
{context_str}

Tasks to schedule:
{tasks_str}

Create an optimal schedule:
- Fit all tasks within the free window without overlapping existing events.
- Add 5-10 minute breaks between tasks.
- Order by priority if possible.
- Use realistic event_type values: meeting, task, study, reminder.

Return ONLY a JSON array:
[
  {{
    "title": "...",
    "description": "...",
    "start_datetime": "2026-06-29T17:00:00",
    "end_datetime": "2026-06-29T18:00:00",
    "event_type": "task"
  }}
]
"""
        response = model.generate_content(prompt)
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        suggested = json.loads(raw)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini error: {exc}")

    return ok({"suggested_events": suggested})


@router.post("/confirm")
def confirm_schedule(
    body: ConfirmScheduleRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Save the accepted AI-suggested events as real events.
    Only called after user clicks 'Accept' in the frontend.
    """
    user_tz = getattr(current_user, "timezone", "Asia/Kolkata")
    created_ids = []

    parse_errors = []
    for ev in body.events:
        try:
            from dateutil.parser import parse as parse_date
            start_local = parse_date(ev.start_datetime)
            end_local   = parse_date(ev.end_datetime) if ev.end_datetime else start_local
        except Exception as e:
            parse_errors.append(str(e))
            continue

        start_utc = TimezoneService.to_utc(start_local, user_tz)
        end_utc   = TimezoneService.to_utc(end_local,   user_tz)

        try:
            event_type = EventType(ev.event_type)
        except ValueError:
            event_type = EventType.meeting

        try:
            event = EventRepository.create(
                db=db,
                user_id=current_user.id,
                title=ev.title,
                description=ev.description,
                event_type=event_type,
                start_datetime=start_utc,
                end_datetime=end_utc,
            )
            created_ids.append(event.id)
            
            try:
                NotificationService.schedule_event_notification(db, event, current_user)
            except Exception:
                pass
        except Exception as e:
            # Catch DB constraints or enum errors
            raise HTTPException(status_code=500, detail=f"Database error saving event: {str(e)}")

    if not created_ids and body.events:
        raise HTTPException(status_code=400, detail=f"Failed to parse and save any events. Errors: {parse_errors}")

    # Broadcast SSE
    try:
        from backend.api.sse import broadcast_event
        broadcast_event(current_user.id, "schedule_negotiated", {"count": len(created_ids)})
    except Exception:
        pass

    return ok({
        "message": f"Schedule saved! {len(created_ids)} events created.",
        "event_ids": created_ids,
    })
