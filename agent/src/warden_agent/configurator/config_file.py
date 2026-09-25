"""Reading and rewriting the agent's configuration file.

The file is small and flat, and an administrator may have edited it by hand,
so a rewrite keeps every key that was set. `tomllib` reads but cannot write and
cannot keep comments, so the file is regenerated from a short template with
its own comments. A table or a list, which a rewrite could not keep faithfully,
is refused rather than silently lost.
"""

import json
import tomllib
from pathlib import Path
from typing import Any

from warden_agent.fileio import write_atomically

#: The order the known keys are written in, each with the comment above it.
_KNOWN: dict[str, str] = {
    "server_url": "Address of the Warden server.",
    "ca_file": (
        "A certificate authority the agent trusts in addition to the system's own\n"
        "# store: the authority of a server that issues its own certificate."
    ),
    "hostname": "Defaults to the OS hostname if left unset.",
    "poll_interval_seconds": "How often the agent asks the server for tasks.",
    "inventory_interval_seconds": "How often the agent sends an inventory snapshot.",
    "retention_hours": (
        "Must be at least 4 (the request-window cap, constitution principle 3/4)."
    ),
    "buffer_path": "The local event buffer.",
    "state_path": "The agent's id and key, written by the agent itself.",
}

_HEADER = (
    "# Warden agent configuration. Rewritten by the connection window, which keeps\n"
    "# every key set here. The enrollment token is never written to this file.\n"
)

#: Never written by this module: a live one-time secret does not belong on disk.
_NEVER_WRITTEN = frozenset({"enrollment_token"})


class UnsupportedConfigError(ValueError):
    """The configuration holds something a rewrite could not keep faithfully."""


def read_config(path: Path) -> dict[str, Any]:
    """The file's keys as written; an absent file is an empty configuration."""
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def check_writable(values: dict[str, Any]) -> None:
    """Raise `UnsupportedConfigError` if `write_config` would refuse `values`.

    Lets a caller find out before it does something it cannot take back, such
    as spending a one-time token.
    """
    for key, value in values.items():
        if key not in _NEVER_WRITTEN:
            _toml_value(key, value)


def write_config(path: Path, values: dict[str, Any]) -> None:
    """Replace the file with `values`, atomically, or leave it as it was."""
    lines = [_HEADER]
    unknown = [key for key in values if key not in _KNOWN]
    for key in [*_KNOWN, *unknown]:
        if key not in values or key in _NEVER_WRITTEN:
            continue
        comment = _KNOWN.get(key)
        if comment:
            lines.append(f"\n# {comment}\n")
        else:
            lines.append("\n")
        lines.append(f"{key} = {_toml_value(key, values[key])}\n")
    write_atomically(path, "".join(lines))


def _toml_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        return _toml_string(value)
    raise UnsupportedConfigError(
        f"{key} is a {type(value).__name__}; the file holds only plain values "
        "and a rewrite would lose it, so edit the file by hand"
    )


def _toml_string(text: str) -> str:
    # A backslash-heavy value (a Windows path) reads best as a literal string,
    # which needs no escaping; anything else falls back to a basic string.
    if "\\" in text and not any(c in text for c in "'\n\r\x7f"):
        return f"'{text}'"
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")
