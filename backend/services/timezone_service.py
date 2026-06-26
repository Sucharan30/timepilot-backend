"""
backend/services/timezone_service.py

Central timezone utility service.

All timestamps in the database are stored in UTC.
This service converts between UTC and a user's IANA timezone string
(e.g. "Asia/Kolkata", "America/New_York") when reading/writing data.

Rules:
  - ALWAYS store UTC in the database.
  - NEVER manually add +5:30 or any hardcoded offset.
  - Always use pytz for conversions.
  - Convert to user tz ONLY when returning data to the frontend or Telegram.
"""
from datetime import datetime, timezone
from typing import Optional

import pytz


DEFAULT_TIMEZONE = "Asia/Kolkata"


class TimezoneService:

    @staticmethod
    def get_tz(tz_string: Optional[str]) -> pytz.BaseTzInfo:
        """Return a pytz timezone object, falling back to Asia/Kolkata on error."""
        try:
            return pytz.timezone(tz_string or DEFAULT_TIMEZONE)
        except pytz.exceptions.UnknownTimeZoneError:
            return pytz.timezone(DEFAULT_TIMEZONE)

    @staticmethod
    def to_user_tz(dt: Optional[datetime], user_timezone: Optional[str]) -> Optional[datetime]:
        """
        Convert a UTC datetime to the user's local timezone.
        Handles both naive UTC datetimes and timezone-aware datetimes.
        Returns None if dt is None.
        """
        if dt is None:
            return None

        tz = TimezoneService.get_tz(user_timezone)

        # Ensure dt is timezone-aware UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Normalise to UTC first if it has a different tz
            dt = dt.astimezone(pytz.utc)

        return dt.astimezone(tz)

    @staticmethod
    def to_utc(dt: Optional[datetime], user_timezone: Optional[str]) -> Optional[datetime]:
        """
        Convert a local datetime (in user's timezone) to UTC.
        If dt already has tzinfo, it will be respected.
        Returns None if dt is None.
        """
        if dt is None:
            return None

        tz = TimezoneService.get_tz(user_timezone)

        # If naive, assume it's in the user's timezone
        if dt.tzinfo is None:
            dt = tz.localize(dt)

        return dt.astimezone(pytz.utc)

    @staticmethod
    def now_in_tz(user_timezone: Optional[str]) -> datetime:
        """Return the current time in the user's timezone (timezone-aware)."""
        tz = TimezoneService.get_tz(user_timezone)
        return datetime.now(pytz.utc).astimezone(tz)

    @staticmethod
    def now_utc() -> datetime:
        """Return current UTC time (timezone-aware)."""
        return datetime.now(pytz.utc)

    @staticmethod
    def format_for_display(dt: Optional[datetime], user_timezone: Optional[str]) -> Optional[str]:
        """
        Convert UTC datetime to user's local time and return as ISO 8601 string.
        Frontend receives the correct local time without any manual offset.
        """
        if dt is None:
            return None
        local_dt = TimezoneService.to_user_tz(dt, user_timezone)
        return local_dt.isoformat()

    @staticmethod
    def day_bounds_utc(user_timezone: Optional[str], date: Optional[datetime] = None) -> tuple[datetime, datetime]:
        """
        Given a date (defaults to today) in the user's timezone,
        return (start_of_day_utc, end_of_day_utc) as aware UTC datetimes.

        Use these for DB queries to find events within a local calendar day.
        """
        tz = TimezoneService.get_tz(user_timezone)
        now_local = datetime.now(pytz.utc).astimezone(tz) if date is None else date.astimezone(tz)

        day_start_local = now_local.replace(hour=0,  minute=0,  second=0,  microsecond=0)
        day_end_local   = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

        day_start_utc = day_start_local.astimezone(pytz.utc)
        day_end_utc   = day_end_local.astimezone(pytz.utc)

        return day_start_utc, day_end_utc

    @staticmethod
    def validate_iana(tz_string: str) -> bool:
        """Return True if the given string is a valid IANA timezone identifier."""
        try:
            pytz.timezone(tz_string)
            return True
        except pytz.exceptions.UnknownTimeZoneError:
            return False
