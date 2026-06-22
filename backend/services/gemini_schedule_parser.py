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

_SYSTEM_PROMPT = """You are a scheduling assistant that extracts structured data from natural language.

Given a scheduling message, return ONLY valid JSON (no markdown, no explanation) with these keys:
  - title      (string)              : short event title
  - event_type (string)              : one of meeting, appointment, class, task, reminder, deadline
  - date       (string or null)      : date as written by the user, e.g. "Friday", "June 25", "tomorrow"
  - time       (string or null)      : time as written, e.g. "3 PM", "15:00", "morning"
  - notes      (string or null)      : any extra details

Examples:
  Input:  "Team standup tomorrow at 9am"
  Output: {"title":"Team standup","event_type":"meeting","date":"tomorrow","time":"9am","notes":null}

  Input:  "Doctor appointment next Monday 2 PM"
  Output: {"title":"Doctor appointment","event_type":"appointment","date":"next Monday","time":"2 PM","notes":null}

  Input:  "Submit project deadline Friday"
  Output: {"title":"Submit project","event_type":"deadline","date":"Friday","time":null,"notes":null}
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
                system_instruction=_SYSTEM_PROMPT,
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
