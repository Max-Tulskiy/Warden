"""Hardware/software inventory: append-only snapshots and detected changes.

Kept in two separate tables on purpose (constitution principle 6): a new
snapshot never overwrites the previous one, and a detected change is its own
row rather than being inferred later by diffing snapshots on read.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base, UTCDateTime, json_column_type


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    hardware: Mapped[dict[str, Any]] = mapped_column(json_column_type())
    software: Mapped[dict[str, Any]] = mapped_column(json_column_type())
    content_hash: Mapped[str] = mapped_column(String(64))


class InventoryChange(Base):
    __tablename__ = "inventory_changes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    added: Mapped[dict[str, Any]] = mapped_column(json_column_type())
    removed: Mapped[dict[str, Any]] = mapped_column(json_column_type())
    modified: Mapped[dict[str, Any]] = mapped_column(json_column_type())
