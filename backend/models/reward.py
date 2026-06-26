"""
backend/models/reward.py

Reward model — stores AI-generated celebration rewards when users hit
streak milestones. Reward types: badge, free_time, budget_bonus.
"""
import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class RewardType(str, enum.Enum):
    badge        = "badge"
    free_time    = "free_time"
    budget_bonus = "budget_bonus"
    achievement  = "achievement"


class Reward(Base):
    __tablename__ = "rewards"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reward_type  = Column(Enum(RewardType), nullable=False, default=RewardType.badge)
    reward_text  = Column(Text, nullable=False)          # AI-generated celebration message
    streak_type  = Column(String(100), nullable=True)    # Which streak triggered this
    streak_count = Column(Integer, nullable=True)        # Milestone count
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="rewards")
