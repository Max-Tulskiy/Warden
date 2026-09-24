"""The operating limits: read by any operator, changed by administrators (D-11)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from warden_server.api.deps import ADMIN_ONLY_RESPONSES, require_admin, require_operator
from warden_server.db import get_db
from warden_server.models.operator import Operator
from warden_server.schemas.auth import MIN_PASSWORD_LENGTH
from warden_server.schemas.event import MAX_REPORT_EVENTS
from warden_server.schemas.inventory import MAX_INVENTORY_ENTRIES
from warden_server.schemas.policy import (
    SESSION_MINUTES_BOUNDS,
    TOKEN_TTL_HOURS_BOUNDS,
    WINDOW_HOURS_BOUNDS,
    Bounds,
    PolicyBounds,
    PolicyOut,
    PolicyUpdateIn,
    PolicyValues,
)
from warden_server.schemas.report import MAX_PAGE_SIZE
from warden_server.services import policy as policy_service
from warden_server.services.audit import log_event

router = APIRouter(
    prefix="/api/v1", tags=["policy"], dependencies=[Depends(require_operator)]
)

_BOUNDS = PolicyBounds(
    max_request_window_hours=Bounds(
        min=WINDOW_HOURS_BOUNDS[0], max=WINDOW_HOURS_BOUNDS[1]
    ),
    enrollment_token_ttl_hours=Bounds(
        min=TOKEN_TTL_HOURS_BOUNDS[0], max=TOKEN_TTL_HOURS_BOUNDS[1]
    ),
    session_lifetime_minutes=Bounds(
        min=SESSION_MINUTES_BOUNDS[0], max=SESSION_MINUTES_BOUNDS[1]
    ),
)


def _current(db: Session) -> PolicyOut:
    """The limits in force, each read from where it is enforced."""
    effective = policy_service.effective_policy(db)
    return PolicyOut(
        max_request_window_hours=effective.max_request_window_hours,
        enrollment_token_ttl_hours=effective.enrollment_token_ttl_hours,
        session_lifetime_minutes=effective.session_lifetime_minutes,
        min_password_length=MIN_PASSWORD_LENGTH,
        max_report_events=MAX_REPORT_EVENTS,
        max_inventory_entries=MAX_INVENTORY_ENTRIES,
        max_page_size=MAX_PAGE_SIZE,
        overridden=effective.overridden,
        defaults=policy_service.configured_defaults(),
        bounds=_BOUNDS,
    )


@router.get("/policy", response_model=PolicyOut)
def get_policy(db: Session = Depends(get_db)) -> PolicyOut:
    """Return the limits in force, and the range and default of each editable one."""
    return _current(db)


@router.put("/policy", response_model=PolicyOut, responses=ADMIN_ONLY_RESPONSES)
def save_policy(
    payload: PolicyUpdateIn,
    operator: Operator = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PolicyOut:
    """Save all three values, putting them in force from the next use.

    A session, an enrollment token, or a queued request that already exists
    keeps what it was issued with. Saving what is already in force writes
    nothing to the audit log.
    """
    actor = operator.username
    changes = policy_service.save_policy(
        db, PolicyValues(**payload.model_dump()), actor=actor
    )
    if changes:
        log_event(
            db, actor=actor, action="policy.changed", target="policy", detail=changes
        )
    db.commit()
    return _current(db)


@router.delete("/policy", response_model=PolicyOut, responses=ADMIN_ONLY_RESPONSES)
def reset_policy(
    operator: Operator = Depends(require_admin), db: Session = Depends(get_db)
) -> PolicyOut:
    """Forget the saved policy, so the server's configured values apply again."""
    actor = operator.username
    changes = policy_service.reset_policy(db)
    if changes:
        log_event(
            db, actor=actor, action="policy.reset", target="policy", detail=changes
        )
    db.commit()
    return _current(db)
