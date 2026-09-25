"""The status file the connection window reads: codes, written atomically."""

import json
import os
from datetime import UTC, datetime

from warden_agent.core.transport import FailureKind
from warden_agent.status import AgentStatus, StatusStore

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _store(tmp_path) -> StatusStore:
    return StatusStore(tmp_path / "status.json", now=lambda: NOW)


def test_a_missing_file_reads_as_nothing_known(tmp_path):
    assert _store(tmp_path).read() == AgentStatus()
    assert _store(tmp_path).read().state is None


def test_waiting_records_why_and_running_clears_it(tmp_path):
    store = _store(tmp_path)

    store.record_waiting("not_configured")
    assert store.read().state == "waiting"
    assert store.read().detail == "not_configured"

    store.record_running()
    assert store.read().state == "running"
    assert store.read().detail is None


def test_a_success_records_when_and_clears_the_last_error(tmp_path):
    store = _store(tmp_path)
    store.record_failure(FailureKind.UNREACHABLE)

    store.record_success()

    status = store.read()
    assert status.last_success_at == NOW
    assert status.last_error is None
    assert status.last_error_at is None


def test_a_failure_stores_its_code_and_time_and_nothing_else(tmp_path):
    store = _store(tmp_path)

    store.record_failure(FailureKind.CERTIFICATE_NOT_TRUSTED)

    stored = json.loads((tmp_path / "status.json").read_text())
    assert stored["last_error"] == "certificate_not_trusted"
    assert set(stored) == {
        "state",
        "detail",
        "last_success_at",
        "last_error",
        "last_error_at",
    }


def test_what_one_store_writes_another_reads(tmp_path):
    _store(tmp_path).record_success()

    assert StatusStore(tmp_path / "status.json").read().last_success_at == NOW


def test_a_corrupt_or_unknown_file_reads_as_nothing_known(tmp_path):
    path = tmp_path / "status.json"
    for text in ("not json", '{"detail": "from-a-newer-version"}', "[]"):
        path.write_text(text)

        assert StatusStore(path).read() == AgentStatus()


def test_a_write_leaves_no_temporary_file_behind(tmp_path):
    _store(tmp_path).record_success()

    assert sorted(item.name for item in tmp_path.iterdir()) == ["status.json"]


def test_a_write_that_fails_does_not_stop_the_agent(tmp_path, monkeypatch):
    """On Windows a reader holding the file can make the replace fail."""

    def refuse(*_args, **_kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr(os, "replace", refuse)

    _store(tmp_path).record_success()  # must not raise

    assert not (tmp_path / "status.json").exists()
