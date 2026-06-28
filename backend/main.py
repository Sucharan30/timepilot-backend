"""
backend/main.py

TimePilot AI — FastAPI application entry point.
Railway Procfile: uvicorn backend.main:app --host 0.0.0.0 --port $PORT

Startup:
  - Reads settings from environment variables (Railway Variables / .env)
  - Creates all DB tables via SQLAlchemy
  - Starts APScheduler (notifications + daily briefing)
  - Registers all API routers
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from backend.database import engine, Base
from backend.core.config import get_settings
from backend.core.dependencies import get_db
from backend.scheduler.scheduler import start_scheduler, stop_scheduler

# ── CRITICAL: Import ALL models BEFORE create_all() ──────────────────────────
# This registers every table with Base.metadata.
# Order matters — models with FK dependencies must import their parent models first.
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
from backend.models.saving_goal import SavingGoal             # noqa: F401
from backend.models.reward import Reward                      # noqa: F401

# ── Routers ──────────────────────────────────────────────────────────
from backend.api.auth import router as auth_router
from backend.api.telegram import router as telegram_router
from backend.api.events import router as events_router
from backend.api.schedule import router as schedule_router
from backend.api.overview import router as overview_router
from backend.api.expenses import router as expenses_router
from backend.api.budget import router as budget_router
from backend.api.analytics import router as analytics_router
from backend.api.ai import router as ai_router
from backend.api.settings import router as settings_router
from backend.api.search import router as search_router
from backend.api.saving_goals import router as saving_goals_router
from backend.api.streaks import router as streaks_router
from backend.api.rewards import router as rewards_router
from backend.api.sse import router as sse_router
from backend.api.notifications import router as notifications_router
from backend.api.study_planner import router as study_planner_router
from backend.api.ai_schedule import router as ai_schedule_router

# ── Lifespan (startup + shutdown) ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────
    Base.metadata.create_all(bind=engine)   # create new tables
    
    # Auto-migrate missing columns for existing users table
    try:
        with engine.begin() as conn:
            # Add timezone column if missing
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR(100) NOT NULL DEFAULT 'Asia/Kolkata';"))
            except Exception:
                pass
            
            # Add briefing_time column if missing
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN briefing_time VARCHAR(5) NOT NULL DEFAULT '07:00';"))
            except Exception:
                pass
            
            # Add notification_enabled column if missing
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN notification_enabled BOOLEAN NOT NULL DEFAULT 1;"))
            except Exception:
                pass
            
            # Add reminder_minutes column if missing
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN reminder_minutes INTEGER NOT NULL DEFAULT 15;"))
            except Exception:
                pass
            
            # Add briefing_enabled column if missing
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN briefing_enabled BOOLEAN NOT NULL DEFAULT 1;"))
            except Exception:
                pass
            
            # Add notification_categories column if missing
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN notification_categories VARCHAR(255) NOT NULL DEFAULT 'meeting,appointment,task,class,deadline,reminder';"))
            except Exception:
                pass
                
            # Add telegram_chat_id to otp_verifications if missing
            try:
                conn.execute(text("ALTER TABLE otp_verifications ADD COLUMN telegram_chat_id VARCHAR(50) NULL;"))
            except Exception:
                pass
                
            # Add attempt_count to otp_verifications if missing
            try:
                conn.execute(text("ALTER TABLE otp_verifications ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;"))
            except Exception:
                pass

            # ── Recurring Event columns ──────────────────────────────────────
            try:
                conn.execute(text("ALTER TABLE events ADD COLUMN is_recurring BOOLEAN NOT NULL DEFAULT 0;"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE events ADD COLUMN recurrence_type VARCHAR(20) NULL DEFAULT 'none';"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE events ADD COLUMN recurrence_interval INTEGER NULL DEFAULT 1;"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE events ADD COLUMN recurrence_end_date DATE NULL;"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE events ADD COLUMN parent_event_id INTEGER NULL;"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE events ADD COLUMN exception_date VARCHAR(10) NULL;"))
            except Exception:
                pass

            # ── Migrate event_type ENUM to include 'study' ───────────────────
            try:
                conn.execute(text(
                    "ALTER TABLE events MODIFY COLUMN event_type ENUM('meeting','appointment','class','task','reminder','deadline','study') NOT NULL DEFAULT 'meeting';"
                ))
            except Exception:
                pass

            # ── Notification enhancements (title, body, type, is_read) ───────
            try:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN title VARCHAR(255) NULL;"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN body TEXT NULL;"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN notification_type VARCHAR(50) NULL DEFAULT 'event_reminder';"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0;"))
            except Exception:
                pass

    except Exception as e:
        print(f"Migration error: {e}")

    start_scheduler()                        # start APScheduler jobs
    yield
    # ── Shutdown ───────────────────────────────────────────────────
    stop_scheduler()


# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TimePilot AI",
    description="AI-powered scheduling assistant backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS (permit Next.js frontend on any origin during development) ────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Tighten in production to specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(telegram_router)
app.include_router(events_router)
app.include_router(schedule_router)
app.include_router(overview_router)
app.include_router(expenses_router)
app.include_router(budget_router)
app.include_router(analytics_router)
app.include_router(ai_router)
app.include_router(settings_router)
app.include_router(search_router)
app.include_router(saving_goals_router)
app.include_router(streaks_router)
app.include_router(rewards_router)
app.include_router(sse_router)
app.include_router(notifications_router)
app.include_router(study_planner_router)
app.include_router(ai_schedule_router)


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


@app.get("/debug/events-count", tags=["Debug"])
def debug_events_count(db: Session = Depends(get_db)):
    """
    DEBUG ONLY — Returns the total number of events in the database.
    Use this to verify the events table was created and data is being saved.
    Example: GET /debug/events-count
    """
    settings = get_settings()
    if not settings.DEBUG:
        return {"error": "Debug endpoints are disabled. Set DEBUG=true in .env"}

    from backend.repositories.event_repository import EventRepository
    count = EventRepository.count_all(db)
    return {"count": count}


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