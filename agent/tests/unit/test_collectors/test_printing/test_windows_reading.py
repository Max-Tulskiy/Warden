"""Tests for the Windows printing backend's event-log reading glue.

`win32evtlog` exists only on Windows, so these tests install a stand-in
module that mirrors the part of pywin32's real interface the collector
uses. Its handles are closed with `Close()` and it has no `EvtClose`
function, like the real module -- the `windows-latest` CI leg runs the same
code against the real channel (`test_windows_live.py`).
"""

import sys
from types import SimpleNamespace

import pytest

from warden_agent.collectors.printing.windows import WindowsPrintingCollector

_EVENT_XML = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <System>
    <TimeCreated SystemTime="2024-10-10T13:55:36.000000000Z"/>
  </System>
  <EventData>
    <Data Name="Param1">report.pdf</Data>
    <Data Name="Param2">jsmith</Data>
    <Data Name="Param3">OfficePrinter</Data>
  </EventData>
</Event>"""


class _FakeHandle:
    def __init__(self, name: str = "handle") -> None:
        self.name = name
        self.closed = False

    def Close(self) -> None:  # pywin32 spells it this way
        self.closed = True


class _FakeEventLog:
    """A `win32evtlog` stand-in that serves the given batches of events."""

    def __init__(self, batches: list[list[_FakeHandle]], *, fail: bool = False) -> None:
        self.query_handle = _FakeHandle("query")
        self.seeks: list[tuple[object, int, int, object]] = []
        self._batches = iter(batches)
        self._fail = fail
        self.module = SimpleNamespace(
            EvtQueryChannelPath=1,
            EvtQueryForwardDirection=2,
            EvtSeekRelativeToBookmark=3,
            EvtRenderEventXml=4,
            EvtRenderBookmark=5,
            EvtQuery=self._query,
            EvtSeek=self._seek,
            EvtNext=self._next,
            EvtRender=self._render,
            EvtCreateBookmark=self._create_bookmark,
        )

    def _query(self, _channel: str, _flags: int, _query: str) -> _FakeHandle:
        return self.query_handle

    def _seek(self, handle: object, offset: int, flags: int, bookmark: object) -> None:
        self.seeks.append((handle, offset, flags, bookmark))

    def _next(self, _handle: object, _count: int) -> tuple[_FakeHandle, ...]:
        if self._fail:
            raise OSError("the event log is not readable")
        return tuple(next(self._batches, []))

    def _render(self, _event: object, flag: int) -> str:
        return _EVENT_XML if flag == self.module.EvtRenderEventXml else "<bookmark/>"

    def _create_bookmark(self, xml: str) -> _FakeHandle:
        return _FakeHandle(f"bookmark:{xml}")


@pytest.fixture
def install(monkeypatch):
    def _install(event_log: _FakeEventLog) -> None:
        monkeypatch.setitem(sys.modules, "win32evtlog", event_log.module)

    return _install


async def test_a_printed_document_becomes_an_event(install):
    install(_FakeEventLog([[_FakeHandle()]]))

    events = await WindowsPrintingCollector().collect()

    assert [event.payload for event in events] == [
        {"printer": "OfficePrinter", "user": "jsmith", "job_name": "report.pdf"}
    ]


async def test_the_query_handle_is_closed_after_reading(install):
    event_log = _FakeEventLog([[_FakeHandle()]])
    install(event_log)

    await WindowsPrintingCollector().collect()

    assert event_log.query_handle.closed


async def test_the_query_handle_is_closed_when_reading_fails(install):
    event_log = _FakeEventLog([], fail=True)
    install(event_log)

    with pytest.raises(OSError, match="not readable"):
        await WindowsPrintingCollector().collect()

    assert event_log.query_handle.closed


async def test_the_next_pass_resumes_after_the_last_event_it_saw(install):
    event_log = _FakeEventLog([[_FakeHandle()], []])
    install(event_log)
    collector = WindowsPrintingCollector()

    await collector.collect()
    assert event_log.seeks == []  # nothing to resume from on the first pass

    await collector.collect()

    [(handle, offset, flags, bookmark)] = event_log.seeks
    assert handle is event_log.query_handle
    assert offset == 0
    assert flags == event_log.module.EvtSeekRelativeToBookmark
    assert bookmark.name == "bookmark:<bookmark/>"
