"""Web-history collector: Chromium-family and Firefox backends.

Unlike the other categories, this one has no per-OS split -- both browsers
store history in a SQLite database of the same shape everywhere they run,
so `ChromiumHistoryCollector`/`FirefoxHistoryCollector` differ by *browser*,
not by platform. Only the default profile-path lookup in `paths.py` is
OS-specific.
"""

from warden_agent.collectors.web.chromium import ChromiumHistoryCollector
from warden_agent.collectors.web.firefox import FirefoxHistoryCollector

__all__ = ["ChromiumHistoryCollector", "FirefoxHistoryCollector"]
