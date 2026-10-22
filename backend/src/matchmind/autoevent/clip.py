"""Write a short clip of the pixel path for the docs.

Each clip frame shows what the vision step saw (the rendered synthetic frame,
scaled up 2x) with what it recovered drawn on top (yellow crosses for players,
a magenta box for the ball), and the label burnt into the picture:
"Rendered synthetic top-down video, not broadcast footage; no real-video model".

MP4 (H.264) through ffmpeg when it is installed; otherwise, and always for
the still, PNG files written with the standard library.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import numpy as np

from .font5x7 import draw_text
from .pixels import PixelConfig, PixelPath
from .tracking import TrackingFeed

UP = 2
BAND = 48
LINE1 = "RENDERED SYNTHETIC TOP-DOWN VIDEO,"
LINE2 = "NOT BROADCAST FOOTAGE; NO REAL-VIDEO MODEL"
LABEL_RGB = (251, 191, 36)
CROSS_RGB = (250, 204, 21)
BALL_BOX_RGB = (236, 72, 153)


def write_png(path: str | Path, img: np.ndarray) -> Path:
    """Minimal RGB PNG writer (no third-party imaging library)."""
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[i].tobytes() for i in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    return out


def compose(path: PixelPath, img: np.ndarray, rec, caption: str) -> np.ndarray:
    """One clip frame: label band, the frame scaled up, recovered positions on top."""
    big = np.repeat(np.repeat(img, UP, axis=0), UP, axis=1)
    h, w, _ = big.shape
    canvas = np.zeros((h + 2 * BAND, w, 3), np.uint8)
    canvas[:] = (11, 17, 32)
    canvas[BAND : BAND + h] = big
    draw_text(canvas, LINE1, 8, 6, LABEL_RGB, scale=2)
    draw_text(canvas, LINE2, 8, 26, LABEL_RGB, scale=2)
    draw_text(canvas, caption, 8, BAND + h + 8, (226, 232, 240), scale=2)
    draw_text(canvas, "CROSSES: POSITIONS RECOVERED FROM PIXELS", 8, BAND + h + 28, CROSS_RGB, scale=1)
    r = path.raster

    def at(x: float, y: float) -> tuple[int, int]:
        u, v = r.to_px(x, y)
        return int(u * UP), int(v * UP) + BAND

    for n in range(len(path.feed.player_ids)):
        p = rec.player(n)
        if p is None:
            continue
        cx, cy = at(*p)
        for d in range(-3, 4):
            for x, y in ((cx + d, cy), (cx, cy + d)):
                if 0 <= y < canvas.shape[0] and 0 <= x < w:
                    canvas[y, x] = CROSS_RGB
    if rec.ball is not None:
        cx, cy = at(*rec.ball)
        for d in range(-4, 5):
            for x, y in ((cx + d, cy - 4), (cx + d, cy + 4), (cx - 4, cy + d), (cx + 4, cy + d)):
                if 0 <= y < canvas.shape[0] and 0 <= x < w:
                    canvas[y, x] = BALL_BOX_RGB
    return canvas


def write_clip(
    feed: TrackingFeed,
    lo: int,
    seconds: float,
    out: str | Path,
    *,
    cfg: PixelConfig | None = None,
    still: str | Path | None = None,
    caption_of=None,
) -> dict:
    """Render frames lo..lo+seconds, run the vision step, write the clip (and a still)."""
    from matchmind.simulator.script import format_clock

    path = PixelPath(feed, cfg)
    hi = min(len(feed.frames), lo + round(seconds * feed.hz))
    frames: list[np.ndarray] = []

    def keep(k, img, rec):
        f = feed.frames[k]
        caption = caption_of(f) if caption_of else f"{feed.match_id}  {format_clock(f.clock_s, f.period)}"
        frames.append(compose(path, img, rec, caption))

    path.recover(lo, hi, on_image=keep)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {"frames": len(frames), "still": None, "clip": None, "format": None}
    if still is not None and frames:
        result["still"] = str(write_png(still, frames[len(frames) // 2]))
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and frames and out.suffix.lower() == ".mp4":
        h, w, _ = frames[0].shape
        cmd = [
            ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}", "-r", f"{feed.hz:g}", "-i", "-", "-an", "-c:v", "libx264",
            "-preset", "veryslow", "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
        ]  # fmt: skip
        subprocess.run(cmd, input=b"".join(f.tobytes() for f in frames), check=True)
        result.update(clip=str(out), format="mp4")
    elif frames:
        # No ffmpeg: a strip of five frames instead of a clip.
        picks = [frames[round(i * (len(frames) - 1) / 4)] for i in range(5)]
        strip = np.concatenate(picks, axis=0)
        png = out.with_suffix(".png")
        write_png(png, strip)
        result.update(clip=str(png), format="png-strip")
    return result
