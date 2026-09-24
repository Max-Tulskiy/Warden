"""The `operators` table: administrator accounts for the web panel."""

import uuid
from enum import StrEnum

from sqlalchemy import Enum, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base


class OperatorRole(StrEnum):
    """What an account may do. Two roles, enforced by the server (D-10)."""

    ADMIN = "admin"
    VIEWER = "viewer"


class OperatorStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    #: Raised to end every session issued to this operator: a session token
    #: carries the value it was issued at and is refused once they differ
    #: (constitution D-9).
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    #: Read from the row on every request, not carried in the token, so a change
    #: applies to the person's next action. No default: creating an account
    #: without saying what it may do is an error, never a silent administrator.
    role: Mapped[OperatorRole] = mapped_column(Enum(OperatorRole, native_enum=False))
    status: Mapped[OperatorStatus] = mapped_column(
        Enum(OperatorStatus, native_enum=False),
        default=OperatorStatus.ACTIVE,
        server_default="ACTIVE",
    )
