"""
backend/api/streaks.py

Streak tracking API:
  GET /streaks — return all streak types for the current user
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.response import ok
from backend.services.streak_engine import StreakEngine

router = APIRouter(prefix="/streaks", tags=["Streaks"])


@router.get("")
def get_streaks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return all streak records for the authenticated user.

    Streak types: productivity, workout, study, expense_logging
    Each record includes current_count and longest_count.
    """
    streaks = StreakEngine.get_all_streaks(db, current_user.id)

    # Ensure standard streak types exist even if never triggered
    standard_types = ["productivity", "workout", "study", "expense_logging"]
    existing_types = {s["streak_type"] for s in streaks}

    for stype in standard_types:
        if stype not in existing_types:
            # Get or create initialises to 0 without incrementing
            StreakEngine.get_or_create_streak(db, current_user.id, stype)

    # Re-fetch after ensuring all types exist
    streaks = StreakEngine.get_all_streaks(db, current_user.id)
    return ok(streaks)
