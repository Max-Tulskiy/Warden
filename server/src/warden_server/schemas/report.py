"""Schemas for the cross-station report."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from warden_server.models.event import EventCategory
from warden_server.schemas.event import EventOut

DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 2000


class ReportFilter(BaseModel):
    """Query parameters of `GET /api/v1/events`.

    The range is a read of events the server has already stored, not a request
    sent to any agent, so the four-hour cap on agent windows (constitution
    principle 3) does not apply to it.
    """

    start: datetime
    end: datetime
    agent_id: list[uuid.UUID] = Field(default_factory=list)
    category: EventCategory | None = None
    limit: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(0, ge=0)

    @field_validator("start", "end")
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        """Treat a naive timestamp as UTC and convert any offset to UTC.

        Normalizing before the range check means one naive and one aware
        value cannot raise `TypeError` mid-comparison, and SQLite (which drops
        an offset rather than applying it) is handed UTC values.
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_range(self) -> "ReportFilter":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class ReportEventOut(EventOut):
    """One event of a cross-station report, labeled with its station.

    `hostname` is the station's current name; it is not versioned.
    """

    agent_id: uuid.UUID
    hostname: str
