"""
backend/services/otp_service.py

Business logic for OTP lifecycle:
  - generate_and_store_otp  → creates a new OTP row in otp_verifications
  - verify_otp              → validates OTP against DB (expiry + single-use)

Uses OTPProvider abstraction; the concrete provider is injected via factory.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.otp_verification import OTPVerification
from backend.services.otp_provider import get_otp_provider

# OTP is valid for 10 minutes
OTP_TTL_MINUTES = 10


class OTPVerifyResult(str, Enum):
    """Granular result codes so the API layer can return specific errors."""
    SUCCESS = "success"
    NOT_FOUND = "not_found"       # No matching phone+otp record, or already used
    EXPIRED = "expired"           # Record found but past expires_at


class OTPService:

    @staticmethod
    def generate_and_store_otp(phone_number: str, db: Session) -> str:
        """
        1. Generate a 6-digit OTP via the configured provider.
        2. Invalidate any existing unused OTPs for this phone (prevents replay).
        3. Persist a new OTPVerification row.
        4. Attempt to send via provider (no-op for MockOTPProvider).
        Returns the plain OTP string so the caller can decide whether to expose it.
        """
        provider = get_otp_provider()
        otp_code = provider.generate_otp()

        # Invalidate old unused OTPs for the same phone
        (
            db.query(OTPVerification)
            .filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.is_used == False,  # noqa: E712
            )
            .update({"is_used": True}, synchronize_session=False)
        )

        # Store UTC naive datetime — MySQL DATETIME has no timezone info
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)

        record = OTPVerification(
            phone_number=phone_number,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False,
        )
        db.add(record)
        db.commit()

        # Attempt delivery (fire-and-forget for now)
        try:
            provider.send_otp(phone_number, otp_code)
        except Exception as e:
            print(f"[OTPService] Delivery failed: {e}")

        print(f"[OTPService] OTP stored for {phone_number}: {otp_code} (expires in {OTP_TTL_MINUTES}m)")
        return otp_code

    @staticmethod
    def verify_otp(phone_number: str, otp_code: str, db: Session) -> OTPVerifyResult:
        """
        Validate the OTP against the latest unused, non-expired row.
        Marks it as used on success.
        Returns OTPVerifyResult enum — SUCCESS, NOT_FOUND, or EXPIRED.
        """
        # Look for any record matching phone + code (used or not) to diagnose issues
        record: Optional[OTPVerification] = (
            db.query(OTPVerification)
            .filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.otp_code == otp_code,
            )
            .order_by(OTPVerification.created_at.desc())
            .first()
        )

        if record is None:
            print(f"[OTPService] verify_otp: No record found for phone={phone_number}, otp={otp_code}")
            return OTPVerifyResult.NOT_FOUND

        if record.is_used:
            print(f"[OTPService] verify_otp: OTP already used for phone={phone_number}")
            return OTPVerifyResult.NOT_FOUND

        # Compare expiry — both as UTC naive datetimes to avoid tz issues
        now_utc = datetime.utcnow()
        exp = record.expires_at

        # Strip tzinfo if present (MySQL usually returns naive, but be safe)
        if exp.tzinfo is not None:
            exp = exp.replace(tzinfo=None)

        if exp < now_utc:
            print(f"[OTPService] verify_otp: OTP expired at {exp}, now is {now_utc}")
            return OTPVerifyResult.EXPIRED

        # ✅ Valid — mark as used
        record.is_used = True
        db.commit()
        print(f"[OTPService] verify_otp: SUCCESS for phone={phone_number}")
        return OTPVerifyResult.SUCCESS

    @staticmethod
    def get_latest_otp_debug(phone_number: str, db: Session) -> Optional[dict]:
        """
        DEBUG ONLY — returns the most recent OTP record for a phone number.
        Used by the /debug/otp-check endpoint.
        """
        record = (
            db.query(OTPVerification)
            .filter(OTPVerification.phone_number == phone_number)
            .order_by(OTPVerification.created_at.desc())
            .first()
        )
        if not record:
            return None

        now_utc = datetime.utcnow()
        exp = record.expires_at
        if exp.tzinfo is not None:
            exp = exp.replace(tzinfo=None)

        return {
            "id": record.id,
            "phone_number": record.phone_number,
            "otp_code": record.otp_code,
            "expires_at": str(record.expires_at),
            "is_used": record.is_used,
            "created_at": str(record.created_at),
            "is_expired": exp < now_utc,
            "seconds_remaining": max(0, int((exp - now_utc).total_seconds())),
        }
