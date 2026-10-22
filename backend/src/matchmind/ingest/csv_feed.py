"""The generic CSV adapter: one row per on-ball action, plus a small mapping file.

Default columns (rename any of them in the mapping):

    type,minute,second,team,player,x,y,end_x,end_y,outcome[,period]

- `type`: an action (pass, carry, dribble, shot, interception, tackle, clearance,
  recovery, foul, card), or your own word mapped in `types`.
- `minute`, `second`: elapsed match time as on a broadcast clock (47:10 in the
  first half's stoppage time is minute 47 with `period` 1). Without a `period`
  column, minutes before 45 are the first half and the rest the second.
- `team`: a club id; `player`: shirt number (default) or `<team>-<number>` id.
- `x`, `y`, `end_x`, `end_y`: on your pitch (`pitch.length` x `pitch.width`,
  origin bottom-left unless `pitch.origin: top_left`), scaled to 105 x 68 m.
  The home club attacks towards high x for the whole match, as in our schema.
- `outcome`: pass complete/incomplete/out, shot goal/saved/blocked/off_target,
  card yellow/red, or your own words mapped in `outcomes`.

Mapping file (YAML or JSON):

    format: generic-csv/1
    match_id: EXT-0001
    kickoff: 2026-10-24T15:00:00Z
    home: RVT
    away: GLD
    columns: {type: action}        # optional renames, our name -> your header
    types: {Pass: pass}            # optional
    outcomes: {Scored: goal}       # optional
    pitch: {length: 100, width: 100, origin: bottom_left}   # optional
    player_ref: number             # or player_id

The adapter adds what the schema needs and a CSV does not carry: match_start
(line-ups from the roster), period_start / period_end, match_end and the
scores, possession ids (a new one each time the team on the ball changes) and
the receiver of a completed pass (the next actor, when a teammate). Everything
then goes through the same strict checks as a JSON feed.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from matchmind.schema import PITCH_LENGTH_M, PITCH_WIDTH_M, Event, EventType, LineupPlayer, Outcome, Point
from matchmind.simulator.script import format_clock
from matchmind.simulator.teams import Team

from .errors import IngestError
from .roster import parse_structured, read_small_text, resolve_teams
from .validate import DEFAULT_LIMITS, MATCH_ID_RE, Limits

MAPPING_MAX_BYTES = 16 * 1024
MAX_CELL_CHARS = 64
HALF_TIME_BREAK_S = 900.0

FIELDS = ("type", "minute", "second", "team", "player", "x", "y", "end_x", "end_y", "outcome", "period")
REQUIRED = ("type", "minute", "second", "team")
ACTIONS = (
    EventType.PASS,
    EventType.CARRY,
    EventType.DRIBBLE,
    EventType.SHOT,
    EventType.INTERCEPTION,
    EventType.TACKLE,
    EventType.CLEARANCE,
    EventType.RECOVERY,
    EventType.FOUL,
    EventType.CARD,
)
OUTCOMES_BY_TYPE: dict[EventType, set[str]] = {
    EventType.PASS: {"complete", "incomplete", "out"},
    EventType.SHOT: {"goal", "saved", "blocked", "off_target"},
    EventType.CARD: {"yellow", "red"},
}
# Actions with a start and an end location.
MOVES = {EventType.PASS, EventType.CARRY, EventType.DRIBBLE, EventType.SHOT, EventType.CLEARANCE}


class PitchSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    length: float = Field(default=PITCH_LENGTH_M, gt=0, le=1000)
    width: float = Field(default=PITCH_WIDTH_M, gt=0, le=1000)
    origin: Literal["bottom_left", "top_left"] = "bottom_left"


class Mapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["generic-csv/1"]
    match_id: str
    kickoff: datetime
    home: str
    away: str
    columns: dict[str, str] = Field(default_factory=dict, max_length=len(FIELDS))
    types: dict[str, str] = Field(default_factory=dict, max_length=64)
    outcomes: dict[str, str] = Field(default_factory=dict, max_length=64)
    pitch: PitchSpec = Field(default_factory=PitchSpec)
    player_ref: Literal["number", "player_id"] = "number"

    @field_validator("match_id")
    @classmethod
    def _match_id(cls, v: str) -> str:
        v = v.strip().upper()
        if not MATCH_ID_RE.match(v):
            raise ValueError("match_id must be 3-32 capital letters, digits or hyphens")
        return v

    @field_validator("home", "away")
    @classmethod
    def _team(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("kickoff")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("kickoff needs a time zone, e.g. 2026-10-24T15:00:00Z")
        return v.astimezone(UTC)

    @field_validator("columns")
    @classmethod
    def _columns(cls, v: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(v) - set(FIELDS))
        if unknown:
            raise ValueError(f"unknown column names {unknown}; use {', '.join(FIELDS)}")
        return v

    @field_validator("types")
    @classmethod
    def _types(cls, v: dict[str, str]) -> dict[str, str]:
        allowed = {t.value for t in ACTIONS}
        bad = sorted({t for t in v.values() if t not in allowed})
        if bad:
            raise ValueError(f"types can only map to {', '.join(sorted(allowed))}")
        return v

    @field_validator("outcomes")
    @classmethod
    def _outcomes(cls, v: dict[str, str]) -> dict[str, str]:
        allowed = {o.value for o in Outcome} | {"yellow", "red"}
        bad = sorted({o for o in v.values() if o not in allowed})
        if bad:
            raise ValueError(f"outcomes can only map to {', '.join(sorted(allowed))}")
        return v


def load_mapping(path: str | Path) -> Mapping:
    text = read_small_text(path, MAPPING_MAX_BYTES, "Mapping file")
    try:
        return Mapping.model_validate(parse_structured(text, path))
    except ValidationError as exc:
        raise IngestError.from_validation("mapping file", exc) from None


class _Rows:
    """Cell access by our field name, with plain-word errors that name the row."""

    def __init__(self, mapping: Mapping, header: list[str]) -> None:
        self.col = {f: mapping.columns.get(f, f) for f in FIELDS}
        missing = [self.col[f] for f in REQUIRED if self.col[f] not in header]
        if missing:
            raise IngestError(f"The CSV is missing the column(s) {', '.join(missing)}")
        self.index = {f: header.index(self.col[f]) for f in FIELDS if self.col[f] in header}

    def get(self, row: list[str], name: str) -> str:
        i = self.index.get(name)
        if i is None or i >= len(row):
            return ""
        cell = row[i].strip()
        if len(cell) > MAX_CELL_CHARS:
            raise ValueError(f"{self.col[name]} is longer than {MAX_CELL_CHARS} characters")
        return cell

    def number(self, row: list[str], name: str, required: bool = False) -> float | None:
        cell = self.get(row, name)
        if not cell:
            if required:
                raise ValueError(f"{self.col[name]} is empty")
            return None
        try:
            value = float(cell)
        except ValueError:
            raise ValueError(f"{self.col[name]} '{cell}' is not a number") from None
        if not math.isfinite(value):
            raise ValueError(f"{self.col[name]} is not a finite number")
        return value


class _Builder:
    def __init__(self, mapping: Mapping, teams: dict[str, Team]) -> None:
        self.m = mapping
        self.teams = teams
        self.events: list[Event] = []
        self.score = {mapping.home: 0, mapping.away: 0}
        self.period: int | None = None
        self.first_half_end = 2700.0
        self.possession = 0
        self.poss_team: str | None = None

    def ts(self, period: int, clock_s: float) -> datetime:
        if period == 1:
            return self.m.kickoff + timedelta(seconds=clock_s)
        over = max(0.0, self.first_half_end - 2700.0)
        return self.m.kickoff + timedelta(seconds=clock_s + over + HALF_TIME_BREAK_S)

    def emit(self, etype: EventType, period: int, clock_s: float, **fields: Any) -> Event:
        seq = len(self.events)
        event = Event(
            event_id=f"{self.m.match_id}-{seq:05d}",
            match_id=self.m.match_id,
            seq=seq,
            ts=self.ts(period, clock_s),
            period=period,
            clock_s=clock_s,
            match_clock=format_clock(clock_s, period),
            type=etype,
            **fields,
        )
        self.events.append(event)
        return event

    def start(self) -> None:
        lineups = [
            LineupPlayer(player_id=p.player_id, team=tid, name=p.name, number=p.number, position=p.position)
            for tid in (self.m.home, self.m.away)
            for p in self.teams[tid].players
        ]
        self.emit(
            EventType.MATCH_START,
            1,
            0.0,
            lineups=lineups,
            details={"home": self.m.home, "away": self.m.away, "source": "generic_csv"},
        )

    def scores(self) -> dict[str, int]:
        return {"score_home": self.score[self.m.home], "score_away": self.score[self.m.away]}

    def enter_period(self, period: int, clock_s: float) -> None:
        if self.period == period:
            return
        if self.period is not None and period < self.period:
            raise ValueError("the period goes backwards")
        if self.period is not None:
            last = self.events[-1].clock_s
            self.emit(EventType.PERIOD_END, self.period, last, details=self.scores())
            self.first_half_end = last
        if period == 2 and self.period is None:
            self.emit(EventType.PERIOD_START, 1, 0.0)
            self.emit(EventType.PERIOD_END, 1, 2700.0, details=self.scores())
        self.period = period
        self.emit(EventType.PERIOD_START, period, 0.0 if period == 1 else 2700.0)
        self.poss_team = None

    def finish(self) -> None:
        if self.period is None:
            raise IngestError("The CSV has no rows")
        last = self.events[-1].clock_s
        self.emit(EventType.PERIOD_END, self.period, last, details=self.scores())
        self.emit(EventType.MATCH_END, self.period, last, details=self.scores())

    def player(self, ref: str, team: str) -> str | None:
        if not ref:
            return None
        if self.m.player_ref == "player_id":
            pid = ref.upper()
        else:
            try:
                number = int(float(ref))
            except ValueError:
                raise ValueError(f"player '{ref}' is not a shirt number") from None
            pid = f"{team}-{number}"
        if not any(p.player_id == pid for p in self.teams[team].players):
            raise ValueError(f"{team} has no player {ref}")
        return pid

    def point(self, rows: _Rows, row: list[str], xname: str, yname: str) -> Point | None:
        x, y = rows.number(row, xname), rows.number(row, yname)
        if x is None and y is None:
            return None
        if x is None or y is None:
            raise ValueError(f"{rows.col[xname]} and {rows.col[yname]} go together")
        spec = self.m.pitch
        if not (0 <= x <= spec.length and 0 <= y <= spec.width):
            raise ValueError(f"({x:g}, {y:g}) is off a {spec.length:g} x {spec.width:g} pitch")
        px = x * PITCH_LENGTH_M / spec.length
        py = y * PITCH_WIDTH_M / spec.width
        if spec.origin == "top_left":
            py = PITCH_WIDTH_M - py
        return Point(x=round(px, 2), y=round(py, 2))

    def row(self, rows: _Rows, row: list[str]) -> None:
        raw_type = rows.get(row, "type")
        etype_name = self.m.types.get(raw_type, raw_type.lower())
        try:
            etype = EventType(etype_name)
        except ValueError:
            raise ValueError(f"type '{raw_type}' is not a supported action") from None
        if etype not in ACTIONS:
            raise ValueError(f"type '{raw_type}' is not a supported action")
        minute = rows.number(row, "minute", required=True)
        second = rows.number(row, "second", required=True)
        assert minute is not None and second is not None
        if minute < 0 or not 0 <= second < 60 or minute != int(minute):
            raise ValueError("minute must be a whole number of 0 or more and second 0-59")
        clock_s = minute * 60 + second
        period_cell = rows.number(row, "period")
        period = int(period_cell) if period_cell is not None else (1 if clock_s < 2700 else 2)
        if period not in (1, 2):
            raise ValueError("period must be 1 or 2")
        team = rows.get(row, "team").upper()
        if team not in (self.m.home, self.m.away):
            raise ValueError(f"team '{team}' is not playing in this match")
        player = self.player(rows.get(row, "player"), team)
        raw_outcome = rows.get(row, "outcome")
        outcome_name = self.m.outcomes.get(raw_outcome, raw_outcome.lower()) if raw_outcome else ""
        allowed = OUTCOMES_BY_TYPE.get(etype)
        if allowed is not None and outcome_name not in allowed:
            raise ValueError(f"a {etype.value} needs an outcome of {', '.join(sorted(allowed))}")
        start = self.point(rows, row, "x", "y")
        end = self.point(rows, row, "end_x", "end_y") if etype in MOVES else None
        self.enter_period(period, clock_s)
        if self.events and clock_s < self.events[-1].clock_s:
            raise ValueError("rows must be in time order")
        if team != self.poss_team:
            self.possession += 1
            self.poss_team = team
        fields: dict[str, Any] = {"team": team, "player_id": player, "start": start, "end": end}
        fields["possession_id"] = self.possession
        details: dict[str, Any] = {}
        if etype == EventType.CARD:
            if player is None:
                raise ValueError("a card needs a player")
            details["card"] = outcome_name
        elif outcome_name:
            fields["outcome"] = Outcome(outcome_name)
        if etype == EventType.SHOT and outcome_name == "goal":
            self.score[team] += 1
            details.update(self.scores())
        self.emit(etype, period, clock_s, details=details, **fields)

    def link_receivers(self) -> None:
        """A completed pass is received by the next actor, when a teammate."""
        for i, e in enumerate(self.events[:-1]):
            if e.type == EventType.PASS and e.outcome == Outcome.COMPLETE:
                nxt = self.events[i + 1]
                if nxt.team == e.team and nxt.player_id and nxt.player_id != e.player_id:
                    self.events[i] = e.model_copy(update={"receiver_id": nxt.player_id})


def read_csv_feed(
    path: str | Path,
    mapping_path: str | Path,
    roster: dict[str, Team] | None,
    limits: Limits = DEFAULT_LIMITS,
) -> list[Event]:
    """Raw events built from a CSV feed (validated afterwards by validate_events)."""
    mapping = load_mapping(mapping_path)
    teams = resolve_teams([mapping.home, mapping.away], roster)
    if mapping.home == mapping.away:
        raise IngestError("home and away must be different clubs")
    text = Path(path).read_text(encoding="utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise IngestError("The CSV is empty") from None
    rows = _Rows(mapping, header)
    builder = _Builder(mapping, teams)
    builder.start()
    for lineno, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(builder.events) >= limits.max_events - 3:
            raise IngestError(f"The feed has more than {limits.max_events} events")
        if len(row) > len(header) + 2:
            raise IngestError(f"Row {lineno} has more cells than the header")
        try:
            builder.row(rows, row)
        except (ValueError, ValidationError) as exc:
            msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            raise IngestError(f"Row {lineno} is not valid", [msg]) from None
    builder.finish()
    builder.link_receivers()
    return builder.events
