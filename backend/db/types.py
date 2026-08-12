"""Custom SQLAlchemy column types.

UTCDateTime exists because SQLite silently drops tzinfo on round-trip for
`DateTime(timezone=True)` — a value written as timezone-aware UTC comes
back out as a naive datetime, which then blows up any comparison against
a fresh `datetime.now(timezone.utc)` with `TypeError: can't compare
offset-naive and offset-aware datetimes`. Postgres doesn't have this
problem (it returns aware values natively), so this type normalizes both
directions to guarantee "always aware UTC" regardless of dialect —
correct now on SQLite, and a no-op on Postgres later.
"""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
