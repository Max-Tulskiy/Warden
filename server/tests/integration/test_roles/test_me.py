"""`GET /api/v1/auth/me`: who am I, and what may I do (spec 005, R-15)."""


def test_an_administrator_learns_their_name_and_role(client, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"username": "admin", "role": "admin"}


def test_an_observer_learns_their_name_and_role(client, viewer_headers):
    response = client.get("/api/v1/auth/me", headers=viewer_headers)

    assert response.status_code == 200
    assert response.json() == {"username": "watcher", "role": "viewer"}


def test_no_token_is_unauthorized(client):
    assert client.get("/api/v1/auth/me").status_code == 401
