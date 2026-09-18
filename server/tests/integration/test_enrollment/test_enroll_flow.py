"""Integration: an operator issues a token, then an agent enrolls with it."""


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


def test_issuing_a_token_requires_an_operator(client):
    response = client.post("/api/v1/enrollment-tokens")

    assert response.status_code == 401
