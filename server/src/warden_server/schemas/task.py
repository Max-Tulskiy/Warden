"""Schemas for the task queue an agent polls."""

import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, model_validator

from warden_server.config import get_settings
from warden_server.models.task import TaskKind, TaskStatus


class WindowRequestIn(BaseModel):
    """A request an operator places for a station's data over a time window.

    The window is capped at `max_request_window_hours` (4 by default,
    constitution principle 3); this is the server-side half of the check that
    is repeated independently on the agent.
    """

    window_start: datetime
    window_end: datetime

    @model_validator(mode="after")
    def validate_range(self) -> "WindowRequestIn":
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        max_hours = get_settings().max_request_window_hours
        if self.window_end - self.window_start > timedelta(hours=max_hours):
            raise ValueError(f"the request window must not exceed {max_hours} hours")
        return self


class TaskOut(BaseModel):
    id: uuid.UUID
    kind: TaskKind
    window_start: datetime
    window_end: datetime
    status: TaskStatus

    model_config = {"from_attributes": True}
