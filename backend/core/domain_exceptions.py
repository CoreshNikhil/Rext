"""Generic business-rule exceptions shared across non-auth services
(residents, imports, and later billing/payments). Auth-specific errors
live in core/exceptions.py — kept separate since they have a different
shape of caller (public endpoints vs admin-only CRUD).
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all non-auth business-rule violations."""


class NotFoundError(DomainError):
    """Requested resource does not exist."""


class ConflictError(DomainError):
    """Uniqueness or state conflict — duplicate house/mobile/meter, an
    action attempted in the wrong state, etc."""


_STATUS_MAP: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
}


def domain_error_status_code(exc: DomainError) -> int:
    return _STATUS_MAP.get(type(exc), 400)
