"""
backend/models/__init__.py

Import every model here so that Base.metadata.create_all() in main.py
can discover all tables automatically.
"""
from backend.models.user import User                          # noqa: F401
from backend.models.otp_verification import OTPVerification  # noqa: F401
from backend.models.session import UserSession                # noqa: F401
from backend.models.telegram_account import TelegramAccount  # noqa: F401
