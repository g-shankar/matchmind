"""Where matches come from: JSONL files, or new deterministic simulations."""

from __future__ import annotations

import random
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path

from matchmind.schema import Event
from matchmind.simulator import MatchEngine, random_script
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.script import Beat, MatchScript

DEFAULT_SEED_START = 1000
DEFAULT_BEATS = 3
KICKOFF_WEEKS = 52  # generated matches are spread over a season of weekly fixtures
# Who shoots and who is open, and who runs and who carries (fictional squads, as in the demo script).
MISSED_OPTIONS = {
    "NBR": [("NBR-11", "NBR-9"), ("NBR-7", "NBR-9"), ("NBR-10", "NBR-9")],
    "HCY": [("HCY-7", "HCY-9"), ("HCY-10", "HCY-9"), ("HCY-11", "HCY-9")],
}
RUNS = {"NBR": ("NBR-9", "NBR-10"), "HCY": ("HCY-9", "HCY-10")}


def _decision_beats(seed: int, count: int) -> list[Beat]:
    """`count` story beats ("should he have passed?" and unfound runs), spread over the match.

    The engine's own chance model rarely produces these situations (a few per hundred
    shots), so without beats the decision labels would have almost no positives. Beats are
    marked in the event labels (`scripted:*`), so they stay separable from natural play."""
    rng = random.Random(seed)
    span = 78 / max(count, 1)
    beats: list[Beat] = []
    for i in range(count):
        minute = int(8 + i * span + rng.random() * (span - 1))
        if 44 <= minute <= 46:
            minute = 41  # keep clear of half time
        at = f"{minute:02d}:{rng.randint(0, 59):02d}"
        team = rng.choice(["NBR", "HCY"])
        if i % 2 == 0:
            player, open_player = rng.choice(MISSED_OPTIONS[team])
            outcome = rng.choice(["saved", "blocked", "off_target"])
            beats.append(
                Beat(
                    type="missed_option",
                    at=at,
                    team=team,
                    player=player,
                    open_player=open_player,
                    outcome=outcome,
                )
            )
        else:
            runner, carrier = RUNS[team]
            beats.append(Beat(type="run_not_found", at=at, team=team, player=runner, carrier=carrier))
    return beats


def generated_script(seed: int, beats: int = DEFAULT_BEATS) -> MatchScript:
    """The match for a seed: the engine's chance model decides the goals, plus `beats` story beats.
    Same seed, same match, whatever else is generated."""
    home, away = ("NBR", "HCY") if seed % 2 else ("HCY", "NBR")
    script = random_script(f"MM-GEN-{seed:05d}", home=home, away=away)
    return script.model_copy(
        update={
            "kickoff": script.kickoff + timedelta(weeks=seed % KICKOFF_WEEKS),
            "beats": _decision_beats(seed, beats),
        }
    )


def generate_match(seed: int, beats: int = DEFAULT_BEATS) -> list[Event]:
    return MatchEngine(generated_script(seed, beats), seed).run()


def jsonl_files(paths: Iterable[str | Path]) -> list[Path]:
    """Expand files and directories (every *.jsonl inside) into a sorted list."""
    found: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            found += sorted(p.glob("*.jsonl"))
        elif p.is_file():
            found.append(p)
        else:
            raise FileNotFoundError(f"{p} does not exist")
    return found


def load_matches(
    inputs: Iterable[str | Path] = (),
    seeds: int = 0,
    seed_start: int = DEFAULT_SEED_START,
    beats: int = DEFAULT_BEATS,
) -> list[list[Event]]:
    """Matches from files plus `seeds` new simulations (seed_start .. seed_start + seeds - 1),
    sorted by match id so the result never depends on the order of the arguments."""
    if seeds < 0 or not 0 <= beats <= 8:
        raise ValueError("--seeds must be zero or more and --beats between 0 and 8")
    matches = [read_jsonl(path) for path in jsonl_files(inputs)]
    matches += [generate_match(seed_start + i, beats) for i in range(seeds)]
    matches = [m for m in matches if m]
    ids = [m[0].match_id for m in matches]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"the same match id appears twice: {', '.join(dupes)}")
    return sorted(matches, key=lambda m: m[0].match_id)
