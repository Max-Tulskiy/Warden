"""Integration: an operator issues a token, then an agent enrolls with it."""

from datetime import UTC, datetime

from sqlalchemy import select, update

from warden_server.models.audit import AuditLogEntry
from warden_server.models.enrollment import EnrollmentToken
from warden_server.security import hash_secret_token


def test_enroll_with_a_freshly_issued_token_succeeds(client, auth_headers):
    issued = client.post("/api/v1/enrollment-tokens", headers=auth_headers)
    assert issued.status_code == 201
    token = issued.json()["token"]

    response = client.post(
        "/api/v1/enroll",
        json={"token": token, "hostname": "WORKSTATION-42", "os": "windows"},
    )

    assert response.status_code == 201
    body = response.json()
    assert "agent_id" in body
    assert "agent_key" in body


def test_enroll_rejects_an_unknown_token(client):
    response = client.post(
        "/api/v1/enroll",
        json={"token": "not-a-real-token", "hostname": "H", "os": "linux"},
    )

    assert response.status_code == 400


def test_enroll_rejects_a_token_already_used(client, enrollment_token):
    first = client.post(
        "/api/v1/enroll",
        json={"token": enrollment_token, "hostname": "H1", "os": "linux"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/enroll",
        json={"token": enrollment_token, "hostname": "H2", "os": "linux"},
    )

    assert second.status_code == 400


def test_enroll_rejection_is_audited(client, db_session, enrollment_token):
    client.post(
        "/api/v1/enroll",
        json={"token": enrollment_token, "hostname": "H1", "os": "linux"},
    )

    response = client.post(
        "/api/v1/enroll",
        json={"token": enrollment_token, "hostname": "H2", "os": "linux"},
    )
    assert response.status_code == 400

    entry = db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == "agent.enroll_rejected")
    ).scalar_one()
    assert entry.actor == "H2"


def test_issuing_a_token_requires_an_operator(client):
    response = client.post("/api/v1/enrollment-tokens")

    assert response.status_code == 401


def test_token_claim_is_a_single_conditional_update(db_session, enrollment_token):
    """Exercises the exact UPDATE `enroll()` uses to claim a token.

    This proves the claim is one conditional SQL statement -- a second
    claim against the same still-uncommitted transaction sees zero rows,
    not the token object read as still-unused -- which is what closes the
    race a plain SELECT-then-check would leave open (CWE-362). It does
    NOT reproduce genuine concurrent PostgreSQL transactions: the shared
    `db_session`/`client` fixtures pin every request to one session over
    one connection, and `TestClient` is synchronous.
    """
    token_hash = hash_secret_token(enrollment_token)
    now = datetime.now(UTC)
    claim = (
        update(EnrollmentToken)
        .where(
            EnrollmentToken.token_hash == token_hash,
            EnrollmentToken.used_at.is_(None),
            EnrollmentToken.expires_at >= now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )

    first = db_session.execute(claim)
    assert first.rowcount == 1

    second = db_session.execute(claim)
    assert second.rowcount == 0
