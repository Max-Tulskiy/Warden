"""Schemas for events an agent delivers when completing a window-request task."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from warden_server.models.event import EventCategory

#: Generous headroom over a realistic worst case: the process collector
#: reports process *starts*, not a snapshot every pass, so even a busy
#: 4-hour window (the request-window cap) realistically produces a low
#: thousands of events across all categories combined, not tens of
#: thousands. Bounds one report's memory footprint (CWE-770) without
#: rejecting a legitimate agent.
MAX_REPORT_EVENTS = 10_000


class EventIn(BaseModel):
    category: EventCategory
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def _assume_utc_if_naive(cls, value: datetime) -> datetime:
        """A timestamp with no offset is treated as UTC.

        Without this, an event submitted with a naive timestamp would
        crash the window-boundary check in `submit_report` with
        `TypeError: can't compare offset-naive and offset-aware
        datetimes` instead of being rejected with a normal 400/422.
        """
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ReportIn(BaseModel):
    """The body of `POST /api/v1/agents/{id}/reports`: an agent's answer to one task."""

    task_id: uuid.UUID
    events: list[EventIn] = Field(default_factory=list, max_length=MAX_REPORT_EVENTS)


class EventOut(BaseModel):
    id: uuid.UUID
    category: EventCategory
    occurred_at: datetime
    payload: dict[str, Any]

    model_config = {"from_attributes": True}
