"""
backend/schemas/auth.py

Request/Response Pydantic schemas for authentication endpoints.
"""
from typing import Optional
from pydantic import BaseModel, field_validator
import re

from backend.schemas.user import UserOut


# ── /auth/send-otp ────────────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Allow E.164 format: +<country_code><number>, e.g. +919999999999"""
        pattern = r"^\+[1-9]\d{6,14}$"
        if not re.match(pattern, v):
            raise ValueError("Phone number must be in E.164 format, e.g. +919999999999")
        return v


class SendOTPResponse(BaseModel):
    message: str
    # otp is only populated in DEBUG mode; omitted in production
    otp: Optional[str] = None


# ── /auth/verify-otp ─────────────────────────────────────────────────────────

class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp: str


class VerifyOTPResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


# ── /auth/refresh-token ───────────────────────────────────────────────────────

class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
