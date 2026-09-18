"""Schemas for agent enrollment and the station list."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from warden_server.models.agent import AgentStatus


class EnrollRequest(BaseModel):
    token: str
    hostname: str = Field(min_length=1, max_length=255)
    os: str = Field(min_length=1, max_length=64)


class EnrollResponse(BaseModel):
    agent_id: uuid.UUID
    agent_key: str


class AgentOut(BaseModel):
    id: uuid.UUID
    hostname: str
    os: str
    status: AgentStatus
    enrolled_at: datetime
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}
