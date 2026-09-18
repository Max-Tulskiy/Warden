"""Schemas for hardware/software inventory snapshots and detected changes."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

#: A Debian-family desktop typically carries 2,000-4,500 installed
#: packages; this leaves headroom for a heavily loaded workstation while
#: still bounding one snapshot's size (CWE-770).
MAX_INVENTORY_ENTRIES = 10_000


class InventoryIn(BaseModel):
    """The body of `POST /api/v1/agents/{id}/inventory`.

    Also doubles as the agent's heartbeat: the server always updates
    `last_seen_at` on receipt, regardless of whether the snapshot's content
    actually changed (constitution D-4).
    """

    hardware: dict[str, Any] = Field(
        default_factory=dict, max_length=MAX_INVENTORY_ENTRIES
    )
    software: dict[str, Any] = Field(
        default_factory=dict, max_length=MAX_INVENTORY_ENTRIES
    )


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
