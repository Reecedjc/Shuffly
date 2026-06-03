from datetime import date
from pathlib import Path

from app.models import Episode
from app.ordering import (
    mixed_timeline,
    random_shuffle,
    selected_order,
    show_shuffle_episode_order,
)


def episode(show, season, number, title=None, premiered=None):
    title = title or f"Episode {number}"
    return Episode(
        id=f"{show}-{season}-{number}",
        path=Path(
            f"/media/{show}/Season {season:02d}/"
            f"{show} - S{season:02d}E{number:02d}.mkv"
        ),
        show=show,
        season=season,
        episode=number,
        title=title,
        premiere_date=premiered,
    )


def test_show_shuffle_takes_one_episode_per_show_before_repeating():
    episodes = [
        episode("A", 1, 1),
        episode("A", 1, 2),
        episode("B", 1, 1),
        episode("B", 1, 2),
        episode("C", 1, 1),
        episode("C", 1, 2),
    ]

    result = show_shuffle_episode_order(episodes, 6, seed=42)
    first_round = result[:3]

    assert {item.show for item in first_round} == {"A", "B", "C"}
    assert all(item.episode == 1 for item in first_round)


def test_random_shuffle_uses_seed_and_max_items():
    episodes = [
        episode("A", 1, 1),
        episode("A", 1, 2),
        episode("A", 1, 3),
        episode("A", 1, 4),
    ]

    first = random_shuffle(episodes, 3, seed=7)
    second = random_shuffle(episodes, 3, seed=7)

    assert first == second
    assert first != episodes[:3]
    assert len(first) == 3


def test_show_shuffle_preserves_episode_order_inside_each_show():
    episodes = [
        episode("A", 1, 1),
        episode("A", 1, 2),
        episode("A", 1, 3),
        episode("B", 1, 1),
        episode("B", 1, 2),
        episode("B", 1, 3),
    ]

    result = show_shuffle_episode_order(episodes, 6, seed=1)
    by_show = {
        "A": [item.episode for item in result if item.show == "A"],
        "B": [item.episode for item in result if item.show == "B"],
    }

    assert by_show["A"] == [1, 2, 3]
    assert by_show["B"] == [1, 2, 3]


def test_mixed_timeline_uses_premiere_date_before_fallback_order():
    first = episode("Beta", 1, 1, premiered=date(2020, 1, 1))
    second = episode("Alpha", 1, 1, premiered=date(2020, 1, 2))
    missing = episode("Alpha", 1, 2)

    assert mixed_timeline([missing, second, first], 10) == [
        first,
        second,
        missing,
    ]


def test_selected_order_follows_selected_ids():
    first = episode("A", 1, 1)
    second = episode("B", 1, 1)

    assert selected_order(
        [first, second],
        [second.id, first.id],
        10,
    ) == [second, first]
