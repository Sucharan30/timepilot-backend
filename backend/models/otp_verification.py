"""
backend/models/otp_verification.py

Stores OTP codes generated during Telegram authentication.
Each row is single-use; expired or used rows can be periodically purged.
"""
from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.sql import func

from backend.database import Base


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id               = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phone_number     = Column(String(20), nullable=False, index=True)
    otp_code         = Column(String(10), nullable=False)
    expires_at       = Column(DateTime(timezone=True), nullable=False)
    is_used          = Column(Boolean, default=False, nullable=False)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Which Telegram chat generated this OTP (nullable for legacy rows)
    telegram_chat_id = Column(String(50), nullable=True, index=True)
    # OTP request count within rate-limit window (tracked in service layer)
    attempt_count    = Column(Integer, nullable=False, default=0)
