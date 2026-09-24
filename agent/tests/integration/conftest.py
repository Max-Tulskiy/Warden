"""Fixtures for cross-package integration tests.

These spin up the real `warden_server` FastAPI app in-process, over
`httpx.ASGITransport` -- no network socket, no separately running server --
so the agent's `ServerClient` is checked against actual server behavior
instead of a hand-written stub of it (constitution principle 11: the two
sides of the contract are exercised together, not just separately).
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from warden_server.db import Base, get_db
from warden_server.main import app
from warden_server.models.enrollment import EnrollmentToken
from warden_server.models.operator import Operator, OperatorRole
from warden_server.security import (
    create_access_token,
    generate_secret_token,
    hash_password,
    hash_secret_token,
)

from warden_agent.core.transport import ServerClient


@pytest.fixture
def server_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def enrollment_token(server_db) -> str:
    token = generate_secret_token()
    now = datetime.now(UTC)
    server_db.add(
        EnrollmentToken(
            token_hash=hash_secret_token(token),
            created_by="tests",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )
    server_db.commit()
    return token


@pytest.fixture
def operator_bearer_token(server_db) -> str:
    operator = Operator(
        username="admin",
        password_hash=hash_password("s3cret-pass"),
        role=OperatorRole.ADMIN,
    )
    server_db.add(operator)
    server_db.commit()
    # A session token carries the operator's version; the server refuses one
    # that does not match it.
    return create_access_token(operator.username, operator.token_version)


@pytest.fixture
async def server_client(server_db) -> Generator[ServerClient]:
    transport = httpx.ASGITransport(app=app)
    client = ServerClient("http://testserver", transport=transport)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def raw_client(server_db) -> Generator[httpx.AsyncClient]:
    """A plain HTTP client for the operator side of the exchange (panel API)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client
