"""Operator login and password change."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.api.deps import require_operator
from warden_server.db import get_db
from warden_server.models.operator import Operator
from warden_server.schemas.auth import LoginRequest, PasswordChangeIn, TokenResponse
from warden_server.security import create_access_token, hash_password, verify_password
from warden_server.services import throttle
from warden_server.services.audit import log_event

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
    if operator is None or not verify_password(
        payload.password, operator.password_hash
    ):
        log_event(
            db,
            actor=payload.username,
            action="operator.login_failed",
            target=payload.username,
            detail={"reason": "unknown_user" if operator is None else "bad_password"},
        )
        db.commit()
        throttle.record_failure(payload.username)
        raise invalid_credentials

    throttle.reset(payload.username)
    log_event(
        db, actor=operator.username, action="operator.login", target=operator.username
    )
    db.commit()
    return TokenResponse(access_token=create_access_token(operator.username))


@router.post("/password", status_code=204, response_class=Response)
def change_password(
    payload: PasswordChangeIn,
    operator: Operator = Depends(require_operator),
    db: Session = Depends(get_db),
) -> Response:
    """Change the signed-in operator's own password.

    Already-issued session tokens are stateless JWTs and keep working until
    they expire; nothing here revokes them. Failed attempts are throttled
    under a key of their own, so a holder of a stolen token cannot use this
    endpoint to lock the operator out of login.
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

    # A 400, not a 401: a 401 would read to the panel as an expired session.
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
    throttle.reset(throttle_key)
    log_event(
        db,
        actor=operator.username,
        action="operator.password_change",
        target=operator.username,
    )
    db.commit()
    return Response(status_code=204)
