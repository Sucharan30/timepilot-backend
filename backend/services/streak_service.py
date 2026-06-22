"""
backend/services/streak_service.py

Tracks and updates user streaks for productivity and expense logging.
"""
from sqlalchemy.orm import Session

from backend.models.streak import Streak
from backend.repositories.analytics_repository import StreakRepository
from typing import List


STREAK_TYPES = ["productivity", "expense_logging"]


class StreakService:

    @staticmethod
    def get_all(user_id: int, db: Session) -> List[Streak]:
        """Return all streaks for the user, creating defaults if needed."""
        for streak_type in STREAK_TYPES:
            StreakRepository.get_or_create(db, user_id, streak_type)
        return StreakRepository.get_all_for_user(db, user_id)

    @staticmethod
    def increment(user_id: int, streak_type: str, db: Session) -> Streak:
        """Increment a streak by 1 day."""
        streak = StreakRepository.get_or_create(db, user_id, streak_type)
        return StreakRepository.increment(db, streak)

    @staticmethod
    def reset(user_id: int, streak_type: str, db: Session) -> Streak:
        """Reset a streak to 0 (user missed a day)."""
        streak = StreakRepository.get_or_create(db, user_id, streak_type)
        return StreakRepository.reset(db, streak)
