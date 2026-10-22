"""Which matches can be exported: the bundled dataset plus a small seeded range.

Bundled matches are the files in `backend/data/matches` (listed in its
`manifest.json`). Seeded matches are simulated on request, deterministically:
the same seed always gives the same match, byte for byte (the generator the
Lakehouse export uses, `analytics.sources.generate_match`). The public API only
offers seeds `SEED_START .. SEED_START + API_SEED_COUNT - 1`; the CLI takes any.

Match ids are looked up in this allow-list; a file path is never built from
what a caller sends.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from matchmind.analytics.sources import DEFAULT_BEATS, DEFAULT_SEED_START, generate_match, generated_script
from matchmind.schema import Event
from matchmind.simulator.publisher import read_jsonl

SEED_START = DEFAULT_SEED_START
API_SEED_COUNT = 20
CLI_MAX_SEED = 99_999
SEEDED_ID_RE = re.compile(r"^MM-GEN-(\d{5})$")
_FILE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,31}\.jsonl$")

SCENARIOS = {
    "demo_storyline": (
        "Scripted demo storyline: home club 2-0 up, red card 52', pressure 60-75', "
        "away win 3-2 in stoppage time, two missed square balls and an unfound run."
    ),
    "chance_model": "Unscripted: every goal comes from the engine's own chance model.",
    "chance_model_with_beats": (
        f"Chance model plus {DEFAULT_BEATS} decision beats ('should he have passed?' shots and "
        "unfound runs), marked scripted:* in the labels."
    ),
}

_DATA = Path("data") / "matches"
_BACKEND_DIR = Path(__file__).resolve().parents[3]


def default_dataset_dir() -> Path:
    """MATCHMIND_DATASET_DIR, else the bundled dataset next to the source tree or under the
    working directory (a non-editable install puts this module in site-packages)."""
    env = os.environ.get("MATCHMIND_DATASET_DIR")
    if env:
        return Path(env)
    for base in (_BACKEND_DIR, Path.cwd(), Path.cwd() / "backend"):
        if (base / _DATA / "manifest.json").is_file():
            return base / _DATA
    return _BACKEND_DIR / _DATA


@dataclass(frozen=True)
class MatchEntry:
    match_id: str
    kind: str  # "bundled" or "seeded"
    scenario: str
    seed: int
    home: str
    away: str
    score: str | None = None  # known up front for bundled matches
    events: int | None = None
    file: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("file")
        return out


def seeded_id(seed: int) -> str:
    return f"MM-GEN-{seed:05d}"


def seeded_entry(seed: int) -> MatchEntry:
    script = generated_script(seed)
    return MatchEntry(
        match_id=seeded_id(seed),
        kind="seeded",
        scenario="chance_model_with_beats",
        seed=seed,
        home=script.home,
        away=script.away,
    )


@lru_cache(maxsize=4)
def _bundled(dataset_dir: str) -> tuple[MatchEntry, ...]:
    root = Path(dataset_dir)
    manifest = root / "manifest.json"
    if not manifest.is_file():
        return ()
    entries = []
    for row in json.loads(manifest.read_text(encoding="utf-8")):
        name = str(row["file"])
        if not _FILE_RE.match(name) or not (root / name).is_file():
            continue  # only plain file names inside the dataset folder
        entries.append(
            MatchEntry(
                match_id=str(row["match_id"]),
                kind="bundled",
                scenario="demo_storyline" if row.get("scripted") else "chance_model",
                seed=int(row["seed"]),
                home=str(row["home"]),
                away=str(row["away"]),
                score=str(row["score"]),
                events=int(row["events"]),
                file=name,
            )
        )
    return tuple(entries)


def bundled_entries(dataset_dir: Path | None = None) -> list[MatchEntry]:
    return list(_bundled(str(dataset_dir or default_dataset_dir())))


def api_entries(dataset_dir: Path | None = None) -> list[MatchEntry]:
    """Everything the public API offers."""
    seeded = [seeded_entry(SEED_START + i) for i in range(API_SEED_COUNT)]
    return bundled_entries(dataset_dir) + seeded


def find(match_id: str, dataset_dir: Path | None = None, any_seed: bool = False) -> MatchEntry | None:
    """The allow-listed entry for a match id, or None. `any_seed` (CLI only) widens the seeds."""
    for entry in bundled_entries(dataset_dir):
        if entry.match_id == match_id:
            return entry
    m = SEEDED_ID_RE.match(match_id)
    if m:
        seed = int(m.group(1))
        lo, hi = (0, CLI_MAX_SEED) if any_seed else (SEED_START, SEED_START + API_SEED_COUNT - 1)
        if lo <= seed <= hi:
            return seeded_entry(seed)
    return None


@lru_cache(maxsize=8)
def _load(match_id: str, dataset_dir: str, file: str | None, seed: int) -> tuple[Event, ...]:
    if file is not None:
        return tuple(read_jsonl(Path(dataset_dir) / file))
    return tuple(generate_match(seed))


def load_match(entry: MatchEntry, dataset_dir: Path | None = None) -> list[Event]:
    return list(_load(entry.match_id, str(dataset_dir or default_dataset_dir()), entry.file, entry.seed))
