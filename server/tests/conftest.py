"""Shared pytest fixtures.

The whole server test suite runs against an in-memory SQLite database
(constitution principle 7: server logic is testable without real hardware,
and without a standing PostgreSQL instance either) and a FastAPI `TestClient`
wired to that same database session, so anything an endpoint commits is
immediately visible to a test's own assertions.
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from warden_server.db import Base, get_db
from warden_server.main import app
from warden_server.models.enrollment import EnrollmentToken
from warden_server.models.operator import Operator, OperatorRole
from warden_server.security import (
    generate_secret_token,
    hash_password,
    hash_secret_token,
)


@pytest.fixture
def db_session() -> Generator[Session]:
    # StaticPool keeps every session on the same underlying connection, or
    # SQLAlchemy would open a fresh, empty in-memory database on the next
    # connection and "no such table" would follow create_all immediately.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient]:
    def override_get_db() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def operator_password() -> str:
    return "correct-horse-battery-staple"


@pytest.fixture
def operator(db_session: Session, operator_password: str) -> Operator:
    op = Operator(
        username="admin",
        password_hash=hash_password(operator_password),
        role=OperatorRole.ADMIN,
    )
    db_session.add(op)
    db_session.commit()
    return op


@pytest.fixture
def auth_headers(
    client: TestClient, operator: Operator, operator_password: str
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": operator_password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def enrollment_token(db_session: Session, operator: Operator) -> str:
    """A valid, unused enrollment token, inserted directly (bypassing the
    issuing endpoint, which is covered by its own test)."""
    token = generate_secret_token()
    db_session.add(
        EnrollmentToken(
            token_hash=hash_secret_token(token),
            created_by=operator.username,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    db_session.commit()
    return token


@pytest.fixture
def enrolled_agent(client: TestClient, enrollment_token: str) -> dict[str, str]:
    """Enroll an agent through the real endpoint; returns id and key."""
    response = client.post(
        "/api/v1/enroll",
        json={"token": enrollment_token, "hostname": "WORKSTATION-01", "os": "linux"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def agent_headers(enrolled_agent: dict[str, str]) -> dict[str, str]:
    return {"X-Agent-Key": enrolled_agent["agent_key"]}


@pytest.fixture
def viewer_password() -> str:
    return "observer-secret-passphrase"


@pytest.fixture
def viewer(db_session: Session, viewer_password: str) -> Operator:
    """An observer: may look at what was collected, but not act on it."""
    account = Operator(
        username="watcher",
        password_hash=hash_password(viewer_password),
        role=OperatorRole.VIEWER,
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def viewer_headers(
    client: TestClient, viewer: Operator, viewer_password: str
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": viewer.username, "password": viewer_password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
