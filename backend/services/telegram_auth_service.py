"""
backend/services/telegram_auth_service.py

Telegram-only authentication business logic.

Handles two flows:
  1. First-time user: shares phone contact via Telegram →
     - get_or_create User
     - upsert TelegramAccount
     - generate 6-digit OTP (5 min TTL, rate-limited)
     - send OTP to Telegram
     - frontend verifies via POST /auth/verify-otp (phone + OTP)

  2. Returning user: sends /code or /login in Telegram →
     - look up TelegramAccount by chat_id
     - generate + send new OTP
     - frontend verifies via POST /auth/verify-otp

This service is called exclusively from TelegramProvider — never from API routes.
"""
import random
from datetime import timedelta

from sqlalchemy.orm import Session

from backend.repositories.user_repository import UserRepository
from backend.repositories.telegram_repository import TelegramRepository
from backend.repositories.otp_repository import (
    OTPRepository,
    OTP_RATE_LIMIT_MAX,
    OTP_RATE_LIMIT_WINDOW_MINUTES,
)
from backend.services.timezone_service import TimezoneService

# OTP is valid for 5 minutes (spec requirement)
OTP_TTL_MINUTES = 5


def _generate_otp() -> str:
    """Generate a cryptographically sufficient 6-digit OTP."""
    return str(random.randint(100_000, 999_999))


class TelegramAuthService:

    @staticmethod
    def handle_new_user_contact(
        chat_id: str,
        phone_number: str,
        telegram_username: str,
        db: Session,
        send_message_fn,
    ) -> None:
        """
        Called when a user shares their phone contact in Telegram.

        Steps:
          1. Rate-limit check.
          2. get_or_create User (phone_number is the primary identity).
          3. Upsert TelegramAccount → link chat_id.
          4. Generate + store OTP.
          5. Send OTP to Telegram.
        """
        # Standardise E.164 format
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        # ── Rate limiting ──────────────────────────────────────────────────────
        recent_count = OTPRepository.count_recent_requests(db, phone_number)
        if recent_count >= OTP_RATE_LIMIT_MAX:
            send_message_fn(
                chat_id,
                f"⚠️ Too many OTP requests. Please wait {OTP_RATE_LIMIT_WINDOW_MINUTES} minutes and try again.",
            )
            return

        # ── Upsert user ────────────────────────────────────────────────────────
        user, created = UserRepository.get_or_create(db, phone_number)

        # ── Upsert TelegramAccount ─────────────────────────────────────────────
        TelegramRepository.get_or_create_for_user(
            db=db,
            user_id=user.id,
            chat_id=str(chat_id),
            username=telegram_username,
        )

        # ── Generate OTP ───────────────────────────────────────────────────────
        otp_code  = _generate_otp()
        expires_at = TimezoneService.now_utc() + timedelta(minutes=OTP_TTL_MINUTES)

        OTPRepository.invalidate_old(db, phone_number)
        OTPRepository.create(
            db=db,
            phone_number=phone_number,
            otp_code=otp_code,
            expires_at=expires_at,
            telegram_chat_id=str(chat_id),
        )

        # ── Send OTP via Telegram ──────────────────────────────────────────────
        greeting = "🎉 Welcome to TimePilot AI!" if created else "👋 Welcome back!"
        send_message_fn(
            chat_id,
            f"{greeting}\n\n"
            f"🔐 <b>Your TimePilot Login Code</b>\n\n"
            f"<code>{otp_code}</code>\n\n"
            f"⏱ Expires in {OTP_TTL_MINUTES} minutes.\n\n"
            f"Enter this code on the TimePilot website to log in.",
        )
        print(f"[TelegramAuthService] OTP sent to chat_id={chat_id} for phone={phone_number}")

    @staticmethod
    def handle_returning_user_code(
        chat_id: str,
        db: Session,
        send_message_fn,
    ) -> None:
        """
        Called when a returning user sends /code or /login.

        Steps:
          1. Look up TelegramAccount by chat_id.
          2. If not found → ask to share contact first.
          3. Rate-limit check.
          4. Generate + store OTP.
          5. Send OTP to Telegram.
        """
        account = TelegramRepository.get_by_chat_id(db, str(chat_id))
        if not account or not account.is_connected:
            send_message_fn(
                chat_id,
                "⚠️ Your Telegram is not linked to a TimePilot account yet.\n\n"
                "Please tap /start and share your phone number to get started.",
            )
            return

        user = UserRepository.get_by_id(db, account.user_id)
        if not user or not user.is_active:
            send_message_fn(chat_id, "⚠️ Account not found or deactivated. Please contact support.")
            return

        # ── Rate limiting ──────────────────────────────────────────────────────
        recent_count = OTPRepository.count_recent_requests(db, user.phone_number)
        if recent_count >= OTP_RATE_LIMIT_MAX:
            send_message_fn(
                chat_id,
                f"⚠️ Too many OTP requests. Please wait {OTP_RATE_LIMIT_WINDOW_MINUTES} minutes and try again.",
            )
            return

        # ── Generate OTP ───────────────────────────────────────────────────────
        otp_code  = _generate_otp()
        expires_at = TimezoneService.now_utc() + timedelta(minutes=OTP_TTL_MINUTES)

        OTPRepository.invalidate_old(db, user.phone_number)
        OTPRepository.create(
            db=db,
            phone_number=user.phone_number,
            otp_code=otp_code,
            expires_at=expires_at,
            telegram_chat_id=str(chat_id),
        )

        name = user.full_name or "there"
        send_message_fn(
            chat_id,
            f"👋 Welcome back, {name}!\n\n"
            f"🔐 <b>Your TimePilot Login Code</b>\n\n"
            f"<code>{otp_code}</code>\n\n"
            f"⏱ Expires in {OTP_TTL_MINUTES} minutes.\n\n"
            f"Enter this code on the TimePilot website to log in.",
        )
        print(f"[TelegramAuthService] Returning user OTP sent to chat_id={chat_id}")
