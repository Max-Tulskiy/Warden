"""Windows printing backend: reads Event ID 307 from the PrintService
Operational log.

Uses `win32evtlog`'s newer `Evt*` API, not the classic `OpenEventLog` --
that older API only reaches the four traditional logs (Application, System,
Security, Setup), not an "Applications and Services" channel like
PrintService/Operational. `win32evtlog` only exists on Windows, so it is
imported lazily inside the function that needs it -- this module must stay
importable on any platform (constitution principle 1). Only that thin
event-reading glue is untested outside the `windows-latest` CI leg and a
live check (Section VI); `parse_print_event_xml` carries the actual field
extraction and is unit-tested on fixture XML on every platform.
"""

import asyncio
from datetime import datetime
from typing import Any, TypedDict
from xml.etree import ElementTree  # nosec B405

from warden_agent.core.models import OutgoingEvent

_CHANNEL = "Microsoft-Windows-PrintService/Operational"
_DOCUMENT_PRINTED_EVENT_ID = 307
_EVT_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
_MIN_EVENT_DATA_VALUES = 3


class PrintRecord(TypedDict):
    document_name: str
    user: str
    printer: str
    occurred_at: datetime


def parse_print_event_xml(xml_text: str) -> PrintRecord | None:
    """Extract the fields Event 307 carries from its rendered XML.

    Field order in the EventData for ID 307: document name, username,
    printer name (then port/session/byte count, not needed here).
    """
    try:
        # Local OS event data via win32evtlog, not untrusted network input --
        # see the module docstring for where this XML actually comes from.
        root = ElementTree.fromstring(xml_text)  # noqa: S314  # nosec B314
    except ElementTree.ParseError:
        return None

    system = root.find(f"{_EVT_NS}System")
    time_created = system.find(f"{_EVT_NS}TimeCreated") if system is not None else None
    if time_created is None or "SystemTime" not in time_created.attrib:
        return None
    try:
        occurred_at = datetime.fromisoformat(
            time_created.attrib["SystemTime"].replace("Z", "+00:00")
        )
    except ValueError:
        return None

    event_data = root.find(f"{_EVT_NS}EventData")
    if event_data is None:
        return None
    values = [element.text or "" for element in event_data.findall(f"{_EVT_NS}Data")]
    if len(values) < _MIN_EVENT_DATA_VALUES:
        return None

    return PrintRecord(
        document_name=values[0],
        user=values[1],
        printer=values[2],
        occurred_at=occurred_at,
    )


class WindowsPrintingCollector:
    category = "printing"

    def __init__(self) -> None:
        self._bookmark: Any = None

    async def collect(self) -> list[OutgoingEvent]:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[OutgoingEvent]:
        events = []
        for xml_text in self._read_new_events():
            record = parse_print_event_xml(xml_text)
            if record is None:
                continue
            events.append(
                OutgoingEvent(
                    category=self.category,
                    occurred_at=record["occurred_at"],
                    payload={
                        "printer": record["printer"],
                        "user": record["user"],
                        "job_name": record["document_name"],
                    },
                )
            )
        return events

    def _read_new_events(self) -> list[str]:
        import win32evtlog  # Windows-only; see module docstring

        query = f"*[System[(EventID={_DOCUMENT_PRINTED_EVENT_ID})]]"
        flags = win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryForwardDirection
        handle = win32evtlog.EvtQuery(_CHANNEL, flags, query)
        try:
            if self._bookmark is not None:
                win32evtlog.EvtSeek(
                    handle, 0, win32evtlog.EvtSeekRelativeToBookmark, self._bookmark
                )

            xml_events = []
            while True:
                batch = win32evtlog.EvtNext(handle, 32)
                if not batch:
                    break
                for event in batch:
                    xml_events.append(
                        win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
                    )
                    self._bookmark = win32evtlog.EvtCreateBookmark(
                        win32evtlog.EvtRender(event, win32evtlog.EvtRenderBookmark)
                    )
            return xml_events
        finally:
            win32evtlog.EvtClose(handle)
