"""Tests for parsing PrintService Event 307's rendered XML (fixture data)."""

from warden_agent.collectors.printing.windows import parse_print_event_xml

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


def test_parses_document_user_and_printer():
    record = parse_print_event_xml(_EVENT_XML)

    assert record is not None
    assert record["document_name"] == "report.pdf"
    assert record["user"] == "jsmith"
    assert record["printer"] == "OfficePrinter"
    assert record["occurred_at"].year == 2024


def test_malformed_xml_returns_none():
    assert parse_print_event_xml("not xml at all") is None


def test_missing_event_data_returns_none():
    xml_text = (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        '<System><TimeCreated SystemTime="2024-10-10T13:55:36.000000000Z"/></System>'
        "</Event>"
    )

    assert parse_print_event_xml(xml_text) is None


def test_missing_timestamp_returns_none():
    xml_text = (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        "<System></System>"
        "</Event>"
    )

    assert parse_print_event_xml(xml_text) is None
