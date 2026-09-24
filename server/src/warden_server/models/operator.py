"""The `operators` table: administrator accounts for the web panel."""

import uuid

from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from warden_server.db import Base


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
