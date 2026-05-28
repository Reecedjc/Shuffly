from __future__ import annotations

import os
import shutil
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import MARKER_FILE, OUTPUT_DIR
from app.models import Episode
from app.util import safe_filename


class GenerationError(RuntimeError):
    pass


def delete_playlist_folder(title: str, output_root: Path = OUTPUT_DIR) -> bool:
    folder = output_root / safe_filename(title, "Shuffly Playlist")
    if not folder.exists():
        return False
    if not (folder / MARKER_FILE).is_file():
        raise GenerationError(
            f"Refusing to delete '{folder}' because it does not contain "
            f"{MARKER_FILE}."
        )
    try:
        shutil.rmtree(folder)
    except OSError as error:
        raise GenerationError(
            f"Could not delete playlist folder '{folder}': {error}"
        ) from error
    return True


def rename_playlist_folder(
    old_title: str,
    new_title: str,
    output_root: Path = OUTPUT_DIR,
) -> bool:
    old_folder = output_root / safe_filename(old_title, "Shuffly Playlist")
    new_folder = output_root / safe_filename(new_title, "Shuffly Playlist")
    if not old_folder.exists():
        return False
    if not (old_folder / MARKER_FILE).is_file():
        raise GenerationError(
            f"Refusing to rename '{old_folder}' because it does not contain "
            f"{MARKER_FILE}."
        )
    if new_folder.exists():
        raise GenerationError(
            f"Refusing to rename to '{new_folder}' because that folder "
            "already exists."
        )
    try:
        old_folder.rename(new_folder)
    except OSError as error:
        raise GenerationError(
            f"Could not rename playlist folder '{old_folder}': {error}"
        ) from error
    return True


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_SUFFIXES = ("", "-thumb", "-landscape")


def generate_playlist_show(
    title: str,
    episodes: list[Episode],
    output_root: Path = OUTPUT_DIR,
    poster_paths: list[Path] | None = None,
    mode_label: str | None = None,
    show_names: list[str] | None = None,
) -> Path:
    if not episodes:
        raise GenerationError("No episodes matched this playlist.")

    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise GenerationError(
            f"Could not create output folder '{output_root}': {error}"
        ) from error
    folder_name = safe_filename(title, "Shuffly Playlist")
    final_dir = output_root / folder_name
    temp_dir = output_root / f".{folder_name}.tmp-{uuid.uuid4().hex}"

    if final_dir.exists() and not (final_dir / MARKER_FILE).is_file():
        raise GenerationError(
            f"Refusing to replace '{final_dir}' because it does not "
            f"contain {MARKER_FILE}."
        )

    try:
        _write_playlist_dir(
            temp_dir,
            title,
            episodes,
            poster_paths=poster_paths,
            mode_label=mode_label,
            show_names=show_names,
        )
        if final_dir.exists():
            shutil.rmtree(final_dir)
        temp_dir.rename(final_dir)
    except OSError as error:
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except OSError:
                pass
        raise GenerationError(f"Could not generate playlist: {error}") from error

    return final_dir


def validate_symlink_access(
    episodes: list[Episode],
    output_root: Path = OUTPUT_DIR,
) -> dict:
    output_root.mkdir(parents=True, exist_ok=True)
    checks = []
    for episode in episodes[:10]:
        checks.append(
            {
                "source": str(episode.path),
                "source_exists": episode.path.exists(),
                "source_absolute": episode.path.is_absolute(),
                "note": (
                    "Jellyfin must be able to resolve this exact target "
                    "path from its own container."
                ),
            }
        )
    return {
        "output_root": str(output_root),
        "output_root_exists": output_root.exists(),
        "strategy": "absolute symlink targets",
        "checks": checks,
    }


