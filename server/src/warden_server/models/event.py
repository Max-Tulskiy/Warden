"""The `events` table: category events an agent delivers for a requested window."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base, UTCDateTime, json_column_type


class EventCategory(StrEnum):
    REMOVABLE_MEDIA = "removable_media"
    PRINTING = "printing"
    PROCESSES = "processes"
    WEB = "web"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        # Serves the cross-station report, which filters on time alone;
        # without it that query would scan the whole table.
        Index("ix_events_occurred_at", "occurred_at"),
        # Serves the daily report's per-station range query and the
        # already-known-event lookup that backs deduplication on ingestion
        # (specs/007-event-deduplication/), both of which filter on a
        # station together with a time range or exact timestamps.
        Index("ix_events_agent_id_occurred_at", "agent_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory, native_enum=False)
    )
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[dict[str, Any]] = mapped_column(json_column_type())
