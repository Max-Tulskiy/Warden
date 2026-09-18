"""Integration: operator login and access to protected panel endpoints."""


def test_login_with_correct_credentials_returns_a_bearer_token(
    client, operator, operator_password
):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": operator_password},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"  # noqa: S105 -- OAuth2 scheme name


def test_login_with_a_wrong_password_is_rejected(client, operator):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": operator.username, "password": "wrong"},
    )

    assert response.status_code == 401


def test_panel_endpoints_reject_a_request_without_a_token(client):
    response = client.get("/api/v1/agents")

    assert response.status_code == 401


def test_panel_endpoints_accept_a_valid_token(client, auth_headers):
    response = client.get("/api/v1/agents", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []
