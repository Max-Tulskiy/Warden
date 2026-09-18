"""Linux printing backend: tails CUPS' `page_log` for new print jobs.

CUPS logs one line per page; this collector reports one event per *job*
(the assignment's "documents sent to print", not per page) by remembering
which `(printer, job-id)` pairs it has already reported and skipping later
pages of the same job.
"""

import asyncio
from pathlib import Path

from warden_agent.collectors.printing.parsing import parse_page_log_line
from warden_agent.core.models import OutgoingEvent


class LinuxPrintingCollector:
    category = "printing"

    def __init__(self, *, page_log_path: Path = Path("/var/log/cups/page_log")) -> None:
        self._page_log_path = page_log_path
        self._offset = 0
        self._seen_jobs: set[tuple[str, str]] = set()

    async def collect(self) -> list[OutgoingEvent]:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[OutgoingEvent]:
        events = []
        for line in self._read_new_lines():
            record = parse_page_log_line(line)
            if record is None:
                continue
            job_key = (record["printer"], record["job_id"])
            if job_key in self._seen_jobs:
                continue
            self._seen_jobs.add(job_key)
            events.append(
                OutgoingEvent(
                    category=self.category,
                    occurred_at=record["occurred_at"],
                    payload={
                        "printer": record["printer"],
                        "user": record["user"],
                        "job_id": record["job_id"],
                        "job_name": record["job_name"],
                        "hostname": record["hostname"],
                    },
                )
            )
        return events

    def _read_new_lines(self) -> list[str]:
        if not self._page_log_path.is_file():
            return []
        try:
            with self._page_log_path.open(
                encoding="utf-8", errors="replace"
            ) as log_file:
                log_file.seek(self._offset)
                content = log_file.read()
                self._offset = log_file.tell()
        except OSError:
            return []
        return [line for line in content.splitlines() if line.strip()]
