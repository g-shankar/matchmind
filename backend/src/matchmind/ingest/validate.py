"""Strict checks and id normalisation, shared by every way a match gets in.

Files (`feed.py`), the generic CSV adapter (`csv_feed.py`) and the live Event
Hubs stream (`stream.py`) all end here, so a feed is held to exactly the same
rules whatever door it came through:

- one match, starting with `match_start` (home, away and line-ups), clubs that are
  bundled or in the roster, line-up players that match the roster by shirt number
  and name, and no real names anywhere (the fact-checker's banned list);
- every player reference (actor, receiver, pressure, freeze frames, tracking and
  `*_id` details) is in the line-up and every team is home or away;
- the match clock never runs backwards (`(period, clock_s)` non-decreasing, ties
  allowed: several events in the same second are normal), clocks stay in their
  half, and `ts` never runs backwards;
- size caps on everything an outsider controls (events, details, labels, frames).

Normalising: match and club ids are upper-cased, player ids become
`<team>-<number>`, and event ids
become `<match_id>-<seq:05d>`. On the bundled matches this changes nothing.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from matchmind.crew.fact_checker import banned_names_in
from matchmind.schema import Event, EventType, FramePlayer, LineupPlayer, TrackingFrame
from matchmind.simulator.teams import Team

from .errors import IngestError
from .roster import POSITION_RE, check_name, resolve_teams


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 20 * 1024 * 1024  # whole file
    max_line_bytes: int = 256 * 1024  # one event (a match_start with line-ups is about 3 KB)
    max_events: int = 10_000  # a bundled match has about 2,100
    max_detail_keys: int = 16
    max_detail_chars: int = 80
    max_labels: int = 8
    max_frame_players: int = 22
    max_tracking_frames: int = 20
    max_pressure_players: int = 11


DEFAULT_LIMITS = Limits()

MATCH_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,31}$")
CLOCK_RE = re.compile(r"^\d{2,3}(?:\+\d{1,2})?:\d{2}$")
DETAIL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
LABEL_RE = re.compile(r"^[a-z_]{1,32}(?::[A-Za-z0-9_\-]{1,40})?$")
MAX_BALL_SPEED_MPS = 60.0
MAX_PLAYER_SPEED_MPS = 15.0
HALF_S, FULL_S, MAX_STOPPAGE_S = 2700.0, 5400.0, 1800.0
PERIOD_BOUNDS = {1: (0.0, HALF_S + MAX_STOPPAGE_S), 2: (HALF_S, FULL_S + MAX_STOPPAGE_S)}


def _plain(text: str, what: str, limit: int) -> None:
    if len(text) > limit:
        raise IngestError(f"{what} is longer than {limit} characters")
    if any(not ch.isprintable() for ch in text):
        raise IngestError(f"{what} contains control characters")
    if banned_names_in(text):
        raise IngestError(f"{what} mentions a real name; use invented names only")


@dataclass
class MatchContext:
    """What every later event of a match is checked against, built from its match_start."""

    match_id: str
    home: str
    away: str
    teams: dict[str, Team]
    id_map: dict[str, str]  # player id as the feed wrote it -> canonical <team>-<number>
    team_of: dict[str, str]  # canonical player id -> team
    limits: Limits = field(default=DEFAULT_LIMITS)

    @classmethod
    def from_start(
        cls, start: Event, roster: dict[str, Team] | None = None, limits: Limits = DEFAULT_LIMITS
    ) -> MatchContext:
        if start.type != EventType.MATCH_START:
            raise IngestError("A feed must begin with a match_start event")
        match_id = start.match_id.strip().upper()
        if not MATCH_ID_RE.match(match_id):
            raise IngestError("match_id must be 3-32 capital letters, digits or hyphens")
        home = str(start.details.get("home", "")).strip().upper()
        away = str(start.details.get("away", "")).strip().upper()
        if not home or not away or home == away:
            raise IngestError("match_start needs details.home and details.away (two different clubs)")
        teams = resolve_teams([home, away], roster)
        if not start.lineups:
            raise IngestError("match_start needs the line-ups")
        if len(start.lineups) > 50:
            raise IngestError("match_start has more than 50 line-up entries")
        id_map: dict[str, str] = {}
        team_of: dict[str, str] = {}
        for lp in start.lineups:
            team_id = lp.team.strip().upper()
            if team_id not in teams:
                raise IngestError(f"Line-up player {lp.player_id[:32]} plays for a club not in this match")
            by_number = {p.number: p for p in teams[team_id].players}
            player = by_number.get(lp.number)
            if player is None:
                raise IngestError(f"{team_id} has no number {lp.number} in its roster")
            try:
                name = check_name(lp.name, "Line-up name")
            except ValueError as exc:
                raise IngestError(str(exc)) from None
            if name != player.name:
                raise IngestError(f"Line-up name for {team_id} number {lp.number} does not match the roster")
            if lp.player_id in id_map or player.player_id in team_of:
                raise IngestError(f"{player.player_id} appears twice in the line-ups")
            id_map[lp.player_id] = player.player_id
            team_of[player.player_id] = team_id
        for tid in (home, away):
            if sum(t == tid for t in team_of.values()) < 7:
                raise IngestError(f"{tid} needs at least 7 players in the line-up")
        for canonical in list(team_of):
            id_map.setdefault(canonical, canonical)  # canonical ids are always accepted too
        return cls(match_id, home, away, teams, id_map, team_of, limits)

    # --- one event --------------------------------------------------------------------------

    def _player(self, pid: str | None, where: str) -> str | None:
        if pid is None:
            return None
        canonical = self.id_map.get(pid)
        if canonical is None:
            raise IngestError(f"{where} '{pid[:32]}' is not in the line-ups")
        return canonical

    def _team(self, team: str | None, where: str) -> str | None:
        if team is None:
            return None
        tid = team.strip().upper()
        if tid not in (self.home, self.away):
            raise IngestError(f"{where} '{team[:16]}' is not playing in this match")
        return tid

    def _frame_players(self, players: list[FramePlayer], where: str) -> list[FramePlayer]:
        if len(players) > self.limits.max_frame_players:
            raise IngestError(f"{where} lists more than {self.limits.max_frame_players} players")
        out = []
        for fp in players:
            pid = self._player(fp.player_id, f"{where} player")
            assert pid is not None
            team = self._team(fp.team, f"{where} team")
            if team != self.team_of[pid]:
                raise IngestError(f"{where} puts {pid} in the wrong team")
            out.append(fp.model_copy(update={"player_id": pid, "team": team}))
        return out

    def _details(self, details: dict[str, Any]) -> dict[str, Any]:
        lim = self.limits
        if len(details) > lim.max_detail_keys:
            raise IngestError(f"details has more than {lim.max_detail_keys} keys")
        out: dict[str, Any] = {}
        for key, value in details.items():
            if not DETAIL_KEY_RE.match(key):
                raise IngestError(f"details key '{key[:32]}' must be lower_snake_case, at most 32 characters")
            if isinstance(value, float) and not math.isfinite(value):
                raise IngestError(f"details.{key} is not a finite number")
            if isinstance(value, str):
                _plain(value, f"details.{key}", lim.max_detail_chars)
                if key.endswith("_id") or key in PLAYER_DETAIL_KEYS:
                    value = self._player(value, f"details.{key}")
                elif key in ("home", "away"):
                    value = value.strip().upper()
            elif key.endswith("_id") or key in PLAYER_DETAIL_KEYS or key in ("home", "away"):
                raise IngestError(f"details.{key} must be text")
            out[key] = _check_known_detail(key, value)
        return out

    def normalise(self, event: Event, seq: int) -> Event:
        """Check one event against the match and return its canonical form."""
        lim = self.limits
        if event.match_id.strip().upper() != self.match_id:
            raise IngestError("Every event must belong to the same match")
        if not CLOCK_RE.match(event.match_clock):
            raise IngestError("match_clock looks like '67:20' or '90+2:15'")
        lo, hi = PERIOD_BOUNDS[event.period]
        if not lo <= event.clock_s <= hi:
            raise IngestError(f"clock_s {event.clock_s:g} is outside period {event.period}")
        if event.ts.tzinfo is None or event.ts.utcoffset() is None:
            raise IngestError("ts must carry a time zone (UTC, ending in Z)")
        for name, value, cap in (
            ("ball_speed_mps", event.ball_speed_mps, MAX_BALL_SPEED_MPS),
            ("player_speed_mps", event.player_speed_mps, MAX_PLAYER_SPEED_MPS),
        ):
            if value is not None and not (math.isfinite(value) and value <= cap):
                raise IngestError(f"{name} must be at most {cap:g} m/s")
        if event.lineups is not None and event.type != EventType.MATCH_START:
            raise IngestError("Only match_start carries line-ups")
        if len(event.labels) > lim.max_labels or any(not LABEL_RE.match(lb) for lb in event.labels):
            raise IngestError(f"labels: at most {lim.max_labels}, each like 'scripted:goal'")
        if len(event.pressure_players) > lim.max_pressure_players:
            raise IngestError(f"pressure_players lists more than {lim.max_pressure_players} players")
        team = self._team(event.team, "team")
        player = self._player(event.player_id, "player_id")
        if player is not None and team is not None and self.team_of[player] != team:
            raise IngestError(f"player_id {player} does not play for {team}")
        if player is not None and team is None:
            team = self.team_of[player]
        update: dict[str, Any] = {
            "event_id": f"{self.match_id}-{seq:05d}",
            "match_id": self.match_id,
            "seq": seq,
            "team": team,
            "player_id": player,
            "receiver_id": self._player(event.receiver_id, "receiver_id"),
            "pressure_players": [self._player(p, "pressure_players") for p in event.pressure_players],
            "details": self._details(event.details),
        }
        if event.freeze_frame is not None:
            update["freeze_frame"] = self._frame_players(event.freeze_frame, "freeze_frame")
        if event.tracking is not None:
            if len(event.tracking) > lim.max_tracking_frames:
                raise IngestError(f"tracking has more than {lim.max_tracking_frames} frames")
            update["tracking"] = [
                TrackingFrame(
                    t_offset_s=f.t_offset_s, ball=f.ball, players=self._frame_players(f.players, "tracking")
                )
                for f in event.tracking
            ]
        if event.type == EventType.MATCH_START:
            assert event.lineups is not None
            update["lineups"] = [self._lineup(lp) for lp in event.lineups]
        return event.model_copy(update=update)

    def _lineup(self, lp: LineupPlayer) -> LineupPlayer:
        pid = self.id_map[lp.player_id]
        team = self.teams[self.team_of[pid]]
        player = team.player(pid)
        position = lp.position.strip().upper()
        if not POSITION_RE.match(position):
            raise IngestError("Line-up positions are 1-4 capital letters, e.g. GK, RCB, CAM, ST")
        _plain(position, "Line-up position", 8)
        return LineupPlayer(
            player_id=pid, team=team.team_id, name=player.name, number=player.number, position=position
        )


# Detail keys other code reads: their types and ranges are fixed, whatever the source.
PLAYER_DETAIL_KEYS = frozenset({"blocked_by"})
DETAIL_INTS = {"score_home": (0, 99), "score_away": (0, 99), "seed": (0, 2**31 - 1)}
DETAIL_CHOICES = {
    "card": frozenset({"yellow", "red"}),
    "pass_type": frozenset({"ground", "cross", "through_ball", "kickoff"}),
}


def _check_known_detail(key: str, value: Any) -> Any:
    if key in DETAIL_INTS:
        lo, hi = DETAIL_INTS[key]
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise IngestError(f"details.{key} must be a whole number from {lo} to {hi}")
    elif key in DETAIL_CHOICES and value not in DETAIL_CHOICES[key]:
        raise IngestError(f"details.{key} must be one of {', '.join(sorted(DETAIL_CHOICES[key]))}")
    return value


class ClockGuard:
    """The order rules: seq strictly up, (period, clock_s) and ts never back."""

    def __init__(self) -> None:
        self.last: Event | None = None

    def check(self, event: Event) -> None:
        last = self.last
        if last is not None:
            if event.seq <= last.seq:
                raise IngestError(f"seq {event.seq} is not after {last.seq}")
            if (event.period, event.clock_s) < (last.period, last.clock_s):
                raise IngestError(
                    f"the match clock runs backwards at seq {event.seq} ({event.match_clock} after "
                    f"{last.match_clock})"
                )
            if event.ts < last.ts:
                raise IngestError(f"ts runs backwards at seq {event.seq}")
            if last.type == EventType.MATCH_END:
                raise IngestError("Nothing may follow match_end")
        if event.type == EventType.MATCH_START and last is not None:
            raise IngestError("A feed holds exactly one match_start")
        self.last = event


def validate_events(
    events: list[Event],
    roster: dict[str, Team] | None = None,
    limits: Limits = DEFAULT_LIMITS,
    require_end: bool = True,
) -> tuple[list[Event], dict[str, Team]]:
    """A whole match, checked and normalised. Raises IngestError with the first problem."""
    if not events:
        raise IngestError("The feed is empty")
    if len(events) > limits.max_events:
        raise IngestError(f"The feed has more than {limits.max_events} events")
    ctx = MatchContext.from_start(events[0], roster, limits)
    guard = ClockGuard()
    seen_ids: set[str] = set()
    out: list[Event] = []
    for i, event in enumerate(events):
        if event.event_id in seen_ids:
            raise IngestError(f"event_id '{event.event_id[:48]}' appears twice")
        seen_ids.add(event.event_id)
        try:
            guard.check(event)
            out.append(ctx.normalise(event, seq=i))
        except IngestError as exc:
            raise IngestError(f"Event {i} (seq {event.seq}) is not valid", [str(exc)]) from None
    if require_end and out[-1].type != EventType.MATCH_END:
        raise IngestError("The feed must end with a match_end event")
    return out, ctx.teams
