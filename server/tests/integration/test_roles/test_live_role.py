"""A role change applies to the same token on its next request (spec 005, R-12).

The role is read from the database on every request and is not in the token,
so nothing has to be reissued. The role is changed straight in the database
here; the endpoint that does it in practice is covered in `test_operators`.
"""

from warden_server.models.operator import OperatorRole


def _set_role(db_session, operator, role):
    operator.role = role
    db_session.commit()


def test_a_promoted_observer_can_use_administrator_endpoints_with_the_same_token(
    client, viewer, viewer_headers, db_session
):
    assert (
        client.post("/api/v1/enrollment-tokens", headers=viewer_headers).status_code
        == 403
    )

    _set_role(db_session, viewer, OperatorRole.ADMIN)

    assert (
        client.post("/api/v1/enrollment-tokens", headers=viewer_headers).status_code
        == 201
    )


def test_a_demoted_administrator_is_refused_on_the_next_request_but_keeps_the_session(
    client, auth_headers, operator, db_session
):
    assert (
        client.post("/api/v1/enrollment-tokens", headers=auth_headers).status_code
        == 201
    )

    _set_role(db_session, operator, OperatorRole.VIEWER)

    assert (
        client.post("/api/v1/enrollment-tokens", headers=auth_headers).status_code
        == 403
    )
    assert client.get("/api/v1/agents", headers=auth_headers).status_code == 200
