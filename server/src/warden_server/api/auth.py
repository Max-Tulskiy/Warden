"""Operator login, password change, and ending sessions."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.api.deps import require_operator
from warden_server.db import get_db
from warden_server.models.operator import Operator, OperatorStatus
from warden_server.schemas.auth import (
    LoginRequest,
    MeOut,
    PasswordChangeIn,
    TokenResponse,
)
from warden_server.security import create_access_token, hash_password, verify_password
from warden_server.services import throttle
from warden_server.services.audit import log_event
from warden_server.services.policy import effective_policy
from warden_server.services.sessions import end_sessions

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _session_lifetime(db: Session) -> timedelta:
    """How long a session issued now lasts: the policy in force, read afresh."""
    return timedelta(minutes=effective_policy(db).session_lifetime_minutes)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if throttle.is_throttled(payload.username):
        log_event(
            db,
            actor=payload.username,
            action="operator.login_throttled",
            target=payload.username,
        )
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts, try again later",
        )

    operator = db.execute(
        select(Operator).where(Operator.username == payload.username)
    ).scalar_one_or_none()

    invalid_credentials = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
    )
    password_ok = operator is not None and verify_password(
        payload.password, operator.password_hash
    )
    # The password is checked first, so a wrong password on a disabled account
    # still reads as a wrong password; only the log tells a disabled account.
    if operator is None or not password_ok or operator.status != OperatorStatus.ACTIVE:
        if operator is None:
            reason = "unknown_user"
        elif not password_ok:
            reason = "bad_password"
        else:
            reason = "disabled"
        log_event(
            db,
            actor=payload.username,
            action="operator.login_failed",
            target=payload.username,
            detail={"reason": reason},
        )
        db.commit()
        throttle.record_failure(payload.username)
        raise invalid_credentials

    throttle.reset(payload.username)
    log_event(
        db, actor=operator.username, action="operator.login", target=operator.username
    )
    db.commit()
    return TokenResponse(
        access_token=create_access_token(
            operator.username, operator.token_version, _session_lifetime(db)
        )
    )


@router.get("/me", response_model=MeOut)
def me(operator: Operator = Depends(require_operator)) -> MeOut:
    """Who is signed in and what they may do; the panel shapes itself by it."""
    return MeOut(username=operator.username, role=operator.role)


@router.post("/password", response_model=TokenResponse)
def change_password(
    payload: PasswordChangeIn,
    operator: Operator = Depends(require_operator),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Change the signed-in operator's own password.

    A successful change ends every session issued so far and returns a token
    for the new version, so the session that made the change carries on while
    all the others are refused on their next request. A failed attempt ends
    nothing. Failed attempts are throttled under a key of their own, so a
    holder of a stolen token cannot use this endpoint to lock the operator out
    of login.
    """
    throttle_key = f"password-change:{operator.username}"
    if throttle.is_throttled(throttle_key):
        log_event(
            db,
            actor=operator.username,
            action="operator.password_change_throttled",
            target=operator.username,
        )
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts, try again later",
        )

    # A 400, not a 401: a 401 would read to the panel as an ended session.
    if not verify_password(payload.current_password, operator.password_hash):
        log_event(
            db,
            actor=operator.username,
            action="operator.password_change_failed",
            target=operator.username,
            detail={"reason": "bad_current_password"},
        )
        db.commit()
        throttle.record_failure(throttle_key)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )

    operator.password_hash = hash_password(payload.new_password)
    end_sessions(db, operator)
    throttle.reset(throttle_key)
    log_event(
        db,
        actor=operator.username,
        action="operator.password_change",
        target=operator.username,
    )
    db.commit()
    db.refresh(operator)
    return TokenResponse(
        access_token=create_access_token(
            operator.username, operator.token_version, _session_lifetime(db)
        )
    )


@router.post("/logout-all", status_code=204, response_class=Response)
def logout_all(
    operator: Operator = Depends(require_operator),
    db: Session = Depends(get_db),
) -> Response:
    """End every session of the signed-in operator, this one included."""
    end_sessions(db, operator)
    log_event(
        db,
        actor=operator.username,
        action="operator.sessions_revoked",
        target=operator.username,
    )
    db.commit()
    return Response(status_code=204)
