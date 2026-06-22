"""
backend/api/analytics.py

Analytics endpoints (JWT-protected):

  GET /analytics/daily    — today's analytics summary
  GET /analytics/weekly   — this week's analytics summary
  GET /analytics/monthly  — this month's analytics summary
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.response import ok
from backend.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/daily")
def daily_analytics(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns analytics summary for today (UTC)."""
    result = AnalyticsService.daily(user_id=current_user.id, db=db)
    return ok(result.model_dump())


@router.get("/weekly")
def weekly_analytics(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns analytics summary for the current week (Mon–today UTC)."""
    result = AnalyticsService.weekly(user_id=current_user.id, db=db)
    return ok(result.model_dump())


@router.get("/monthly")
def monthly_analytics(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns analytics summary for the current month (1st–today UTC)."""
    result = AnalyticsService.monthly(user_id=current_user.id, db=db)
    return ok(result.model_dump())
