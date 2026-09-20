"""Schema for the read-only operating policy shown in the panel's settings."""

from pydantic import BaseModel


class PolicyOut(BaseModel):
    """Server limits an administrator can see but not change from the panel.

    An explicit allow-list: every field is named here on purpose, so a secret
    or connection string in `Settings` can never reach the response by being
    added there.
    """

    max_request_window_hours: int
    enrollment_token_ttl_hours: int
    session_lifetime_minutes: int
    min_password_length: int
    max_report_events: int
    max_inventory_entries: int
    max_page_size: int
