"""The migration that gives operators a role and a status (spec 005, R-14, A-15).

It runs against a real temporary SQLite file, not the in-memory fixtures, so the
account that exists *before* the migration is a genuine pre-upgrade row.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from warden_server.config import get_settings

SERVER_DIR = Path(__file__).resolve().parents[3]
BEFORE_ROLES = "d23c48cef8fe"
LEGACY_ID = "11111111111111111111111111111111"


@pytest.fixture
def database(tmp_path, monkeypatch) -> Iterator[Path]:
    path = tmp_path / "migration.db"
    monkeypatch.setenv("WARDEN_DATABASE_URL", f"sqlite:///{path}")
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def _alembic() -> Config:
    # No ini file: it would reconfigure logging for the rest of the test run.
    config = Config()
    config.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    return config


def _columns(path: Path, table: str) -> dict[str, tuple]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    # name -> (type, notnull, default)
    return {row[1]: (row[2], row[3], row[4]) for row in rows}


def _insert_legacy_operator(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO operators (id, username, password_hash) "
            "VALUES (?, 'legacy', 'hash')",
            (LEGACY_ID,),
        )


def test_an_existing_operator_becomes_an_active_administrator(database):
    command.upgrade(_alembic(), BEFORE_ROLES)
    _insert_legacy_operator(database)

    command.upgrade(_alembic(), "head")

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT username, role, status FROM operators"
        ).fetchall()
    assert row == [("legacy", "ADMIN", "ACTIVE")]


def test_the_finished_role_column_has_no_default_but_status_keeps_one(database):
    command.upgrade(_alembic(), "head")

    columns = _columns(database, "operators")
    assert columns["role"][1] == 1 and columns["role"][2] is None
    assert columns["status"][1] == 1 and "ACTIVE" in str(columns["status"][2])


def test_a_raw_insert_without_a_role_is_refused(database):
    command.upgrade(_alembic(), "head")

    with sqlite3.connect(database) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO operators (id, username, password_hash, token_version) "
            "VALUES (?, 'raw', 'hash', 0)",
            (LEGACY_ID,),
        )


def test_downgrading_removes_both_columns_and_keeps_the_operator(database):
    command.upgrade(_alembic(), BEFORE_ROLES)
    _insert_legacy_operator(database)
    command.upgrade(_alembic(), "head")

    # To the revision before the roles, not `-1`: later revisions sit above them.
    command.downgrade(_alembic(), BEFORE_ROLES)

    columns = _columns(database, "operators")
    assert "role" not in columns and "status" not in columns
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT username FROM operators").fetchall() == [
            ("legacy",)
        ]


def test_the_models_and_the_migrations_agree(database):
    """The same check as `alembic check`: nothing left for autogenerate to add."""
    command.upgrade(_alembic(), "head")

    command.check(_alembic())
