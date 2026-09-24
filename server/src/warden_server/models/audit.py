"""The `audit_log` table: a record of every notable action (principle 8)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base, UTCDateTime, json_column_type


class AuditLogEntry(Base):
    __tablename__ = "audit_log"
    # Serves the audit log viewer, which reads a time range; without it that
    # query would scan a table that only ever grows.
    __table_args__ = (Index("ix_audit_log_occurred_at", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    detail: Mapped[dict[str, Any]] = mapped_column(json_column_type())
