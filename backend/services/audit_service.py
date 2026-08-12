"""Single entry point for writing audit log rows.

Called from the service layer only, never from routers — so audit
coverage doesn't depend on remembering to add it at every endpoint.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models.audit_log import AuditLog
from backend.db.models.enums import ActorType


def record(
    db: Session,
    *,
    actor_type: ActorType,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before_state,
            after_state=after_state,
        )
    )
    db.commit()
