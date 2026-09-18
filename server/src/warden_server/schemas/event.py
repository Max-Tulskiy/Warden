"""Schemas for events an agent delivers when completing a window-request task."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from warden_server.models.event import EventCategory


class EventIn(BaseModel):
    category: EventCategory
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportIn(BaseModel):
    """The body of `POST /api/v1/agents/{id}/reports`: an agent's answer to one task."""

    task_id: uuid.UUID
    events: list[EventIn] = Field(default_factory=list)


class EventOut(BaseModel):
    id: uuid.UUID
    category: EventCategory
    occurred_at: datetime
    payload: dict[str, Any]

    model_config = {"from_attributes": True}
