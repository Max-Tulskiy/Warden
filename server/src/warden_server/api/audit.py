"""Read endpoint for the audit log (constitution principle 8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from warden_server.api.deps import ADMIN_ONLY_RESPONSES, require_admin
from warden_server.db import get_db
from warden_server.models.audit import AuditLogEntry
from warden_server.models.operator import Operator
from warden_server.schemas.audit import AuditEntryOut, AuditFilter
from warden_server.services.audit import log_event

router = APIRouter(
    prefix="/api/v1",
    tags=["audit"],
    dependencies=[Depends(require_admin)],
    responses=ADMIN_ONLY_RESPONSES,
)


@router.get("/audit", response_model=list[AuditEntryOut])
def audit_log(
    audit: Annotated[AuditFilter, Query()],
    operator: Operator = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AuditLogEntry]:
    """Audit entries for a time range, newest first.

    The range is half-open, `[start, end)`, like the fleet report. `id` breaks
    ties so offset paging stays stable when several entries share a timestamp.
    Reading the log is itself recorded in it, as `view.audit_log`, before any
    entry is read, so the entry for a read can appear in its own result; if it
    cannot be stored the request fails and no data is returned.

    `action` is either one code or a dotted group: `operator.login` matches
    only itself, `operator` matches every `operator.*`. A plain string prefix
    would let `operator.login` also return `operator.login_failed`.
    """
    log_event(
        db,
        actor=operator.username,
        action="view.audit_log",
        target="audit_log",
        detail={
            "start": audit.start.isoformat(),
            "end": audit.end.isoformat(),
            "actor": audit.actor,
            "action": audit.action,
            "limit": audit.limit,
            "offset": audit.offset,
        },
    )
    db.commit()
    query = select(AuditLogEntry).where(
        AuditLogEntry.occurred_at >= audit.start,
        AuditLogEntry.occurred_at < audit.end,
    )
    if audit.actor is not None:
        query = query.where(AuditLogEntry.actor == audit.actor)
    if audit.action is not None:
        query = query.where(
            or_(
                AuditLogEntry.action == audit.action,
                AuditLogEntry.action.startswith(f"{audit.action}.", autoescape=True),
            )
        )

    return list(
        db.execute(
            query.order_by(AuditLogEntry.occurred_at.desc(), AuditLogEntry.id)
            .limit(audit.limit)
            .offset(audit.offset)
        )
        .scalars()
        .all()
    )
