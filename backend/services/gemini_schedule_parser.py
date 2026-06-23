"""
backend/services/gemini_schedule_parser.py

Gemini-powered natural language → structured schedule parser.

Input:  "Meeting Friday 3 PM"
Output: {
    "title":      "Meeting",
    "event_type": "meeting",
    "date":       "Friday",
    "time":       "3 PM",
    "notes":      null
}

Uses Google Gemini via the google-generativeai SDK.
GEMINI_API_KEY must be set in Railway Variables / .env.
"""
import json
import re
from typing import Any, Dict

from fastapi import HTTPException, status

from backend.core.config import get_settings

settings = get_settings()


# ── Prompt template ───────────────────────────────────────────────────────────

def get_system_prompt() -> str:
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).astimezone().isoformat()
    return f"""You are a scheduling assistant that extracts structured data from natural language.
Today's current date and time is: {now_iso}

Given a scheduling message, return ONLY valid JSON (no markdown, no explanation) with these keys:
  - title          (string)              : short event title
  - event_type     (string)              : one of meeting, appointment, class, task, reminder, deadline
  - start_datetime (string)              : EXACT start datetime in ISO 8601 format (e.g. "2026-06-24T15:00:00+05:30"). Calculate this based on the user's message and today's date.
  - end_datetime   (string or null)      : EXACT end datetime in ISO 8601 format, or null if not specified.
  - notes          (string or null)      : any extra details

Examples:
  Input:  "Team standup tomorrow at 9am"
  Output: {{"title":"Team standup","event_type":"meeting","start_datetime":"2026-06-24T09:00:00+05:30","end_datetime":null,"notes":null}}
"""

# ── Parser ────────────────────────────────────────────────────────────────────

class GeminiScheduleParser:
    """Wraps the Gemini API to parse scheduling messages."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy-initialise the Gemini client so startup doesn't crash if key is absent."""
        if self._client is not None:
            return self._client

        if not settings.GEMINI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GEMINI_API_KEY is not configured. Add it to Railway Variables.",
            )

        try:
            import google.generativeai as genai  # noqa: PLC0415
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._client = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=get_system_prompt(),
            )
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="google-generativeai package not installed. Run: pip install google-generativeai",
            )

        return self._client

    def parse(self, message: str) -> Dict[str, Any]:
        """
        Send the user's message to Gemini and return the parsed JSON dict.
        Raises HTTPException on Gemini error or invalid JSON.
        """
        model = self._get_client()

        try:
            # We recreate the model to inject the current time into system_instruction
            import google.generativeai as genai
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=get_system_prompt(),
            )
            response = model.generate_content(message)
            raw_text = response.text.strip()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gemini API error: {exc}",
            )

        # Strip markdown code fences if Gemini adds them
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Gemini returned non-JSON output: {raw_text}",
            )

        # Normalise event_type to a known value; fall back to "reminder"
        valid_types = {"meeting", "appointment", "class", "task", "reminder", "deadline"}
        if parsed.get("event_type") not in valid_types:
            parsed["event_type"] = "reminder"

        return parsed


# ── Singleton ─────────────────────────────────────────────────────────────────

gemini_parser = GeminiScheduleParser()
