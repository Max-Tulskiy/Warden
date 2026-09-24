"""Schemas for the cross-station report."""

import uuid

from pydantic import Field

from warden_server.models.event import EventCategory
from warden_server.schemas.event import EventOut
from warden_server.schemas.timerange import TimeRange

DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 2000


class ReportFilter(TimeRange):
    """Query parameters of `GET /api/v1/events`.

    The range is a read of events the server has already stored, not a request
    sent to any agent, so the four-hour cap on agent windows (constitution
    principle 3) does not apply to it.
    """

    agent_id: list[uuid.UUID] = Field(default_factory=list)
    category: EventCategory | None = None
    limit: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(0, ge=0)


class ReportEventOut(EventOut):
    """One event of a cross-station report, labeled with its station.

    `hostname` is the station's current name; it is not versioned.
    """

    agent_id: uuid.UUID
    hostname: str
