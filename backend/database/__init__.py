"""
backend/database/__init__.py

SQLAlchemy engine, session factory, and declarative Base.

NOTE: Both backend/database.py and backend/database/ exist.
Python resolves "backend.database" to this package (__init__.py).
This file contains the same setup as database.py so all imports work.
database.py is kept only as a legacy reference but is no longer imported by Python.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

Base = declarative_base()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
