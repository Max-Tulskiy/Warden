"""The `agents` table: one row per enrolled workstation agent."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base, UTCDateTime


class AgentStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hostname: Mapped[str] = mapped_column(String(255))
    os: Mapped[str] = mapped_column(String(64))
    agent_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, native_enum=False), default=AgentStatus.ACTIVE
    )
    enrolled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
