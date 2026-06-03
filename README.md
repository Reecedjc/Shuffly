<h1>
  Shuffly
</h1>

Shuffly is a small Docker app that creates Jellyfin-visible playlist shows
without copying your media.

It scans mounted TV folders, lets you choose shows or individual episodes in a
web UI, and writes a generated show folder containing symlinks back to the
original files. Jellyfin can then see each generated playlist as its own custom
show.

## Playlist modes

- **Shuffle** randomizes the selected episodes.
- **Shuffled in order** shuffles between selected shows while preserving episode
  order within each show.
- **Manual Order** uses the episode order shown in the selected episode list.
- **Sort by release date** sorts by episode NFO `premiered`/`aired` date when
  available, then by show, season, and episode.

## What it creates

Each generated playlist is written as a normal TV show folder:

```text
/output/
  Action Shows Shuffle/
    .shuffly-owned
    tvshow.nfo
    Season 01/
      Action Shows Shuffle - S01E001 - Show A - Pilot.mkv -> /media/Show A/Season 01/Show A - S01E01.mkv
      Action Shows Shuffle - S01E001 - Show A - Pilot.nfo
```

Generated media entries are symlinks, not copies. Jellyfin must be able to
resolve the symlink target paths. The simplest setup is to mount the same source
media paths into both the Shuffly and Jellyfin containers.

## Recommended Docker setup

You do not need to change Jellyfin's existing media mount paths. The goal is to
make Shuffly see the same host folders that Jellyfin already sees, while adding
one shared output folder that both containers can access.

Example Shuffly service:

```yaml
services:
  shuffly:
    image: ghcr.io/reecedjc/shuffly:latest
    container_name: shuffly
    ports:
      - "8097:8097"
    volumes:
      - /path/to/tv-library-1:/tv:ro
      - /path/to/tv-library-2:/tv_2:ro
      - /path/to/shuffly-output:/output:rw
      - /path/to/shuffly-config:/config:rw
    restart: unless-stopped
```

The GHCR package must be public for users to pull it without signing in.

## Quick start

After creating the `docker-compose.yml` file above, run:

```bash
docker compose up -d
```

Open <http://localhost:8097>.

After Shuffly starts, add the mounted container paths in Shuffly's **Settings**
tab. Fresh installs do not auto-enable any media or output folders.

Example Jellyfin volume additions:

```yaml
services:
  jellyfin:
    volumes:
      - /path/to/tv-library-1:/tv
      - /path/to/tv-library-2:/tv_2
      - /path/to/shuffly-output:/shuffly
```

In this layout:

- Jellyfin keeps its existing media paths.
- Shuffly mounts the same source folders read-only.
- Both containers share the same `/output` path.
- Jellyfin only needs the extra `/output` mount added to its compose file.
- In Shuffly Settings, add `/tv` and `/tv_2` as media folders and `/output`
  as a playlist output folder.

If Jellyfin sees the media at different paths from Shuffly, the generated
symlinks may appear broken inside Jellyfin. Matching the container paths avoids
that problem without changing your Jellyfin library layout.

## Jellyfin setup

After generating playlists, add Shuffly's output folder as a Jellyfin **Shows**
library. Each generated playlist appears as a custom show.

## Safe regeneration

Shuffly writes a hidden marker file into every generated playlist folder:

```text
/output/<Playlist Title>/.shuffly-owned
```

Regeneration only replaces folders that contain that marker. If a folder with
the same playlist title exists without `.shuffly-owned`, Shuffly refuses to
overwrite it. Shuffly never deletes the configured output root.

## Development

The included `docker-compose.yml` builds the app from the local source tree and
uses local placeholder folders:

- `./sample-media` mounted read-only as `/media`
- `./sample-output` mounted read-write as `/output`
- `./config` mounted read-write as `/config`

`./sample-media` is not included with the repository. Docker Compose may create
it as an empty folder when starting the development stack.

```bash
docker compose up --build
```

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload --port 8097
```
