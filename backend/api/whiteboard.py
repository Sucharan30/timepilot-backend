import json
import base64
from datetime import datetime, timezone
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import google.generativeai as genai

from backend.core.config import get_settings
from backend.core.dependencies import get_db, get_current_user
from backend.repositories.event_repository import EventRepository
from backend.models.event import EventType
from backend.schemas.response import ok
from backend.services.timezone_service import TimezoneService

router = APIRouter(prefix="/whiteboard", tags=["Whiteboard"])
settings = get_settings()

class WhiteboardPayload(BaseModel):
    image: str

@router.post("/analyze")
def analyze_whiteboard(
    payload: WhiteboardPayload,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Analyzes the whiteboard canvas (Base64 image) and automatically extracts tasks/events to the schedule.
    """
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Gemini API Key missing")

    if not payload.image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Invalid image format")

    try:
        header, encoded = payload.image.split(",", 1)
        image_data = base64.b64decode(encoded)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode image data")

    # Configure Gemini
    genai.configure(api_key=settings.GEMINI_API_KEY)
    
    # We use gemini-2.5-flash as it supports image multimodal input
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=(
            "You are an AI assistant parsing whiteboard notes/drawings. "
            "Identify action items, tasks, or scheduled events from the image. "
            "Return a JSON array of objects, each containing: "
            "title (string), description (string), type (string: 'task', 'meeting', 'study', 'other'). "
            "If no clear time is specified, assume it's a task. "
            "Output ONLY valid JSON."
        )
    )

    try:
        # Pass the image data to Gemini
        contents = [
            {
                "mime_type": "image/png",
                "data": image_data
            },
            "Extract all action items, tasks, and events from this whiteboard."
        ]
        
        response = model.generate_content(contents)
        raw = response.text.strip()
        
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        items = json.loads(raw.strip())
        
    except Exception as e:
        print("Gemini Vision Error:", e)
        raise HTTPException(status_code=500, detail="Failed to analyze whiteboard image")

    # Create events from extracted items
    user_tz = current_user.timezone or "Asia/Kolkata"
    now = datetime.now(timezone.utc)
    
    count = 0
    for item in items:
        # Default start time is now
        event = EventRepository.create(
            db=db,
            user_id=current_user.id,
            title=item.get("title", "Whiteboard Task"),
            description=item.get("description", ""),
            event_type=EventType(item.get("type", "task")) if item.get("type") in ["task", "meeting", "study", "habit", "other"] else EventType.task,
            start_datetime=now,
            end_datetime=None
        )
        count += 1
        
    # Broadcast event so frontend updates
    try:
        from backend.api.sse import broadcast_event
        broadcast_event(current_user.id, "event_created", {"source": "whiteboard", "count": count})
    except Exception:
        pass

    return ok({"message": f"Successfully added {count} items from the whiteboard to your schedule."})
