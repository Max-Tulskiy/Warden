"""Schemas for issuing agent enrollment tokens."""

from datetime import datetime

from pydantic import BaseModel


class EnrollmentTokenOut(BaseModel):
    """The plaintext token, returned once at creation time and never again."""

    token: str
    expires_at: datetime
