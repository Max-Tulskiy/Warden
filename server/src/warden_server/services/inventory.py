"""Configuration-change detection (constitution principle 6).

A new snapshot is always stored (it is the audit trail); a change record is
created only when its content differs from the station's previous snapshot,
so that re-submitting an unchanged snapshot stays a no-op for the change
timeline the panel shows the administrator.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.models.inventory import InventoryChange, InventorySnapshot


def canonical_hash(hardware: dict[str, Any], software: dict[str, Any]) -> str:
    """A stable hash of a snapshot's content, independent of key order."""
    payload = json.dumps(
        {"hardware": hardware, "software": software},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _diff_section(old: dict[str, Any], new: dict[str, Any]) -> tuple[dict, dict, dict]:
    old_keys, new_keys = set(old.keys()), set(new.keys())
    added = {key: new[key] for key in new_keys - old_keys}
    removed = {key: old[key] for key in old_keys - new_keys}
    modified = {
        key: {"old": old[key], "new": new[key]}
        for key in old_keys & new_keys
        if old[key] != new[key]
    }
    return added, removed, modified


def ingest_snapshot(
    db: Session,
    *,
    agent_id: uuid.UUID,
    hardware: dict[str, Any],
    software: dict[str, Any],
) -> InventoryChange | None:
    """Store a new snapshot and, if it differs from the previous one, a change record.

    Returns the created `InventoryChange`, or `None` when the snapshot's
    content hash matches the station's last known snapshot.
    """
    content_hash = canonical_hash(hardware, software)
    previous = db.execute(
        select(InventorySnapshot)
        .where(InventorySnapshot.agent_id == agent_id)
        .order_by(InventorySnapshot.collected_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    db.add(
        InventorySnapshot(
            agent_id=agent_id,
            collected_at=now,
            hardware=hardware,
            software=software,
            content_hash=content_hash,
        )
    )

    if previous is None:
        # First-ever snapshot for this station: nothing to compare against, so
        # everything present counts as "added" rather than being silently
        # skipped — the administrator still gets a baseline change entry.
        hw_added, hw_removed, hw_modified = _diff_section({}, hardware)
        sw_added, sw_removed, sw_modified = _diff_section({}, software)
    elif previous.content_hash == content_hash:
        return None
    else:
        hw_added, hw_removed, hw_modified = _diff_section(previous.hardware, hardware)
        sw_added, sw_removed, sw_modified = _diff_section(previous.software, software)

    change = InventoryChange(
        agent_id=agent_id,
        detected_at=now,
        added={"hardware": hw_added, "software": sw_added},
        removed={"hardware": hw_removed, "software": sw_removed},
        modified={"hardware": hw_modified, "software": sw_modified},
    )
    db.add(change)
    # The id is a column default that only exists after a flush; callers (the
    # audit entry) name the change by it, so it must be assigned before return.
    db.flush()
    return change
