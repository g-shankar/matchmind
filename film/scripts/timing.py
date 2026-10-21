"""Lay the film out on a 120 BPM grid from the voiceover, into film/timing.json.

Scenes start on bar lines (2 s). Inside a scene the lines run in order with
a small gap; each cue word gets a time estimated from its character position
inside the spoken part of its line. Every picture action reads its time from
here, and the music and sfx are built against the same grid.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf

FILM = Path(__file__).resolve().parents[1]
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT
FPS = 30
LEAD = {1: 0.5, 2: 0.5, 3: 0.5, 4: 1.0, 5: 0.8, 6: 0.5, 7: 0.6, 8: 0.6}
TAIL = {1: 0.8, 2: 0.6, 3: 0.6, 4: 1.6, 5: 3.0, 6: 4.4, 7: 1.2, 8: 2.8}
SCENES = {1: "title", 2: "pipeline", 3: "crew", 4: "should-he-have-passed", 5: "split", 6: "languages",
          7: "overlay", 8: "azure"}


def speech_span(path: Path) -> tuple[float, float, float]:
    s, sr = sf.read(path)
    env = np.abs(s)
    idx = np.nonzero(env > 0.02 * env.max())[0]
    return idx[0] / sr, idx[-1] / sr, len(s) / sr


def snap_up(t: float, step: float) -> float:
    return math.ceil(round(t / step, 6)) * step


def main() -> None:
    vo = json.loads((FILM / "vo.json").read_text())
    lines_by_scene: dict[int, list[dict]] = {}
    for line in vo["lines"]:
        lines_by_scene.setdefault(line["scene"], []).append(line)

    t = 0.0
    scenes, lines, cues = [], [], {}
    for n in sorted(lines_by_scene):
        start = t
        cur = start + LEAD[n]
        for i, line in enumerate(lines_by_scene[n]):
            if i:
                cur += line.get("gap_before", 0.3)
            on, off, total = speech_span(FILM / "out/vo" / f"{line['id']}.wav")
            entry = {"id": line["id"], "scene": n, "start": round(cur, 3), "end": round(cur + total, 3),
                     "speech": [round(cur + on, 3), round(cur + off, 3)], "text": line["text"],
                     "caption": line["text"] if line.get("caption", True) is True else (line["caption"] or None)}
            lines.append(entry)
            low = line["text"].lower()
            for cue in line.get("cues", []):
                pos = low.index(cue.lower())
                frac = pos / max(len(low), 1)
                key = f"{line['id']}.{cue.lower().replace(' ', '-')}"
                cues[key] = round(cur + on + frac * (off - on), 3)
            cur += total
        end = snap_up(cur + TAIL[n], BAR)
        scenes.append({"n": n, "name": SCENES[n], "start": round(start, 3), "duration": round(end - start, 3)})
        t = end

    timing = {"fps": FPS, "bpm": BPM, "beat": BEAT, "bar": BAR, "duration": round(t, 3),
              "beats": [round(i * BEAT, 3) for i in range(int(t / BEAT) + 1)],
              "scenes": scenes, "lines": lines, "cues_raw": cues,
              # picture actions and their sounds land on the nearest beat
              "cues": {k: round(round(v / BEAT) * BEAT, 3) for k, v in cues.items()}}
    (FILM / "timing.json").write_text(json.dumps(timing, indent=1) + "\n")
    for s in scenes:
        print(f"scene {s['n']} {s['name']:<24} {s['start']:6.1f} +{s['duration']:.1f}")
    print(f"total {t:.1f} s")


if __name__ == "__main__":
    main()
