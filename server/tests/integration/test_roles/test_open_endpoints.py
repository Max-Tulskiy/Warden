"""Only four operations may be reached without any credential (spec 005, R-9).

The fourth, the server's published certificate authority, is decision D-13.
"""

from warden_server.main import app

OPEN_OPERATIONS = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/enroll"),
    ("GET", "/health"),
    ("GET", "/api/v1/tls/ca"),
}


def test_only_login_enrollment_health_and_the_authority_are_open():
    """Everything else needs a bearer token or an agent key, so a new endpoint
    added without either fails here instead of shipping open."""
    unauthenticated = set()
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            headers = {
                parameter["name"].lower()
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "header"
            }
            if not operation.get("security") and "x-agent-key" not in headers:
                unauthenticated.add((method.upper(), path))

    assert unauthenticated == OPEN_OPERATIONS
