"""Schemas for hardware/software inventory snapshots and detected changes."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InventoryIn(BaseModel):
    """The body of `POST /api/v1/agents/{id}/inventory`.

    Also doubles as the agent's heartbeat: the server always updates
    `last_seen_at` on receipt, regardless of whether the snapshot's content
    actually changed (constitution D-4).
    """

    hardware: dict[str, Any] = Field(default_factory=dict)
    software: dict[str, Any] = Field(default_factory=dict)


class InventoryChangeOut(BaseModel):
    id: uuid.UUID
    detected_at: datetime
    added: dict[str, Any]
    removed: dict[str, Any]
    modified: dict[str, Any]

    model_config = {"from_attributes": True}


class InventorySnapshotOut(BaseModel):
    id: uuid.UUID
    collected_at: datetime
    hardware: dict[str, Any]
    software: dict[str, Any]

    model_config = {"from_attributes": True}
