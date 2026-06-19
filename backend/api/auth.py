"""
backend/api/auth.py

Authentication endpoints:
  POST  /auth/send-otp       — generate OTP for a phone number
  POST  /auth/verify-otp     — verify OTP, receive JWT tokens
  POST  /auth/refresh-token  — get new access token from refresh token
  POST  /auth/logout         — invalidate current session
  GET   /auth/me             — return current authenticated user

All responses use the standard { "success": true, "data": ... } wrapper.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.dependencies import get_db, get_current_user
from backend.schemas.auth import (
    SendOTPRequest,
    VerifyOTPRequest,
    RefreshTokenRequest,
)
from backend.schemas.response import ok, err
from backend.schemas.user import UserOut
from backend.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


# ── POST /auth/send-otp ───────────────────────────────────────────────────────

@router.post("/send-otp")
def send_otp(
    body: SendOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Generate a 6-digit OTP for the given phone number.
    In DEBUG mode the OTP is returned in the response (for testing).
    In production, set DEBUG=false on Railway — the OTP is sent via SMS only.
    """
    try:
        data = AuthService.send_otp(
            phone_number=body.phone_number,
            db=db,
            debug=settings.DEBUG,
        )
        return ok(data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=err(str(exc)),
        )


# ── POST /auth/verify-otp ─────────────────────────────────────────────────────

@router.post("/verify-otp")
def verify_otp(
    body: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Verify a previously-issued OTP.
    On success: upserts user, issues access + refresh tokens, saves session.
    """
    data = AuthService.verify_otp(
        phone_number=body.phone_number,
        otp_code=body.otp,
        db=db,
    )
    # UserOut is a Pydantic model — convert to dict for JSON serialisation
    data["user"] = data["user"].model_dump()
    return ok(data)


# ── POST /auth/refresh-token ──────────────────────────────────────────────────

@router.post("/refresh-token")
def refresh_token(
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access token.
    The refresh token itself is NOT rotated (stateless; rotation comes in Day-3+).
    """
    data = AuthService.refresh_access_token(
        refresh_token=body.refresh_token,
        db=db,
    )
    return ok(data)


# ── POST /auth/logout ─────────────────────────────────────────────────────────

@router.post("/logout")
def logout(
    refresh_token: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Invalidate the current session.
    Optionally pass `refresh_token` in the query string to target a specific session.
    If omitted, ALL sessions for the user are deleted (global logout).
    """
    data = AuthService.logout(
        refresh_token=refresh_token,
        user=current_user,
        db=db,
    )
    return ok(data)


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get("/me")
def me(current_user=Depends(get_current_user)):
    """
    Returns the profile of the currently authenticated user.
    Requires: Authorization: Bearer <access_token>
    """
    return ok(UserOut.model_validate(current_user).model_dump())
