"""
backend/api/study_planner.py

AI-powered Study Planner endpoints:

  POST /study/generate  — Gemini generates a study plan (returns list of events, NOT saved)
  POST /study/confirm   — Saves the generated plan as real events

Study sessions are normal Events with event_type = "study".
This keeps analytics, reminders, calendar, and streaks working automatically.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.dependencies import get_db, get_current_user
from backend.repositories.event_repository import EventRepository
from backend.models.event import EventType
from backend.schemas.response import ok
from backend.services.notification_service import NotificationService
from backend.services.timezone_service import TimezoneService

router = APIRouter(prefix="/study", tags=["Study Planner"])
settings = get_settings()


class StudyPlanRequest(BaseModel):
    subject: str
    chapters: int
    exam_date: str          # "YYYY-MM-DD"
    daily_hours: float = 2  # study hours per day


class StudySessionItem(BaseModel):
    title: str
    description: str
    start_datetime: str
    end_datetime: str
    event_type: str = "study"


class StudyConfirmRequest(BaseModel):
    sessions: List[StudySessionItem]


@router.post("/generate")
def generate_study_plan(
    body: StudyPlanRequest,
    current_user=Depends(get_current_user),
):
    """
    Use Gemini to generate a study plan.
    Returns a list of planned sessions — NOT saved until /study/confirm is called.
    """
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured.")

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=(
                "You are a smart study planner. Generate a day-by-day study schedule. "
                "Return ONLY a JSON array of study sessions. Each session must have: "
                "title, description, start_datetime (ISO 8601 local), end_datetime (ISO 8601 local). "
                "Do NOT include any markdown formatting or extra text."
            )
        )

        now = datetime.now()
        prompt = f"""
Subject: {body.subject}
Total chapters: {body.chapters}
Exam date: {body.exam_date}
Daily study hours: {body.daily_hours}
Today's date: {now.strftime('%Y-%m-%d')}

Generate a day-by-day study plan from today until one day before the exam.
Distribute chapters evenly across the days.
Include revision sessions and a mock test on the last day.
Each session should be {body.daily_hours} hours long, starting at 08:00 AM.

Return ONLY a JSON array like:
[
  {{
    "title": "Study: OS Chapter 1-2",
    "description": "Cover Introduction and Process Management chapters",
    "start_datetime": "2026-06-29T08:00:00",
    "end_datetime": "2026-06-29T10:00:00"
  }}
]
"""
        response = model.generate_content(prompt)
        raw = response.text.strip()
        # Strip markdown if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        sessions = json.loads(raw)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini error: {exc}")

    return ok(sessions)


@router.post("/confirm")
def confirm_study_plan(
    body: StudyConfirmRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Save the confirmed study plan sessions as real events.
    Each session becomes an Event with event_type=study.
    """
    import pytz
    user_tz = getattr(current_user, "timezone", "Asia/Kolkata")
    created_events = []

    for session in body.sessions:
        try:
            from dateutil.parser import parse as parse_date
            start_local = parse_date(session.start_datetime)
            end_local   = parse_date(session.end_datetime)
        except Exception as e:
            continue

        start_utc = TimezoneService.to_utc(start_local, user_tz)
        end_utc   = TimezoneService.to_utc(end_local, user_tz)

        try:
            event = EventRepository.create(
                db=db,
                user_id=current_user.id,
                title=session.title,
                description=session.description,
                event_type=EventType.study,
                start_datetime=start_utc,
                end_datetime=end_utc,
            )
            created_events.append(event.id)
            
            # Schedule reminder for each study session
            try:
                NotificationService.schedule_event_notification(db, event, current_user)
            except Exception:
                pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error saving session: {str(e)}")

    if not created_events and body.sessions:
        raise HTTPException(status_code=400, detail="Failed to parse and save any sessions. The AI may have generated invalid dates.")

    # Broadcast SSE update
    try:
        from backend.api.sse import broadcast_event
        broadcast_event(current_user.id, "study_plan_created", {"count": len(created_events)})
    except Exception:
        pass

    return ok({
        "message": f"Study plan saved! {len(created_events)} sessions created.",
        "event_ids": created_events
    })
