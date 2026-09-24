"""Schemas for reading the audit log."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from warden_server.schemas.report import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from warden_server.schemas.timerange import TimeRange


class AuditFilter(TimeRange):
    """Query parameters of `GET /api/v1/audit`.

    The range is a read of rows the server already holds, not a request sent
    to any agent, so the four-hour cap on agent windows (constitution
    principle 3) does not apply to it.
    """

    #: Matched exactly. It can be an operator's username, a station's id, or
    #: the hostname a caller announced while registering.
    actor: str | None = Field(None, min_length=1, max_length=255)

    #: An exact action code (`operator.login`) or a dotted group (`operator`).
    #: The alphabet is that of the codes themselves and holds no `%`, so a
    #: value never carries a `LIKE` wildcard; the underscore is part of it and
    #: is escaped by the query.
    action: str | None = Field(
        None, min_length=1, max_length=64, pattern=r"^[a-z0-9_.]+$"
    )

    limit: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(0, ge=0)


class AuditEntryOut(BaseModel):
    """One audit log row.

    `action` stays a plain string on purpose: a row written by an older or a
    newer server must still be readable, so the set of codes is not enforced
    on the way out.
    """

    id: uuid.UUID
    actor: str
    action: str
    target: str
    occurred_at: datetime
    detail: dict[str, Any]

    model_config = {"from_attributes": True}
