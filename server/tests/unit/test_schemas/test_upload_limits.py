"""Tests for the upload size caps that bound agent report/inventory payloads
(CWE-770, Codex Security 2026-09-18 standard scan)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from warden_server.schemas.event import MAX_REPORT_EVENTS, EventIn, ReportIn
from warden_server.schemas.inventory import MAX_INVENTORY_ENTRIES, InventoryIn


def _event() -> dict:
    return {
        "category": "processes",
        "occurred_at": datetime(2026, 1, 1, tzinfo=UTC),
        "payload": {},
    }


def test_a_report_at_the_event_limit_is_accepted():
    report = ReportIn(task_id="00000000-0000-0000-0000-000000000000", events=[])
    assert report.events == []

    report = ReportIn(
        task_id="00000000-0000-0000-0000-000000000000",
        events=[EventIn(**_event()) for _ in range(MAX_REPORT_EVENTS)],
    )
    assert len(report.events) == MAX_REPORT_EVENTS


def test_a_report_over_the_event_limit_is_rejected():
    with pytest.raises(ValidationError, match="at most"):
        ReportIn(
            task_id="00000000-0000-0000-0000-000000000000",
            events=[_event() for _ in range(MAX_REPORT_EVENTS + 1)],
        )


def test_inventory_at_the_entry_limit_is_accepted():
    inventory = InventoryIn(
        hardware={},
        software={f"pkg-{i}": "1.0" for i in range(MAX_INVENTORY_ENTRIES)},
    )
    assert len(inventory.software) == MAX_INVENTORY_ENTRIES


def test_inventory_over_the_entry_limit_is_rejected():
    with pytest.raises(ValidationError, match="at most"):
        InventoryIn(
            hardware={},
            software={f"pkg-{i}": "1.0" for i in range(MAX_INVENTORY_ENTRIES + 1)},
        )
