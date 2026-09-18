"""Schemas for operator authentication."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Caps input length ahead of Argon2id verification (CWE-307): without
    # this, an oversized password body pays the deliberately expensive
    # hashing cost before being rejected.
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 -- OAuth2 scheme name, not a secret
