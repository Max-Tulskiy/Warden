"""Pure parsing of a CUPS `page_log` line.

Kept separate from the file-tailing collector so the actual format
knowledge is unit-tested against fixture lines on any platform, not only
where a real CUPS installation is writing them (constitution principle 7).

CUPS logs one line per *page*, in the order: printer, user, job-id,
`[date/time]`, page-number, num-copies, billing, hostname, job-name, media,
sides. The date/time field has an internal space (`13:55:36 +0000`) between
the bracket, and job-name can itself contain spaces, so this cannot be a
plain `str.split()` -- the bracketed timestamp is extracted first, and
job-name is whatever sits between the fixed-position fields before it and
the two fixed-position fields (media, sides) after it.
"""

import re
from datetime import datetime
from typing import TypedDict

_LINE_PATTERN = re.compile(r"^(\S+) (\S+) (\S+) \[([^\]]+)\] (.+)$")
_TIMESTAMP_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

#: page, num-copies, billing, hostname before job-name; media, sides after it.
_FIELDS_BEFORE_JOB_NAME = 4
_FIELDS_AFTER_JOB_NAME = 2


class PrintRecord(TypedDict):
    printer: str
    user: str
    job_id: str
    occurred_at: datetime
    hostname: str
    job_name: str


def parse_page_log_line(line: str) -> PrintRecord | None:
    match = _LINE_PATTERN.match(line.strip())
    if match is None:
        return None
    printer, user, job_id, timestamp_text, remainder = match.groups()

    try:
        occurred_at = datetime.strptime(timestamp_text, _TIMESTAMP_FORMAT)
    except ValueError:
        return None

    tokens = remainder.split()
    minimum_tokens = _FIELDS_BEFORE_JOB_NAME + _FIELDS_AFTER_JOB_NAME
    if len(tokens) < minimum_tokens:
        return None
    hostname = tokens[3]
    job_name = " ".join(tokens[_FIELDS_BEFORE_JOB_NAME:-_FIELDS_AFTER_JOB_NAME])

    return PrintRecord(
        printer=printer,
        user=user,
        job_id=job_id,
        occurred_at=occurred_at,
        hostname=hostname,
        job_name=job_name or "-",
    )
