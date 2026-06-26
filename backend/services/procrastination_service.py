"""
backend/services/procrastination_service.py

Procrastination detection service.

Analyzes user behavior patterns to detect procrastination:
  - Repeated postponements (events rescheduled multiple times)
  - Missed deadlines (deadline events still "scheduled" after their time)
  - Cancelled meetings
  - Late completions

Calls Gemini to generate personalized insights.
"""
from datetime import timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.event import Event, EventStatus, EventType
from backend.services.timezone_service import TimezoneService


class ProcrastinationService:

    @staticmethod
    def analyze(db: Session, user_id: int, user_timezone: Optional[str] = None) -> dict:
        """
        Analyze the user's recent events for procrastination patterns.
        Returns raw metrics and an AI-generated insight.
        """
        now_utc = TimezoneService.now_utc()
        thirty_days_ago = now_utc - timedelta(days=30)

        # ── Missed deadlines ──────────────────────────────────────────────────
        missed_deadlines = (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.event_type == EventType.deadline,
                Event.status == EventStatus.scheduled,
                Event.start_datetime < now_utc,
            )
            .count()
        )

        # ── Cancelled meetings (last 30 days) ─────────────────────────────────
        cancelled_events = (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.status == EventStatus.cancelled,
                Event.updated_at >= thirty_days_ago,
            )
            .count()
        )

        # ── Total events in last 30 days ──────────────────────────────────────
        total_recent = (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.created_at >= thirty_days_ago,
            )
            .count()
        )

        # ── Completed vs missed tasks ─────────────────────────────────────────
        completed_tasks = (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.event_type == EventType.task,
                Event.status == EventStatus.completed,
                Event.updated_at >= thirty_days_ago,
            )
            .count()
        )

        missed_tasks = (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.event_type == EventType.task,
                Event.status == EventStatus.scheduled,
                Event.start_datetime < now_utc,
            )
            .count()
        )

        # ── Procrastination score (0–100) ─────────────────────────────────────
        score = 0
        if total_recent > 0:
            negative = min(missed_deadlines * 20 + cancelled_events * 5 + missed_tasks * 10, 100)
            score = min(negative, 100)

        # ── Gemini insight ────────────────────────────────────────────────────
        insight = ProcrastinationService._generate_insight(
            missed_deadlines=missed_deadlines,
            cancelled_events=cancelled_events,
            missed_tasks=missed_tasks,
            completed_tasks=completed_tasks,
            score=score,
        )

        return {
            "procrastination_score": score,
            "analysis_period_days": 30,
            "metrics": {
                "missed_deadlines": missed_deadlines,
                "cancelled_events": cancelled_events,
                "missed_tasks": missed_tasks,
                "completed_tasks": completed_tasks,
                "total_events_created": total_recent,
            },
            "insight": insight,
            "severity": (
                "low" if score < 20
                else "medium" if score < 50
                else "high"
            ),
        }

    @staticmethod
    def _generate_insight(
        missed_deadlines: int,
        cancelled_events: int,
        missed_tasks: int,
        completed_tasks: int,
        score: int,
    ) -> str:
        """
        Generate a personalized insight using Gemini.
        Falls back to a rule-based message if Gemini is unavailable.
        """
        try:
            from backend.core.config import get_settings
            import google.generativeai as genai

            settings = get_settings()
            if not settings.GEMINI_API_KEY:
                raise ValueError("No Gemini key")

            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.0-flash")

            prompt = f"""You are a productivity coach for TimePilot AI.

User's 30-day activity data:
- Missed deadlines: {missed_deadlines}
- Cancelled events: {cancelled_events}  
- Missed tasks (past due, not done): {missed_tasks}
- Completed tasks: {completed_tasks}
- Procrastination score: {score}/100

Write a short, encouraging, actionable 2-3 sentence insight about their procrastination patterns.
Be specific, kind, and give one concrete tip. Keep it under 80 words."""

            response = model.generate_content(prompt)
            return response.text.strip()

        except Exception as exc:
            print(f"[ProcrastinationService] Gemini unavailable: {exc}")
            return ProcrastinationService._fallback_insight(score)

    @staticmethod
    def _fallback_insight(score: int) -> str:
        if score < 20:
            return "Great job! You're staying on top of your schedule. Keep up the momentum."
        elif score < 50:
            return (
                "You have some missed tasks and cancelled events recently. "
                "Try scheduling smaller time blocks for important items first thing in the morning."
            )
        else:
            return (
                "There are several missed deadlines and tasks that need attention. "
                "Consider breaking large tasks into 15-minute focused sessions "
                "and reviewing your schedule each morning. You've got this!"
            )
