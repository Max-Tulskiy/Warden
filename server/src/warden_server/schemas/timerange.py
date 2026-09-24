"""The half-open time range shared by the panel's read filters."""

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator, model_validator


class TimeRange(BaseModel):
    """`start` and `end` of a read query, normalized and checked once.

    Holds only the two timestamps: a subclass declares its own filters and
    paging after them, which keeps the order of its query parameters (and so
    `contracts/openapi.yaml`) as it was before the range was shared.
    """

    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        """Treat a naive timestamp as UTC and convert any offset to UTC.

        Normalizing before the range check means one naive and one aware
        value cannot raise `TypeError` mid-comparison, and SQLite (which drops
        an offset rather than applying it) is handed UTC values.
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_range(self) -> "TimeRange":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self
