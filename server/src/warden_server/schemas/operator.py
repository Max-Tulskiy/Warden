"""Schemas for administrators managing operator accounts."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from warden_server.models.operator import OperatorRole, OperatorStatus
from warden_server.schemas.auth import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

#: A username starts with a letter or digit and continues with letters, digits,
#: and `. _ @ -`, up to 64 characters. It becomes the session subject and the
#: audit actor, so lookalikes and control characters are kept out of it.
USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$"


class OperatorOut(BaseModel):
    """An account as an administrator sees it: never any password data."""

    id: uuid.UUID
    username: str
    role: OperatorRole
    status: OperatorStatus

    model_config = {"from_attributes": True}


class OperatorCreateIn(BaseModel):
    """The body of `POST /api/v1/operators`."""

    username: str = Field(pattern=USERNAME_PATTERN)
    role: OperatorRole
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH
    )


class OperatorUpdateIn(BaseModel):
    """The body of `PATCH /api/v1/operators/{id}`: a role, a status, or both.

    Any other field is refused, so a password can never ride along in a general
    update; resetting one has its own endpoint with its own rules.
    """

    model_config = ConfigDict(extra="forbid")

    role: OperatorRole | None = None
    status: OperatorStatus | None = None

    @model_validator(mode="after")
    def _needs_something_to_change(self) -> "OperatorUpdateIn":
        if self.role is None and self.status is None:
            raise ValueError("give a role, a status, or both")
        return self


class OperatorPasswordResetIn(BaseModel):
    """The body of `POST /api/v1/operators/{id}/password`."""

    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(
        min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH
    )
