"""Application settings, loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Warden server.

    All values can be overridden through environment variables prefixed with
    `WARDEN_` (e.g. `WARDEN_DATABASE_URL`), or through a `.env` file in the
    working directory.
    """

    model_config = SettingsConfigDict(env_prefix="WARDEN_", env_file=".env")

    database_url: str = "sqlite:///./warden.db"
    jwt_secret: str = "change-me-in-production"  # noqa: S105 -- placeholder, not a real secret
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 8
    max_request_window_hours: int = 4
    enrollment_token_ttl_hours: int = 24
    cors_origins: list[str] = ["http://localhost:5173"]

    # A file holding the certificate of the authority that issued the server's
    # own certificate; published at GET /api/v1/tls/ca (decision D-13). Unset
    # when the certificate comes from a public authority.
    tls_ca_path: Path | None = None

    # Optional: an initial operator account created on first startup (see
    # services.bootstrap.ensure_seed_operator), meant for a fresh
    # docker-compose deployment that has no operators yet. Leaving either
    # unset skips seeding entirely.
    seed_admin_username: str | None = None
    seed_admin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
