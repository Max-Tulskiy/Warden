"""Live check of the Windows printing backend's event-log query.

Skipped everywhere except an actual Windows runner: exercises a real
`win32evtlog` query against the PrintService/Operational channel
(constitution Section VI). No print jobs are expected on a CI runner, so an
empty result is the correct outcome -- this checks that the query itself
runs against the real channel without error, not that it finds anything.
"""

import sys

import pytest

from warden_agent.collectors.printing.windows import WindowsPrintingCollector

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="exercises a real win32evtlog query, Windows only"
)


async def test_collect_runs_without_error():
    collector = WindowsPrintingCollector()

    events = await collector.collect()

    assert isinstance(events, list)
