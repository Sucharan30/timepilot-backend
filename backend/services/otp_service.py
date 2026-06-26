"""
backend/services/otp_service.py

Business logic for OTP lifecycle:
  - generate_and_store_otp  → creates a new OTP row via OTPRepository
  - verify_otp              → validates OTP against DB (expiry + single-use)
  - get_latest_otp_debug    → debug helper

OTP TTL is 5 minutes (spec requirement).
Delivery is via Telegram (see TelegramAuthService); this service only stores.
"""
from datetime import timedelta
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.otp_verification import OTPVerification
from backend.repositories.otp_repository import OTPRepository
from backend.services.timezone_service import TimezoneService

# OTP is valid for 5 minutes (changed from 10 per spec)
OTP_TTL_MINUTES = 5


class OTPVerifyResult(str, Enum):
    """Granular result codes so the API layer can return specific errors."""
    SUCCESS   = "success"
    NOT_FOUND = "not_found"   # No matching phone+otp record, or already used
    EXPIRED   = "expired"     # Record found but past expires_at


class OTPService:

    @staticmethod
    def generate_and_store_otp(phone_number: str, db: Session) -> str:
        """
        Legacy entry point — used by AuthService.send_otp().
        In the new flow, OTP generation is handled by TelegramAuthService,
        which calls OTPRepository directly.

        Kept for backward compatibility with the /auth/send-otp endpoint.
        Returns the OTP code (exposed in DEBUG mode only).
        """
        import random
        otp_code   = str(random.randint(100_000, 999_999))
        expires_at = TimezoneService.now_utc() + timedelta(minutes=OTP_TTL_MINUTES)

        OTPRepository.invalidate_old(db, phone_number)
        OTPRepository.create(
            db=db,
            phone_number=phone_number,
            otp_code=otp_code,
            expires_at=expires_at,
        )

        print(f"[OTPService] OTP stored for {phone_number}: {otp_code} (expires in {OTP_TTL_MINUTES}m)")
        return otp_code

    @staticmethod
    def verify_otp(phone_number: str, otp_code: str, db: Session) -> OTPVerifyResult:
        """
        Validate the OTP against the latest unused, non-expired row.
        Marks it as used on success.
        Returns OTPVerifyResult enum — SUCCESS, NOT_FOUND, or EXPIRED.
        """
        record: Optional[OTPVerification] = OTPRepository.get_latest_by_phone(db, phone_number, otp_code)

        if record is None:
            print(f"[OTPService] verify_otp: No record found for phone={phone_number}, otp={otp_code}")
            return OTPVerifyResult.NOT_FOUND

        if record.is_used:
            print(f"[OTPService] verify_otp: OTP already used for phone={phone_number}")
            return OTPVerifyResult.NOT_FOUND

        # Compare expiry using timezone-aware UTC
        now_utc = TimezoneService.now_utc()
        exp = record.expires_at

        # Ensure exp is timezone-aware
        if exp.tzinfo is None:
            import pytz
            exp = pytz.utc.localize(exp)

        if exp < now_utc:
            print(f"[OTPService] verify_otp: OTP expired at {exp}, now is {now_utc}")
            return OTPVerifyResult.EXPIRED

        # ✅ Valid — mark as used
        OTPRepository.mark_used(db, record)
        print(f"[OTPService] verify_otp: SUCCESS for phone={phone_number}")
        return OTPVerifyResult.SUCCESS

    @staticmethod
    def get_latest_otp_debug(phone_number: str, db: Session) -> Optional[dict]:
        """
        DEBUG ONLY — returns the most recent OTP record for a phone number.
        Used by the /debug/otp-check endpoint.
        """
        record = OTPRepository.get_most_recent(db, phone_number)
        if not record:
            return None

        now_utc = TimezoneService.now_utc()
        exp = record.expires_at
        if exp.tzinfo is None:
            import pytz
            exp = pytz.utc.localize(exp)

        return {
            "id": record.id,
            "phone_number": record.phone_number,
            "otp_code": record.otp_code,
            "telegram_chat_id": record.telegram_chat_id,
            "expires_at": str(record.expires_at),
            "is_used": record.is_used,
            "created_at": str(record.created_at),
            "is_expired": exp < now_utc,
            "seconds_remaining": max(0, int((exp - now_utc).total_seconds())),
        }
