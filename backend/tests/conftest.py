"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import models  # noqa: F401 - registers every table on Base.metadata
from backend.db.base import Base


@pytest.fixture()
def db_session():
    # In-memory SQLite + StaticPool: one connection shared across the whole
    # test (plain in-memory SQLite is per-connection and would otherwise
    # lose all tables between statements).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
