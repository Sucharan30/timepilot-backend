"""
backend/providers/telegram/telegram_provider.py

Concrete Telegram provider with full command handling.

Supported commands / messages:
  "Hello"                  → greeting
  "show today's schedule"  → list today's events
  "Spent ₹500 on food"     → expense NLP → confirmation flow
  "Meeting Friday 3 PM"    → schedule NLP → confirmation flow
  "confirm"                → save pending action
  "cancel"                 → discard pending action

Confirmation flow uses an in-memory pending store keyed by chat_id.
(For multi-process Railway deployments, replace with Redis or DB table.)
"""
import httpx
from typing import Any

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

        # ── Contact Sharing (Account Linking) ─────────────────────────────────
        if "contact" in message:
            self._handle_contact(chat_id, message["contact"])
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

        # ── Hello / greeting ──────────────────────────────────────────────────
        if text_lower in ("hello", "hi", "hey", "/start"):
            self._handle_start(chat_id)
            return

        # ── Today's schedule ──────────────────────────────────────────────────
        if "today" in text_lower and ("schedule" in text_lower or "event" in text_lower):
            self._handle_today_schedule(chat_id, user_obj)
            return

        # ── Expense detection: contains currency keywords ─────────────────────
        if any(kw in text_lower for kw in ("spent", "spend", "₹", "rs", "rupee", "bought", "paid")):
            self._handle_expense_nlp(chat_id, text)
            return

        # ── Schedule detection: everything else goes to schedule parser ───────
        self._handle_schedule_nlp(chat_id, text)

    # ── Authentication / Start ────────────────────────────────────────────────

    def _handle_start(self, chat_id) -> None:
        from backend.database import SessionLocal
        from backend.models.telegram_account import TelegramAccount
        
        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(
                TelegramAccount.telegram_chat_id == str(chat_id)
            ).first()
            
            if not account or not account.is_connected:
                # Ask for phone number
                keyboard = {
                    "keyboard": [[{"text": "📱 Share Phone Number", "request_contact": True}]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True
                }
                self.send_message(
                    chat_id,
                    "👋 <b>Welcome to TimePilot AI!</b>\n\n"
                    "To link your Telegram to your TimePilot account, please tap the button below to share your phone number.",
                    reply_markup=keyboard
                )
                return
        finally:
            db.close()

        # Already linked
        self.send_message(chat_id,
            "👋 <b>Hello! I am TimePilot AI.</b>\n\n"
            "Here's what I can do:\n"
            "• <code>show today's schedule</code> — see today's events\n"
            "• <code>Meeting Friday 3 PM</code> — schedule an event\n"
            "• <code>Spent ₹500 on food</code> — log an expense\n"
            "• <code>confirm</code> / <code>cancel</code> — confirm or cancel a pending action"
        )

    def _handle_contact(self, chat_id, contact: dict) -> None:
        phone_number = contact.get("phone_number")
        if not phone_number:
            return
            
        # Standardize phone number (add + if missing)
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number
            
        from backend.database import SessionLocal
        from backend.models.user import User
        from backend.models.telegram_account import TelegramAccount
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.phone_number == phone_number).first()
            if not user:
                # Remove custom keyboard
                remove_kb = {"remove_keyboard": True}
                self.send_message(
                    chat_id, 
                    f"⚠️ No TimePilot account found with `{phone_number}`.\n\n"
                    "Please log into the web app first, then come back and type `/start` again.",
                    reply_markup=remove_kb
                )
                return
                
            # Create or update TelegramAccount
            account = db.query(TelegramAccount).filter(TelegramAccount.user_id == user.id).first()
            if not account:
                account = TelegramAccount(user_id=user.id)
                db.add(account)
                
            account.telegram_chat_id = str(chat_id)
            account.is_connected = True
            db.commit()
            
            remove_kb = {"remove_keyboard": True}
            self.send_message(
                chat_id,
                "✅ <b>Account Linked Successfully!</b>\n\n"
                "You can now manage your schedule and expenses directly from Telegram.\n"
                "Try saying: <code>show today's schedule</code>",
                reply_markup=remove_kb
            )
        except Exception as exc:
            self.send_message(chat_id, "⚠️ Failed to link account due to an internal error.")
            print(f"[TelegramProvider] Contact linking error: {exc}")
        finally:
            db.close()

    # ── Today's Schedule ──────────────────────────────────────────────────────

    def _handle_today_schedule(self, chat_id, user_obj: dict) -> None:
        # We don't have user_id here — telegram_chat_id is the link.
        # Lookup the user by chat_id in DB.
        from backend.database import SessionLocal
        from backend.models.telegram_account import TelegramAccount
        from backend.repositories.event_repository import EventRepository

        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(
                TelegramAccount.telegram_chat_id == str(chat_id)
            ).first()
            if not account:
                self.send_message(chat_id, "⚠️ Your Telegram is not linked to a TimePilot account yet.\nPlease log in via the app first.")
                return

            events = EventRepository.get_today_for_user(db, account.user_id)
            if not events:
                self.send_message(chat_id, "📅 <b>Today's Schedule</b>\n\nNo events scheduled for today. Enjoy your free time! 🎉")
                return

            lines = "\n".join([f"  • {e.start_datetime.strftime('%I:%M %p')} — <b>{e.title}</b>" for e in events])
            self.send_message(chat_id, f"📅 <b>Today's Schedule</b>\n\n{lines}")
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
            f"  Date:   {parsed.get('date') or '—'}\n"
            f"  Time:   {parsed.get('time') or '—'}\n\n"
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
            self.send_message(
                chat_id,
                "✅ <b>Event noted!</b>\n\n"
                "To set the exact date/time, please use the TimePilot app "
                "or call POST /schedule/confirm with the full datetime.\n\n"
                f"Title: <b>{pending['data'].get('title', '—')}</b>"
            )

    def _handle_cancel(self, chat_id) -> None:
        _pending.pop(str(chat_id), None)
        self.send_message(chat_id, "❌ Action cancelled.")

    def _save_expense(self, chat_id, data: dict) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal
        from backend.database import SessionLocal
        from backend.models.telegram_account import TelegramAccount
        from backend.repositories.expense_repository import ExpenseRepository

        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(
                TelegramAccount.telegram_chat_id == str(chat_id)
            ).first()
            if not account:
                self.send_message(chat_id, "⚠️ Account not linked. Please log in via the app first.")
                return

            ExpenseRepository.create(
                db=db,
                user_id=account.user_id,
                amount=Decimal(str(data["amount"])),
                category=data["category"],
                description=data.get("description"),
                expense_date=datetime.now(timezone.utc),
            )
            self.send_message(chat_id, f"✅ <b>Expense saved!</b>\n₹{data.get('amount', 0)} on {data.get('category', 'misc')} logged successfully.")
        except Exception as exc:
            self.send_message(chat_id, f"⚠️ Failed to save expense: {exc}")
        finally:
            db.close()
