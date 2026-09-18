"""Tests for the Linux printing backend against a real temporary log file
(constitution principle 7): incremental reading and per-job deduplication.
"""

from warden_agent.collectors.printing.linux import LinuxPrintingCollector

_LINE_1 = (
    "OfficePrinter jsmith 42 [10/Oct/2024:13:55:36 +0000] "
    "1 1 - workstation-07 report.pdf letter one-sided"
)
_LINE_2_SAME_JOB = (
    "OfficePrinter jsmith 42 [10/Oct/2024:13:55:37 +0000] "
    "2 1 - workstation-07 report.pdf letter one-sided"
)
_LINE_3_NEW_JOB = (
    "OfficePrinter agreen 43 [10/Oct/2024:14:02:11 +0000] "
    "1 1 - workstation-12 invoice.pdf letter one-sided"
)


async def test_a_new_job_is_reported_once(tmp_path):
    log_path = tmp_path / "page_log"
    log_path.write_text(_LINE_1 + "\n")
    collector = LinuxPrintingCollector(page_log_path=log_path)

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload["job_id"] == "42"
    assert events[0].payload["job_name"] == "report.pdf"


async def test_a_second_page_of_the_same_job_is_not_reported_again(tmp_path):
    log_path = tmp_path / "page_log"
    log_path.write_text(_LINE_1 + "\n")
    collector = LinuxPrintingCollector(page_log_path=log_path)
    await collector.collect()

    with log_path.open("a") as f:
        f.write(_LINE_2_SAME_JOB + "\n")

    events = await collector.collect()

    assert events == []


async def test_only_newly_appended_lines_are_read(tmp_path):
    log_path = tmp_path / "page_log"
    log_path.write_text(_LINE_1 + "\n")
    collector = LinuxPrintingCollector(page_log_path=log_path)
    await collector.collect()

    with log_path.open("a") as f:
        f.write(_LINE_3_NEW_JOB + "\n")

    events = await collector.collect()

    assert len(events) == 1
    assert events[0].payload["job_id"] == "43"


async def test_a_missing_log_file_yields_no_events(tmp_path):
    collector = LinuxPrintingCollector(page_log_path=tmp_path / "does-not-exist")

    assert await collector.collect() == []
