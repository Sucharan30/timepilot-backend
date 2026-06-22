"""
backend/schemas/analytics.py

Pydantic schemas for analytics, recommendations, insights, and streaks.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


# ── Analytics ─────────────────────────────────────────────────────────────────

class AnalyticsResponse(BaseModel):
    period:               str            # "daily" | "weekly" | "monthly"
    total_study_minutes:  int
    total_meeting_minutes: int
    total_personal_minutes: int
    total_expenses:       Decimal
    most_active_category: Optional[str]
    productivity_score:   float          # 0.0 – 100.0
    event_count:          int
    expense_count:        int


# ── Recommendation ────────────────────────────────────────────────────────────

class RecommendationResponse(BaseModel):
    id:                  int
    user_id:             int
    recommendation_text: str
    created_at:          datetime

    model_config = {"from_attributes": True}


# ── AI Insight ────────────────────────────────────────────────────────────────

class AIInsightResponse(BaseModel):
    id:           int
    user_id:      int
    insight_text: str
    created_at:   datetime

    model_config = {"from_attributes": True}


# ── Streak ────────────────────────────────────────────────────────────────────

class StreakResponse(BaseModel):
    id:            int
    user_id:       int
    streak_type:   str
    current_count: int
    longest_count: int
    updated_at:    datetime

    model_config = {"from_attributes": True}
