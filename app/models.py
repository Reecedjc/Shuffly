from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlencode


@dataclass(frozen=True)
class Episode:
    id: str
    path: Path
    show: str
    season: int | None
    episode: int | None
    title: str
    premiere_date: date | None = None
    plot: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "path": str(self.path),
            "show": self.show,
            "season": self.season,
            "episode": self.episode,
            "title": self.title,
            "premiere_date": (
                self.premiere_date.isoformat()
                if self.premiere_date
                else None
            ),
            "plot": self.plot,
        }


@dataclass(frozen=True)
class Show:
    name: str
    path: Path
    episodes: tuple[Episode, ...]
    poster_path: Path | None = None

    def to_dict(self) -> dict:
        poster_url = None
        if self.poster_path:
            query = urlencode({"path": str(self.poster_path)})
            poster_url = f"/api/image?{query}"

        return {
            "name": self.name,
            "path": str(self.path),
            "episodes": [episode.to_dict() for episode in self.episodes],
            "poster_url": poster_url,
        }
