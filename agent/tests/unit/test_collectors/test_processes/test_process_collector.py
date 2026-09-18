"""Tests for the process-start collector -- genuinely exercises `psutil`
against a real short-lived child process, not a fixture: process
enumeration needs no OS-specific mocking to be testable cross-platform.
"""

import asyncio
import subprocess
import sys

from warden_agent.collectors.processes import ProcessCollector


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])


async def test_a_newly_started_process_is_reported():
    collector = ProcessCollector()
    await collector.collect()  # baseline: mark already-running processes as seen

    proc = _spawn_sleeper()
    try:
        await asyncio.sleep(0.3)  # let the OS make the new process visible
        events = await collector.collect()
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    matching = [e for e in events if e.payload["pid"] == proc.pid]
    assert len(matching) == 1
    assert matching[0].category == "processes"
    assert matching[0].payload["name"]


async def test_a_process_already_seen_is_not_reported_again():
    collector = ProcessCollector()
    proc = _spawn_sleeper()
    try:
        await asyncio.sleep(0.3)
        first = await collector.collect()
        second = await collector.collect()
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert any(event.payload["pid"] == proc.pid for event in first)
    assert not any(event.payload["pid"] == proc.pid for event in second)
