from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from app.config import VIDEO_EXTENSIONS
from app.models import Episode, Show


POSTER_NAMES = [
    "poster.jpg",
    "poster.png",
    "folder.jpg",
    "folder.png",
    "show.jpg",
    "show.png",
]

LEADING_ARTICLE_PATTERN = re.compile(r"^the\s+", re.IGNORECASE)

EPISODE_PATTERNS = [
    re.compile(r"[Ss](?P<season>\d{1,2})[ ._-]*[Ee](?P<episode>\d{1,3})"),
    re.compile(
        r"(?<!\d)(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?!\d)",
        re.IGNORECASE,
    ),
]

QUALITY_TAG_PATTERN = re.compile(
    r"""
    (?:^|[\s._-])
    (
        480p|576p|720p|1080p|2160p|4k|8k|
        web[-_. ]?dl|webrip|web|bluray|blu[-_. ]?ray|bdrip|brrip|
        hdtv|dvdrip|remux|proper|repack|extended|internal|
        x264|x265|h\.?264|h\.?265|hevc|av1|10bit|hdr|dv|dolby[-_. ]?vision|
        aac|ac3|eac3|dts|truehd|atmos|ddp?5\.1|ddp?7\.1
    )
    (?=$|[\s._-])
    """,
    re.IGNORECASE | re.VERBOSE,
)


def scan_media_roots(roots: list[Path]) -> list[Show]:
    shows: dict[Path, list[Episode]] = {}
    for root in roots:
        if not root.exists():
            continue
        for file_path in root.rglob("*"):
            if (
                not file_path.is_file()
                or file_path.suffix.lower() not in VIDEO_EXTENSIONS
            ):
                continue
            show_path = _show_path(root, file_path)
            episode = _episode_from_path(root, show_path, file_path)
            shows.setdefault(show_path, []).append(episode)

    output = [
        Show(
            name=path.name,
            path=path,
            episodes=tuple(sorted(episodes, key=lambda item: (
                item.season if item.season is not None else 9999,
                item.episode if item.episode is not None else 9999,
                item.title.lower(),
            ))),
            poster_path=_find_poster(path),
        )
        for path, episodes in shows.items()
    ]
    return sorted(output, key=lambda show: _show_sort_key(show.name))


def _show_path(root: Path, file_path: Path) -> Path:
    relative = file_path.relative_to(root)
    if len(relative.parts) >= 2:
        return root / relative.parts[0]
    return file_path.parent


def _episode_from_path(
    root: Path,
    show_path: Path,
    file_path: Path,
) -> Episode:
    season, episode = _parse_season_episode(file_path.name)
    title = _parse_title(file_path.stem, show_path.name)
    premiere_date, plot = _read_episode_metadata(file_path.with_suffix(".nfo"))
    episode_id = hashlib.sha1(
        str(file_path.resolve()).encode("utf-8")
    ).hexdigest()
    return Episode(
        id=episode_id,
        path=file_path,
        show=show_path.name,
        season=season,
        episode=episode,
        title=title,
        premiere_date=premiere_date,
        plot=plot,
    )


def _parse_season_episode(name: str) -> tuple[int | None, int | None]:
    for pattern in EPISODE_PATTERNS:
        match = pattern.search(name)
        if match:
            return int(match.group("season")), int(match.group("episode"))
    return None, None


def _parse_title(stem: str, show_name: str) -> str:
    value = re.sub(
        re.escape(show_name),
        "",
        stem,
        flags=re.IGNORECASE,
    ).strip(" ._-")
    value = re.sub(r"[Ss]\d{1,2}[ ._-]*[Ee]\d{1,3}", "", value).strip(" ._-")
    value = re.sub(
        r"(?<!\d)\d{1,2}x\d{1,3}(?!\d)",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip(" ._-")
    value = _strip_quality_tags(value)
    value = re.sub(r"[._]+", " ", value).strip()
    return value or stem


def _strip_quality_tags(value: str) -> str:
    previous = None
    while previous != value:
        previous = value
        value = QUALITY_TAG_PATTERN.sub(" ", value)
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    return value.strip(" ._-")


def _find_poster(show_dir: Path) -> Path | None:
    for name in POSTER_NAMES:
        candidate = show_dir / name
        if candidate.is_file():
            return candidate
    return None


def _show_sort_key(name: str) -> str:
    return LEADING_ARTICLE_PATTERN.sub("", name).lower()


def _read_episode_metadata(nfo_path: Path) -> tuple[date | None, str | None]:
    if not nfo_path.exists():
        return None, None
    try:
        root = ET.parse(nfo_path).getroot()
    except ET.ParseError:
        return None, None
    plot = _read_episode_plot(root)
    for tag in ("premiered", "aired"):
        value = root.findtext(tag)
        if not value:
            continue
        try:
            return date.fromisoformat(value[:10]), plot
        except ValueError:
            continue
    return None, plot


def _read_episode_plot(root: ET.Element) -> str | None:
    for tag in ("plot", "outline", "overview"):
        value = root.findtext(tag)
        if value and value.strip():
            return value.strip()
    return None
