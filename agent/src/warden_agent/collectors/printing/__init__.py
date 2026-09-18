"""Print-job collector.

The platform backend is chosen at runtime.
"""

from warden_agent.collectors.printing.linux import LinuxPrintingCollector
from warden_agent.collectors.printing.windows import WindowsPrintingCollector

__all__ = ["LinuxPrintingCollector", "WindowsPrintingCollector"]
