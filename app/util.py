from __future__ import annotations

import re
from pathlib import Path


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")


def safe_filename(value: str, fallback: str = "Untitled") -> str:
    cleaned = INVALID_FILENAME_CHARS.sub(" ", value).strip()
    cleaned = WHITESPACE.sub(" ", cleaned)
    cleaned = cleaned.rstrip(". ")
    return cleaned or fallback


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
