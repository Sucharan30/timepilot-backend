"""
backend/providers/telegram/telegram_provider.py

Full-featured Telegram bot with Intent Router.

Architecture:
  Message → Intent Detection → Local Handler → (Gemini only for complex NLP)

Intent Categories:
  greeting      → hi, hello, hey
  thanks        → thanks, thank you
  bye           → bye, goodbye
  help          → help, /help
  status        → "how am i doing"
  schedule_view → today's schedule, tomorrow's schedule
  schedule_crud → create/update/delete events via NLP
  expense_crud  → log/update/delete expenses
  budget_crud   → set/show/update/delete budgets
  study         → study plan commands
  analytics     → show analytics/stats
  auth          → /start, /code, /login
  confirm/cancel → confirm, yes / cancel, no
  fallback      → Gemini
"""
import re
import httpx
from typing import Any, Optional

from backend.providers.telegram.base import TelegramProviderBase
from backend.core.config import get_settings

settings = get_settings()

_API_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

# In-memory pending confirmation store: {chat_id: {type, data, raw}}
_pending: dict = {}

# Conversation state: {chat_id: {"step": str, "data": dict}}
_state: dict = {}


# ── Intent Detection ──────────────────────────────────────────────────────────

def detect_intent(text: str) -> str:
    t = text.lower().strip()

    # Auth
    if t in ("/start", "start"):
        return "start"
    if t in ("/code", "/login", "code", "login"):
        return "login"

    # Confirm / Cancel
    if t in ("confirm", "yes", "/confirm", "y", "ok", "save"):
        return "confirm"
    if t in ("cancel", "no", "/cancel", "n", "nope", "discard"):
        return "cancel"

    # Greetings
    if any(t.startswith(g) for g in ("hi", "hello", "hey", "good morning", "good afternoon", "good evening", "namaste", "sup", "howdy")):
        return "greeting"

    # Thanks
    if any(kw in t for kw in ("thank", "thanks", "thx", "ty")):
        return "thanks"

    # Bye
    if any(kw in t for kw in ("bye", "goodbye", "see you", "cya", "ttyl", "take care")):
        return "bye"

    # Help
    if t in ("/help", "help", "commands", "what can you do", "?"):
        return "help"

    # Status / How am I doing
    if any(kw in t for kw in ("how am i", "how i am", "my status", "my stats", "my progress", "how doing")):
        return "status"

    # Explicit CREATE commands (highest priority for schedule)
    if any(kw in t for kw in ("schedule a", "schedule an", "create a", "add a", "remind me", "set a reminder", "book a")):
        return "schedule_create"

    # Schedule VIEW
    if any(phrase in t for phrase in ("my schedule", "what is my schedule", "show my schedule", "today's schedule", "schedule for today")):
        return "schedule_today"
    if any(phrase in t for phrase in ("tomorrow's schedule", "schedule for tomorrow")):
        return "schedule_tomorrow"
    if "upcoming" in t or ("next" in t and "schedule" in t):
        return "schedule_upcoming"
    if "show" in t and any(kw in t for kw in ("event", "meeting", "schedule", "appointment")):
        return "schedule_today"

    # Schedule DELETE
    if any(kw in t for kw in ("delete event", "remove event", "cancel event", "delete meeting", "cancel meeting", "remove meeting")):
        return "delete_event"
    if t.startswith("delete ") or t.startswith("remove "):
        # Could be delete event, expense or budget
        if any(kw in t for kw in ("budget", "limit")):
            return "delete_budget"
        if any(kw in t for kw in ("expense", "spent", "spending")):
            return "delete_expense"
        return "delete_event"

    # Expense VIEW
    if "show" in t and any(kw in t for kw in ("expense", "spending", "spent", "money")):
        if "today" in t:
            return "expense_today"
        return "expense_month"
    if "today" in t and any(kw in t for kw in ("expense", "spent")):
        return "expense_today"

    # Budget CRUD
    if any(kw in t for kw in ("set budget", "budget for", "set food budget", "set travel", "set shopping")):
        return "set_budget"
    if t.startswith("set ") and "budget" in t:
        return "set_budget"
    if "increase" in t and "budget" in t:
        return "update_budget"
    if "decrease" in t and "budget" in t:
        return "update_budget"
    if "show" in t and "budget" in t:
        return "show_budget"
    if "remaining" in t and "budget" in t:
        return "show_budget"
    if "budget" in t and any(kw in t for kw in ("₹", "rs", "rupee", "inr")):
        return "set_budget"

    # Study
    if any(kw in t for kw in ("study plan", "study schedule", "create study", "exam", "chapters")):
        return "study"

    # Analytics
    if any(kw in t for kw in ("analytics", "statistics", "stats", "productivity", "report", "my report")):
        return "analytics"

    # Expense CREATE (keywords that strongly suggest logging an expense)
    if any(kw in t for kw in ("spent", "spend", "₹", "rs ", "rupee", "bought", "paid", "purchased", "expense")):
        return "expense_create"

    # Schedule CREATE / General Conversational Fallback
    return "schedule_create"


