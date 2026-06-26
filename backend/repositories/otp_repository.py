"""
backend/repositories/otp_repository.py

Data-access layer for OTPVerification table.
Extracted from OTPService so services stay DB-agnostic.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.otp_verification import OTPVerification

# Rate-limit window in minutes
OTP_RATE_LIMIT_WINDOW_MINUTES = 5
# Max OTP requests per window per phone number
OTP_RATE_LIMIT_MAX = 3


class OTPRepository:

    @staticmethod
    def create(
        db: Session,
        phone_number: str,
        otp_code: str,
        expires_at: datetime,
        telegram_chat_id: Optional[str] = None,
    ) -> OTPVerification:
        """Persist a new OTP record."""
        record = OTPVerification(
            phone_number=phone_number,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False,
            telegram_chat_id=telegram_chat_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def invalidate_old(db: Session, phone_number: str) -> None:
        """Mark all existing unused OTPs for this phone as used (prevents replay)."""
        (
            db.query(OTPVerification)
            .filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.is_used == False,   # noqa: E712
            )
            .update({"is_used": True}, synchronize_session=False)
        )
        db.commit()

    @staticmethod
    def get_latest_by_phone(db: Session, phone_number: str, otp_code: str) -> Optional[OTPVerification]:
        """Return the most recent OTP record matching phone + code."""
        return (
            db.query(OTPVerification)
            .filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.otp_code == otp_code,
            )
            .order_by(OTPVerification.created_at.desc())
            .first()
        )

    @staticmethod
    def get_most_recent(db: Session, phone_number: str) -> Optional[OTPVerification]:
        """Return the most recent OTP record for a phone (any code)."""
        return (
            db.query(OTPVerification)
            .filter(OTPVerification.phone_number == phone_number)
            .order_by(OTPVerification.created_at.desc())
            .first()
        )

    @staticmethod
    def count_recent_requests(db: Session, phone_number: str) -> int:
        """
        Count OTP requests in the last OTP_RATE_LIMIT_WINDOW_MINUTES minutes.
        Used for rate-limiting: max OTP_RATE_LIMIT_MAX per window.
        """
        window_start = datetime.now(timezone.utc) - timedelta(minutes=OTP_RATE_LIMIT_WINDOW_MINUTES)
        return (
            db.query(func.count(OTPVerification.id))
            .filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.created_at >= window_start,
            )
            .scalar()
        )

    @staticmethod
    def mark_used(db: Session, record: OTPVerification) -> None:
        """Mark a single OTP record as used."""
        record.is_used = True
        db.commit()
