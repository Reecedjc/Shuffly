from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.generator import (
    GenerationError,
    delete_playlist_folder,
    generate_playlist_show,
    rename_playlist_folder,
    validate_symlink_access,
)
from app.config import APP_NAME, CONFIG_DIR
from app.models import Episode
from app.ordering import (
    mixed_timeline,
    selected_order,
    show_shuffle_episode_order,
)
from app.scanner import scan_media_roots
from app.storage import (
    DuplicateFolderError,
    DuplicatePlaylistError,
    PlaylistImportError,
    add_media_folder,
    add_output_folder,
    delete_playlist,
    get_default_output_folder,
    get_playlist,
    get_settings,
    init_db,
    list_media_folders,
    list_playlists,
    remove_media_folder,
    remove_output_folder,
    mark_generated,
    replace_all_playlists,
    set_default_output_folder,
    upsert_playlist,
)
from app.util import safe_filename


class PlaylistPayload(BaseModel):
    id: int | None = None
    title: str = Field(min_length=1)
    mode: str
    selected_show_paths: list[str] = []
    selected_episode_ids: list[str] = []
    max_items: int = Field(default=5000, ge=1, le=5000)
    seed: int | None = None
    output_folder: str | None = None


class FolderPayload(BaseModel):
    path: str = Field(min_length=1)


SYSTEM_BROWSER_PATHS = {
    "/app",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/home",
    "/lib",
    "/lib64",
    "/opt",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/srv",
    "/sys",
    "/tmp",
    "/usr",
    "/var",
}

MODE_LABELS = {
    "show_shuffle": "Shuffled in Order",
    "selected_order": "Manually Ordered",
    "mixed_timeline": "Sorted by Release Date",
}

app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return Path("static/index.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "app": APP_NAME,
        "config_dir": str(CONFIG_DIR),
        "symlink_strategy": "absolute",
    }


@app.get("/api/settings")
def settings() -> dict[str, Any]:
    data = get_settings()
    default_output = get_default_output_folder()
    return {
        **data,
        "default_output_folder": (
            str(default_output) if default_output else None
        ),
        "config_folder": str(CONFIG_DIR),
    }


@app.post("/api/settings/media-folders")
def add_media_folder_endpoint(payload: FolderPayload) -> dict[str, Any]:
    folder = _validated_folder(payload.path, purpose="media")
    try:
        add_media_folder(folder)
    except DuplicateFolderError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return settings()


@app.delete("/api/settings/media-folders")
def remove_media_folder_endpoint(payload: FolderPayload) -> dict[str, Any]:
    remove_media_folder(Path(payload.path))
    return settings()


@app.post("/api/settings/output-folders")
def add_output_folder_endpoint(payload: FolderPayload) -> dict[str, Any]:
    folder = _validated_folder(payload.path, purpose="output")
    try:
        add_output_folder(folder)
    except DuplicateFolderError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return settings()


@app.delete("/api/settings/output-folders")
def remove_output_folder_endpoint(payload: FolderPayload) -> dict[str, Any]:
    try:
        remove_output_folder(Path(payload.path))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return settings()


@app.post("/api/settings/output-folders/default")
def set_default_output_folder_endpoint(
    payload: FolderPayload,
) -> dict[str, Any]:
    try:
        set_default_output_folder(Path(payload.path))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return settings()


@app.get("/api/browse")
def browse(path: str = Query("/")) -> dict[str, Any]:
    current = Path(path).resolve()
    if not current.exists() or not current.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found.")
    if current != Path("/") and not _is_browsable_path(current):
        raise HTTPException(status_code=403, detail="Access denied.")
    try:
        children = _browser_children(current)
    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        ) from error
    root_view = current == Path("/")
    directories = []
    for child in children:
        directories.append({
            "name": str(child) if root_view else child.name,
            "path": str(child),
        })
    parent = _browser_parent(current)
    return {
        "path": str(current),
        "parent": str(parent) if parent else None,
        "directories": directories,
    }


@app.get("/api/image")
def serve_image(path: str = Query(...)) -> FileResponse:
    resolved = Path(path).resolve()
    if not _is_allowed_media_path(resolved):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(resolved)


@app.get("/api/scan")
def scan() -> dict[str, Any]:
    shows = scan_media_roots(list_media_folders())
    return {"shows": [show.to_dict() for show in shows]}


@app.get("/api/playlists")
def playlists() -> dict[str, Any]:
    pls = list_playlists()
    cfg = get_settings()
    default_out = get_default_output_folder()
    for pl in pls:
        pl["poster_url"] = _playlist_poster_url(pl, cfg, default_out)
    return {"playlists": pls}


@app.post("/api/playlists")
def save_playlist(payload: PlaylistPayload) -> dict[str, Any]:
    valid_modes = {"show_shuffle", "selected_order", "mixed_timeline"}
    if payload.mode not in valid_modes:
        raise HTTPException(status_code=400, detail="Unknown playlist mode.")
    output_folder = _resolve_output_folder(payload.output_folder)
    old = get_playlist(payload.id) if payload.id else None
    if old and old["title"] != payload.title:
        try:
            rename_playlist_folder(
                old["title"],
                payload.title,
                _playlist_output_folder(old),
            )
        except GenerationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    data = payload.model_dump()
    data["output_folder"] = str(output_folder) if output_folder else None
    try:
        playlist = upsert_playlist(data)
    except DuplicatePlaylistError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"playlist": playlist}


