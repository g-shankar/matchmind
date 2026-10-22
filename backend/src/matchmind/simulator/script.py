"""Match scripts: YAML files that pin the story beats of a simulated match."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from .teams import get_team

HALF_S = 2700.0
FULL_S = 5400.0

BeatType = Literal[
    "goal", "disallowed_goal", "missed_option", "run_not_found", "red_card", "pressure_spell", "milestone"
]

_CLOCK = re.compile(r"(\d{1,2})(?:\+(\d{1,2}))?:(\d{2})")


def parse_clock(text: str) -> tuple[int, float]:
    """'67:30' -> (2, 4050.0); '45+1:30' -> (1, 2790.0); '90+2:15' -> (2, 5535.0)."""
    m = _CLOCK.fullmatch(text.strip())
    if not m:
        raise ValueError(f"Bad match clock '{text}'. Use MM:SS, 45+M:SS or 90+M:SS.")
    minutes, extra, seconds = int(m[1]), m[2], int(m[3])
    if seconds >= 60:
        raise ValueError(f"Bad seconds in '{text}'")
    if extra is not None:
        if minutes not in (45, 90):
            raise ValueError(f"Stoppage time must follow 45 or 90: '{text}'")
        return (1 if minutes == 45 else 2), minutes * 60 + int(extra) * 60 + seconds
    total = minutes * 60 + seconds
    if total > FULL_S:
        raise ValueError(f"'{text}' is past 90:00; use 90+M:SS")
    return (1 if total < HALF_S else 2), float(total)


def format_clock(clock_s: float, period: int) -> str:
    base = HALF_S if period == 1 else FULL_S
    if clock_s > base:
        extra = clock_s - base
        return f"{int(base // 60)}+{int(extra // 60)}:{int(extra % 60):02d}"
    return f"{int(clock_s // 60):02d}:{int(clock_s % 60):02d}"


class Beat(BaseModel):
    type: BeatType
    at: str
    until: str | None = None
    team: str
    player: str | None = None
    assist: str | None = None
    open_player: str | None = None
    carrier: str | None = None
    outcome: Literal["saved", "blocked", "off_target"] = "saved"
    intensity: float = Field(default=0.5, ge=0, le=1)
    label: str | None = None
    # disallowed_goal: why VAR rules it out, and how long the check takes (match seconds).
    reason: Literal["offside", "handball", "foul"] = "offside"
    review_s: float = Field(default=70.0, ge=10, le=300)

    @property
    def period(self) -> int:
        return parse_clock(self.at)[0]

    @property
    def at_s(self) -> float:
        return parse_clock(self.at)[1]

    @property
    def until_s(self) -> float:
        return parse_clock(self.until)[1] if self.until else self.at_s


_REQUIRED = {
    "goal": ("player",),
    "disallowed_goal": ("player",),
    "missed_option": ("player", "open_player"),
    "run_not_found": ("player",),
    "red_card": ("player",),
    "pressure_spell": ("until",),
    "milestone": ("player", "label"),
}


class MatchScript(BaseModel):
    match_id: str
    home: str = "NBR"
    away: str = "HCY"
    kickoff: datetime = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
    stoppage_minutes: tuple[int, int] | None = None
    random_goals: bool = False
    beats: list[Beat] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> MatchScript:
        teams = {t: get_team(t) for t in (self.home, self.away)}
        if self.home == self.away:
            raise ValueError("home and away must differ")
        for beat in self.beats:
            for field in _REQUIRED[beat.type]:
                if getattr(beat, field) is None:
                    raise ValueError(f"{beat.type} beat at {beat.at} needs '{field}'")
            if beat.team not in teams:
                raise ValueError(f"Beat team {beat.team} is not playing")
            for pid in (beat.player, beat.assist, beat.open_player, beat.carrier):
                if pid is not None:
                    teams[beat.team].player(pid)  # raises if not in that team
            _ = beat.at_s  # validates the clock string
            if beat.until is not None and beat.until_s <= beat.at_s:
                raise ValueError(f"Beat at {beat.at} ends before it starts")
        return self


def load_script(spec: str | Path) -> MatchScript:
    """Load a script from a file path, or by name from the bundled scripts."""
    path = Path(spec)
    if path.suffix in {".yaml", ".yml"} and path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = resources.files(__package__).joinpath(f"scripts/{spec}.yaml").read_text("utf-8")
    return MatchScript.model_validate(yaml.safe_load(text))


def random_script(match_id: str, home: str = "NBR", away: str = "HCY") -> MatchScript:
    """An unscripted match where goals come from the engine's own chance model."""
    return MatchScript(match_id=match_id, home=home, away=away, random_goals=True)
