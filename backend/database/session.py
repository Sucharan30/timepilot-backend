"""
backend/database/session.py

Convenience re-export. All core DB objects live in backend/database.py (the file).
This module exists for IDE discoverability only.

Usage:
    from backend.database import Base, engine, SessionLocal
"""
# Avoid circular imports — do not import here.
# Import directly from backend.database in all application code.