@app.post("/api/playlists/{playlist_id}/generate")
def generate(playlist_id: int) -> dict[str, Any]:
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")
    episodes, poster_paths = _episodes_and_poster_paths(playlist)
    output_folder = _playlist_output_folder(playlist)
    try:
        ordered = _order_episodes(playlist, episodes)
        output_path = generate_playlist_show(
            playlist["title"],
            ordered,
            output_folder,
            poster_paths=poster_paths,
            mode_label=MODE_LABELS.get(playlist["mode"]),
            show_names=_playlist_show_names(episodes),
        )
    except GenerationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=409,
            detail=f"Could not generate playlist: {error}",
        ) from error
    mark_generated(playlist_id)
    return {
        "output_path": str(output_path),
        "episode_count": len(ordered),
        "validation": validate_symlink_access(ordered, output_folder),
    }


@app.get("/api/playlists/{playlist_id}/poster")
def playlist_poster(playlist_id: int) -> FileResponse:
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")
    output_folder = _playlist_poster_output_folder(playlist)
    if output_folder is None:
        raise HTTPException(status_code=404, detail="Poster not found.")
    poster = (
        output_folder
        / safe_filename(playlist["title"], "Shuffly Playlist")
        / "folder.jpg"
    )
    if not poster.is_file():
        raise HTTPException(status_code=404, detail="Poster not found.")
    if not _is_allowed_output_path(poster):
        raise HTTPException(status_code=403, detail="Access denied.")
    return FileResponse(poster, media_type="image/jpeg")


@app.get("/api/playlists/{playlist_id}/validate")
def validate(playlist_id: int) -> dict[str, Any]:
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")
    ordered = _order_episodes(playlist, _episodes_for_playlist(playlist))
    return validate_symlink_access(ordered, _playlist_output_folder(playlist))


@app.delete("/api/playlists/{playlist_id}")
def delete_playlist_endpoint(playlist_id: int) -> dict[str, Any]:
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found.")
    try:
        delete_playlist_folder(
            playlist["title"],
            _playlist_output_folder(playlist),
        )
    except GenerationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    delete_playlist(playlist_id)
    return {"deleted": playlist_id}


@app.get("/api/export")
def export_playlists() -> dict[str, Any]:
    return {"version": 1, "playlists": list_playlists()}


@app.post("/api/import")
def import_playlists(payload: dict[str, Any]) -> dict[str, Any]:
    playlists = payload.get("playlists")
    if not isinstance(playlists, list):
        raise HTTPException(
            status_code=400,
            detail="Import payload must contain a playlists array.",
        )
    try:
        replace_all_playlists(playlists)
    except DuplicatePlaylistError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PlaylistImportError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"playlists": list_playlists()}


def _episodes_for_playlist(playlist: dict[str, Any]) -> list[Episode]:
    episodes, _ = _episodes_and_poster_paths(playlist)
    return episodes


def _episodes_and_poster_paths(
    playlist: dict[str, Any],
) -> tuple[list[Episode], list[Path]]:
    """Return (episodes, show_poster_paths) for the given playlist.

    Scans the media library once; collects poster paths for shows that
    contribute episodes to the playlist (alphabetical order, up to 4).
    """
    selected_show_paths = set(playlist["selected_show_paths"])
    selected_episode_ids = set(playlist["selected_episode_ids"])
    shows = scan_media_roots(list_media_folders())
    episodes: list[Episode] = []
    poster_paths: list[Path] = []
    for show in shows:
        include_show = str(show.path) in selected_show_paths
        has_selected_episode = any(
            episode.id in selected_episode_ids for episode in show.episodes
        )
        if include_show or has_selected_episode:
            episodes.extend(show.episodes)
            if show.poster_path and len(poster_paths) < 4:
                poster_paths.append(show.poster_path)
    if selected_episode_ids:
        episodes = [
            episode
            for episode in episodes
            if episode.id in selected_episode_ids
        ]
    return episodes, poster_paths


def _order_episodes(
    playlist: dict[str, Any],
    episodes: list[Episode],
) -> list[Episode]:
    max_items = int(playlist["max_items"])
    mode = playlist["mode"]
    if mode == "show_shuffle":
        return show_shuffle_episode_order(
            episodes,
            max_items,
            playlist.get("seed"),
        )
    if mode == "mixed_timeline":
        return mixed_timeline(episodes, max_items)
    if mode == "selected_order":
        selected_ids = playlist["selected_episode_ids"] or [
            episode.id for episode in episodes
        ]
        return selected_order(episodes, selected_ids, max_items)
    raise HTTPException(status_code=400, detail="Unknown playlist mode.")


def _playlist_show_names(episodes: list[Episode]) -> list[str]:
    names = []
    seen = set()
    for episode in episodes:
        key = episode.show.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(episode.show)
    return names


