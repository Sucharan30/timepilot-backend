"""
backend/api/ai.py

AI-powered endpoints:

  GET  /recommendations/generate   — Gemini analyzes data → saves + returns recommendations
  GET  /insights/generate          — Gemini generates data insights → saves + returns
  GET  /streaks                    — Returns current and longest streaks (legacy — use /streaks)
  GET  /ai/procrastination         — Procrastination behavior analysis
  POST /ai/schedule-negotiate      — AI schedule negotiation (optimal scheduling in free window)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.analytics import AIInsightResponse, RecommendationResponse, StreakResponse
from backend.schemas.response import ok
from backend.services.ai_service import InsightService, RecommendationService
from backend.services.streak_service import StreakService
from backend.services.procrastination_service import ProcrastinationService
from backend.services.schedule_negotiation_service import ScheduleNegotiationService

router = APIRouter(tags=["AI & Streaks"])


# ── GET /recommendations/generate ────────────────────────────────────────────

@router.get("/recommendations/generate")
def generate_recommendations(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Calls Gemini with the user's events and expenses.
    Stores up to 3 new recommendations in the DB and returns them.
    """
    recs = RecommendationService.generate(user_id=current_user.id, db=db)
    return ok([RecommendationResponse.model_validate(r).model_dump() for r in recs])


# ── GET /insights/generate ────────────────────────────────────────────────────

@router.get("/insights/generate")
def generate_insights(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Calls Gemini with the user's events and expenses to produce data insights.
    Stores up to 3 new insights in the DB and returns them.
    """
    insights = InsightService.generate(user_id=current_user.id, db=db)
    return ok([AIInsightResponse.model_validate(i).model_dump() for i in insights])


# ── GET /streaks (legacy — kept for backward compat) ─────────────────────────

@router.get("/streaks")
def get_streaks_legacy(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Returns all streaks for the authenticated user.
    Auto-creates default streak types if they don't exist yet.
    NOTE: Prefer GET /streaks (dedicated router) for new frontends.
    """
    streaks = StreakService.get_all(user_id=current_user.id, db=db)
    return ok([StreakResponse.model_validate(s).model_dump() for s in streaks])


# ── GET /ai/procrastination ───────────────────────────────────────────────────

@router.get("/ai/procrastination")
def get_procrastination_analysis(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Analyze the user's behavior patterns over the last 30 days to detect procrastination.

    Returns:
      - procrastination_score (0–100)
      - metrics (missed_deadlines, cancelled_events, missed_tasks, completed_tasks)
      - AI-generated insight and personalized tips
      - severity: low | medium | high
    """
    result = ProcrastinationService.analyze(
        db=db,
        user_id=current_user.id,
        user_timezone=getattr(current_user, "timezone", None),
    )
    return ok(result)


# ── POST /ai/schedule-negotiate ───────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    activity: str
    duration_minutes: int = 30
    priority: str = "medium"   # low | medium | high


class ScheduleNegotiateRequest(BaseModel):
    requests: List[ScheduleRequest]
    free_window_start: str    # ISO 8601 datetime in user's local time, e.g. "2024-01-15T17:00:00"
    free_window_end: str      # ISO 8601 datetime in user's local time, e.g. "2024-01-15T21:00:00"


@router.post("/ai/schedule-negotiate")
def negotiate_schedule(
    body: ScheduleNegotiateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    AI Schedule Negotiation.

    Submit a list of activities you want to do (with durations and priorities)
    and your free time window. Gemini will generate an optimal schedule,
    handle conflicts, and suggest resolutions.

    Example request:
    {
      "requests": [
        {"activity": "Gym", "duration_minutes": 60, "priority": "high"},
        {"activity": "Client Call", "duration_minutes": 30, "priority": "high"},
        {"activity": "Study", "duration_minutes": 90, "priority": "medium"}
      ],
      "free_window_start": "2024-01-15T17:00:00",
      "free_window_end": "2024-01-15T21:00:00"
    }
    """
    result = ScheduleNegotiationService.negotiate(
        db=db,
        user_id=current_user.id,
        requests=[r.model_dump() for r in body.requests],
        free_window_start=body.free_window_start,
        free_window_end=body.free_window_end,
        user_timezone=getattr(current_user, "timezone", None),
    )
    return ok(result)


# ── POST /ai/chat ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    text: str

@router.post("/ai/chat")
def ai_chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Conversational AI endpoint for the Floating AI Assistant.
    Parses user requests and interacts with Gemini.
    """
    # For MVP, we route this to the schedule parser to simulate intelligent parsing
    from backend.services.gemini_schedule_parser import gemini_parser
    try:
        parsed_data = gemini_parser.parse(body.text)
        return ok({"message": f"I analyzed your request. Here's what I understood: {parsed_data.get('title', 'Action')} scheduled for {parsed_data.get('start_datetime', 'sometime')}. To confirm this action, you can use the command palette or schedule page."})
    except Exception as e:
        return ok({"message": "I'm your TimePilot AI. How can I help you today?"})
