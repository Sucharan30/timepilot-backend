"""
backend/models/recommendation.py

Recommendation and AIInsight models.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class Recommendation(Base):
    __tablename__ = "recommendations"

    id                  = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id             = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_text = Column(Text, nullable=False)
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="recommendations")


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_text = Column(Text, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="ai_insights")