def _playlist_poster_url(
    playlist: dict[str, Any],
    cfg: dict[str, Any] | None = None,
    default_out: Path | None = None,
) -> str | None:
    """Return the poster API URL if folder.jpg exists for this playlist."""
    try:
        if cfg is None:
            cfg = get_settings()
        if default_out is None:
            default_out = get_default_output_folder()
        configured = {item["path"] for item in cfg["output_folders"]}
        output_folder = _playlist_poster_output_folder(
            playlist,
            configured,
            default_out,
        )
        if output_folder is None:
            return None
        poster = (
            output_folder
            / safe_filename(playlist["title"], "Shuffly Playlist")
            / "folder.jpg"
        )
        if poster.is_file():
            return f"/api/playlists/{playlist['id']}/poster"
        return None
    except Exception:
        return None


def _playlist_poster_output_folder(
    playlist: dict[str, Any],
    configured: set[str] | None = None,
    default_out: Path | None = None,
) -> Path | None:
    if configured is None:
        configured = {
            item["path"]
            for item in get_settings()["output_folders"]
        }
    out_str = playlist.get("output_folder")
    if out_str:
        return Path(out_str) if out_str in configured else None
    if default_out is None:
        default_out = get_default_output_folder()
    return default_out


def _is_allowed_output_path(path: Path) -> bool:
    for item in get_settings()["output_folders"]:
        try:
            path.resolve().relative_to(Path(item["path"]).resolve())
            return True
        except ValueError:
            continue
    return False


def _is_allowed_media_path(path: Path) -> bool:
    for root in list_media_folders():
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        return True
    return False


def _is_browsable_path(path: Path) -> bool:
    for root in _browser_root_children():
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        return True
    return False


def _playlist_output_folder(playlist: dict[str, Any]) -> Path:
    return _resolve_output_folder(playlist.get("output_folder"))


def _resolve_output_folder(value: str | None) -> Path:
    configured = {item["path"] for item in get_settings()["output_folders"]}
    if value and value in configured:
        return Path(value)
    default = get_default_output_folder()
    if default:
        return default
    raise HTTPException(
        status_code=409,
        detail="No output folder is configured.",
    )


def _validated_folder(value: str, purpose: str) -> Path:
    folder = Path(value)
    if not folder.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="Folder path must be absolute.",
        )
    try:
        resolved = folder.resolve(strict=True)
    except OSError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Folder does not exist: {folder}",
        ) from error
    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Folder is not a directory: {resolved}",
        )
    if _is_system_config_folder(resolved):
        raise HTTPException(
            status_code=400,
            detail=f"System folder is not configurable: {resolved}",
        )
    if purpose == "media" and not _has_folder_access(resolved, read=True):
        raise HTTPException(
            status_code=400,
            detail=f"Media folder is not readable: {resolved}",
        )
    if purpose == "output" and not _has_folder_access(resolved, write=True):
        raise HTTPException(
            status_code=400,
            detail=f"Output folder is not writable: {resolved}",
        )
    return resolved


def _has_folder_access(
    folder: Path,
    read: bool = False,
    write: bool = False,
) -> bool:
    mode = 0
    if read:
        mode |= os.R_OK
    if write:
        mode |= os.W_OK
    mode |= os.X_OK
    return folder.exists() and folder.is_dir() and os.access(folder, mode)


def _is_system_config_folder(path: Path) -> bool:
    if path == Path("/") or path in {
        Path(blocked) for blocked in SYSTEM_BROWSER_PATHS
    }:
        return True
    try:
        path.relative_to(CONFIG_DIR.resolve())
    except ValueError:
        return False
    return True


def _browser_children(current: Path) -> list[Path]:
    if current == Path("/"):
        return _browser_root_children()
    return sorted(
        (item for item in current.iterdir() if item.is_dir()),
        key=lambda item: item.name.lower(),
    )


def _browser_parent(current: Path) -> Path | None:
    if current == Path("/"):
        return None
    parent = current.parent
    if parent == current:
        return None
    if _is_browsable_path(parent):
        return parent
    return Path("/")


def _browser_root_children() -> list[Path]:
    candidates = {
        Path(item)
        for item in _mounted_browser_paths()
        if not _is_system_browser_path(Path(item))
    }
    return sorted(
        (item for item in candidates if item.exists() and item.is_dir()),
        key=lambda item: item.name.lower(),
    )


def _is_system_browser_path(path: Path) -> bool:
    if path == Path("/"):
        return True
    for blocked in SYSTEM_BROWSER_PATHS:
        blocked_path = Path(blocked)
        try:
            path.relative_to(blocked_path)
        except ValueError:
            continue
        return True
    return False


def _mounted_browser_paths() -> list[str]:
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return []
    mounts: list[str] = []
    try:
        lines = mountinfo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        fields = line.split()
        if len(fields) < 5:
            continue
        mount_point = fields[4].replace("\\040", " ")
        path = Path(mount_point)
        if not _is_system_browser_path(path):
            mounts.append(str(path))
    return mounts
