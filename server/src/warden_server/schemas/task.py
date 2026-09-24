"""Schemas for the task queue an agent polls."""

import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, model_validator

from warden_server.models.task import TaskKind, TaskStatus
from warden_server.schemas.policy import WINDOW_HOURS_CEILING


class WindowRequestIn(BaseModel):
    """A request an operator places for a station's data over a time window.

    The window is capped at the constant four-hour ceiling (constitution
    principle 3); this is the server-side half of the check that is repeated
    independently on the agent, and it needs no database. The limit an
    administrator may have set below the ceiling is enforced by the endpoint.
    """

    window_start: datetime
    window_end: datetime

    @model_validator(mode="after")
    def validate_range(self) -> "WindowRequestIn":
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        if self.window_end - self.window_start > timedelta(hours=WINDOW_HOURS_CEILING):
            raise ValueError(
                f"the request window must not exceed {WINDOW_HOURS_CEILING} hours"
            )
        return self


class TaskOut(BaseModel):
    id: uuid.UUID
    kind: TaskKind
    window_start: datetime
    window_end: datetime
    status: TaskStatus

    model_config = {"from_attributes": True}
