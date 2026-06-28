"""
backend/api/notifications.py

Website Notification Center endpoints (JWT-protected):

  GET    /notifications            — list all notifications for user (unread first)
  PUT    /notifications/read-all   — mark all as read
  PUT    /notifications/{id}/read  — mark a notification as read
  DELETE /notifications/{id}       — delete a notification
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.models.notification import Notification
from backend.schemas.response import ok

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all notifications for the user — unread first, then by time desc."""
    notifs = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.notification_time.desc())
        .limit(50)
        .all()
    )
    result = []
    for n in notifs:
        result.append({
            "id": n.id,
            "event_id": n.event_id,
            "notification_time": n.notification_time.isoformat() if n.notification_time else None,
            "title": getattr(n, "title", None),
            "body": getattr(n, "body", None),
            "notification_type": getattr(n, "notification_type", "event_reminder"),
            "is_read": getattr(n, "is_read", False),
            "sent": n.sent,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })
    return ok(result)


@router.put("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark all notifications as read for the user."""
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
    ).update({"is_read": True})
    db.commit()
    return ok({"message": "All notifications marked as read."})


@router.put("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark a single notification as read."""
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    notif.is_read = True
    db.commit()
    return ok({"message": "Notification marked as read."})


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a notification."""
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    db.delete(notif)
    db.commit()
    return ok({"message": "Notification deleted."})
