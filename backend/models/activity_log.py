"""
backend/models/activity_log.py

ActivityLog model — tracks time spent on categories for analytics.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id               = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type    = Column(String(100), nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False, default=0)
    log_date         = Column(DateTime(timezone=True), nullable=False)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="activity_logs")
