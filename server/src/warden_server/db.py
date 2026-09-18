"""Database engine and session management."""

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, create_engine, types
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from warden_server.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def json_column_type() -> JSON:
    """JSON type that renders as JSONB on PostgreSQL and plain JSON elsewhere.

    Falling back to plain JSON keeps unit and integration tests runnable
    against SQLite (constitution principle 7) while production, on
    PostgreSQL, gets JSONB's indexing and operator support.
    """
    return JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(types.TypeDecorator):
    """A `DateTime(timezone=True)` that is always timezone-aware in Python, in UTC.

    SQLite silently drops the timezone from a `DateTime(timezone=True)`
    column on read, giving back a naive datetime; PostgreSQL preserves it
    correctly. Normalizing on both the write and the read side here keeps
    the ORM layer consistent across both databases (constitution principle
    7: tests run against SQLite, production against PostgreSQL).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    def process_result_value(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


def _make_engine():
    settings = get_settings()
    # SQLite is used for local development and for the test suite (principle 7
    # of the constitution: server logic is testable without real hardware or a
    # standing Postgres instance); production deployments point
    # WARDEN_DATABASE_URL at PostgreSQL instead.
    connect_args = (
        {"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {}
    )
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session]:
    """FastAPI dependency yielding a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
