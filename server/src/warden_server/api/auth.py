"""Operator login."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.db import get_db
from warden_server.models.operator import Operator
from warden_server.schemas.auth import LoginRequest, TokenResponse
from warden_server.security import create_access_token, verify_password
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
