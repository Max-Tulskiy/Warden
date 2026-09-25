"""The migration that adds the saved operating policy (spec 006, A-18).

Runs against a real temporary SQLite file so the database that exists before the
migration is a genuine pre-upgrade one.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from warden_server.config import get_settings

SERVER_DIR = Path(__file__).resolve().parents[3]
BEFORE_POLICY = "afddc26b2815"

INSERT = (
    "INSERT INTO policy_overrides (id, max_request_window_hours, "
    "enrollment_token_ttl_hours, session_lifetime_minutes, updated_at, updated_by) "
    "VALUES (?, 2, 12, 60, '2026-09-24 12:00:00', 'admin')"
)


@pytest.fixture
def database(tmp_path, monkeypatch) -> Iterator[Path]:
    path = tmp_path / "migration.db"
    monkeypatch.setenv("WARDEN_DATABASE_URL", f"sqlite:///{path}")
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def _alembic() -> Config:
    config = Config()
    config.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    return config


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_an_existing_database_gets_an_empty_policy_table(database):
    command.upgrade(_alembic(), BEFORE_POLICY)
    assert "policy_overrides" not in _tables(database)

    command.upgrade(_alembic(), "head")

    assert "policy_overrides" in _tables(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM policy_overrides"
        ).fetchone() == (0,)


def test_the_table_holds_at_most_one_row(database):
    command.upgrade(_alembic(), "head")

    with sqlite3.connect(database) as connection:
        connection.execute(INSERT, (1,))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(INSERT, (2,))


def test_downgrading_drops_the_table_and_keeps_the_rest(database):
    command.upgrade(_alembic(), "head")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO operators (id, username, password_hash, token_version, role, "
            "status) VALUES ('11111111111111111111111111111111', 'kept', 'h', 0, "
            "'ADMIN', 'ACTIVE')"
        )

    # To the revision before the policy table, not `-1`: later revisions sit above it.
    command.downgrade(_alembic(), BEFORE_POLICY)

    assert "policy_overrides" not in _tables(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT username FROM operators").fetchall() == [
            ("kept",)
        ]


def test_the_models_and_the_migrations_agree(database):
    command.upgrade(_alembic(), "head")

    command.check(_alembic())
