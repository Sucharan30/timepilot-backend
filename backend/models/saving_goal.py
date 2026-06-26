"""
backend/models/saving_goal.py

SavingGoal model — tracks user savings objectives with target amount,
current saved amount, deadline, and status.
"""
import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class GoalStatus(str, enum.Enum):
    active    = "active"
    completed = "completed"
    cancelled = "cancelled"


class SavingGoal(Base):
    __tablename__ = "saving_goals"

    id             = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_name      = Column(String(200), nullable=False)
    description    = Column(Text, nullable=True)
    target_amount  = Column(Numeric(12, 2), nullable=False)
    current_saved  = Column(Numeric(12, 2), nullable=False, default=0)
    deadline       = Column(DateTime(timezone=True), nullable=True)
    status         = Column(Enum(GoalStatus), nullable=False, default=GoalStatus.active)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="saving_goals")