def _write_playlist_dir(
    base_dir: Path,
    title: str,
    episodes: list[Episode],
    poster_paths: list[Path] | None = None,
    mode_label: str | None = None,
    show_names: list[str] | None = None,
) -> None:
    season_dir = base_dir / "Season 01"
    season_dir.mkdir(parents=True, exist_ok=False)
    _write_tvshow_nfo(
        base_dir / "tvshow.nfo",
        title,
        mode_label,
        show_names or _unique_show_names(episodes),
    )

    for index, episode in enumerate(episodes, start=1):
        extension = episode.path.suffix
        file_display_title = _episode_file_display_title(episode)
        file_name = safe_filename(
            f"{title} - S01E{index:03d} - {file_display_title}",
            f"{title} - S01E{index:03d}",
        )
        target = season_dir / f"{file_name}{extension}"
        os.symlink(str(episode.path.resolve()), target)
        _link_episode_images(episode.path, target)
        _write_episode_nfo(target.with_suffix(".nfo"), title, episode, index)

    # Composite playlist poster (folder.jpg) — read by Jellyfin as show art
    if poster_paths:
        try:
            from app.poster import build_playlist_poster
            poster_bytes = build_playlist_poster(poster_paths)
            (base_dir / "folder.jpg").write_bytes(poster_bytes)
        except Exception:
            pass  # poster failure must never abort playlist generation

    (base_dir / MARKER_FILE).write_text(
        "Generated by Shuffly. This marker permits safe regeneration.\n",
        encoding="utf-8",
    )


def _write_tvshow_nfo(
    path: Path,
    title: str,
    mode_label: str | None = None,
    show_names: list[str] | None = None,
) -> None:
    root = ET.Element("tvshow")
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "sorttitle").text = title
    ET.SubElement(root, "plot").text = _tvshow_plot(mode_label, show_names)
    _write_xml(path, root)


def _write_episode_nfo(
    path: Path,
    playlist_title: str,
    episode: Episode,
    index: int,
) -> None:
    root = ET.Element("episodedetails")
    ET.SubElement(root, "title").text = _episode_display_title(episode)
    ET.SubElement(root, "showtitle").text = playlist_title
    ET.SubElement(root, "season").text = "1"
    ET.SubElement(root, "episode").text = str(index)
    ET.SubElement(root, "plot").text = episode.plot or ""
    if episode.premiere_date:
        ET.SubElement(root, "aired").text = episode.premiere_date.isoformat()
        ET.SubElement(root, "premiered").text = (
            episode.premiere_date.isoformat()
        )
    _write_xml(path, root)


def _write_xml(path: Path, root: ET.Element) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _tvshow_plot(
    mode_label: str | None,
    show_names: list[str] | None,
) -> str:
    plot = "Generated by Shuffly."
    if mode_label:
        plot = f"{plot} ({mode_label})."
    if show_names:
        plot = f"{plot} Shows include {', '.join(show_names)}."
    return plot


def _unique_show_names(episodes: list[Episode]) -> list[str]:
    names = []
    seen = set()
    for episode in episodes:
        key = episode.show.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(episode.show)
    return names


def _episode_display_title(episode: Episode) -> str:
    code = _original_episode_code(episode)
    return f"{episode.show} - {episode.title} - {code}"


def _episode_file_display_title(episode: Episode) -> str:
    return f"{episode.show} - {episode.title}"


def _original_episode_code(episode: Episode) -> str:
    if episode.season is None or episode.episode is None:
        return "S??E??"
    return f"S{episode.season:02d}E{episode.episode:02d}"


def _link_episode_images(source_video: Path, target_video: Path) -> None:
    for source_image in _episode_image_candidates(source_video):
        target_image = target_video.with_name(
            f"{target_video.stem}{source_image.suffix}"
        )
        if not target_image.exists():
            os.symlink(str(source_image.resolve()), target_image)


def _episode_image_candidates(source_video: Path) -> list[Path]:
    candidates = []
    for suffix in IMAGE_SUFFIXES:
        for extension in IMAGE_EXTENSIONS:
            candidate = source_video.with_name(
                f"{source_video.stem}{suffix}{extension}"
            )
            if candidate.is_file():
                candidates.append(candidate)
    return candidates
