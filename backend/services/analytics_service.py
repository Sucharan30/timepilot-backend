"""
backend/services/analytics_service.py

Business logic for time and expense analytics.
Calculates daily / weekly / monthly summaries.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session

from backend.repositories.analytics_repository import ActivityLogRepository
from backend.repositories.event_repository import EventRepository
from backend.repositories.expense_repository import ExpenseRepository
from backend.schemas.analytics import AnalyticsResponse


# ── Category mapping from event_type → analytics bucket ──────────────────────
_STUDY_TYPES    = {"class", "deadline", "task"}
_MEETING_TYPES  = {"meeting", "appointment"}
_PERSONAL_TYPES = {"reminder"}


def _score(study_min: int, meeting_min: int, total_events: int) -> float:
    """
    Simple productivity score 0-100 based on:
      - 40 pts: study/task time (max 120 min/day)
      - 30 pts: meeting balance (penalise excessive meetings)
      - 30 pts: event completion ratio (events logged vs 5 expected/day)
    """
    study_score   = min(study_min / 120, 1.0) * 40
    meeting_score = max(0, 1 - meeting_min / 240) * 30
    event_score   = min(total_events / 5, 1.0) * 30
    return round(study_score + meeting_score + event_score, 1)


class AnalyticsService:

    @staticmethod
    def _compute(user_id: int, db: Session, start: datetime, end: datetime, period: str) -> AnalyticsResponse:
        events   = EventRepository.get_all_for_user(db, user_id)
        expenses = ExpenseRepository.get_for_period(db, user_id, start, end)

        # Filter events in period
        period_events = [e for e in events if start <= e.start_datetime.replace(tzinfo=timezone.utc) <= end]

        study_min   = 0
        meeting_min = 0
        personal_min = 0

        for e in period_events:
            if e.end_datetime:
                dur = int((e.end_datetime - e.start_datetime).total_seconds() / 60)
            else:
                dur = 30  # default 30 min if no end time
            etype = e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type)
            if etype in _STUDY_TYPES:
                study_min += dur
            elif etype in _MEETING_TYPES:
                meeting_min += dur
            else:
                personal_min += dur

        total_expenses = Decimal(str(sum(float(ex.amount) for ex in expenses)))

        # Most active category from expenses
        cat_totals: dict = {}
        for ex in expenses:
            cat_totals[ex.category] = cat_totals.get(ex.category, 0) + float(ex.amount)
        most_active = max(cat_totals, key=cat_totals.get) if cat_totals else None

        return AnalyticsResponse(
            period=period,
            total_study_minutes=study_min,
            total_meeting_minutes=meeting_min,
            total_personal_minutes=personal_min,
            total_expenses=total_expenses,
            most_active_category=most_active,
            productivity_score=_score(study_min, meeting_min, len(period_events)),
            event_count=len(period_events),
            expense_count=len(expenses),
        )

    @staticmethod
    def daily(user_id: int, db: Session) -> AnalyticsResponse:
        now   = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return AnalyticsService._compute(user_id, db, start, end, "daily")

    @staticmethod
    def weekly(user_id: int, db: Session) -> AnalyticsResponse:
        now   = datetime.now(timezone.utc)
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now
        return AnalyticsService._compute(user_id, db, start, end, "weekly")

    @staticmethod
    def monthly(user_id: int, db: Session) -> AnalyticsResponse:
        now   = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end   = now
        return AnalyticsService._compute(user_id, db, start, end, "monthly")
