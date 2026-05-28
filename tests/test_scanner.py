from app.scanner import scan_media_roots


def test_scan_media_roots_parses_jellyfin_style_show_layout(tmp_path):
    episode = (
        tmp_path
        / "Show A"
        / "Season 01"
        / "Show A - S01E02 - The Second.mkv"
    )
    episode.parent.mkdir(parents=True)
    episode.write_text("media", encoding="utf-8")

    shows = scan_media_roots([tmp_path])

    assert len(shows) == 1
    assert shows[0].name == "Show A"
    assert shows[0].episodes[0].season == 1
    assert shows[0].episodes[0].episode == 2
    assert shows[0].episodes[0].title == "The Second"


def test_scan_media_roots_strips_quality_from_episode_title(tmp_path):
    episode = (
        tmp_path
        / "Show A"
        / "Season 01"
        / "Show A - S01E02 - The Second 1080p WEB-DL x265 AAC.mkv"
    )
    episode.parent.mkdir(parents=True)
    episode.write_text("media", encoding="utf-8")

    shows = scan_media_roots([tmp_path])

    assert shows[0].episodes[0].title == "The Second"


def test_scan_media_roots_sorts_shows_ignoring_leading_the(tmp_path):
    for show_name in ("The Office", "Abbott Elementary", "Better Call Saul"):
        episode = (
            tmp_path
            / show_name
            / "Season 01"
            / f"{show_name} S01E01.mkv"
        )
        episode.parent.mkdir(parents=True)
        episode.write_text("media", encoding="utf-8")

    shows = scan_media_roots([tmp_path])

    assert [show.name for show in shows] == [
        "Abbott Elementary",
        "Better Call Saul",
        "The Office",
    ]


def test_scan_media_roots_reads_episode_plot_from_nfo(tmp_path):
    episode = (
        tmp_path
        / "Show A"
        / "Season 01"
        / "Show A - S01E02 - The Second.mkv"
    )
    nfo = episode.with_suffix(".nfo")
    episode.parent.mkdir(parents=True)
    episode.write_text("media", encoding="utf-8")
    nfo.write_text(
        """
        <episodedetails>
          <plot>Original episode overview.</plot>
          <aired>2020-01-02</aired>
        </episodedetails>
        """,
        encoding="utf-8",
    )

    shows = scan_media_roots([tmp_path])

    assert shows[0].episodes[0].plot == "Original episode overview."
    assert shows[0].episodes[0].premiere_date.isoformat() == "2020-01-02"


def test_show_poster_url_is_query_encoded(tmp_path):
    episode = (
        tmp_path
        / "Show & A #1"
        / "Season 01"
        / "Show & A #1 - S01E01.mkv"
    )
    poster = tmp_path / "Show & A #1" / "poster.jpg"
    episode.parent.mkdir(parents=True)
    episode.write_text("media", encoding="utf-8")
    poster.write_text("poster", encoding="utf-8")

    shows = scan_media_roots([tmp_path])

    assert shows[0].to_dict()["poster_url"].startswith("/api/image?path=")
    assert "%26" in shows[0].to_dict()["poster_url"]
    assert "%231" in shows[0].to_dict()["poster_url"]
