"""Shared test configuration."""

import os

# Qt has no display on a CI runner; the window tests run on its offscreen
# platform. Set before anything imports PySide6, and only when the environment
# has not chosen a platform itself.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
