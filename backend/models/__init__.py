"""
backend/models/__init__.py

Import every model here so that Base.metadata.create_all() in main.py
can discover all tables automatically.
Order: parent tables first, then children (FK dependency order).
"""
from backend.models.user import User                          # noqa: F401
from backend.models.otp_verification import OTPVerification  # noqa: F401
from backend.models.session import UserSession                # noqa: F401
from backend.models.telegram_account import TelegramAccount  # noqa: F401
from backend.models.event import Event                        # noqa: F401
from backend.models.notification import Notification          # noqa: F401
from backend.models.expense import Expense, Budget            # noqa: F401
from backend.models.activity_log import ActivityLog           # noqa: F401
from backend.models.recommendation import Recommendation, AIInsight  # noqa: F401
from backend.models.streak import Streak                      # noqa: F401
