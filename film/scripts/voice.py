"""Voiceover: one WAV per line from vo.json with Kokoro (local, Apache-2.0),
plus each line's duration in film/out/vo/durations.json.

Needs `pip install kokoro-onnx soundfile` and the two model files from
https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
in $KOKORO_DIR (default ~/.cache/kokoro).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

FILM = Path(__file__).resolve().parents[1]
MODELS = Path(os.environ.get("KOKORO_DIR", Path.home() / ".cache/kokoro"))


def main() -> None:
    vo = json.loads((FILM / "vo.json").read_text())
    k = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    out = FILM / "out/vo"
    out.mkdir(parents=True, exist_ok=True)
    durations = {}
    for line in vo["lines"]:
        samples, sr = k.create(
            line["text"],
            voice=line.get("voice", vo["voice"]),
            speed=line.get("speed", vo["speed"]),
            lang=line.get("lang", vo["lang"]),
        )
        sf.write(out / f"{line['id']}.wav", samples, sr)
        durations[line["id"]] = round(len(samples) / sr, 3)
        print(f"{line['id']}: {durations[line['id']]:.2f} s")
    (out / "durations.json").write_text(json.dumps(durations, indent=1) + "\n")
    print(f"total {sum(durations.values()):.1f} s")


if __name__ == "__main__":
    main()
