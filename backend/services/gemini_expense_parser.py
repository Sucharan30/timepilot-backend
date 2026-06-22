"""
backend/services/gemini_expense_parser.py

Gemini NLP parser for expense messages.

Input:  "Spent ₹500 on food"
Output: {"amount": 500, "category": "food", "description": null}
"""
import json
import re
from typing import Any, Dict

from fastapi import HTTPException, status

from backend.core.config import get_settings

settings = get_settings()

_SYSTEM_PROMPT = """You are a financial assistant that extracts structured data from expense messages.

Given an expense message, return ONLY valid JSON (no markdown, no explanation) with these keys:
  - amount      (number)        : the numeric amount spent (no currency symbols)
  - category    (string)        : one of food, transport, education, entertainment, health, shopping, utilities, other
  - description (string or null): short description of what was bought

Examples:
  Input:  "Spent ₹500 on food"
  Output: {"amount": 500, "category": "food", "description": null}

  Input:  "Bought textbooks for ₹1200"
  Output: {"amount": 1200, "category": "education", "description": "textbooks"}

  Input:  "Uber to college cost 80 rupees"
  Output: {"amount": 80, "category": "transport", "description": "Uber to college"}
"""

VALID_CATEGORIES = {"food", "transport", "education", "entertainment", "health", "shopping", "utilities", "other"}


class GeminiExpenseParser:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not settings.GEMINI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GEMINI_API_KEY is not configured.",
            )
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._client = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=_SYSTEM_PROMPT,
            )
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="google-generativeai package not installed.",
            )
        return self._client

    def parse(self, message: str) -> Dict[str, Any]:
        model = self._get_client()
        try:
            response = model.generate_content(message)
            raw_text = response.text.strip()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gemini API error: {exc}")

        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Gemini returned non-JSON: {raw_text}")

        if parsed.get("category") not in VALID_CATEGORIES:
            parsed["category"] = "other"
        if "amount" not in parsed or not isinstance(parsed["amount"], (int, float)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not extract amount from message.")

        return parsed


gemini_expense_parser = GeminiExpenseParser()
