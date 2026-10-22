"""Rosters for external feeds: invented clubs and players, checked strictly.

A feed that uses the two bundled clubs (`simulator/teams.py`) needs no roster.
Any other club must come with a roster file (JSON or YAML):

    teams:
      - team_id: RVT                 # 2-4 capital letters
        name: Riverton Athletic
        short_name: RVT              # optional
        formation: 4-4-2             # optional
        primary_color: "#1d6f42"     # optional
        secondary_color: "#0b2a19"   # optional
        style: Compact mid-block     # optional, at most 120 characters
        players:                     # 7 to 25, unique shirt numbers
          - {number: 1, name: Ansel Brook, position: GK}

Player ids are always `<team_id>-<number>` inside PitchPulse. Names must look
like names (letters, spaces, apostrophes, dots and hyphens) and must not contain
a real club, player, manager, stadium, competition or broadcaster from the
fact-checker's banned list.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from matchmind.crew.fact_checker import banned_names_in
from matchmind.simulator.teams import TEAMS, Player, Team

from .errors import IngestError

ROSTER_MAX_BYTES = 64 * 1024
TEAM_ID_RE = re.compile(r"^[A-Z]{2,4}$")
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '’.\-]{1,2}[^\W\d_]+)*\.?$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
FORMATION_RE = re.compile(r"^\d(?:-\d){1,4}$")
POSITION_RE = re.compile(r"^[A-Z]{1,4}$")

# Position code -> line. Anything else is a midfielder.
_LINES = {
    "GK": "GK",
    **dict.fromkeys(("RB", "LB", "CB", "RCB", "LCB", "RWB", "LWB", "SW", "DF", "D"), "DEF"),
    **dict.fromkeys(("ST", "CF", "RW", "LW", "RF", "LF", "RAM", "LAM", "FW", "F", "SS"), "FWD"),
}
# Rough base spots by line (own attacking frame); only the simulator and the
# tracking renderer use them, and neither runs on external feeds.
_BASES = {"GK": (5.0, 34.0), "DEF": (25.0, 34.0), "MID": (45.0, 34.0), "FWD": (70.0, 34.0)}


def line_for(position: str) -> str:
    return _LINES.get(position.upper(), "MID")


def check_name(value: str, what: str) -> str:
    """A person or club name: plain letters, and never a real one from the banned list."""
    value = " ".join(value.split())
    if not 2 <= len(value) <= 40 or not NAME_RE.match(value):
        raise ValueError(f"{what} '{value[:40]}' must be 2-40 letters (spaces, ' . - allowed)")
    if banned_names_in(value):
        raise ValueError(f"{what} '{value}' looks like a real name; use invented names only")
    return value


class RosterPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=99)
    name: str = Field(max_length=60)
    position: str = Field(max_length=4)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return check_name(v, "Player name")

    @field_validator("position")
    @classmethod
    def _position(cls, v: str) -> str:
        v = v.strip().upper()
        if not POSITION_RE.match(v):
            raise ValueError("position must be 1-4 capital letters, e.g. GK, RCB, CAM, ST")
        return v


class RosterTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str
    name: str = Field(max_length=60)
    short_name: str = ""
    formation: str = "4-4-2"
    primary_color: str = "#e8e8e8"
    secondary_color: str = "#1a1a1a"
    style: str = Field(default="", max_length=120)
    players: list[RosterPlayer] = Field(min_length=7, max_length=25)

    @field_validator("team_id", "short_name")
    @classmethod
    def _team_id(cls, v: str) -> str:
        v = v.strip().upper()
        if v and not TEAM_ID_RE.match(v):
            raise ValueError("team ids and short names are 2-4 capital letters")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return check_name(v, "Club name")

    @field_validator("style")
    @classmethod
    def _style(cls, v: str) -> str:
        v = " ".join(v.split())
        if any(not (ch.isprintable()) for ch in v):
            raise ValueError("style must be plain text")
        if banned_names_in(v):
            raise ValueError("style mentions a real name; use invented names only")
        return v

    @field_validator("formation")
    @classmethod
    def _formation(cls, v: str) -> str:
        if not FORMATION_RE.match(v):
            raise ValueError("formation looks like 4-3-3")
        return v

    @field_validator("primary_color", "secondary_color")
    @classmethod
    def _color(cls, v: str) -> str:
        if not COLOR_RE.match(v):
            raise ValueError("colours are #rrggbb")
        return v.lower()

    @model_validator(mode="after")
    def _unique_numbers(self) -> RosterTeam:
        numbers = [p.number for p in self.players]
        if len(set(numbers)) != len(numbers):
            raise ValueError(f"{self.team_id} has the same shirt number twice")
        if sum(line_for(p.position) == "GK" for p in self.players) < 1:
            raise ValueError(f"{self.team_id} needs a goalkeeper (position GK)")
        return self

    def to_team(self) -> Team:
        players = tuple(
            Player(
                player_id=f"{self.team_id}-{p.number}",
                name=p.name,
                number=p.number,
                position=p.position,
                line=line_for(p.position),
                base=_BASES[line_for(p.position)],
            )
            for p in self.players
        )
        return Team(
            team_id=self.team_id,
            name=self.name,
            formation=self.formation,
            strength=0.5,
            players=players,
            short_name=self.short_name or self.team_id,
            primary_color=self.primary_color,
            secondary_color=self.secondary_color,
            style=self.style,
        )


class Roster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    teams: list[RosterTeam] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _unique(self) -> Roster:
        ids = [t.team_id for t in self.teams]
        if len(set(ids)) != len(ids):
            raise ValueError("the same team id appears twice")
        return self


def read_small_text(path: str | Path, limit: int, what: str) -> str:
    path = Path(path)
    if not path.is_file():
        raise IngestError(f"{what} not found: {path}")
    if path.stat().st_size > limit:
        raise IngestError(f"{what} is larger than {limit // 1024} KB")
    return path.read_text(encoding="utf-8-sig")


def parse_structured(text: str, path: str | Path) -> Any:
    """JSON for .json files, YAML (safe loader) for anything else."""
    try:
        return json.loads(text) if str(path).lower().endswith(".json") else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as exc:
        raise IngestError(f"{Path(path).name} is not valid JSON or YAML") from exc


def roster_from_data(data: Any) -> dict[str, Team]:
    try:
        roster = Roster.model_validate(data)
    except ValidationError as exc:
        raise IngestError.from_validation("roster", exc) from None
    return {t.team_id: t.to_team() for t in roster.teams}


def load_roster(path: str | Path) -> dict[str, Team]:
    text = read_small_text(path, ROSTER_MAX_BYTES, "Roster file")
    return roster_from_data(parse_structured(text, path))


def resolve_teams(team_ids: list[str], roster: dict[str, Team] | None) -> dict[str, Team]:
    """The clubs for a feed: from the roster when given, else the two bundled clubs."""
    out: dict[str, Team] = {}
    for tid in team_ids:
        if roster is not None and tid in roster:
            out[tid] = roster[tid]
        elif tid in TEAMS:
            out[tid] = TEAMS[tid]
        else:
            raise IngestError(
                f"Club '{tid}' is not one of the bundled clubs ({', '.join(TEAMS)}); "
                "pass a roster file with invented names"
            )
    return out
