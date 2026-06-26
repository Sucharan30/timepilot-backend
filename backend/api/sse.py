"""
backend/api/sse.py

Server-Sent Events (SSE) endpoint for real-time dashboard synchronization.

GET /events/stream  — EventSource endpoint (JWT via query param or header)

Events pushed to the frontend:
  - event_created / event_updated / event_deleted
  - notification_sent
  - budget_updated
  - streak_updated
  - ai_insight

Architecture:
  - In-memory per-user event queues (works on single-process deployments).
  - For multi-process Railway deployments, replace the queue with Redis pub/sub.
"""
import asyncio
import json
from collections import defaultdict
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from backend.core.dependencies import get_db, get_current_user
from backend.services.jwt_service import JWTService
from backend.repositories.user_repository import UserRepository
from backend.database import SessionLocal

router = APIRouter(prefix="/events", tags=["Real-time Sync"])

# ── In-memory queues ──────────────────────────────────────────────────────────
# { user_id: asyncio.Queue }
_user_queues: dict[int, list[asyncio.Queue]] = defaultdict(list)


def broadcast_event(user_id: int, event_type: str, data: dict) -> None:
    """
    Put an SSE event on all active queues for the given user.
    Called from EventService, ExpenseService, etc. (fire-and-forget).
    Safe to call from sync code — uses put_nowait.
    """
    payload = json.dumps({"type": event_type, **data})
    for q in list(_user_queues.get(user_id, [])):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # Drop if client is too slow


async def _event_generator(user_id: int, queue: asyncio.Queue) -> AsyncGenerator:
    """Yield SSE events from the user's queue until the client disconnects."""
    # Send a connection confirmation
    yield {"event": "connected", "data": json.dumps({"user_id": user_id, "status": "connected"})}

    try:
        while True:
            # Wait for an event with a keepalive ping every 30 seconds
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30)
                yield {"event": "update", "data": data}
            except asyncio.TimeoutError:
                # Keepalive — prevents proxy/CDN from closing the connection
                yield {"event": "ping", "data": "{}"}
    except asyncio.CancelledError:
        pass
    finally:
        # Remove queue when client disconnects
        queues = _user_queues.get(user_id, [])
        if queue in queues:
            queues.remove(queue)


# ── GET /events/stream ────────────────────────────────────────────────────────

@router.get("/stream")
async def event_stream(
    token: str = Query(..., description="JWT access token (passed as query param for EventSource)"),
):
    """
    SSE endpoint for real-time dashboard updates.

    Connect with EventSource in JavaScript:
      const es = new EventSource('/events/stream?token=<access_token>');
      es.addEventListener('update', (e) => { const data = JSON.parse(e.data); ... });
      es.addEventListener('ping', () => {}); // ignore keepalives

    Events:
      type: event_created | event_updated | event_deleted
            notification_sent | budget_updated | streak_updated | ai_insight
    """
    # Validate JWT from query param (EventSource can't send Authorization headers)
    try:
        payload = JWTService.decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Create a dedicated queue for this connection
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _user_queues[user_id].append(queue)

    return EventSourceResponse(
        _event_generator(user_id, queue),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )
