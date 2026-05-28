from pathlib import Path

import pytest
from fastapi import HTTPException

from app.config import MARKER_FILE
import app.main as main
from app.models import Episode, Show
from app.generator import delete_playlist_folder
from app.storage import (
    DuplicateFolderError,
    add_media_folder,
    add_output_folder,
    delete_playlist,
    get_default_output_folder,
    get_settings,
    get_playlist,
    init_db,
    remove_output_folder,
    replace_all_playlists,
    set_default_output_folder,
    upsert_playlist,
)


def raise_generation_error(*args):
    raise main.GenerationError("blocked")


def patch_settings_db(monkeypatch, db_path):
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: get_settings(db_path),
    )
    monkeypatch.setattr(
        main,
        "get_default_output_folder",
        lambda: get_default_output_folder(db_path),
    )


def test_selected_episode_ids_work_without_selected_show_paths(monkeypatch):
    chosen = Episode(
        id="chosen",
        path=Path("/media/Show A/Season 01/Show A - S01E01.mkv"),
        show="Show A",
        season=1,
        episode=1,
        title="Pilot",
    )
    other = Episode(
        id="other",
        path=Path("/media/Show A/Season 01/Show A - S01E02.mkv"),
        show="Show A",
        season=1,
        episode=2,
        title="Second",
    )
    monkeypatch.setattr(
        main,
        "scan_media_roots",
        lambda roots: [
            Show(
                name="Show A",
                path=Path("/media/Show A"),
                episodes=(chosen, other),
            )
        ],
    )
    monkeypatch.setattr(
        main,
        "list_media_folders",
        lambda: [Path("/media")],
    )

    episodes = main._episodes_for_playlist(
        {
            "selected_show_paths": [],
            "selected_episode_ids": ["chosen"],
        }
    )

    assert episodes == [chosen]


def test_media_path_authorization_rejects_prefix_collision(monkeypatch):
    monkeypatch.setattr(
        main,
        "list_media_folders",
        lambda: [Path("/media/tv")],
    )

    assert main._is_allowed_media_path(Path("/media/tv/poster.jpg"))
    assert not main._is_allowed_media_path(Path("/media/tv-other/poster.jpg"))


