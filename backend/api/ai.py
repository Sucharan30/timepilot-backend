"""
backend/api/ai.py

AI-powered recommendations, insights, and streaks endpoints:

  GET /recommendations/generate  — Gemini analyzes data → saves + returns recommendations
  GET /insights/generate         — Gemini generates data insights → saves + returns
  GET /streaks                   — Returns current and longest streaks
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.analytics import AIInsightResponse, RecommendationResponse, StreakResponse
from backend.schemas.response import ok
from backend.services.ai_service import InsightService, RecommendationService
from backend.services.streak_service import StreakService

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


# ── GET /streaks ──────────────────────────────────────────────────────────────

@router.get("/streaks")
def get_streaks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Returns all streaks for the authenticated user.
    Auto-creates default streak types (productivity, expense_logging) if they don't exist yet.
    """
    streaks = StreakService.get_all(user_id=current_user.id, db=db)
    return ok([StreakResponse.model_validate(s).model_dump() for s in streaks])
