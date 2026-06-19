"""
backend/schemas/response.py

Standardised API response wrappers used across all endpoints.
Frontend always receives:
    { "success": true,  "data": ... }
    { "success": false, "error": "..." }
"""
from typing import Any, Optional
from pydantic import BaseModel


class SuccessResponse(BaseModel):
    success: bool = True
    data: Any = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str


def ok(data: Any = None) -> dict:
    """Helper — returns a serialisable success payload."""
    return {"success": True, "data": data}


def err(message: str) -> dict:
    """Helper — returns a serialisable error payload."""
    return {"success": False, "error": message}
