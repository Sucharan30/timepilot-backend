"""
scripts/reset_auth_tables.py

Safe development script — drops and recreates all authentication-related tables.

USE ONLY IN DEVELOPMENT.
This will permanently delete all data in:
  - users
  - otp_verifications
  - sessions
  - telegram_accounts

Run from the project root (timepilot-backend/):
    python scripts/reset_auth_tables.py

Requirements:
  - Your .env file must exist with DATABASE_URL set
  - venv must be activated
"""
import sys
import os

# ── Make sure backend package is importable ───────────────────────────────────
# This script lives in scripts/, so we add the project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from backend.database import engine, Base

# ── Import all models so Base.metadata knows all tables ───────────────────────
from backend.models.user import User                          # noqa
from backend.models.otp_verification import OTPVerification  # noqa
from backend.models.session import UserSession                # noqa
from backend.models.telegram_account import TelegramAccount  # noqa


def reset_auth_tables():
    print("=" * 60)
    print("TimePilot AI — Auth Table Reset Script")
    print("=" * 60)
    print()

    with engine.connect() as conn:
        # ── Step 1: Disable FK checks so we can drop in any order ─────────────
        print("⏳  Disabling foreign key checks...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.commit()

        # ── Step 2: Drop the 4 auth tables ────────────────────────────────────
        tables_to_drop = [
            "sessions",
            "telegram_accounts",
            "otp_verifications",
            "users",
        ]
        for table in tables_to_drop:
            print(f"🗑️   Dropping table: {table}")
            conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        conn.commit()

        # ── Step 3: Re-enable FK checks ───────────────────────────────────────
        print("✅  Re-enabling foreign key checks...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()

    print()
    print("🏗️   Recreating tables from SQLAlchemy models...")

    # ── Step 4: Recreate all tables ───────────────────────────────────────────
    Base.metadata.create_all(bind=engine)

    print()
    print("🔍  Verifying columns in users table...")

    with engine.connect() as conn:
        result = conn.execute(text("DESCRIBE users"))
        columns = [row[0] for row in result]

    required_columns = [
        "id", "phone_number", "full_name",
        "is_active", "is_verified", "created_at", "updated_at"
    ]

    all_ok = True
    for col in required_columns:
        if col in columns:
            print(f"  ✅  {col}")
        else:
            print(f"  ❌  MISSING: {col}")
            all_ok = False

    print()
    print("🔍  Verifying all 4 auth tables exist...")

    with engine.connect() as conn:
        result = conn.execute(text("SHOW TABLES"))
        existing_tables = [row[0] for row in result]

    expected_tables = ["users", "otp_verifications", "sessions", "telegram_accounts"]
    for table in expected_tables:
        if table in existing_tables:
            print(f"  ✅  {table}")
        else:
            print(f"  ❌  MISSING: {table}")
            all_ok = False

    print()
    if all_ok:
        print("🎉  All tables recreated successfully! Schema matches models.")
    else:
        print("⚠️   Some tables or columns are missing. Check errors above.")

    print("=" * 60)


if __name__ == "__main__":
    reset_auth_tables()
