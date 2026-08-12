"""Admin system configuration — the SystemConfiguration key/value store
seeded in Phase 1 (rate, fine, OTP settings, regex patterns, auto-period
durations) is only readable/writable through here."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from backend.core.domain_exceptions import ConflictError, NotFoundError
from backend.db.models.admin_user import AdminUser
from backend.db.models.enums import ActorType, ConfigValueType
from backend.db.models.system_configuration import SystemConfiguration
from backend.services import audit_service


def list_config(db: Session) -> list[SystemConfiguration]:
    return db.query(SystemConfiguration).order_by(SystemConfiguration.key).all()


def _validate_value_for_type(key: str, value: str, value_type: ConfigValueType) -> None:
    if value_type == ConfigValueType.INT:
        try:
            int(value)
        except ValueError as exc:
            raise ConflictError(f"'{key}' expects an integer value.") from exc
    elif value_type == ConfigValueType.FLOAT:
        try:
            Decimal(value)
        except InvalidOperation as exc:
            raise ConflictError(f"'{key}' expects a numeric value.") from exc
    elif value_type == ConfigValueType.BOOL and value.lower() not in ("true", "false"):
        raise ConflictError(f"'{key}' expects 'true' or 'false'.")


def update_config(db: Session, admin: AdminUser, key: str, value: str) -> SystemConfiguration:
    config = db.get(SystemConfiguration, key)
    if config is None:
        raise NotFoundError(f"Configuration key '{key}' not found.")

    _validate_value_for_type(key, value, config.value_type)

    before_value = config.value
    config.value = value
    config.updated_by_admin_id = admin.admin_id
    db.commit()
    db.refresh(config)

    audit_service.record(
        db,
        actor_type=ActorType.ADMIN,
        actor_id=admin.admin_id,
        action="system_config.update",
        entity_type="system_configuration",
        entity_id=None,  # SystemConfiguration's PK is a string key, not an int
        before_state={"key": key, "value": before_value},
        after_state={"key": key, "value": value},
    )
    return config
