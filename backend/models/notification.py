"""
backend/models/notification.py

Notification model — tracks when a notification should be sent for an event.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id                = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id           = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id          = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_time = Column(DateTime(timezone=True), nullable=False)
    sent              = Column(Boolean, default=False, nullable=False)
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user  = relationship("User",  back_populates="notifications")
    event = relationship("Event", back_populates="notifications")
