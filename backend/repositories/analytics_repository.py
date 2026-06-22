"""
backend/repositories/analytics_repository.py

Data-access layer for analytics, activity_logs, recommendations,
ai_insights, and streaks tables.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.activity_log import ActivityLog
from backend.models.recommendation import AIInsight, Recommendation
from backend.models.streak import Streak


# ── Analytics / Activity Log Repository ───────────────────────────────────────

class ActivityLogRepository:

    @staticmethod
    def create(
        db: Session,
        user_id: int,
        activity_type: str,
        duration_minutes: int,
        log_date: datetime,
    ) -> ActivityLog:
        log = ActivityLog(
            user_id=user_id,
            activity_type=activity_type,
            duration_minutes=duration_minutes,
            log_date=log_date,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_for_period(
        db: Session, user_id: int, start: datetime, end: datetime
    ) -> List[ActivityLog]:
        return (
            db.query(ActivityLog)
            .filter(
                ActivityLog.user_id == user_id,
                ActivityLog.log_date >= start,
                ActivityLog.log_date <= end,
            )
            .order_by(ActivityLog.log_date.desc())
            .all()
        )

    @staticmethod
    def get_minutes_by_type(
        db: Session, user_id: int, start: datetime, end: datetime
    ) -> dict:
        """Returns {activity_type: total_minutes} for a time period."""
        rows = (
            db.query(ActivityLog.activity_type, func.sum(ActivityLog.duration_minutes))
            .filter(
                ActivityLog.user_id == user_id,
                ActivityLog.log_date >= start,
                ActivityLog.log_date <= end,
            )
            .group_by(ActivityLog.activity_type)
            .all()
        )
        return {row[0]: int(row[1]) for row in rows}


# ── Recommendation Repository ─────────────────────────────────────────────────

class RecommendationRepository:

    @staticmethod
    def create(db: Session, user_id: int, text: str) -> Recommendation:
        rec = Recommendation(user_id=user_id, recommendation_text=text)
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec

    @staticmethod
    def get_latest_for_user(db: Session, user_id: int, limit: int = 5) -> List[Recommendation]:
        return (
            db.query(Recommendation)
            .filter(Recommendation.user_id == user_id)
            .order_by(Recommendation.created_at.desc())
            .limit(limit)
            .all()
        )


# ── AI Insight Repository ─────────────────────────────────────────────────────

class AIInsightRepository:

    @staticmethod
    def create(db: Session, user_id: int, text: str) -> AIInsight:
        insight = AIInsight(user_id=user_id, insight_text=text)
        db.add(insight)
        db.commit()
        db.refresh(insight)
        return insight

    @staticmethod
    def get_latest_for_user(db: Session, user_id: int, limit: int = 5) -> List[AIInsight]:
        return (
            db.query(AIInsight)
            .filter(AIInsight.user_id == user_id)
            .order_by(AIInsight.created_at.desc())
            .limit(limit)
            .all()
        )


# ── Streak Repository ─────────────────────────────────────────────────────────

class StreakRepository:

    @staticmethod
    def get_or_create(db: Session, user_id: int, streak_type: str) -> Streak:
        streak = (
            db.query(Streak)
            .filter(Streak.user_id == user_id, Streak.streak_type == streak_type)
            .first()
        )
        if streak is None:
            streak = Streak(user_id=user_id, streak_type=streak_type)
            db.add(streak)
            db.commit()
            db.refresh(streak)
        return streak

    @staticmethod
    def get_all_for_user(db: Session, user_id: int) -> List[Streak]:
        return (
            db.query(Streak)
            .filter(Streak.user_id == user_id)
            .order_by(Streak.streak_type)
            .all()
        )

    @staticmethod
    def increment(db: Session, streak: Streak) -> Streak:
        streak.current_count += 1
        if streak.current_count > streak.longest_count:
            streak.longest_count = streak.current_count
        db.commit()
        db.refresh(streak)
        return streak

    @staticmethod
    def reset(db: Session, streak: Streak) -> Streak:
        streak.current_count = 0
        db.commit()
        db.refresh(streak)
        return streak
