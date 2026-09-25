"""Writing a file so a reader never sees half of it."""

import os
import shutil
from pathlib import Path


def write_atomically(path: Path, text: str, *, mode: int | None = None) -> None:
    """Replace `path` with `text` in one step, or leave it exactly as it was.

    The text goes to a temporary file beside `path` and is moved over it. With
    `mode` the new file gets those permission bits; otherwise it keeps those of
    the file it replaces, if there is one.
    """
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        if mode is not None:
            temporary.chmod(mode)
        elif path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
