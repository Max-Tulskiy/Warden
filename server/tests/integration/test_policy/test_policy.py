"""Integration: the read-only operating-policy endpoint (spec 002, R-7, A-7)."""

from warden_server.config import get_settings
from warden_server.schemas.auth import MIN_PASSWORD_LENGTH
from warden_server.schemas.event import MAX_REPORT_EVENTS
from warden_server.schemas.inventory import MAX_INVENTORY_ENTRIES
from warden_server.schemas.report import MAX_PAGE_SIZE

ALLOWED_FIELDS = {
    "max_request_window_hours",
    "enrollment_token_ttl_hours",
    "session_lifetime_minutes",
    "min_password_length",
    "max_report_events",
    "max_inventory_entries",
    "max_page_size",
}


def test_policy_requires_an_operator_token(client):
    assert client.get("/api/v1/policy").status_code == 401


def test_each_value_equals_what_actually_enforces_it(client, auth_headers):
    settings = get_settings()

    body = client.get("/api/v1/policy", headers=auth_headers).json()

    assert body == {
        "max_request_window_hours": settings.max_request_window_hours,
        "enrollment_token_ttl_hours": settings.enrollment_token_ttl_hours,
        "session_lifetime_minutes": settings.jwt_expire_minutes,
        "min_password_length": MIN_PASSWORD_LENGTH,
        "max_report_events": MAX_REPORT_EVENTS,
        "max_inventory_entries": MAX_INVENTORY_ENTRIES,
        "max_page_size": MAX_PAGE_SIZE,
    }


def test_the_response_exposes_only_the_allow_listed_fields(client, auth_headers):
    body = client.get("/api/v1/policy", headers=auth_headers).json()

    assert set(body) == ALLOWED_FIELDS


def test_no_secret_or_connection_string_is_exposed(client, auth_headers):
    settings = get_settings()

    text = client.get("/api/v1/policy", headers=auth_headers).text

    assert settings.jwt_secret not in text
    assert settings.database_url not in text
