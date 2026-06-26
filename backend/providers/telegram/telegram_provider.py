"""
backend/providers/telegram/telegram_provider.py

Concrete Telegram provider with full command handling and authentication.

Authentication commands:
  /start   → if new: ask for phone | if returning: send OTP immediately
  /code    → generate + send OTP for returning users
  /login   → alias for /code

NLP commands:
  "show today's schedule"  → list today's events (timezone-correct)
  "Spent ₹500 on food"     → expense NLP → confirmation flow
  "Meeting Friday 3 PM"    → schedule NLP → confirmation flow
  "confirm"                → save pending action
  "cancel"                 → discard pending action

Timezone fix:
  All datetime displays are converted to user's local timezone before sending.
"""
import httpx
from typing import Any, Optional

from backend.providers.telegram.base import TelegramProviderBase
from backend.core.config import get_settings

settings = get_settings()

_API_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

# In-memory pending confirmation store: {chat_id: {"type": "schedule"|"expense", "data": dict}}
_pending: dict = {}


class TelegramProvider(TelegramProviderBase):

    # ── Send ──────────────────────────────────────────────────────────────────

    def send_message(self, chat_id: str | int, text: str, reply_markup: dict = None) -> bool:
        if not settings.TELEGRAM_BOT_TOKEN:
            print("[TelegramProvider] TELEGRAM_BOT_TOKEN is not set. Skipping send.")
            return False

        url     = f"{_API_BASE}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            response = httpx.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            print(f"[TelegramProvider] Failed to send message: {exc}")
            return False

    # ── Handle Update ─────────────────────────────────────────────────────────

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message", {})
        if not message:
            return

        chat_id  = message.get("chat", {}).get("id")
        user_obj = message.get("from", {})

        if not chat_id:
            return

        # ── Contact Sharing (First-time Account Linking + OTP) ─────────────────
        if "contact" in message:
            self._handle_contact(chat_id, message["contact"], user_obj)
            return

        text = (message.get("text") or "").strip()
        if not text:
            return

        text_lower = text.lower()

        # ── Confirmation responses ────────────────────────────────────────────
        if text_lower in ("confirm", "yes", "/confirm"):
            self._handle_confirm(chat_id)
            return
        if text_lower in ("cancel", "no", "/cancel"):
            self._handle_cancel(chat_id)
            return

        # ── Authentication commands ───────────────────────────────────────────
        if text_lower in ("/start", "start"):
            self._handle_start(chat_id, user_obj)
            return

        if text_lower in ("/code", "/login", "code", "login"):
            self._handle_login_code(chat_id)
            return

        # ── Today's schedule ──────────────────────────────────────────────────
        if "today" in text_lower and ("schedule" in text_lower or "event" in text_lower):
            self._handle_today_schedule(chat_id, user_obj)
            return

        # ── Expense detection ─────────────────────────────────────────────────
        if any(kw in text_lower for kw in ("spent", "spend", "₹", "rs", "rupee", "bought", "paid")):
            self._handle_expense_nlp(chat_id, text)
            return

        # ── Schedule detection (fallback) ─────────────────────────────────────
        self._handle_schedule_nlp(chat_id, text)

    # ── /start ────────────────────────────────────────────────────────────────

    def _handle_start(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.repositories.telegram_repository import TelegramRepository

        db = SessionLocal()
        try:
            account = TelegramRepository.get_by_chat_id(db, str(chat_id))

            if account and account.is_connected:
                # Returning user — send OTP directly instead of asking for phone again
                self._handle_login_code(chat_id)
                return

            # New user — ask for phone number
            keyboard = {
                "keyboard": [[{"text": "📱 Share Phone Number", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            self.send_message(
                chat_id,
                "👋 <b>Welcome to TimePilot AI!</b>\n\n"
                "To create or link your account, please tap the button below to share your phone number.\n\n"
                "You'll receive a login code here on Telegram.",
                reply_markup=keyboard
            )
        finally:
            db.close()

    # ── /code or /login ───────────────────────────────────────────────────────

    def _handle_login_code(self, chat_id) -> None:
        """Generate and send OTP to a returning user."""
        from backend.database import SessionLocal
        from backend.services.telegram_auth_service import TelegramAuthService

        db = SessionLocal()
        try:
            TelegramAuthService.handle_returning_user_code(
                chat_id=str(chat_id),
                db=db,
                send_message_fn=self.send_message,
            )
        finally:
            db.close()

    # ── Contact Sharing → First-time OTP ──────────────────────────────────────

    def _handle_contact(self, chat_id, contact: dict, user_obj: dict) -> None:
        phone_number = contact.get("phone_number")
        if not phone_number:
            return

        # Standardize phone number (add + if missing)
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        telegram_username = user_obj.get("username")

        from backend.database import SessionLocal
        from backend.services.telegram_auth_service import TelegramAuthService

        # Remove custom keyboard first
        remove_kb = {"remove_keyboard": True}
        self.send_message(chat_id, "📱 Phone number received! Generating your login code...", reply_markup=remove_kb)

        db = SessionLocal()
        try:
            TelegramAuthService.handle_new_user_contact(
                chat_id=str(chat_id),
                phone_number=phone_number,
                telegram_username=telegram_username,
                db=db,
                send_message_fn=self.send_message,
            )
        except Exception as exc:
            self.send_message(chat_id, "⚠️ Failed to generate login code due to an internal error. Please try again.")
            print(f"[TelegramProvider] Contact handling error: {exc}")
        finally:
            db.close()

    # ── Today's Schedule (timezone-correct) ───────────────────────────────────

    def _handle_today_schedule(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.repositories.telegram_repository import TelegramRepository
        from backend.repositories.event_repository import EventRepository
        from backend.repositories.user_repository import UserRepository
        from backend.services.timezone_service import TimezoneService

        db = SessionLocal()
        try:
            account = TelegramRepository.get_by_chat_id(db, str(chat_id))
            if not account:
                self.send_message(
                    chat_id,
                    "⚠️ Your Telegram is not linked to a TimePilot account yet.\n"
                    "Send /start to get started.",
                )
                return

            user = UserRepository.get_by_id(db, account.user_id)
            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"

            # Get events for today in the user's local timezone
            day_start, day_end = TimezoneService.day_bounds_utc(user_tz)
            events = EventRepository.get_for_period(db, account.user_id, day_start, day_end)

            if not events:
                self.send_message(
                    chat_id,
                    "📅 <b>Today's Schedule</b>\n\nNo events scheduled for today. Enjoy your free time! 🎉"
                )
                return

            lines = []
            for e in events:
                # Convert UTC start time to user's local timezone for display
                local_start = TimezoneService.to_user_tz(e.start_datetime, user_tz)
                time_str = local_start.strftime("%I:%M %p") if local_start else "?"
                lines.append(f"  • {time_str} — <b>{e.title}</b>")

            self.send_message(chat_id, f"📅 <b>Today's Schedule</b>\n\n" + "\n".join(lines))
        finally:
            db.close()

    # ── Expense NLP Flow ──────────────────────────────────────────────────────

    def _handle_expense_nlp(self, chat_id, text: str) -> None:
        try:
            from backend.services.gemini_expense_parser import gemini_expense_parser
            parsed = gemini_expense_parser.parse(text)
        except Exception as exc:
            self.send_message(chat_id, f"⚠️ Could not parse expense: {exc}")
            return

        _pending[str(chat_id)] = {"type": "expense", "data": parsed, "raw": text}

        self.send_message(
            chat_id,
            f"💰 <b>Confirm Expense</b>\n\n"
            f"  Amount:      ₹{parsed.get('amount', '0')}\n"
            f"  Category:    {parsed.get('category', 'unknown')}\n"
            f"  Description: {parsed.get('description') or '—'}\n\n"
            f"Reply <b>confirm</b> to save or <b>cancel</b> to discard."
        )

    # ── Schedule NLP Flow ─────────────────────────────────────────────────────

    def _handle_schedule_nlp(self, chat_id, text: str) -> None:
        try:
            from backend.services.gemini_schedule_parser import gemini_parser
            parsed = gemini_parser.parse(text)
        except Exception as exc:
            self.send_message(chat_id, f"⚠️ Could not parse schedule: {exc}")
            return

        _pending[str(chat_id)] = {"type": "schedule", "data": parsed, "raw": text}

        self.send_message(
            chat_id,
            f"📅 <b>Confirm Event</b>\n\n"
            f"  Title:  {parsed.get('title', '—')}\n"
            f"  Type:   {parsed.get('event_type', '—')}\n"
            f"  Start:  {parsed.get('start_datetime', '—')}\n\n"
            f"Reply <b>confirm</b> to save or <b>cancel</b> to discard."
        )

    # ── Confirm / Cancel ──────────────────────────────────────────────────────

    def _handle_confirm(self, chat_id) -> None:
        pending = _pending.pop(str(chat_id), None)
        if not pending:
            self.send_message(chat_id, "⚠️ No pending action to confirm.")
            return

        if pending["type"] == "expense":
            self._save_expense(chat_id, pending["data"])
        elif pending["type"] == "schedule":
            self._save_schedule(chat_id, pending["data"])

    def _handle_cancel(self, chat_id) -> None:
        _pending.pop(str(chat_id), None)
        self.send_message(chat_id, "❌ Action cancelled.")

    def _save_expense(self, chat_id, data: dict) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal
        from backend.database import SessionLocal
        from backend.repositories.telegram_repository import TelegramRepository
        from backend.repositories.expense_repository import ExpenseRepository

        db = SessionLocal()
        try:
            account = TelegramRepository.get_by_chat_id(db, str(chat_id))
            if not account:
                self.send_message(chat_id, "⚠️ Account not linked. Please send /start first.")
                return

            ExpenseRepository.create(
                db=db,
                user_id=account.user_id,
                amount=Decimal(str(data["amount"])),
                category=data["category"],
                description=data.get("description"),
                expense_date=datetime.now(timezone.utc),
            )
            self.send_message(
                chat_id,
                f"✅ <b>Expense saved!</b>\n₹{data.get('amount', 0)} on {data.get('category', 'misc')} logged successfully."
            )

            # SSE broadcast
            try:
                from backend.api.sse import broadcast_event
                broadcast_event(account.user_id, "budget_updated", {"source": "telegram"})
            except Exception:
                pass

        except Exception as exc:
            self.send_message(chat_id, f"⚠️ Failed to save expense: {exc}")
        finally:
            db.close()

    def _save_schedule(self, chat_id, data: dict) -> None:
        from datetime import datetime
        from backend.database import SessionLocal
        from backend.repositories.telegram_repository import TelegramRepository
        from backend.repositories.event_repository import EventRepository
        from backend.repositories.user_repository import UserRepository
        from backend.models.event import EventType
        from backend.services.timezone_service import TimezoneService
        from backend.services.notification_service import NotificationService

        db = SessionLocal()
        try:
            account = TelegramRepository.get_by_chat_id(db, str(chat_id))
            if not account:
                self.send_message(chat_id, "⚠️ Account not linked. Please send /start first.")
                return

            user = UserRepository.get_by_id(db, account.user_id)
            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"

            try:
                # Parse datetime from Gemini output
                start_local = datetime.fromisoformat(data["start_datetime"])
                end_local   = datetime.fromisoformat(data["end_datetime"]) if data.get("end_datetime") else None
            except (ValueError, KeyError, TypeError):
                self.send_message(
                    chat_id,
                    "⚠️ Failed to parse the exact date and time. Please schedule via the web app."
                )
                return

            # CRITICAL: Convert from user's local timezone to UTC before storing
            start_utc = TimezoneService.to_utc(start_local, user_tz)
            end_utc   = TimezoneService.to_utc(end_local, user_tz) if end_local else None

            # Ensure enum matches
            event_type_str = data.get("event_type", "meeting")
            try:
                event_type = EventType(event_type_str)
            except ValueError:
                event_type = EventType.meeting

            event = EventRepository.create(
                db=db,
                user_id=account.user_id,
                title=data.get("title", "Event"),
                description=data.get("notes"),
                event_type=event_type,
                start_datetime=start_utc,   # Always store UTC
                end_datetime=end_utc,
            )

            # Auto-schedule notification
            if user:
                try:
                    NotificationService.schedule_event_notification(db, event, user)
                except Exception as exc:
                    print(f"[TelegramProvider] Notification scheduling failed: {exc}")

            # Show confirmation in user's local time
            local_start = TimezoneService.to_user_tz(start_utc, user_tz)
            time_str = local_start.strftime("%I:%M %p, %b %d") if local_start else str(start_utc)

            self.send_message(
                chat_id,
                f"✅ <b>Event scheduled!</b>\n"
                f"<b>{data.get('title')}</b> at {time_str} is now on your calendar."
            )

            # SSE broadcast
            try:
                from backend.api.sse import broadcast_event
                broadcast_event(account.user_id, "event_created", {
                    "event_id": event.id,
                    "title": event.title,
                    "source": "telegram",
                })
            except Exception:
                pass

        except Exception as exc:
            self.send_message(chat_id, f"⚠️ Failed to save event: {exc}")
            print(f"[TelegramProvider] _save_schedule error: {exc}")
        finally:
            db.close()
