"""
backend/api/settings.py

Notification and timezone settings endpoints:
  GET  /settings/notifications  — return current notification settings
  PUT  /settings/notifications  — update notification settings (including timezone)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.notifications import NotificationSettingsUpdate, NotificationSettingsOut
from backend.schemas.response import ok, err
from backend.services.notification_service import NotificationService

router = APIRouter(prefix="/settings", tags=["Settings"])


# ── GET /settings/notifications ───────────────────────────────────────────────

@router.get("/notifications")
def get_notification_settings(
    current_user=Depends(get_current_user),
):
    """Return the current notification preferences for the authenticated user."""
    settings = NotificationService.get_settings(current_user)
    return ok(settings)


# ── PUT /settings/notifications ───────────────────────────────────────────────

@router.put("/notifications")
def update_notification_settings(
    body: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update notification preferences for the authenticated user.
    Only fields included in the request body will be changed.

    timezone accepts IANA timezone strings (e.g. "Asia/Kolkata", "America/New_York").
    briefing_time must be in HH:MM format (e.g. "07:00", "08:30").
    """
    try:
        updated = NotificationService.update_settings(
            db=db,
            user=current_user,
            notification_enabled=body.notification_enabled,
            reminder_minutes=body.reminder_minutes,
            briefing_enabled=body.briefing_enabled,
            briefing_time=body.briefing_time,
            notification_categories=body.notification_categories,
            timezone=body.timezone,
        )
        return ok(updated)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
