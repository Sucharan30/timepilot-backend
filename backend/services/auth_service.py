"""
backend/services/auth_service.py

Top-level authentication orchestrator.
Coordinates OTPService, UserRepository, JWTService, and SessionRepository.
The API layer (api/auth.py) calls only this service — never repos or sub-services directly.
"""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.user import User
from backend.repositories.user_repository import UserRepository
from backend.repositories.session_repository import SessionRepository
from backend.services.otp_service import OTPService, OTPVerifyResult
from backend.services.jwt_service import JWTService
from backend.schemas.auth import VerifyOTPResponse
from backend.schemas.user import UserOut


class AuthService:

    # ── Send OTP ──────────────────────────────────────────────────────────────

    @staticmethod
    def send_otp(phone_number: str, db: Session, debug: bool = False) -> dict:
        """
        Generate and store an OTP for the given phone number.
        Returns the response dict (includes 'otp' only in debug mode).
        """
        otp_code = OTPService.generate_and_store_otp(phone_number, db)

        response: dict = {"message": "OTP generated. Please verify to continue."}
        if debug:
            response["otp"] = otp_code  # Only exposed in DEBUG mode
        return response

    # ── Verify OTP ────────────────────────────────────────────────────────────

    @staticmethod
    def verify_otp(phone_number: str, otp_code: str, db: Session) -> dict:
        """
        Verify OTP → upsert user → mark verified → issue tokens → save session.
        Returns the VerifyOTPResponse payload dict.
        """
        result = OTPService.verify_otp(phone_number, otp_code, db)

        if result == OTPVerifyResult.NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP not found or already used. Please request a new OTP.",
            )
        if result == OTPVerifyResult.EXPIRED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired (valid for 10 minutes). Please request a new OTP.",
            )

        # Upsert user
        user, _ = UserRepository.get_or_create(db, phone_number)
        if not user.is_verified:
            user = UserRepository.mark_verified(db, user)

        # Issue tokens
        access_token = JWTService.create_access_token(user.id)
        refresh_token, expires_at = JWTService.create_refresh_token(user.id)

        # Persist session
        SessionRepository.create_session(
            db=db,
            user_id=user.id,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": UserOut.model_validate(user),
        }

    # ── Refresh Token ─────────────────────────────────────────────────────────

    @staticmethod
    def refresh_access_token(refresh_token: str, db: Session) -> dict:
        """
        Validate refresh token → issue new access token.
        Does NOT rotate the refresh token (stateless rotation deferred to Day-3+).
        """
        # 1. Verify JWT signature + expiry
        try:
            payload = JWTService.decode_token(refresh_token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
            )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is not a refresh token.",
            )

        # 2. Check that the session still exists in DB (not logged out)
        session = SessionRepository.get_by_token(db, refresh_token)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session not found. Please log in again.",
            )

        if not SessionRepository.is_token_valid(session):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired.",
            )

        user_id = int(payload["sub"])
        new_access_token = JWTService.create_access_token(user_id)
        return {"access_token": new_access_token, "token_type": "bearer"}

    # ── Logout ────────────────────────────────────────────────────────────────

    @staticmethod
    def logout(refresh_token: Optional[str], user: User, db: Session) -> dict:
        """
        Invalidate the session associated with the given refresh token.
        If no token provided, deletes all sessions for the user (global logout).
        """
        if refresh_token:
            SessionRepository.delete_session(db, refresh_token)
        else:
            SessionRepository.delete_all_for_user(db, user.id)

        return {"message": "Logged out successfully."}
