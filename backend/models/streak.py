"""
backend/models/streak.py

Streak model — tracks user consistency across activities.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class Streak(Base):
    __tablename__ = "streaks"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    streak_type   = Column(String(100), nullable=False)          # e.g. "productivity", "expense_logging"
    current_count = Column(Integer, nullable=False, default=0)
    longest_count = Column(Integer, nullable=False, default=0)
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="streaks")
