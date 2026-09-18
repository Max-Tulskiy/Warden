"""Append-only audit log (constitution principle 8)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from warden_server.models.audit import AuditLogEntry


def log_event(
    db: Session,
    *,
    actor: str,
    action: str,
    target: str,
    detail: dict[str, Any] | None = None,
) -> AuditLogEntry:
    """Record one audited action.

    The caller is responsible for committing the surrounding transaction;
    this only adds the row, so a single request that both performs an action
    and logs it commits both together.
    """
    entry = AuditLogEntry(
        actor=actor,
        action=action,
        target=target,
        occurred_at=datetime.now(UTC),
        detail=detail or {},
    )
    db.add(entry)
    return entry
