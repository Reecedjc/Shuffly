from __future__ import annotations

import random
from collections import defaultdict, deque
from collections.abc import Iterable

from app.models import Episode


def random_shuffle(
    episodes: Iterable[Episode],
    max_items: int,
    seed: int | None = None,
) -> list[Episode]:
    output = list(episodes)
    random.Random(seed).shuffle(output)
    return output[:max_items]


def show_shuffle_episode_order(
    episodes: Iterable[Episode],
    max_items: int,
    seed: int | None = None,
) -> list[Episode]:
    grouped: dict[str, list[Episode]] = defaultdict(list)
    for episode in episodes:
        grouped[episode.show].append(episode)

    queues = [
        deque(sorted(items, key=_episode_order_key))
        for items in grouped.values()
        if items
    ]
    rng = random.Random(seed)
    output: list[Episode] = []

    while queues and len(output) < max_items:
        rng.shuffle(queues)
        for index in range(len(queues) - 1, -1, -1):
            queue = queues[index]
            output.append(queue.popleft())
            if not queue:
                del queues[index]
            if len(output) >= max_items:
                break

    return output


def mixed_timeline(
    episodes: Iterable[Episode],
    max_items: int,
) -> list[Episode]:
    return sorted(episodes, key=_timeline_key)[:max_items]


def selected_order(
    episodes: Iterable[Episode],
    selected_ids: list[str],
    max_items: int,
) -> list[Episode]:
    by_id = {episode.id: episode for episode in episodes}
    ordered = [
        by_id[episode_id]
        for episode_id in selected_ids
        if episode_id in by_id
    ]
    return ordered[:max_items]


def _episode_order_key(episode: Episode) -> tuple:
    return (
        episode.season if episode.season is not None else 9999,
        episode.episode if episode.episode is not None else 9999,
        episode.title.lower(),
        str(episode.path).lower(),
    )


def _timeline_key(episode: Episode) -> tuple:
    return (
        0 if episode.premiere_date else 1,
        (
            episode.premiere_date.isoformat()
            if episode.premiere_date
            else "9999-12-31"
        ),
        episode.show.lower(),
        episode.season if episode.season is not None else 9999,
        episode.episode if episode.episode is not None else 9999,
        episode.title.lower(),
    )
