"""Shared FastAPI dependencies: database session and authentication."""

import uuid

from fastapi import Depends, Header, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.db import get_db
from warden_server.models.agent import Agent, AgentStatus
from warden_server.models.operator import Operator, OperatorRole, OperatorStatus
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

    The token must be valid, name a known, active operator, and carry that
    operator's current `token_version`.
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
    # issued at, or when the account is disabled. The same 401 as any other
    # refusal: an ended session must not be distinguishable from an invalid one.
    if (
        operator is None
        or operator.status != OperatorStatus.ACTIVE
        or claims.version != operator.token_version
    ):
        raise unauthorized
    return operator


#: The response an administrator-only operation adds to the contract. FastAPI
#: cannot derive it from the dependency, and a caller reading the contract
#: needs to learn that an observer is refused (principle 11).
ADMIN_ONLY_RESPONSES: dict[int | str, dict[str, str]] = {
    status.HTTP_403_FORBIDDEN: {"description": "Administrator role required"}
}


def require_admin(operator: Operator = Depends(require_operator)) -> Operator:
    """Allow only an administrator, on top of a valid session.

    A 403, not a 401: the session is fine and the person is not signed out; the
    panel can tell them they lack the role. The role is read from the row on
    every request, so a change applies to the person's next action (D-10).
    """
    if operator.role != OperatorRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
    return operator
