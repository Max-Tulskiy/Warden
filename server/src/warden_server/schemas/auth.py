"""Schemas for operator authentication."""

from pydantic import BaseModel, Field, model_validator

from warden_server.models.operator import OperatorRole

#: Minimum length of a new operator password. A module constant rather than a
#: setting, like the upload limits: it is a fixed policy the panel reads back
#: through `GET /api/v1/policy`, not a per-deployment tuning knob.
MIN_PASSWORD_LENGTH = 12

#: Caps input length ahead of Argon2id hashing/verification (CWE-307):
#: without it, an oversized password body pays the deliberately expensive
#: hashing cost before being rejected.
MAX_PASSWORD_LENGTH = 1024


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 -- OAuth2 scheme name, not a secret


class PasswordChangeIn(BaseModel):
    """The body of `POST /api/v1/auth/password`."""

    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(
        min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH
    )

    @model_validator(mode="after")
    def _new_password_must_differ(self) -> "PasswordChangeIn":
        # Compares the two inputs only, never against the stored hash, so it
        # cannot be used to probe whether `current_password` is right.
        if self.new_password == self.current_password:
            raise ValueError("the new password must differ from the current one")
        return self


class MeOut(BaseModel):
    """Who the signed-in operator is and what they may do."""

    username: str
    role: OperatorRole
