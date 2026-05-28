from __future__ import annotations

from pathlib import Path

import os


APP_NAME = "Shuffly"
CONFIG_DIR = Path(os.getenv("SHUFFLY_CONFIG_DIR", "/config"))
OUTPUT_DIR = Path("/output")
DATABASE_PATH = CONFIG_DIR / "shuffly.sqlite3"
MARKER_FILE = ".shuffly-owned"

VIDEO_EXTENSIONS = {
    ".avi",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ts",
    ".webm",
    ".wmv",
}
