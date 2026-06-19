"""
backend/schemas/user.py

Pydantic schemas for serialising User data to API responses.
Never expose password hashes or internal flags directly.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    phone_number: str
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
