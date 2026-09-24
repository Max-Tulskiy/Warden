"""Administrators managing operator accounts (constitution D-10)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warden_server.api.deps import ADMIN_ONLY_RESPONSES, require_admin
from warden_server.db import get_db
from warden_server.models.operator import Operator, OperatorStatus
from warden_server.schemas.operator import (
    OperatorCreateIn,
    OperatorOut,
    OperatorPasswordResetIn,
    OperatorUpdateIn,
)
from warden_server.security import hash_password
from warden_server.services import throttle
from warden_server.services.audit import log_event
from warden_server.services.sessions import end_sessions

router = APIRouter(
    prefix="/api/v1/operators",
    tags=["operators"],
    dependencies=[Depends(require_admin)],
    responses=ADMIN_ONLY_RESPONSES,
)


def _load(db: Session, operator_id: uuid.UUID) -> Operator:
    operator = db.get(Operator, operator_id)
    if operator is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown operator")
    return operator


@router.get("", response_model=list[OperatorOut])
def list_operators(db: Session = Depends(get_db)) -> list[Operator]:
    return list(db.execute(select(Operator).order_by(Operator.username)).scalars())


@router.post("", response_model=OperatorOut, status_code=201)
def create_operator(
    payload: OperatorCreateIn,
    caller: Operator = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Operator:
    """Create an account. Usernames are unique regardless of letter case."""
    duplicate = HTTPException(
        status.HTTP_409_CONFLICT, detail="An operator with this username exists"
    )
    taken = db.execute(
        select(Operator.id).where(
            func.lower(Operator.username) == payload.username.lower()
        )
    ).first()
    if taken is not None:
        raise duplicate

    operator = Operator(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(operator)
    log_event(
        db,
        actor=caller.username,
        action="operator.created",
        target=operator.username,
        detail={"role": operator.role.value},
    )
    try:
        db.commit()
    except IntegrityError:
        # Two requests created the same name at once; the unique constraint won.
        db.rollback()
        raise duplicate from None
    db.refresh(operator)
    return operator


@router.patch("/{operator_id}", response_model=OperatorOut)
def update_operator(
    operator_id: uuid.UUID,
    payload: OperatorUpdateIn,
    caller: Operator = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Operator:
    """Change another account's role and/or status.

    An administrator cannot address their own account, so the caller always
    remains an active administrator: the panel's own actions can never leave the
    deployment with none. Setting what the account already has is a no-op and
    writes nothing. Disabling ends the account's sessions; a role change does
    not need to, because the role is read live on every request.
    """
    target = _load(db, operator_id)
    if target.id == caller.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="You cannot change your own role or status",
        )

    if payload.role is not None and payload.role != target.role:
        log_event(
            db,
            actor=caller.username,
            action="operator.role_changed",
            target=target.username,
            detail={"from": target.role.value, "to": payload.role.value},
        )
        target.role = payload.role

    if payload.status is not None and payload.status != target.status:
        target.status = payload.status
        if payload.status == OperatorStatus.DISABLED:
            end_sessions(db, target)
        log_event(
            db,
            actor=caller.username,
            action=(
                "operator.disabled"
                if payload.status == OperatorStatus.DISABLED
                else "operator.enabled"
            ),
            target=target.username,
        )

    db.commit()
    db.refresh(target)
    return target


@router.post("/{operator_id}/password", status_code=204, response_class=Response)
def reset_password(
    operator_id: uuid.UUID,
    payload: OperatorPasswordResetIn,
    caller: Operator = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Set another account's password, ending its sessions.

    Never one's own: that goes through the change form, which asks for the
    current password. The account's login and password-change throttles are
    cleared, so a colleague who was locked out can sign in with the new password.
    """
    target = _load(db, operator_id)
    if target.id == caller.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Change your own password from Settings",
        )

    target.password_hash = hash_password(payload.new_password)
    end_sessions(db, target)
    log_event(
        db,
        actor=caller.username,
        action="operator.password_reset",
        target=target.username,
    )
    db.commit()
    throttle.reset(target.username)
    throttle.reset(f"password-change:{target.username}")
    return Response(status_code=204)
