"""Read-only view of the server's operating limits."""

from fastapi import APIRouter, Depends

from warden_server.api.deps import require_operator
from warden_server.config import get_settings
from warden_server.schemas.auth import MIN_PASSWORD_LENGTH
from warden_server.schemas.event import MAX_REPORT_EVENTS
from warden_server.schemas.inventory import MAX_INVENTORY_ENTRIES
from warden_server.schemas.policy import PolicyOut
from warden_server.schemas.report import MAX_PAGE_SIZE

router = APIRouter(
    prefix="/api/v1", tags=["policy"], dependencies=[Depends(require_operator)]
)


@router.get("/policy", response_model=PolicyOut)
def get_policy() -> PolicyOut:
    """Return the limits the server enforces, read from where they are enforced."""
    settings = get_settings()
    return PolicyOut(
        max_request_window_hours=settings.max_request_window_hours,
        enrollment_token_ttl_hours=settings.enrollment_token_ttl_hours,
        session_lifetime_minutes=settings.jwt_expire_minutes,
        min_password_length=MIN_PASSWORD_LENGTH,
        max_report_events=MAX_REPORT_EVENTS,
        max_inventory_entries=MAX_INVENTORY_ENTRIES,
        max_page_size=MAX_PAGE_SIZE,
    )
