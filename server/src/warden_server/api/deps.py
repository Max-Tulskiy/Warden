"""Shared FastAPI dependencies: database session and authentication."""

import uuid

from fastapi import Depends, Header, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.db import get_db
from warden_server.models.agent import Agent, AgentStatus
from warden_server.models.operator import Operator
from warden_server.security import decode_access_token, verify_secret_token

_bearer_scheme = HTTPBearer(auto_error=False)


def require_agent(
    agent_id: uuid.UUID = Path(...),
    x_agent_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Agent:
    """Authenticate an agent-facing request by its per-agent key (principle 5).

    The key must match the specific `agent_id` in the URL, not just belong to
    some active agent — otherwise one enrolled agent's key would work against
    every other agent's endpoints.
    """
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials"
    )
    if not x_agent_key:
        raise unauthorized
    agent = db.get(Agent, agent_id)
    if (
        agent is None
        or agent.status != AgentStatus.ACTIVE
        or not verify_secret_token(x_agent_key, agent.agent_key_hash)
    ):
        raise unauthorized
    return agent


def require_operator(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Operator:
    """Authenticate an operator-facing (panel) request by a JWT bearer token.

    The token must be valid, name a known operator, and carry that operator's
    current `token_version`.
    """
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing credentials"
    )
    if credentials is None:
        raise unauthorized
    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise unauthorized
    operator = db.execute(
        select(Operator).where(Operator.username == claims.subject)
    ).scalar_one_or_none()
    # A session ends when its operator's version moves past the one it was
    # issued at. The same 401 as any other refusal: an ended session must not
    # be distinguishable from an invalid one.
    if operator is None or claims.version != operator.token_version:
        raise unauthorized
    return operator
