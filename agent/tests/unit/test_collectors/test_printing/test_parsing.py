"""Tests for parsing CUPS `page_log` lines (fixture text)."""

from datetime import datetime, timezone

from warden_agent.collectors.printing.parsing import parse_page_log_line


def test_parses_a_well_formed_line():
    line = (
        "OfficePrinter jsmith 42 [10/Oct/2024:13:55:36 +0000] "
        "1 1 - workstation-07 report.pdf letter one-sided"
    )

    record = parse_page_log_line(line)

    assert record is not None
    assert record["printer"] == "OfficePrinter"
    assert record["user"] == "jsmith"
    assert record["job_id"] == "42"
    assert record["hostname"] == "workstation-07"
    assert record["job_name"] == "report.pdf"
    assert record["occurred_at"] == datetime(
        2024, 10, 10, 13, 55, 36, tzinfo=timezone.utc
    )


def test_a_job_name_containing_spaces_is_preserved():
    line = (
        "OfficePrinter jsmith 42 [10/Oct/2024:13:55:36 +0000] "
        "1 1 - workstation-07 Quarterly Sales Report.docx letter one-sided"
    )

    record = parse_page_log_line(line)

    assert record is not None
    assert record["job_name"] == "Quarterly Sales Report.docx"


def test_a_malformed_line_returns_none():
    assert parse_page_log_line("not a page_log line at all") is None


def test_an_unparseable_timestamp_returns_none():
    line = "P u 1 [not-a-date] 1 1 - h name.pdf letter one-sided"

    assert parse_page_log_line(line) is None


def test_too_few_trailing_fields_returns_none():
    line = "P u 1 [10/Oct/2024:13:55:36 +0000] 1 1"

    assert parse_page_log_line(line) is None
