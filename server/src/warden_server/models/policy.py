"""The `policy_overrides` table: the operating policy an administrator saved."""

from datetime import datetime

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base, UTCDateTime


class PolicyOverride(Base):
    """At most one row, and a row means all three values were saved together.

    No row means nobody has saved a policy, and the server's configured values
    apply. There are no per-value overrides, so "which value is in force" has a
    single answer (D-11).
    """

    __tablename__ = "policy_overrides"
    __table_args__ = (CheckConstraint("id = 1", name="ck_policy_overrides_single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    max_request_window_hours: Mapped[int]
    enrollment_token_ttl_hours: Mapped[int]
    session_lifetime_minutes: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_by: Mapped[str] = mapped_column(String(255))
