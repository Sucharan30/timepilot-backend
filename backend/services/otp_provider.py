"""
backend/services/otp_provider.py

OTP delivery abstraction layer.

Architecture:
  OTPProvider (abstract base)
    ├── MockOTPProvider     ← Day-2: returns OTP in-memory (no SMS)
    ├── TwilioOTPProvider   ← Future Day-X
    └── MSG91OTPProvider    ← Future Day-X

To swap providers, change the `get_otp_provider()` factory below.
The OTPService never knows which provider is active.
"""
import random
from abc import ABC, abstractmethod


class OTPProvider(ABC):
    """Abstract contract every OTP delivery provider must implement."""

    @abstractmethod
    def send_otp(self, phone_number: str, otp_code: str) -> bool:
        """
        Send the OTP to the given phone number.
        Returns True on success, raises on failure.
        """
        ...

    @abstractmethod
    def generate_otp(self) -> str:
        """Generate and return a new OTP string (e.g. 6-digit code)."""
        ...


# ── Mock Provider (Day-2 MVP) ─────────────────────────────────────────────────

class MockOTPProvider(OTPProvider):
    """
    Does NOT send an SMS.
    - generate_otp() returns a random 6-digit code.
    - send_otp() simply logs to stdout (no external calls).
    The OTP is returned to the caller and stored in DB; in DEBUG mode
    it is echoed back in the API response.
    """

    def generate_otp(self) -> str:
        return str(random.randint(100000, 999999))

    def send_otp(self, phone_number: str, otp_code: str) -> bool:
        # In production this would call Twilio/MSG91.
        # For now, just print so Railway logs show it.
        print(f"[MockOTPProvider] OTP for {phone_number}: {otp_code}")
        return True


# ── Future provider stubs (not yet implemented) ───────────────────────────────

class TwilioOTPProvider(OTPProvider):
    """Placeholder — implement when Twilio is added."""

    def generate_otp(self) -> str:
        return str(random.randint(100000, 999999))

    def send_otp(self, phone_number: str, otp_code: str) -> bool:
        raise NotImplementedError("TwilioOTPProvider is not yet implemented.")


class MSG91OTPProvider(OTPProvider):
    """Placeholder — implement when MSG91 is added."""

    def generate_otp(self) -> str:
        return str(random.randint(100000, 999999))

    def send_otp(self, phone_number: str, otp_code: str) -> bool:
        raise NotImplementedError("MSG91OTPProvider is not yet implemented.")


# ── Provider Factory ──────────────────────────────────────────────────────────

def get_otp_provider() -> OTPProvider:
    """
    Factory function — swap this return value when upgrading to a real SMS provider.
    Example: return TwilioOTPProvider()
    """
    return MockOTPProvider()
