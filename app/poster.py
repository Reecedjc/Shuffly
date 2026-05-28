from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

# Output poster dimensions (portrait, matching Jellyfin convention)
POSTER_W = 1000
POSTER_H = 1500
CELL_W = POSTER_W // 2   # 500 — one quarter width
CELL_H = POSTER_H // 2   # 750 — one quarter height

BACKGROUND_PATH = Path(__file__).parent / "background.png"


def _resize_fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Scale img to fit within (max_w, max_h), preserving aspect ratio."""
    ratio = min(max_w / img.width, max_h / img.height)
    new_w = max(1, round(img.width * ratio))
    new_h = max(1, round(img.height * ratio))
    return img.resize((new_w, new_h), Image.LANCZOS)


def _paste(
    canvas: Image.Image,
    img: Image.Image,
    x: int,
    y: int,
) -> None:
    """Paste img onto canvas at (x, y), using alpha channel if present."""
    if img.mode == "RGBA":
        canvas.paste(img, (x, y), img)
    else:
        canvas.paste(img, (x, y))


def build_playlist_poster(poster_paths: list[Path]) -> bytes:
    """
    Composite up to 4 show poster images onto the purple background and
    return the result as JPEG bytes.

    Layouts:
        1 show  — 1/4-size poster centred on background
        2 shows — two 1/4-size posters stacked vertically
        3 shows — two side-by-side on top, one centred below
        4 shows — one in each corner (tiles to fill the full canvas)
    """
    if BACKGROUND_PATH.is_file():
        canvas = Image.open(BACKGROUND_PATH).convert("RGBA")
        canvas = canvas.resize((POSTER_W, POSTER_H), Image.LANCZOS)
    else:
        # Purple fallback when background file is missing
        canvas = Image.new("RGBA", (POSTER_W, POSTER_H), (80, 20, 140))

    images: list[Image.Image] = []
    for path in poster_paths[:4]:
        try:
            images.append(Image.open(path).convert("RGBA"))
        except Exception:
            pass  # skip images that cannot be opened

    n = len(images)
    if n == 0:
        # Nothing to composite — return the bare background
        buf = io.BytesIO()
        canvas.convert("RGB").save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    if n == 1:
        # 1/4-size poster centred on the full canvas
        img_r = _resize_fit(images[0], CELL_W, CELL_H)
        _paste(canvas, img_r,
               (POSTER_W - img_r.width) // 2,
               (POSTER_H - img_r.height) // 2)

    elif n == 2:
        # Two 1/4-size posters stacked vertically, horizontally centred
        for i, img in enumerate(images):
            img_r = _resize_fit(img, CELL_W, CELL_H)
            x = (POSTER_W - img_r.width) // 2
            y = i * CELL_H + (CELL_H - img_r.height) // 2
            _paste(canvas, img_r, x, y)

    elif n == 3:
        # Top row: 2 side-by-side filling the full width
        for i, img in enumerate(images[:2]):
            img_r = _resize_fit(img, CELL_W, CELL_H)
            x = i * CELL_W + (CELL_W - img_r.width) // 2
            y = (CELL_H - img_r.height) // 2
            _paste(canvas, img_r, x, y)
        # Bottom: single poster horizontally centred
        img_r = _resize_fit(images[2], CELL_W, CELL_H)
        _paste(canvas, img_r,
               (POSTER_W - img_r.width) // 2,
               CELL_H + (CELL_H - img_r.height) // 2)

    else:
        # 4 corners — tiles to fill the full canvas
        corners = [
            (0,      0),       # top-left
            (CELL_W, 0),       # top-right
            (0,      CELL_H),  # bottom-left
            (CELL_W, CELL_H),  # bottom-right
        ]
        for img, (cx, cy) in zip(images, corners):
            img_r = _resize_fit(img, CELL_W, CELL_H)
            x = cx + (CELL_W - img_r.width) // 2
            y = cy + (CELL_H - img_r.height) // 2
            _paste(canvas, img_r, x, y)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()
