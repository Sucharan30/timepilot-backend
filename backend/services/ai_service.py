"""
backend/services/ai_service.py

Gemini-powered recommendations and AI insights generation.
Analyzes events, expenses, and activity logs to produce actionable text.
"""
import json
import re
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.recommendation import AIInsight, Recommendation
from backend.repositories.analytics_repository import AIInsightRepository, RecommendationRepository
from backend.repositories.event_repository import EventRepository
from backend.repositories.expense_repository import ExpenseRepository

settings = get_settings()


def _get_gemini_model(system_prompt: str):
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GEMINI_API_KEY not configured.")
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        return genai.GenerativeModel(model_name="gemini-2.5-flash", system_instruction=system_prompt)
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="google-generativeai not installed.")


class RecommendationService:

    @staticmethod
    def generate(user_id: int, db: Session) -> List[Recommendation]:
        events   = EventRepository.get_all_for_user(db, user_id)
        expenses = ExpenseRepository.get_all_for_user(db, user_id)

        event_summary   = [{"title": e.title, "type": str(e.event_type), "status": str(e.status)} for e in events[-10:]]
        expense_summary = [{"amount": float(ex.amount), "category": ex.category} for ex in expenses[-10:]]

        prompt = f"""
User data:
Events (last 10): {json.dumps(event_summary)}
Expenses (last 10): {json.dumps(expense_summary)}

Generate 3 concise, actionable productivity recommendations for this user.
Return ONLY a JSON array of strings, no markdown, no explanation.
Example: ["Recommendation 1", "Recommendation 2", "Recommendation 3"]
"""
        system = "You are a productivity coach. Analyze user data and give specific, actionable advice."
        model = _get_gemini_model(system)

        try:
            response = model.generate_content(prompt)
            raw = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
            raw = re.sub(r"\s*```$", "", raw)
            items: list = json.loads(raw)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gemini error: {exc}")

        results = []
        for text in items[:5]:
            if isinstance(text, str) and text.strip():
                rec = RecommendationRepository.create(db, user_id, text.strip())
                results.append(rec)
        return results


class InsightService:

    @staticmethod
    def generate(user_id: int, db: Session) -> List[AIInsight]:
        expenses = ExpenseRepository.get_all_for_user(db, user_id)
        events   = EventRepository.get_all_for_user(db, user_id)

        expense_summary = [{"amount": float(ex.amount), "category": ex.category} for ex in expenses[-20:]]
        event_summary   = [{"title": e.title, "type": str(e.event_type)} for e in events[-20:]]

        prompt = f"""
User data:
Events: {json.dumps(event_summary)}
Expenses: {json.dumps(expense_summary)}

Generate 3 specific data insights (e.g. "You spend 40% of time in meetings", "Food spending up 20% this week").
Return ONLY a JSON array of strings, no markdown, no explanation.
"""
        system = "You are a data analyst. Generate specific insights based on numbers and patterns."
        model = _get_gemini_model(system)

        try:
            response = model.generate_content(prompt)
            raw = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
            raw = re.sub(r"\s*```$", "", raw)
            items: list = json.loads(raw)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gemini error: {exc}")

        results = []
        for text in items[:5]:
            if isinstance(text, str) and text.strip():
                insight = AIInsightRepository.create(db, user_id, text.strip())
                results.append(insight)
        return results
