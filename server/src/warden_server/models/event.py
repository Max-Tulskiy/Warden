"""The `events` table: category events an agent delivers for a requested window."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base, UTCDateTime, json_column_type


class EventCategory(StrEnum):
    REMOVABLE_MEDIA = "removable_media"
    PRINTING = "printing"
    PROCESSES = "processes"
    WEB = "web"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory, native_enum=False)
    )
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[dict[str, Any]] = mapped_column(json_column_type())
