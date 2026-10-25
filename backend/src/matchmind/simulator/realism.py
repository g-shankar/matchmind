"""Football realism check: per-match averages over seeded unscripted matches.

Run with ``python -m matchmind.simulator.realism`` to print the table.
Every number comes from the stats engine's team totals (plus card events).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from matchmind.schema import EventType
from matchmind.stats.state import StatsEngine

from .engine import MatchEngine
from .script import random_script

SEEDS = tuple(range(1000, 1020))

# (low, high) bounds for the per-match average across SEEDS. Real top-flight
# averages sit near the middle; the bounds allow for a 20-match sample.
RANGES: dict[str, tuple[float, float]] = {
    "goals": (1.5, 4.5),
    "shots": (15.0, 35.0),
    "shots_on_target": (5.0, 15.0),
    "pass_accuracy": (70.0, 90.0),
    # Both teams combined. Typical top-flight matches sit near 850-1,100, with
    # possession-heavy games above 1,200; the engine runs on the high side.
    "passes": (700.0, 1500.0),
    "fouls": (10.0, 35.0),
    "cards": (1.0, 8.0),
}


@dataclass
class MatchLine:
    seed: int
    goals: int
    shots: int
    shots_on_target: int
    passes: int
    pass_accuracy: float
    fouls: int
    cards: int
    possession_home: float
    possession_away: float


def measure(seed: int) -> MatchLine:
    home, away = ("NBR", "HCY") if seed % 2 else ("HCY", "NBR")
    events = MatchEngine(random_script(f"MM-REAL-{seed}", home=home, away=away), seed).run()
    engine = StatsEngine.replay(events)
    t = engine.team_totals()
    h, a = t[home], t[away]
    passes = h.passes + a.passes
    completed = h.passes_completed + a.passes_completed
    # Possession is the pass share, the same definition the live stats windows use.
    poss_h = round(100 * h.passes / passes, 1) if passes else 50.0
    return MatchLine(
        seed=seed,
        goals=h.goals + a.goals,
        shots=h.shots + a.shots,
        shots_on_target=h.shots_on_target + a.shots_on_target,
        passes=passes,
        pass_accuracy=round(100 * completed / passes, 1) if passes else 0.0,
        fouls=h.fouls + a.fouls,
        cards=sum(e.type == EventType.CARD for e in events),
        possession_home=poss_h,
        possession_away=round(100 - poss_h, 1),
    )


def measure_all(seeds=SEEDS) -> list[MatchLine]:
    return [measure(s) for s in seeds]


def averages(lines: list[MatchLine]) -> dict[str, float]:
    return {k: round(sum(getattr(x, k) for x in lines) / len(lines), 2) for k in RANGES}


def table(lines: list[MatchLine]) -> str:
    rows = [
        "| seed | goals | shots | on target | passes | pass acc % | fouls | cards | poss H/A % |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for x in lines:
        rows.append(
            f"| {x.seed} | {x.goals} | {x.shots} | {x.shots_on_target} | {x.passes} | {x.pass_accuracy} "
            f"| {x.fouls} | {x.cards} | {x.possession_home}/{x.possession_away} |"
        )
    rows += ["", "| metric | average | realistic range |", "|---|---|---|"]
    for k, v in averages(lines).items():
        lo, hi = RANGES[k]
        rows.append(f"| {k} | {v} | {lo}-{hi} |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Print the football realism table.")
    p.add_argument("--start", type=int, default=SEEDS[0])
    p.add_argument("--count", type=int, default=len(SEEDS))
    a = p.parse_args(argv)
    print(table(measure_all(range(a.start, a.start + a.count))))


if __name__ == "__main__":
    main()