def test_delete_endpoint_preserves_db_when_folder_delete_refused(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    output_root = tmp_path / "output"
    init_db(db_path)
    add_output_folder(output_root, db_path)
    patch_settings_db(monkeypatch, db_path)
    monkeypatch.setattr(
        main,
        "get_playlist",
        lambda playlist_id: get_playlist(playlist_id, db_path),
    )
    monkeypatch.setattr(
        main,
        "delete_playlist",
        lambda playlist_id: delete_playlist(playlist_id, db_path),
    )
    monkeypatch.setattr(
        main,
        "delete_playlist_folder",
        lambda title, folder: delete_playlist_folder(title, folder),
    )
    playlist = upsert_playlist(
        {
            "title": "My Playlist",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(output_root),
        },
        db_path,
    )
    unsafe = output_root / "My Playlist"
    unsafe.mkdir(parents=True)
    (unsafe / "real-file.txt").write_text("do not delete", encoding="utf-8")

    with pytest.raises(HTTPException) as error:
        main.delete_playlist_endpoint(playlist["id"])

    assert error.value.status_code == 409
    assert get_playlist(playlist["id"], db_path) is not None
    assert (unsafe / "real-file.txt").is_file()


def test_delete_endpoint_deletes_db_after_marked_folder_removed(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    output_root = tmp_path / "output"
    init_db(db_path)
    add_output_folder(output_root, db_path)
    patch_settings_db(monkeypatch, db_path)
    monkeypatch.setattr(
        main,
        "get_playlist",
        lambda playlist_id: get_playlist(playlist_id, db_path),
    )
    monkeypatch.setattr(
        main,
        "delete_playlist",
        lambda playlist_id: delete_playlist(playlist_id, db_path),
    )
    monkeypatch.setattr(
        main,
        "delete_playlist_folder",
        lambda title, folder: delete_playlist_folder(title, folder),
    )
    playlist = upsert_playlist(
        {
            "title": "My Playlist",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(output_root),
        },
        db_path,
    )
    folder = output_root / "My Playlist"
    folder.mkdir(parents=True)
    (folder / MARKER_FILE).write_text("owned", encoding="utf-8")

    assert main.delete_playlist_endpoint(playlist["id"]) == {
        "deleted": playlist["id"],
    }
    assert get_playlist(playlist["id"], db_path) is None
    assert not folder.exists()


def test_save_playlist_does_not_update_db_when_rename_refused(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    add_output_folder(tmp_path / "output", db_path)
    patch_settings_db(monkeypatch, db_path)
    playlist = upsert_playlist(
        {
            "title": "Old Playlist",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(tmp_path / "output"),
        },
        db_path,
    )
    monkeypatch.setattr(
        main,
        "get_playlist",
        lambda playlist_id: get_playlist(playlist_id, db_path),
    )
    monkeypatch.setattr(
        main,
        "upsert_playlist",
        lambda payload: upsert_playlist(payload, db_path),
    )
    monkeypatch.setattr(
        main,
        "rename_playlist_folder",
        raise_generation_error,
    )

    payload = main.PlaylistPayload(
        id=playlist["id"],
        title="New Playlist",
        mode="selected_order",
        selected_show_paths=[],
        selected_episode_ids=[],
    )
    with pytest.raises(HTTPException) as error:
        main.save_playlist(payload)

    assert error.value.status_code == 409
    assert get_playlist(playlist["id"], db_path)["title"] == "Old Playlist"


def test_first_output_folder_becomes_default(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)

    add_output_folder(Path("/output/a"), db_path)
    add_output_folder(Path("/output/b"), db_path)

    settings = get_settings(db_path)
    assert settings["output_folders"][0] == {
        "path": "/output/a",
        "is_default": True,
    }
    assert settings["output_folders"][1] == {
        "path": "/output/b",
        "is_default": False,
    }


def test_only_one_output_folder_can_be_default(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    add_output_folder(Path("/output/a"), db_path)
    add_output_folder(Path("/output/b"), db_path)

    set_default_output_folder(Path("/output/b"), db_path)

    settings = get_settings(db_path)
    defaults = [
        item["path"]
        for item in settings["output_folders"]
        if item["is_default"]
    ]
    assert defaults == ["/output/b"]


def test_removing_default_output_folder_is_refused_when_others_exist(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    add_output_folder(Path("/output/a"), db_path)
    add_output_folder(Path("/output/b"), db_path)

    with pytest.raises(ValueError):
        remove_output_folder(Path("/output/a"), db_path)


def test_removing_only_default_output_folder_is_refused(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    add_output_folder(Path("/output/a"), db_path)

    with pytest.raises(ValueError):
        remove_output_folder(Path("/output/a"), db_path)


def test_settings_include_media_folders(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)

    add_media_folder(Path("/media/tv"), db_path)

    assert get_settings(db_path)["media_folders"] == ["/media/tv"]


def test_duplicate_media_folder_is_rejected(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    add_media_folder(Path("/media/tv"), db_path)

    with pytest.raises(DuplicateFolderError):
        add_media_folder(Path("/media/tv"), db_path)


def test_duplicate_output_folder_is_rejected(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    add_output_folder(Path("/output"), db_path)

    with pytest.raises(DuplicateFolderError):
        add_output_folder(Path("/output"), db_path)


def test_playlist_titles_are_case_insensitive_unique(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    upsert_playlist(
        {
            "title": "Action Shows",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
        },
        db_path,
    )

    with pytest.raises(main.DuplicatePlaylistError):
        upsert_playlist(
            {
                "title": "action shows",
                "mode": "selected_order",
                "selected_show_paths": [],
                "selected_episode_ids": [],
            },
            db_path,
        )


def test_playlist_can_save_same_title_with_same_id_different_case(tmp_path):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    init_db(db_path)
    playlist = upsert_playlist(
        {
            "title": "Action Shows",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
        },
        db_path,
    )

    updated = upsert_playlist(
        {
            "id": playlist["id"],
            "title": "action shows",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
        },
        db_path,
    )

    assert updated["title"] == "action shows"


def test_duplicate_media_folder_endpoint_returns_conflict(
    tmp_path,
    monkeypatch,
):
    folder = tmp_path / "media"
    folder.mkdir()
    monkeypatch.setattr(
        main,
        "add_media_folder",
        lambda folder: (_ for _ in ()).throw(
            DuplicateFolderError("already configured")
        ),
    )

    with pytest.raises(HTTPException) as error:
        main.add_media_folder_endpoint(
            main.FolderPayload(path=str(folder))
        )

    assert error.value.status_code == 409


def test_add_folder_endpoint_rejects_relative_path():
    with pytest.raises(HTTPException) as error:
        main.add_media_folder_endpoint(main.FolderPayload(path="media/tv"))

    assert error.value.status_code == 400


def test_add_output_folder_endpoint_rejects_missing_path(tmp_path):
    with pytest.raises(HTTPException) as error:
        main.add_output_folder_endpoint(
            main.FolderPayload(path=str(tmp_path / "missing"))
        )

    assert error.value.status_code == 400


def test_add_folder_endpoint_rejects_config_folder(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    monkeypatch.setattr(main, "CONFIG_DIR", config)

    with pytest.raises(HTTPException) as error:
        main.add_media_folder_endpoint(main.FolderPayload(path=str(config)))

    assert error.value.status_code == 400


def test_add_folder_endpoint_rejects_config_child(tmp_path, monkeypatch):
    config = tmp_path / "config"
    child = config / "nested"
    child.mkdir(parents=True)
    monkeypatch.setattr(main, "CONFIG_DIR", config)

    with pytest.raises(HTTPException) as error:
        main.add_output_folder_endpoint(main.FolderPayload(path=str(child)))

    assert error.value.status_code == 400


def test_save_playlist_duplicate_title_returns_conflict(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    output_root = tmp_path / "output"
    output_root.mkdir()
    init_db(db_path)
    add_output_folder(output_root, db_path)
    patch_settings_db(monkeypatch, db_path)
    upsert_playlist(
        {
            "title": "Existing",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(output_root),
        },
        db_path,
    )
    monkeypatch.setattr(
        main,
        "upsert_playlist",
        lambda payload: upsert_playlist(payload, db_path),
    )

    with pytest.raises(HTTPException) as error:
        main.save_playlist(
            main.PlaylistPayload(
                title="Existing",
                mode="selected_order",
                selected_show_paths=[],
                selected_episode_ids=[],
                output_folder=str(output_root),
            )
        )

    assert error.value.status_code == 409


def test_import_rejects_bad_payload_without_deleting_existing(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    output_root = tmp_path / "output"
    init_db(db_path)
    add_output_folder(output_root, db_path)
    existing = upsert_playlist(
        {
            "title": "Existing",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(output_root),
        },
        db_path,
    )
    monkeypatch.setattr(
        main,
        "replace_all_playlists",
        lambda playlists: replace_all_playlists(playlists, db_path),
    )

    with pytest.raises(HTTPException) as error:
        main.import_playlists({"playlists": [{"title": "Broken"}]})

    assert error.value.status_code == 400
    assert get_playlist(existing["id"], db_path) is not None


def test_import_duplicate_titles_returns_conflict_without_deleting_existing(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    output_root = tmp_path / "output"
    init_db(db_path)
    add_output_folder(output_root, db_path)
    existing = upsert_playlist(
        {
            "title": "Existing",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(output_root),
        },
        db_path,
    )
    monkeypatch.setattr(
        main,
        "replace_all_playlists",
        lambda playlists: replace_all_playlists(playlists, db_path),
    )

    with pytest.raises(HTTPException) as error:
        main.import_playlists({
            "playlists": [
                {
                    "title": "Duplicate",
                    "mode": "selected_order",
                    "selected_show_paths": [],
                    "selected_episode_ids": [],
                    "max_items": 100,
                },
                {
                    "title": "duplicate",
                    "mode": "selected_order",
                    "selected_show_paths": [],
                    "selected_episode_ids": [],
                    "max_items": 100,
                },
            ],
        })

    assert error.value.status_code == 409
    assert get_playlist(existing["id"], db_path) is not None


def test_generate_os_error_returns_conflict(tmp_path, monkeypatch):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    output_root = tmp_path / "output"
    init_db(db_path)
    add_output_folder(output_root, db_path)
    patch_settings_db(monkeypatch, db_path)
    playlist = upsert_playlist(
        {
            "title": "Playlist",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": ["chosen"],
            "output_folder": str(output_root),
        },
        db_path,
    )
    episode = Episode(
        id="chosen",
        path=Path("/media/Show A/Season 01/Show A - S01E01.mkv"),
        show="Show A",
        season=1,
        episode=1,
        title="Pilot",
    )
    monkeypatch.setattr(
        main,
        "get_playlist",
        lambda playlist_id: get_playlist(playlist_id, db_path),
    )
    monkeypatch.setattr(
        main,
        "_episodes_and_poster_paths",
        lambda playlist: ([episode], []),
    )
    monkeypatch.setattr(
        main,
        "generate_playlist_show",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("permission denied")
        ),
    )

    with pytest.raises(HTTPException) as error:
        main.generate(playlist["id"])

    assert error.value.status_code == 409


def test_browser_root_filters_system_directories(tmp_path, monkeypatch):
    visible = [
        tmp_path / "app",
        tmp_path / "bin",
        tmp_path / "config",
        tmp_path / "mnt",
        tmp_path / "output",
        tmp_path / "tv",
    ]
    for folder in visible:
        folder.mkdir()
    monkeypatch.setattr(main, "SYSTEM_BROWSER_PATHS", {
        str(tmp_path / "app"),
        str(tmp_path / "bin"),
    })
    monkeypatch.setattr(
        main,
        "_mounted_browser_paths",
        lambda: [str(folder) for folder in visible],
    )

    children = main._browser_root_children()

    assert children == [
        tmp_path / "config",
        tmp_path / "mnt",
        tmp_path / "output",
        tmp_path / "tv",
    ]


def test_browser_root_allows_nested_mount_targets(tmp_path, monkeypatch):
    media = tmp_path / "media" / "tv"
    media.mkdir(parents=True)
    monkeypatch.setattr(
        main,
        "_mounted_browser_paths",
        lambda: [str(media), "/proc/self"],
    )

    assert main._browser_root_children() == [media]
    assert main._browser_parent(media) == Path("/")


def test_playlist_poster_url_ignores_removed_saved_output(tmp_path):
    old_output = tmp_path / "old-output"
    default_output = tmp_path / "default-output"
    poster = default_output / "My Playlist" / "folder.jpg"
    poster.parent.mkdir(parents=True)
    poster.write_text("poster", encoding="utf-8")
    playlist = {
        "id": 1,
        "title": "My Playlist",
        "output_folder": str(old_output),
    }
    cfg = {
        "output_folders": [
            {"path": str(default_output), "is_default": True},
        ],
    }

    assert main._playlist_poster_url(playlist, cfg, default_output) is None


def test_playlist_poster_endpoint_serves_configured_output(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    output_root = tmp_path / "output"
    playlist_dir = output_root / "My Playlist"
    playlist_dir.mkdir(parents=True)
    (playlist_dir / "folder.jpg").write_text("poster", encoding="utf-8")
    init_db(db_path)
    add_output_folder(output_root, db_path)
    playlist = upsert_playlist(
        {
            "title": "My Playlist",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(output_root),
        },
        db_path,
    )
    patch_settings_db(monkeypatch, db_path)
    monkeypatch.setattr(
        main,
        "get_playlist",
        lambda playlist_id: get_playlist(playlist_id, db_path),
    )

    response = main.playlist_poster(playlist["id"])

    assert Path(response.path) == playlist_dir / "folder.jpg"


def test_playlist_poster_endpoint_rejects_removed_output(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    old_output = tmp_path / "old-output"
    current_output = tmp_path / "current-output"
    playlist_dir = old_output / "My Playlist"
    playlist_dir.mkdir(parents=True)
    (playlist_dir / "folder.jpg").write_text("poster", encoding="utf-8")
    init_db(db_path)
    add_output_folder(current_output, db_path)
    playlist = upsert_playlist(
        {
            "title": "My Playlist",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(old_output),
        },
        db_path,
    )
    patch_settings_db(monkeypatch, db_path)
    monkeypatch.setattr(
        main,
        "get_playlist",
        lambda playlist_id: get_playlist(playlist_id, db_path),
    )

    with pytest.raises(HTTPException) as error:
        main.playlist_poster(playlist["id"])

    assert error.value.status_code == 404


def test_playlist_poster_endpoint_refuses_unconfigured_output(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "config" / "shuffly.sqlite3"
    unsafe_output = tmp_path / "unsafe-output"
    current_output = tmp_path / "current-output"
    playlist_dir = unsafe_output / "My Playlist"
    playlist_dir.mkdir(parents=True)
    (playlist_dir / "folder.jpg").write_text("poster", encoding="utf-8")
    init_db(db_path)
    add_output_folder(current_output, db_path)
    playlist = upsert_playlist(
        {
            "title": "My Playlist",
            "mode": "selected_order",
            "selected_show_paths": [],
            "selected_episode_ids": [],
            "output_folder": str(current_output),
        },
        db_path,
    )
    patch_settings_db(monkeypatch, db_path)
    monkeypatch.setattr(
        main,
        "get_playlist",
        lambda playlist_id: get_playlist(playlist_id, db_path),
    )
    monkeypatch.setattr(
        main,
        "_playlist_poster_output_folder",
        lambda playlist: unsafe_output,
    )

    with pytest.raises(HTTPException) as error:
        main.playlist_poster(playlist["id"])

    assert error.value.status_code == 403
