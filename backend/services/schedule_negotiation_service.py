"""
backend/services/schedule_negotiation_service.py

AI Schedule Negotiation service.

Given a set of things the user needs to do and a free time window,
Gemini intelligently prioritizes tasks and generates an optimal schedule.

If conflicts exist, it suggests resolutions:
  - Move Study to tomorrow
  - Keep Client Call (higher priority)
  - Schedule Gym at 6 AM before work

Returns a structured schedule plan and rationale.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.event import Event, EventStatus
from backend.services.timezone_service import TimezoneService


class ScheduleNegotiationService:

    @staticmethod
    def negotiate(
        db: Session,
        user_id: int,
        requests: list[dict],
        free_window_start: str,
        free_window_end: str,
        user_timezone: Optional[str] = None,
    ) -> dict:
        """
        AI schedule negotiation.

        Args:
            requests: List of {"activity": str, "duration_minutes": int, "priority": str}
            free_window_start: ISO datetime string (user's local time)
            free_window_end: ISO datetime string (user's local time)
            user_timezone: IANA timezone string

        Returns:
            {
                "schedule": [...allocated activities with times...],
                "conflicts": [...unscheduled items with reasons...],
                "rationale": "AI explanation",
                "suggestions": [...tips...]
            }
        """
        # ── Parse free window ──────────────────────────────────────────────────
        try:
            start_dt = datetime.fromisoformat(free_window_start)
            end_dt   = datetime.fromisoformat(free_window_end)
        except ValueError:
            return {
                "error": "Invalid datetime format. Use ISO 8601 (e.g. 2024-01-15T17:00:00)",
                "schedule": [],
                "conflicts": [],
            }

        # Convert to UTC for existing events check
        start_utc = TimezoneService.to_utc(start_dt, user_timezone)
        end_utc   = TimezoneService.to_utc(end_dt, user_timezone)

        # ── Fetch existing events in this window ──────────────────────────────
        existing_events = (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.status == EventStatus.scheduled,
                Event.start_datetime < end_utc,
                Event.end_datetime > start_utc if Event.end_datetime is not None else Event.start_datetime >= start_utc,
            )
            .order_by(Event.start_datetime.asc())
            .all()
        ) if start_utc and end_utc else []

        existing_summary = [
            f"{e.title} ({e.event_type.value if hasattr(e.event_type, 'value') else e.event_type}) "
            f"at {TimezoneService.to_user_tz(e.start_datetime, user_timezone).strftime('%I:%M %p')}"
            for e in existing_events
        ]

        total_free_minutes = int((end_dt - start_dt).total_seconds() / 60) if start_dt and end_dt else 240
        window_str = f"{start_dt.strftime('%I:%M %p')} to {end_dt.strftime('%I:%M %p')}"

        return ScheduleNegotiationService._call_gemini(
            requests=requests,
            window_str=window_str,
            total_free_minutes=total_free_minutes,
            existing_summary=existing_summary,
            user_timezone=user_timezone,
        )

    @staticmethod
    def _call_gemini(
        requests: list,
        window_str: str,
        total_free_minutes: int,
        existing_summary: list,
        user_timezone: Optional[str],
    ) -> dict:
        try:
            from backend.core.config import get_settings
            import google.generativeai as genai
            import json

            settings = get_settings()
            if not settings.GEMINI_API_KEY:
                raise ValueError("No Gemini key")

            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.0-flash")

            activities_text = "\n".join([
                f"- {r.get('activity', 'Unknown')} ({r.get('duration_minutes', 30)} min, priority: {r.get('priority', 'medium')})"
                for r in requests
            ])

            existing_text = "\n".join(existing_summary) if existing_summary else "None"

            prompt = f"""You are TimePilot AI, an intelligent schedule negotiator.

Free time window: {window_str} ({total_free_minutes} minutes total)
Timezone: {user_timezone or 'Asia/Kolkata'}

Activities to schedule:
{activities_text}

Already scheduled in this window:
{existing_text}

Create the optimal schedule. Respond with valid JSON only:
{{
  "schedule": [
    {{"activity": "...", "start_time": "HH:MM", "end_time": "HH:MM", "duration_minutes": N}}
  ],
  "conflicts": [
    {{"activity": "...", "reason": "...", "suggestion": "..."}}
  ],
  "rationale": "Brief explanation of your scheduling decisions",
  "suggestions": ["tip1", "tip2"]
}}

Rules:
- Prioritize high-priority items first
- Include buffer time between tasks
- If something doesn't fit, put it in conflicts with a suggestion (move to tomorrow, earlier morning, etc.)
- Be realistic about time"""

            response = model.generate_content(prompt)
            text = response.text.strip()

            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            result = json.loads(text)
            return result

        except Exception as exc:
            print(f"[ScheduleNegotiationService] Error: {exc}")
            return {
                "schedule": [],
                "conflicts": [{"activity": r.get("activity", "Unknown"), "reason": "AI scheduling temporarily unavailable", "suggestion": "Try again in a moment"} for r in requests],
                "rationale": "AI scheduling is temporarily unavailable. Please try again.",
                "suggestions": ["Schedule high-priority tasks first", "Leave buffer time between activities"],
                "error": str(exc),
            }