# ── Main Provider ─────────────────────────────────────────────────────────────

class TelegramProvider(TelegramProviderBase):

    def send_message(self, chat_id: str | int, text: str, reply_markup: dict = None) -> bool:
        if not settings.TELEGRAM_BOT_TOKEN:
            return False

        url = f"{_API_BASE}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            response = httpx.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            print(f"[TelegramProvider] send_message error: {exc}")
            return False

    def handle_update(self, update: dict[str, Any]) -> None:
        # Handle Callback Queries first
        if "callback_query" in update:
            self._handle_callback_query(update["callback_query"])
            return

        message = update.get("message", {})
        if not message:
            return

        chat_id  = message.get("chat", {}).get("id")
        user_obj = message.get("from", {})

        if not chat_id:
            return

        # Contact sharing
        if "contact" in message:
            self._handle_contact(chat_id, message["contact"], user_obj)
            return

        text = (message.get("text") or "").strip()
        if not text:
            return

        intent = detect_intent(text)
        print(f"[TelegramProvider] chat_id={chat_id} intent={intent} text={text[:60]}")

        # ── Auth ──────────────────────────────────────────────────────────────
        if intent == "start":
            self._handle_start(chat_id, user_obj)
        elif intent == "login":
            self._handle_login_code(chat_id)

        # ── Confirm / Cancel ──────────────────────────────────────────────────
        elif intent == "confirm":
            self._handle_confirm(chat_id)
        elif intent == "cancel":
            self._handle_cancel(chat_id)

        # ── Greetings & Social ────────────────────────────────────────────────
        elif intent == "greeting":
            self._handle_greeting(chat_id, user_obj)
        elif intent == "thanks":
            self._handle_thanks(chat_id)
        elif intent == "bye":
            self._handle_bye(chat_id)
        elif intent == "help":
            self._handle_help(chat_id)
        elif intent == "status":
            self._handle_status(chat_id, user_obj)

        # ── Schedule ─────────────────────────────────────────────────────────
        elif intent == "schedule_today":
            self._handle_today_schedule(chat_id, user_obj)
        elif intent == "schedule_tomorrow":
            self._handle_tomorrow_schedule(chat_id, user_obj)
        elif intent == "schedule_upcoming":
            self._handle_upcoming_schedule(chat_id, user_obj)
        elif intent == "delete_event":
            self._handle_delete_event_nlp(chat_id, text, user_obj)

        # ── Expense ───────────────────────────────────────────────────────────
        elif intent == "expense_create":
            self._handle_expense_nlp(chat_id, text)
        elif intent == "expense_today":
            self._handle_expense_view(chat_id, user_obj, period="today")
        elif intent == "expense_month":
            self._handle_expense_view(chat_id, user_obj, period="month")
        elif intent == "delete_expense":
            self._handle_delete_expense_nlp(chat_id, text, user_obj)

        # ── Budget ───────────────────────────────────────────────────────────
        elif intent == "set_budget":
            self._handle_set_budget(chat_id, text, user_obj)
        elif intent == "update_budget":
            self._handle_update_budget(chat_id, text, user_obj)
        elif intent == "show_budget":
            self._handle_show_budget(chat_id, user_obj)
        elif intent == "delete_budget":
            self._handle_delete_budget_nlp(chat_id, text, user_obj)

        # ── Study ─────────────────────────────────────────────────────────────
        elif intent == "study":
            self._handle_study_nlp(chat_id, text, user_obj)

        # ── Analytics ────────────────────────────────────────────────────────
        elif intent == "analytics":
            self._handle_analytics(chat_id, user_obj)

        # ── Schedule Create (Gemini fallback) ─────────────────────────────────
        else:
            self._handle_schedule_nlp(chat_id, text)

    # ════════════════════════════════════════════════════════════════════════════
    # Auth handlers (unchanged)
    # ════════════════════════════════════════════════════════════════════════════

    def _handle_start(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.repositories.telegram_repository import TelegramRepository

        db = SessionLocal()
        try:
            account = TelegramRepository.get_by_chat_id(db, str(chat_id))
            if account and account.is_connected:
                self._handle_login_code(chat_id)
                return

            keyboard = {
                "keyboard": [[{"text": "📱 Share Phone Number", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            self.send_message(
                chat_id,
                "👋 <b>Welcome to TimePilot AI!</b>\n\n"
                "I'm your personal productivity assistant. I can help you:\n"
                "📅 Schedule events\n💰 Track expenses\n📊 Manage budgets\n📚 Plan your study sessions\n\n"
                "To get started, tap the button below to share your phone number.",
                reply_markup=keyboard
            )
        finally:
            db.close()

    def _handle_login_code(self, chat_id) -> None:
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

    def _handle_contact(self, chat_id, contact: dict, user_obj: dict) -> None:
        phone_number = contact.get("phone_number")
        if not phone_number:
            return
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        telegram_username = user_obj.get("username")
        remove_kb = {"remove_keyboard": True}
        self.send_message(chat_id, "📱 Phone number received! Generating your login code...", reply_markup=remove_kb)

        from backend.database import SessionLocal
        from backend.services.telegram_auth_service import TelegramAuthService

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
            self.send_message(chat_id, "⚠️ Failed to generate login code. Please try again.")
            print(f"[TelegramProvider] Contact handling error: {exc}")
        finally:
            db.close()

    # ════════════════════════════════════════════════════════════════════════════
    # Smart Conversation Handlers
    # ════════════════════════════════════════════════════════════════════════════

    def _get_user_from_chat(self, db, chat_id):
        from backend.repositories.telegram_repository import TelegramRepository
        from backend.repositories.user_repository import UserRepository
        account = TelegramRepository.get_by_chat_id(db, str(chat_id))
        if not account:
            return None, None
        user = UserRepository.get_by_id(db, account.user_id)
        return account, user

    def _handle_greeting(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            _, user = self._get_user_from_chat(db, chat_id)
            name = (user.full_name.split()[0] if user and user.full_name else
                    user_obj.get("first_name", "there"))

            from datetime import datetime
            import pytz
            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"
            hour = datetime.now(pytz.timezone(user_tz)).hour
            if hour < 12:
                greeting_word = "Good Morning"
            elif hour < 17:
                greeting_word = "Good Afternoon"
            else:
                greeting_word = "Good Evening"

            menu = {
                "keyboard": [
                    [{"text": "📅 Today's Schedule"}, {"text": "💰 Today's Expenses"}],
                    [{"text": "📊 Show Budget"}, {"text": "📈 Analytics"}],
                    [{"text": "❓ Help"}, {"text": "🤔 How am I doing?"}],
                ],
                "resize_keyboard": True,
            }
            self.send_message(
                chat_id,
                f"{greeting_word} {name}! 👋\n\n"
                f"I'm TimePilot AI, your productivity assistant.\n\n"
                f"What would you like to do today?",
                reply_markup=menu
            )
        finally:
            db.close()

    def _handle_thanks(self, chat_id) -> None:
        import random
        responses = [
            "You're welcome! 😊 Anything else I can help with?",
            "Happy to help! 🚀 Let me know if you need anything.",
            "Anytime! Stay productive! 💪",
            "Of course! That's what I'm here for 😄",
        ]
        self.send_message(chat_id, random.choice(responses))

    def _handle_bye(self, chat_id) -> None:
        import random
        responses = [
            "Have a productive day! 🚀",
            "Goodbye! Stay on top of your schedule! 📅",
            "See you! Don't forget to check your daily briefing tomorrow 🌅",
            "Take care! I'll be here when you need me 😊",
        ]
        self.send_message(chat_id, random.choice(responses))

    def _handle_help(self, chat_id) -> None:
        msg = (
            "🤖 <b>TimePilot AI — Commands Guide</b>\n\n"

            "📅 <b>Schedule</b>\n"
            "  • Today's Schedule\n"
            "  • Tomorrow's Schedule\n"
            "  • Meeting tomorrow 3pm\n"
            "  • Study session every night 9pm\n"
            "  • Delete gym\n\n"

            "💰 <b>Expenses</b>\n"
            "  • Spent ₹300 on food\n"
            "  • Today's Expenses\n"
            "  • Monthly Expenses\n"
            "  • Delete food expense\n\n"

            "💼 <b>Budget</b>\n"
            "  • Set food budget ₹7000\n"
            "  • Show Budget\n"
            "  • Increase travel budget ₹1000\n"
            "  • Delete shopping budget\n\n"

            "📚 <b>Study</b>\n"
            "  • Use the web app to create AI study plans\n"
            "  • Today's Schedule shows study sessions\n\n"

            "📊 <b>Analytics</b>\n"
            "  • Analytics\n"
            "  • How am I doing?\n\n"

            "🔑 <b>Auth</b>\n"
            "  • /start — Link account\n"
            "  • /code — Get login code\n\n"

            "💡 <b>Tip</b>: Just talk naturally! I understand most sentences."
        )
        self.send_message(chat_id, msg)

    def _handle_status(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.services.timezone_service import TimezoneService
        from backend.repositories.event_repository import EventRepository
        from backend.repositories.expense_repository import ExpenseRepository
        from backend.models.streak import Streak

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account or not user:
                self.send_message(chat_id, "⚠️ Please link your account first. Send /start")
                return

            user_tz = getattr(user, "timezone", "Asia/Kolkata")
            day_start, day_end = TimezoneService.day_bounds_utc(user_tz)

            # Today's events
            events = EventRepository.get_for_period(db, user.id, day_start, day_end)

            # Today's spending
            today_expenses = ExpenseRepository.get_for_period(db, user.id, day_start, day_end)
            daily_spend = sum(float(e.amount) for e in today_expenses)

            # Streak
            streak_rec = db.query(Streak).filter(
                Streak.user_id == user.id,
                Streak.streak_type == "productivity"
            ).first()
            streak_count = streak_rec.current_count if streak_rec else 0

            # Events summary
            if events:
                event_lines = "\n".join([
                    f"  • {TimezoneService.to_user_tz(e.start_datetime, user_tz).strftime('%I:%M %p')} — {e.title}"
                    for e in events[:5]
                ])
            else:
                event_lines = "  No events today"

            name = user.full_name.split()[0] if user.full_name else "there"
            self.send_message(
                chat_id,
                f"📊 <b>How You're Doing, {name}!</b>\n\n"
                f"📅 <b>Today's Events ({len(events)})</b>\n{event_lines}\n\n"
                f"💰 <b>Today's Spending</b>: ₹{daily_spend:.2f}\n\n"
                f"🔥 <b>Productivity Streak</b>: {streak_count} day(s)\n\n"
                f"Keep it up! 💪"
            )
        finally:
            db.close()

    # ════════════════════════════════════════════════════════════════════════════
    # Schedule Handlers
    # ════════════════════════════════════════════════════════════════════════════

    def _handle_today_schedule(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.repositories.event_repository import EventRepository
        from backend.services.timezone_service import TimezoneService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first. Send /start")
                return

            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"
            day_start, day_end = TimezoneService.day_bounds_utc(user_tz)
            events = EventRepository.get_for_period(db, account.user_id, day_start, day_end)

            if not events:
                self.send_message(chat_id, "📅 <b>Today's Schedule</b>\n\nNo events scheduled for today. Enjoy your free time! 🎉")
                return

            lines = []
            for e in events:
                local_start = TimezoneService.to_user_tz(e.start_datetime, user_tz)
                time_str = local_start.strftime("%I:%M %p") if local_start else "?"
                icon = {"meeting": "🤝", "task": "✅", "study": "📚", "reminder": "⏰", "appointment": "🏥", "class": "🎓", "deadline": "🔴"}.get(str(e.event_type.value if hasattr(e.event_type, 'value') else e.event_type), "📌")
                lines.append(f"  {icon} {time_str} — <b>{e.title}</b>")

            self.send_message(chat_id, f"📅 <b>Today's Schedule</b>\n\n" + "\n".join(lines))
        finally:
            db.close()

    def _handle_tomorrow_schedule(self, chat_id, user_obj: dict) -> None:
        from datetime import timedelta
        from backend.database import SessionLocal
        from backend.repositories.event_repository import EventRepository
        from backend.services.timezone_service import TimezoneService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"
            day_start, day_end = TimezoneService.day_bounds_utc(user_tz)
            tomorrow_start = day_start + timedelta(days=1)
            tomorrow_end   = day_end + timedelta(days=1)

            events = EventRepository.get_for_period(db, account.user_id, tomorrow_start, tomorrow_end)

            if not events:
                self.send_message(chat_id, "📅 <b>Tomorrow's Schedule</b>\n\nNo events scheduled for tomorrow.")
                return

            lines = [
                f"  • {TimezoneService.to_user_tz(e.start_datetime, user_tz).strftime('%I:%M %p')} — <b>{e.title}</b>"
                for e in events
            ]
            self.send_message(chat_id, "📅 <b>Tomorrow's Schedule</b>\n\n" + "\n".join(lines))
        finally:
            db.close()

    def _handle_upcoming_schedule(self, chat_id, user_obj: dict) -> None:
        from datetime import datetime, timezone, timedelta
        from backend.database import SessionLocal
        from backend.repositories.event_repository import EventRepository
        from backend.services.timezone_service import TimezoneService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"
            now = datetime.now(timezone.utc)
            end = now + timedelta(days=7)

            events = EventRepository.get_for_period(db, account.user_id, now, end)

            if not events:
                self.send_message(chat_id, "📅 <b>Upcoming Events</b>\n\nNo events in the next 7 days.")
                return

            lines = [
                f"  • {TimezoneService.to_user_tz(e.start_datetime, user_tz).strftime('%b %d, %I:%M %p')} — <b>{e.title}</b>"
                for e in events[:10]
            ]
            self.send_message(chat_id, "📅 <b>Upcoming Events (Next 7 Days)</b>\n\n" + "\n".join(lines))
        finally:
            db.close()

    def _handle_delete_event_nlp(self, chat_id, text: str, user_obj: dict) -> None:
        """
        Parse event name from text like "delete gym" and find + confirm deletion.
        """
        from backend.database import SessionLocal
        from backend.repositories.event_repository import EventRepository

        # Extract event name: "delete gym" → "gym"
        patterns = [r"delete (.+)", r"remove (.+)", r"cancel (.+)"]
        event_name = None
        for p in patterns:
            m = re.search(p, text.lower())
            if m:
                event_name = m.group(1).strip()
                break

        if not event_name:
            self.send_message(chat_id, "⚠️ Please specify the event name. Example: 'Delete gym'")
            return

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            events = EventRepository.get_all_for_user(db, account.user_id)
            matches = [e for e in events if event_name.lower() in e.title.lower()]

            if not matches:
                self.send_message(chat_id, f"❌ No event found matching '{event_name}'.")
                return

            if len(matches) > 1:
                options = "\n".join([f"  {i+1}. {e.title}" for i, e in enumerate(matches[:5])])
                # Store for later confirmation
                _pending[str(chat_id)] = {"type": "delete_event_select", "data": {"matches": [{"id": e.id, "title": e.title} for e in matches[:5]]}}
                self.send_message(chat_id, f"📋 Found multiple matches:\n{options}\n\nReply with the number to delete, or 'cancel'.")
                return

            event = matches[0]
            _pending[str(chat_id)] = {"type": "delete_event", "data": {"event_id": event.id, "title": event.title}}
            self.send_message(
                chat_id,
                f"🗑️ <b>Delete Event?</b>\n\n<b>{event.title}</b>\n\nReply <b>confirm</b> to delete or <b>cancel</b> to keep it."
            )
        finally:
            db.close()

    # ════════════════════════════════════════════════════════════════════════════
    # Expense Handlers
    # ════════════════════════════════════════════════════════════════════════════

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

    def _handle_expense_view(self, chat_id, user_obj: dict, period: str = "today") -> None:
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import ExpenseRepository
        from backend.services.timezone_service import TimezoneService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"

            if period == "today":
                day_start, day_end = TimezoneService.day_bounds_utc(user_tz)
                expenses = ExpenseRepository.get_for_period(db, account.user_id, day_start, day_end)
                title = "Today's Expenses"
            else:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                from datetime import timezone as tz
                import pytz
                local_now = datetime.now(pytz.timezone(user_tz))
                start = datetime(local_now.year, local_now.month, 1, tzinfo=timezone.utc)
                expenses = ExpenseRepository.get_for_period(db, account.user_id, start, datetime.now(timezone.utc))
                title = "This Month's Expenses"

            if not expenses:
                self.send_message(chat_id, f"💰 <b>{title}</b>\n\nNo expenses recorded.")
                return

            total = sum(float(e.amount) for e in expenses)
            lines = [f"  • ₹{float(e.amount):.0f} — {e.category}" + (f" ({e.description})" if e.description else "") for e in expenses[:10]]
            self.send_message(
                chat_id,
                f"💰 <b>{title}</b>\n\n" + "\n".join(lines) + f"\n\n<b>Total: ₹{total:.2f}</b>"
            )
        finally:
            db.close()

    def _handle_delete_expense_nlp(self, chat_id, text: str, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import ExpenseRepository
        from backend.services.timezone_service import TimezoneService
        from datetime import datetime, timezone, timedelta

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            # Get recent expenses
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=30)
            expenses = ExpenseRepository.get_for_period(db, account.user_id, start, now)

            # Try to find by category name in text
            words = text.lower().split()
            matches = [e for e in expenses if any(w in str(e.category).lower() or w in str(e.description or "").lower() for w in words if len(w) > 2)]

            if not matches:
                self.send_message(chat_id, "❌ No matching expense found. Try 'Today's Expenses' to see your recent expenses.")
                return

            expense = matches[0]
            _pending[str(chat_id)] = {"type": "delete_expense", "data": {"expense_id": expense.id, "amount": float(expense.amount), "category": expense.category}}
            self.send_message(
                chat_id,
                f"🗑️ <b>Delete Expense?</b>\n\n₹{float(expense.amount):.0f} — {expense.category}\n\nReply <b>confirm</b> to delete."
            )
        finally:
            db.close()

    # ════════════════════════════════════════════════════════════════════════════
    # Budget Handlers
    # ════════════════════════════════════════════════════════════════════════════

    def _parse_budget_from_text(self, text: str):
        """Extract category and amount from text like 'set food budget ₹7000'."""
        categories = ["food", "travel", "shopping", "bills", "entertainment", "education", "medical", "savings", "miscellaneous"]
        category = None
        for cat in categories:
            if cat in text.lower():
                category = cat.capitalize()
                break

        # Extract amount
        amount_match = re.search(r"[₹rs\s]*(\d+[\d,]*)", text.lower().replace(",", ""))
        amount = None
        if amount_match:
            amount = float(amount_match.group(1).replace(",", ""))

        return category, amount

    def _handle_set_budget(self, chat_id, text: str, user_obj: dict) -> None:
        from decimal import Decimal
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import BudgetRepository

        category, amount = self._parse_budget_from_text(text)

        if not category or not amount:
            self.send_message(chat_id, "⚠️ Please specify category and amount.\nExample: 'Set food budget ₹7000'")
            return

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            existing = BudgetRepository.get_by_category(db, account.user_id, category)
            if existing:
                BudgetRepository.update(db, existing, monthly_limit=Decimal(str(amount)))
                self.send_message(chat_id, f"✅ <b>{category}</b> budget updated to <b>₹{amount:.0f}</b>/month")
            else:
                BudgetRepository.create(db, account.user_id, category, Decimal(str(amount)))
                self.send_message(chat_id, f"✅ <b>{category}</b> budget set to <b>₹{amount:.0f}</b>/month")
        finally:
            db.close()

    def _handle_update_budget(self, chat_id, text: str, user_obj: dict) -> None:
        from decimal import Decimal
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import BudgetRepository

        category, amount = self._parse_budget_from_text(text)

        if not category or not amount:
            self.send_message(chat_id, "⚠️ Please specify category and amount.\nExample: 'Increase travel budget ₹1000'")
            return

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            existing = BudgetRepository.get_by_category(db, account.user_id, category)
            if not existing:
                self.send_message(chat_id, f"❌ No budget found for {category}. Create one first: 'Set {category} budget ₹{amount:.0f}'")
                return

            is_increase = "increase" in text.lower() or "add" in text.lower()
            if is_increase:
                new_limit = float(existing.monthly_limit) + amount
            else:
                new_limit = max(0, float(existing.monthly_limit) - amount)

            BudgetRepository.update(db, existing, monthly_limit=Decimal(str(new_limit)))
            action = "increased" if is_increase else "decreased"
            self.send_message(chat_id, f"✅ <b>{category}</b> budget {action} to <b>₹{new_limit:.0f}</b>/month")
        finally:
            db.close()

    def _handle_show_budget(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.services.expense_service import BudgetService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            summary = BudgetService.get_summary(user_id=account.user_id, db=db)

            if not summary:
                self.send_message(chat_id, "💼 <b>Budget</b>\n\nNo budgets set yet.\nExample: 'Set food budget ₹7000'")
                return

            lines = []
            total_limit = 0
            total_spent = 0
            for b in summary:
                pct = b["percentage"]
                bar = "🟩" if pct < 80 else "🟨" if pct < 100 else "🟥"
                lines.append(f"  {bar} <b>{b['category']}</b>\n     ₹{b['spent']:.0f} / ₹{b['monthly_limit']:.0f} ({pct:.0f}%)")
                total_limit += b["monthly_limit"]
                total_spent += b["spent"]

            self.send_message(
                chat_id,
                f"💼 <b>Monthly Budget Status</b>\n\n" +
                "\n\n".join(lines) +
                f"\n\n📊 <b>Total: ₹{total_spent:.0f} / ₹{total_limit:.0f}</b>"
            )
        finally:
            db.close()

    def _handle_delete_budget_nlp(self, chat_id, text: str, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import BudgetRepository

        categories = ["food", "travel", "shopping", "bills", "entertainment", "education", "medical", "savings", "miscellaneous"]
        category = None
        for cat in categories:
            if cat in text.lower():
                category = cat.capitalize()
                break

        if not category:
            self.send_message(chat_id, "⚠️ Please specify the budget category.\nExample: 'Delete shopping budget'")
            return

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            existing = BudgetRepository.get_by_category(db, account.user_id, category)
            if not existing:
                self.send_message(chat_id, f"❌ No budget found for {category}.")
                return

            _pending[str(chat_id)] = {"type": "delete_budget", "data": {"budget_id": existing.id, "category": category}}
            self.send_message(
                chat_id,
                f"🗑️ <b>Delete {category} budget?</b>\n\nReply <b>confirm</b> to delete or <b>cancel</b> to keep."
            )
        finally:
            db.close()

    # ════════════════════════════════════════════════════════════════════════════
    # Analytics Handler
    # ════════════════════════════════════════════════════════════════════════════

    def _handle_analytics(self, chat_id, user_obj: dict) -> None:
        from backend.database import SessionLocal
        from backend.services.analytics_service import AnalyticsService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Please link your account first.")
                return

            data = AnalyticsService.daily(user_id=account.user_id, db=db)
            self.send_message(
                chat_id,
                f"📊 <b>Today's Analytics</b>\n\n"
                f"🎯 Productivity Score: <b>{data.productivity_score}/100</b>\n"
                f"📚 Study Time: <b>{data.total_study_minutes} min</b>\n"
                f"🤝 Meeting Time: <b>{data.total_meeting_minutes} min</b>\n"
                f"📅 Events: <b>{data.event_count}</b>\n"
                f"💰 Expenses: <b>₹{float(data.total_expenses):.2f}</b>\n\n"
                f"View full analytics on the web app! 🌐"
            )
        finally:
            db.close()

    # ════════════════════════════════════════════════════════════════════════════
    # Study Info
    # ════════════════════════════════════════════════════════════════════════════

    def _handle_study_info(self, chat_id) -> None:
        self.send_message(
            chat_id,
            "📚 <b>Study Planner</b>\n\n"
            "To create an AI-powered study plan:\n\n"
            "1. Open the <b>TimePilot web app</b>\n"
            "2. Go to <b>Study Planner</b> page\n"
            "3. Enter your subject, chapters, and exam date\n"
            "4. Accept the AI-generated schedule\n\n"
            "Your study sessions will then appear in:\n"
            "📅 Today's Schedule (Telegram)\n"
            "🗓️ Calendar (web app)\n"
            "📊 Analytics (counts as study time)\n\n"
            "Today's schedule: Just type <b>Today's Schedule</b>"
        )

    # ════════════════════════════════════════════════════════════════════════════
    # Confirm / Cancel
    # ════════════════════════════════════════════════════════════════════════════

    def _handle_confirm(self, chat_id) -> None:
        pending = _pending.pop(str(chat_id), None)
        if not pending:
            self.send_message(chat_id, "⚠️ No pending action to confirm.")
            return

        ptype = pending["type"]
        data  = pending["data"]

        if ptype == "expense":
            self._save_expense(chat_id, data)
        elif ptype == "schedule":
            self._save_schedule(chat_id, data)
        elif ptype == "delete_event":
            self._do_delete_event(chat_id, data["event_id"], data["title"])
        elif ptype == "delete_expense":
            self._do_delete_expense(chat_id, data["expense_id"], data["category"])
        elif ptype == "delete_budget":
            self._do_delete_budget(chat_id, data["budget_id"], data["category"])
        elif ptype == "study_plan":
            self._save_study_plan(chat_id, data)
        else:
            self.send_message(chat_id, "⚠️ Unknown pending action.")

    def _handle_cancel(self, chat_id) -> None:
        _pending.pop(str(chat_id), None)
        self.send_message(chat_id, "❌ Action cancelled.")

    # ════════════════════════════════════════════════════════════════════════════
    # Save Helpers
    # ════════════════════════════════════════════════════════════════════════════

    def _save_expense(self, chat_id, data: dict) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import ExpenseRepository

        db = SessionLocal()
        try:
            account, _ = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Account not linked. Send /start first.")
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
                f"✅ <b>Expense saved!</b>\n₹{data.get('amount', 0)} on {data.get('category', 'misc')} logged."
            )
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
        from backend.repositories.event_repository import EventRepository
        from backend.repositories.user_repository import UserRepository
        from backend.models.event import EventType
        from backend.services.timezone_service import TimezoneService
        from backend.services.notification_service import NotificationService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Account not linked. Send /start first.")
                return

            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"

            try:
                start_local = datetime.fromisoformat(data["start_datetime"])
                end_local   = datetime.fromisoformat(data["end_datetime"]) if data.get("end_datetime") else None
            except (ValueError, KeyError, TypeError):
                self.send_message(chat_id, "⚠️ Failed to parse time. Please schedule via the web app.")
                return

            start_utc = TimezoneService.to_utc(start_local, user_tz)
            end_utc   = TimezoneService.to_utc(end_local, user_tz) if end_local else None

            try:
                event_type = EventType(data.get("event_type", "meeting"))
            except ValueError:
                event_type = EventType.meeting

            event = EventRepository.create(
                db=db,
                user_id=account.user_id,
                title=data.get("title", "Event"),
                description=data.get("notes"),
                event_type=event_type,
                start_datetime=start_utc,
                end_datetime=end_utc,
            )

            if user:
                try:
                    NotificationService.schedule_event_notification(db, event, user)
                except Exception:
                    pass

            local_start = TimezoneService.to_user_tz(start_utc, user_tz)
            time_str = local_start.strftime("%I:%M %p, %b %d") if local_start else str(start_utc)

            self.send_message(
                chat_id,
                f"✅ <b>Event scheduled!</b>\n<b>{data.get('title')}</b> at {time_str} is now on your calendar."
            )

            try:
                from backend.api.sse import broadcast_event
                broadcast_event(account.user_id, "event_created", {"event_id": event.id, "title": event.title, "source": "telegram"})
            except Exception:
                pass
        except Exception as exc:
            self.send_message(chat_id, f"⚠️ Failed to save event: {exc}")
        finally:
            db.close()

    def _save_study_plan(self, chat_id, data: list) -> None:
        from datetime import datetime
        from backend.database import SessionLocal
        from backend.repositories.event_repository import EventRepository
        from backend.models.event import EventType
        from backend.services.timezone_service import TimezoneService
        from backend.services.notification_service import NotificationService

        db = SessionLocal()
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if not account:
                self.send_message(chat_id, "⚠️ Account not linked.")
                return

            user_tz = getattr(user, "timezone", "Asia/Kolkata") if user else "Asia/Kolkata"
            events_created = 0

            for session in data:
                try:
                    start_local = datetime.fromisoformat(session["start_datetime"])
                    end_local   = datetime.fromisoformat(session["end_datetime"]) if session.get("end_datetime") else None
                except (ValueError, KeyError, TypeError):
                    continue

                start_utc = TimezoneService.to_utc(start_local, user_tz)
                end_utc   = TimezoneService.to_utc(end_local, user_tz) if end_local else None

                event = EventRepository.create(
                    db=db,
                    user_id=account.user_id,
                    title=session.get("title", "Study Session"),
                    description=session.get("description"),
                    event_type=EventType.study,
                    start_datetime=start_utc,
                    end_datetime=end_utc,
                )
                events_created += 1

                if user:
                    try:
                        NotificationService.schedule_event_notification(db, event, user)
                    except Exception:
                        pass

            self.send_message(
                chat_id,
                f"✅ <b>Study Plan Saved!</b>\n{events_created} sessions added to your calendar."
            )

            try:
                from backend.api.sse import broadcast_event
                broadcast_event(account.user_id, "event_created", {"source": "telegram_study"})
            except Exception:
                pass
        except Exception as exc:
            self.send_message(chat_id, f"⚠️ Failed to save study plan: {exc}")
        finally:
            db.close()

    def _do_delete_event(self, chat_id, event_id: int, title: str) -> None:
        from backend.database import SessionLocal
        from backend.repositories.event_repository import EventRepository

        db = SessionLocal()
        try:
            account, _ = self._get_user_from_chat(db, chat_id)
            if not account:
                return
            event = EventRepository.get_by_id(db, event_id, account.user_id)
            if event:
                EventRepository.delete(db, event)
                self.send_message(chat_id, f"✅ <b>{title}</b> deleted.")
            else:
                self.send_message(chat_id, "❌ Event not found or already deleted.")
        finally:
            db.close()

    def _do_delete_expense(self, chat_id, expense_id: int, category: str) -> None:
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import ExpenseRepository

        db = SessionLocal()
        try:
            account, _ = self._get_user_from_chat(db, chat_id)
            if not account:
                return
            expense = ExpenseRepository.get_by_id(db, expense_id, account.user_id)
            if expense:
                ExpenseRepository.delete(db, expense)
                self.send_message(chat_id, f"✅ {category} expense deleted.")
            else:
                self.send_message(chat_id, "❌ Expense not found.")
        finally:
            db.close()

    def _do_delete_budget(self, chat_id, budget_id: int, category: str) -> None:
        from backend.database import SessionLocal
        from backend.repositories.expense_repository import BudgetRepository

        db = SessionLocal()
        try:
            account, _ = self._get_user_from_chat(db, chat_id)
            if not account:
                return
            budget = BudgetRepository.get_by_id(db, budget_id, account.user_id)
            if budget:
                BudgetRepository.delete(db, budget)
                self.send_message(chat_id, f"✅ <b>{category}</b> budget deleted.")
            else:
                self.send_message(chat_id, "❌ Budget not found.")
        finally:
            db.close()

    # ════════════════════════════════════════════════════════════════════════════
    # Schedule NLP (Gemini fallback)
    # ════════════════════════════════════════════════════════════════════════════

    def _handle_schedule_nlp(self, chat_id, text: str) -> None:
        from backend.database import SessionLocal
        from backend.services.timezone_service import TimezoneService
        from datetime import datetime
        
        db = SessionLocal()
        user_tz = "Asia/Kolkata"
        context_str = ""
        try:
            account, user = self._get_user_from_chat(db, chat_id)
            if user:
                user_tz = getattr(user, "timezone", "Asia/Kolkata")
                from backend.models.event import Event, EventStatus
                from datetime import timedelta, timezone
                now_utc = datetime.now(timezone.utc)
                next_week_utc = now_utc + timedelta(days=7)
                existing_events = db.query(Event).filter(
                    Event.user_id == user.id,
                    Event.status != EventStatus.cancelled,
                    Event.end_datetime > now_utc,
                    Event.start_datetime < next_week_utc
                ).all()
                if existing_events:
                    context_str = "\n".join([f"- {e.title} ({e.start_datetime.strftime('%Y-%m-%d %H:%M')} to {e.end_datetime.strftime('%H:%M')})" for e in existing_events if e.end_datetime])
                    context_str = f"\nCRITICAL: The user has these events scheduled over the next 7 days:\n{context_str}\nDO NOT schedule new tasks overlapping with these existing events!"
        finally:
            db.close()
            
        try:
            from backend.services.gemini_schedule_parser import gemini_parser
            parsed = gemini_parser.parse(text, user_tz, context_str)
        except Exception as exc:
            self.send_message(chat_id, f"⚠️ I didn't understand that. Try 'help' for a list of commands.\n\nError: {exc}")
            return

        if parsed.get("is_conversational"):
            self.send_message(chat_id, parsed.get("response", "I'm not sure how to respond to that."))
            return

        if not parsed or not parsed.get("title"):
            self.send_message(
                chat_id,
                "🤔 I'm not sure what you mean.\n\n"
                "Try:\n"
                "• <b>Today's Schedule</b>\n"
                "• <b>Spent ₹300 food</b>\n"
                "• <b>Meeting tomorrow 3pm</b>\n"
                "• <b>Help</b>"
            )
            return

        _pending[str(chat_id)] = {"type": "schedule", "data": parsed, "raw": text}
        
        # Format the datetime for display
        display_time = parsed.get("start_datetime", "—")
        try:
            if display_time != "—":
                # Assuming parsed time is ISO format
                parsed_dt = datetime.fromisoformat(display_time)
                local_dt = TimezoneService.to_user_tz(parsed_dt, user_tz)
                display_time = local_dt.strftime("%b %d, %I:%M %p")
        except Exception:
            pass
            
        self.send_message(
            chat_id,
            f"📅 <b>Confirm Event</b>\n\n"
            f"  Title:  {parsed.get('title', '—')}\n"
            f"  Type:   {parsed.get('event_type', '—')}\n"
            f"  Start:  {display_time}\n\n"
            f"Reply <b>confirm</b> to save or <b>cancel</b> to discard."
        )
