from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH


class DuplicateFolderError(ValueError):
    pass


class DuplicatePlaylistError(ValueError):
    pass


class PlaylistImportError(ValueError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL,
    selected_show_paths TEXT NOT NULL,
    selected_episode_ids TEXT NOT NULL,
    max_items INTEGER NOT NULL DEFAULT 100,
    seed INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_generated_at TEXT
);

CREATE TABLE IF NOT EXISTS media_folders (
    path TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS output_folders (
    path TEXT PRIMARY KEY,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db(path: Path = DATABASE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        _ensure_column(connection, "playlists", "output_folder", "TEXT")


def list_playlists(path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM playlists ORDER BY title COLLATE NOCASE"
        ).fetchall()
    return [_decode(dict(row)) for row in rows]


def get_playlist(
    playlist_id: int,
    path: Path = DATABASE_PATH,
) -> dict[str, Any] | None:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM playlists WHERE id = ?",
            (playlist_id,),
        ).fetchone()
    return _decode(dict(row)) if row else None


def upsert_playlist(
    payload: dict[str, Any],
    path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    title = payload["title"].strip()
    playlist_id = int(payload["id"]) if payload.get("id") else None
    selected_show_paths = json.dumps(payload.get("selected_show_paths", []))
    selected_episode_ids = json.dumps(payload.get("selected_episode_ids", []))
    values = (
        title,
        payload["mode"],
        selected_show_paths,
        selected_episode_ids,
        int(payload.get("max_items") or 100),
        payload.get("seed"),
        payload.get("output_folder"),
    )
    with sqlite3.connect(path) as connection:
        _ensure_unique_playlist_title(connection, title, playlist_id)
        try:
            if playlist_id is not None:
                connection.execute(
                    """
                    UPDATE playlists
                    SET title = ?, mode = ?,
                        selected_show_paths = ?,
                        selected_episode_ids = ?,
                        max_items = ?, seed = ?,
                        output_folder = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (*values, playlist_id),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO playlists (
                        title, mode, selected_show_paths, selected_episode_ids,
                        max_items, seed, output_folder
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                playlist_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as error:
            raise DuplicatePlaylistError(
                f"Playlist title is already used: {title}"
            ) from error
    playlist = get_playlist(playlist_id, path)
    if playlist is None:
        raise ValueError("Playlist was not saved")
    return playlist


def mark_generated(playlist_id: int, path: Path = DATABASE_PATH) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE playlists
            SET last_generated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (playlist_id,),
        )


def delete_playlist(playlist_id: int, path: Path = DATABASE_PATH) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "DELETE FROM playlists WHERE id = ?",
            (playlist_id,),
        )


def replace_all_playlists(
    playlists: list[dict[str, Any]],
    path: Path = DATABASE_PATH,
) -> None:
    normalized = [_normalize_import_playlist(item) for item in playlists]
    seen_titles: set[str] = set()
    for playlist in normalized:
        key = playlist["title"].casefold()
        if key in seen_titles:
            raise DuplicatePlaylistError(
                f"Playlist title is duplicated in import: {playlist['title']}"
            )
        seen_titles.add(key)

    with sqlite3.connect(path) as connection:
        try:
            connection.execute("DELETE FROM playlists")
            for playlist in normalized:
                _insert_playlist(connection, playlist)
        except sqlite3.IntegrityError as error:
            raise DuplicatePlaylistError(
                "Imported playlists contain duplicate titles."
            ) from error


def _insert_playlist(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO playlists (
            title, mode, selected_show_paths, selected_episode_ids,
            max_items, seed, output_folder
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["title"],
            payload["mode"],
            json.dumps(payload["selected_show_paths"]),
            json.dumps(payload["selected_episode_ids"]),
            payload["max_items"],
            payload["seed"],
            payload["output_folder"],
        ),
    )


def _ensure_unique_playlist_title(
    connection: sqlite3.Connection,
    title: str,
    playlist_id: int | None = None,
) -> None:
    row = connection.execute(
        """
        SELECT id FROM playlists
        WHERE title = ? COLLATE NOCASE
        """,
        (title,),
    ).fetchone()
    if row and (playlist_id is None or int(row[0]) != playlist_id):
        raise DuplicatePlaylistError(
            f"Playlist title is already used: {title}"
        )


def _normalize_import_playlist(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PlaylistImportError("Each imported playlist must be an object.")

    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        raise PlaylistImportError("Each imported playlist needs a title.")

    mode = item.get("mode")
    if mode not in {"show_shuffle", "selected_order", "mixed_timeline"}:
        raise PlaylistImportError(f"Unknown playlist mode: {mode}")

    selected_show_paths = _string_list(
        item.get("selected_show_paths", []),
        "selected_show_paths",
    )
    selected_episode_ids = _string_list(
        item.get("selected_episode_ids", []),
        "selected_episode_ids",
    )
    max_items = _max_items(item.get("max_items", 5000))
    seed = item.get("seed")
    if seed is not None and not isinstance(seed, int):
        raise PlaylistImportError("Playlist seed must be an integer or null.")
    output_folder = item.get("output_folder")
    if output_folder is not None and not isinstance(output_folder, str):
        raise PlaylistImportError(
            "Playlist output_folder must be a string or null."
        )

    return {
        "title": title.strip(),
        "mode": mode,
        "selected_show_paths": selected_show_paths,
        "selected_episode_ids": selected_episode_ids,
        "max_items": max_items,
        "seed": seed,
        "output_folder": output_folder,
    }


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise PlaylistImportError(f"Playlist {field} must be a list of strings.")
    return value


def _max_items(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PlaylistImportError("Playlist max_items must be an integer.")
    if value < 1 or value > 5000:
        raise PlaylistImportError(
            "Playlist max_items must be between 1 and 5000."
        )
    return value


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    row["selected_show_paths"] = json.loads(row["selected_show_paths"])
    row["selected_episode_ids"] = json.loads(row["selected_episode_ids"])
    return row


def get_settings(path: Path = DATABASE_PATH) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        media = connection.execute(
            "SELECT path FROM media_folders ORDER BY path COLLATE NOCASE"
        ).fetchall()
        outputs = connection.execute(
            """
            SELECT path, is_default
            FROM output_folders
            ORDER BY rowid
            """
        ).fetchall()
    return {
        "media_folders": [row["path"] for row in media],
        "output_folders": [
            {"path": row["path"], "is_default": bool(row["is_default"])}
            for row in outputs
        ],
    }


def list_media_folders(path: Path = DATABASE_PATH) -> list[Path]:
    return [Path(item) for item in get_settings(path)["media_folders"]]


def list_output_folders(path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    return get_settings(path)["output_folders"]


def get_default_output_folder(path: Path = DATABASE_PATH) -> Path | None:
    for item in list_output_folders(path):
        if item["is_default"]:
            return Path(item["path"])
    outputs = list_output_folders(path)
    return Path(outputs[0]["path"]) if outputs else None


def add_media_folder(folder: Path, path: Path = DATABASE_PATH) -> None:
    with sqlite3.connect(path) as connection:
        try:
            connection.execute(
                "INSERT INTO media_folders (path) VALUES (?)",
                (str(folder),),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateFolderError(
                f"Media folder is already configured: {folder}"
            ) from error


def remove_media_folder(folder: Path, path: Path = DATABASE_PATH) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "DELETE FROM media_folders WHERE path = ?",
            (str(folder),),
        )


def add_output_folder(folder: Path, path: Path = DATABASE_PATH) -> None:
    with sqlite3.connect(path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM output_folders"
        ).fetchone()[0]
        try:
            connection.execute(
                """
                INSERT INTO output_folders (path, is_default)
                VALUES (?, ?)
                """,
                (str(folder), 1 if count == 0 else 0),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateFolderError(
                f"Output folder is already configured: {folder}"
            ) from error


def remove_output_folder(folder: Path, path: Path = DATABASE_PATH) -> None:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT is_default FROM output_folders WHERE path = ?",
            (str(folder),),
        ).fetchone()
        if not row:
            return
        if row[0]:
            raise ValueError(
                "Make another output folder default before removing this one."
            )
        connection.execute(
            "DELETE FROM output_folders WHERE path = ?",
            (str(folder),),
        )


def set_default_output_folder(
    folder: Path,
    path: Path = DATABASE_PATH,
) -> None:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT path FROM output_folders WHERE path = ?",
            (str(folder),),
        ).fetchone()
        if not row:
            raise ValueError("Output folder is not configured.")
        connection.execute("UPDATE output_folders SET is_default = 0")
        connection.execute(
            "UPDATE output_folders SET is_default = 1 WHERE path = ?",
            (str(folder),),
        )


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    existing = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if column not in existing:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )
