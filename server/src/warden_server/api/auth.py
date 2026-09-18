"""Operator login."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.db import get_db
from warden_server.models.operator import Operator
from warden_server.schemas.auth import LoginRequest, TokenResponse
from warden_server.security import create_access_token, verify_password
from warden_server.services.audit import log_event

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    operator = db.execute(
        select(Operator).where(Operator.username == payload.username)
    ).scalar_one_or_none()

    invalid_credentials = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
    )
    if operator is None or not verify_password(
        payload.password, operator.password_hash
    ):
        raise invalid_credentials

    log_event(
        db, actor=operator.username, action="operator.login", target=operator.username
    )
    db.commit()
    return TokenResponse(access_token=create_access_token(operator.username))
