"""
backend/main.py

TimePilot AI — FastAPI application entry point.
Railway Procfile: uvicorn backend.main:app --host 0.0.0.0 --port $PORT

Startup:
  - Reads settings from environment variables (Railway Variables / .env)
  - Creates all DB tables via SQLAlchemy (migration-ready; Alembic can take over later)
  - Registers all API routers

Existing health-check endpoints (/  /db-test  /tables) are preserved.
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from backend.database import engine, Base
from backend.core.config import get_settings
from backend.core.dependencies import get_db

# ── CRITICAL: Import ALL models BEFORE create_all() ──────────────────────────
# This registers every table with Base.metadata.
# Order matters — models with FK dependencies must import their parent models first.
from backend.models.user import User                          # noqa: F401
from backend.models.otp_verification import OTPVerification  # noqa: F401
from backend.models.session import UserSession                # noqa: F401
from backend.models.telegram_account import TelegramAccount  # noqa: F401

# ── Routers ───────────────────────────────────────────────────────────────────
from backend.api.auth import router as auth_router
from backend.api.telegram import router as telegram_router

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TimePilot AI",
    description="AI-powered scheduling assistant backend",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (permit Next.js frontend on any origin during development) ────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Tighten in production to specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database table creation on startup ───────────────────────────────────────
# create_all() only creates tables that don't exist yet — it does NOT alter
# existing tables. If your schema changed, run: python scripts/reset_auth_tables.py
Base.metadata.create_all(bind=engine)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(telegram_router)


# =============================================================================
# Health-check endpoints (unchanged from Day-1 — kept for Railway monitoring)
# =============================================================================

@app.get("/", tags=["Health"])
def root():
    """Basic liveness check."""
    return {"status": "running", "version": "0.2.0", "app": "TimePilot AI"}


@app.get("/db-test", tags=["Health"])
def db_test():
    """Verifies the Aiven MySQL connection is alive."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return {
                "database": "connected",
                "result": result.scalar(),
            }
    except Exception as e:
        return {
            "database": "failed",
            "error": str(e),
        }


@app.get("/tables", tags=["Health"])
def tables():
    """Lists all tables currently in the connected database."""
    with engine.connect() as conn:
        result = conn.execute(text("SHOW TABLES"))
        return {"tables": [row[0] for row in result]}


@app.get("/schema-check", tags=["Health"])
def schema_check():
    """
    Returns the actual column names of all 4 auth tables as they exist
    in the database RIGHT NOW. Use this to verify the schema matches the models.

    Expected columns:
      users:              id, phone_number, full_name, is_active, is_verified, created_at, updated_at
      otp_verifications:  id, phone_number, otp_code, expires_at, is_used, created_at
      sessions:           id, user_id, refresh_token, expires_at, created_at
      telegram_accounts:  id, user_id, telegram_chat_id, telegram_username, is_connected, created_at
    """
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    def get_columns(table_name: str) -> list[str]:
        if table_name not in existing_tables:
            return [f"TABLE '{table_name}' DOES NOT EXIST"]
        return [col["name"] for col in inspector.get_columns(table_name)]

    # Expected columns from SQLAlchemy models
    expected = {
        "users": ["id", "phone_number", "full_name", "is_active", "is_verified", "created_at", "updated_at"],
        "otp_verifications": ["id", "phone_number", "otp_code", "expires_at", "is_used", "created_at"],
        "sessions": ["id", "user_id", "refresh_token", "expires_at", "created_at"],
        "telegram_accounts": ["id", "user_id", "telegram_chat_id", "telegram_username", "is_connected", "created_at"],
    }

    result = {}
    all_match = True

    for table, exp_cols in expected.items():
        actual_cols = get_columns(table)
        missing = [c for c in exp_cols if c not in actual_cols]
        extra = [c for c in actual_cols if c not in exp_cols and not c.startswith("TABLE")]
        table_ok = len(missing) == 0

        result[table] = {
            "actual_columns": actual_cols,
            "expected_columns": exp_cols,
            "missing_columns": missing,
            "extra_columns": extra,
            "schema_match": table_ok,
        }
        if not table_ok:
            all_match = False

    return {
        "all_schemas_match": all_match,
        "tables": result,
        "action_required": (
            "None — schema is correct!"
            if all_match
            else "Run: python scripts/reset_auth_tables.py to fix mismatches"
        ),
    }


@app.get("/debug/otp-check", tags=["Debug"])
def debug_otp_check(phone_number: str, db: Session = Depends(get_db)):
    """
    DEBUG ONLY — Shows the most recent OTP record stored for a phone number.
    Tells you exactly why verify-otp might be failing:
      - is_used=true  → already used, call send-otp again
      - is_expired=true → expired (>10 min), call send-otp again
      - null result   → phone number never sent an OTP, or table is empty

    Example: GET /debug/otp-check?phone_number=%2B919999999999
    (URL-encode the + as %2B)
    """
    settings = get_settings()
    if not settings.DEBUG:
        return {"error": "Debug endpoints are disabled. Set DEBUG=true in .env"}

    from backend.services.otp_service import OTPService
    record = OTPService.get_latest_otp_debug(phone_number, db)

    if record is None:
        return {
            "found": False,
            "phone_number": phone_number,
            "message": "No OTP record found for this phone number. Call POST /auth/send-otp first.",
        }

    return {
        "found": True,
        "phone_number": phone_number,
        "record": record,
        "diagnosis": (
            "✅ OTP is valid — call POST /auth/verify-otp now"
            if not record["is_used"] and not record["is_expired"]
            else (
                "⚠️ OTP already used — call POST /auth/send-otp to get a new one"
                if record["is_used"]
                else "⚠️ OTP expired — call POST /auth/send-otp to get a new one"
            )
        ),
    }