"""SQLAlchemy declarative base, shared across all ORM models.

A naming convention is set so every constraint (index, unique, check,
foreign key, primary key) gets a stable, predictable name. This matters
specifically for SQLite: Alembic's batch mode (required because SQLite
can't ALTER TABLE arbitrarily) recreates tables under the hood and needs
named constraints to do that reliably.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_column(enum_cls, **kwargs):
    """SQLAlchemy Enum type that stores each member's .value (e.g. "accepted"),
    not its .name (e.g. "ACCEPTED") — keeps DB-stored strings identical to
    what these str-Enum classes serialize to everywhere else (Pydantic, API
    responses). Compiles to a native ENUM on Postgres, VARCHAR+CHECK on
    SQLite — portable across both without code changes.
    """
    return SAEnum(enum_cls, values_callable=lambda x: [e.value for e in x], **kwargs)
