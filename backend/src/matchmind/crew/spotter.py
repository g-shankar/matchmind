"""Spotter: rule-based on purpose, so the same match always yields the same
moments. It turns one event plus the stats engine's numbers into `Moment`s.

Each moment's `facts` hold every number later text may use, already rounded
the way it will be printed, plus the player and team names. Nothing here is
free text from outside: names come from our fictional squads, numbers from the
stats engine.
"""

from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass, field

from matchmind.crew.contracts import FactValue, Moment, MomentKind
from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator.teams import Team
from matchmind.stats.metrics import DISTANCE_MILESTONES_KM, ROCKET_SHOT_KMH, SPEED_BURST_KMH
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

# Distance is a lower-bound estimate from the event stream (roughly 0.2-3.8 km
# per player over a match), so milestones sit low and the text says "estimated".
BIG_CHANCE_XG = 0.3
HARD_PASS_DIFFICULTY = 60
HARD_PASS_GAP_S = 90.0
SPEED_BURST_GAP_S = 1200.0
MOMENTUM_WINDOW_S = 300.0
MOMENTUM_MIN_CHANGE = 40.0
MOMENTUM_MIN_SD = 1.5
MOMENTUM_MIN_SAMPLES = 30
MOMENTUM_GAP_S = 300.0
# A spell is either a territorial siege (field tilt) or a sustained press. The
# demo's scripted spells reach a pressure index of about 31-53 with 70-85% tilt.
PRESSURE_INDEX = 45.0
PRESSURE_TILT_PCT = 70.0
PRESSURE_SPELL_S = 180.0
DIFFICULTY_SCALE = 100

PRIORITY: dict[str, int] = {
    "goal": 95,
    "card.red": 85,
    "card.yellow": 60,
    "big_chance": 70,
    "better_option": 85,
    "unfound_run": 80,
    "momentum_swing": 65,
    "pressure_spell": 60,
    "speed_burst": 40,
    "rocket_shot": 55,
    "distance_milestone": 30,
    "hard_pass": 45,
    "milestone.kick_off": 50,
    "milestone.half_time": 75,
    "milestone.full_time": 90,
    "milestone.player": 50,
}

_APPEARANCE = re.compile(r"^(\d{1,4})(?:st|nd|rd|th) club appearance$")


def r1(x: float) -> float:
    return round(float(x), 1)


def r2(x: float) -> float:
    return round(float(x), 2)


def pct(x: float) -> int:
    return int(round(100 * float(x)))


def surname(name: str) -> str:
    return name.split()[-1] if name.split() else name


@dataclass
class _Welford:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, x: float) -> None:
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    @property
    def sd(self) -> float:
        return math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else 0.0


@dataclass
class _State:
    momentum: deque[tuple[int, float, float]] = field(default_factory=lambda: deque(maxlen=4000))
    momentum_changes: _Welford = field(default_factory=_Welford)
    last_swing_s: float | None = None
    pressure_start: dict[str, tuple[int, float] | None] = field(default_factory=dict)
    pressure_fired: dict[str, bool] = field(default_factory=dict)
    last_burst: dict[str, tuple[int, float]] = field(default_factory=dict)
    last_hard_pass: tuple[int, float] | None = None
    distance_done: dict[str, float] = field(default_factory=dict)


def _elapsed(period: int, clock_s: float) -> float:
    """Monotonic match time: period 1 stoppage time runs past 2700 s while
    period 2 restarts at 2700 s, so add an offset per period."""
    return (period - 1) * 10_000.0 + clock_s


class Spotter:
    def __init__(self, teams: dict[str, Team]) -> None:
        self.teams = teams
        self._names: dict[str, tuple[str, str]] = {}
        for team in teams.values():
            for p in team.players:
                self._names[p.player_id] = (p.name, team.team_id)
        self.state = _State()

    def reset(self) -> None:
        self.state = _State()

    # ---------------------------------------------------------- helpers

    def team_name(self, team_id: str | None) -> str | None:
        if team_id is None:
            return None
        team = self.teams.get(team_id)
        return team.name if team else None

    def _opponent(self, team_id: str, snapshot: MatchStateSnapshot) -> str:
        return snapshot.away_id if team_id == snapshot.home_id else snapshot.home_id

    def _player_name(self, pid: str | None) -> str | None:
        if pid is None:
            return None
        known = self._names.get(pid)
        return known[0] if known else None

    def _base(self, snapshot: MatchStateSnapshot, team_id: str | None) -> dict[str, FactValue]:
        facts: dict[str, FactValue] = {"match_clock": snapshot.match_clock}
        home, away = self.team_name(snapshot.home_id), self.team_name(snapshot.away_id)
        if home:
            facts["home"] = home
        if away:
            facts["away"] = away
        if team_id:
            name = self.team_name(team_id)
            opp = self.team_name(self._opponent(team_id, snapshot))
            if name:
                facts["team"] = name
            if opp:
                facts["opp"] = opp
        return facts

    def _player_facts(
        self, prefix: str, pid: str | None, players: dict[str, PlayerStats]
    ) -> dict[str, FactValue]:
        name = self._player_name(pid)
        if not name or pid is None:
            return {}
        facts: dict[str, FactValue] = {prefix: name, f"{prefix}_short": surname(name)}
        if prefix == "player":
            ps = players.get(pid)
            if ps is not None:
                facts.update(
                    p_goals=ps.goals,
                    p_assists=ps.assists,
                    p_shots=ps.shots,
                    p_xg=r2(ps.xg),
                    p_xa=r2(ps.xa),
                    p_key_passes=ps.key_passes,
                    sprints=ps.sprints,
                    top_speed_kmh=r1(ps.top_speed_kmh),
                )
        return facts

    def _moment(
        self,
        kind: MomentKind,
        key: str,
        event: Event,
        snapshot: MatchStateSnapshot,
        facts: dict[str, FactValue],
        team_id: str | None,
        player_ids: list[str],
        suffix: str = "",
        source_ids: list[str] | None = None,
    ) -> Moment:
        return Moment(
            moment_id=f"{kind.value}{suffix}-{event.event_id}",
            kind=kind,
            clock_s=event.clock_s,
            match_clock=event.match_clock,
            period=event.period,
            team=team_id,
            player_ids=[p for p in player_ids if p],
            facts=facts,
            source_event_ids=source_ids or [event.event_id],
            priority=PRIORITY[key],
        )

    # ------------------------------------------------------------- spot

    def spot(
        self,
        event: Event,
        metrics: EventMetrics,
        snapshot: MatchStateSnapshot,
        players: dict[str, PlayerStats],
    ) -> list[Moment]:
        out: list[Moment] = []
        out += self._milestones(event, snapshot, players)
        out += self._shots(event, metrics, snapshot, players)
        out += self._card(event, snapshot, players)
        out += self._better_option(event, metrics, snapshot, players)
        out += self._unfound_run(event, metrics, snapshot, players)
        out += self._hard_pass(event, metrics, snapshot, players)
        out += self._speed_burst(event, metrics, snapshot, players)
        out += self._distance(event, snapshot, players)
        out += self._momentum(event, snapshot)
        out += self._pressure(event, snapshot)
        return out

    # ------------------------------------------------------- milestones

    def _milestones(self, event: Event, snapshot: MatchStateSnapshot, players) -> list[Moment]:
        phase = None
        if event.type == EventType.PERIOD_START and event.period == 1:
            phase = "kick_off"
        elif event.type == EventType.PERIOD_END and event.period == 1:
            phase = "half_time"
        elif event.type == EventType.MATCH_END:
            phase = "full_time"
        if phase:
            facts = self._base(snapshot, None)
            facts["phase"] = phase
            if phase != "kick_off":
                facts.update(
                    # The score is the engine's, never a number copied from the feed.
                    score_home=snapshot.score_home,
                    score_away=snapshot.score_away,
                    xg_home=r2(snapshot.xg_home),
                    xg_away=r2(snapshot.xg_away),
                    shots_home=snapshot.shots_home,
                    shots_away=snapshot.shots_away,
                )
            return [
                self._moment(MomentKind.MILESTONE, f"milestone.{phase}", event, snapshot, facts, None, [])
            ]
        if event.type == EventType.MILESTONE and event.player_id and event.team:
            facts = self._base(snapshot, event.team)
            facts.update(self._player_facts("player", event.player_id, players))
            if "player" not in facts:
                return []
            facts["phase"] = "player"
            label = event.details.get("label")
            m = _APPEARANCE.match(label) if isinstance(label, str) else None
            if m:
                n = int(m.group(1))
                facts["appearance_n"] = n
            return [
                self._moment(
                    MomentKind.MILESTONE,
                    "milestone.player",
                    event,
                    snapshot,
                    facts,
                    event.team,
                    [event.player_id],
                )
            ]
        return []

    # ------------------------------------------------------------ shots

    def _shots(self, event, metrics: EventMetrics, snapshot, players) -> list[Moment]:
        if event.type != EventType.SHOT or not event.team or not event.player_id:
            return []
        facts = self._base(snapshot, event.team)
        facts.update(self._player_facts("player", event.player_id, players))
        if "player" not in facts:
            return []
        outcome = event.outcome.value if event.outcome else ""
        facts["outcome"] = outcome
        if metrics.chance_quality is not None:
            facts["xg"] = r2(metrics.chance_quality)
            facts["xg_pct"] = pct(metrics.chance_quality)
        if metrics.distance_to_goal_m is not None:
            facts["distance_m"] = int(round(metrics.distance_to_goal_m))
        if metrics.ball_speed_kmh is not None:
            facts["shot_speed_kmh"] = int(round(metrics.ball_speed_kmh))
        if metrics.pitch_zone:
            facts["pitch_zone"] = metrics.pitch_zone
        out: list[Moment] = []
        if event.outcome == Outcome.GOAL:
            g = dict(facts)
            g["score_home"] = snapshot.score_home  # the engine's score, never the feed's
            g["score_away"] = snapshot.score_away
            assist_id = event.details.get("assist_id")
            ids = [event.player_id]
            if isinstance(assist_id, str):
                g.update(self._player_facts("assist", assist_id, players))
                if "assist" in g:
                    ids.append(assist_id)
            out.append(self._moment(MomentKind.GOAL, "goal", event, snapshot, g, event.team, ids))
        elif (metrics.chance_quality or 0.0) >= BIG_CHANCE_XG:
            out.append(
                self._moment(
                    MomentKind.BIG_CHANCE, "big_chance", event, snapshot, facts, event.team, [event.player_id]
                )
            )
        if (metrics.ball_speed_kmh or 0.0) >= ROCKET_SHOT_KMH:
            out.append(
                self._moment(
                    MomentKind.ROCKET_SHOT,
                    "rocket_shot",
                    event,
                    snapshot,
                    dict(facts),
                    event.team,
                    [event.player_id],
                )
            )
        return out

    def _card(self, event, snapshot, players) -> list[Moment]:
        if event.type != EventType.CARD or not event.team or not event.player_id:
            return []
        colour = "red" if str(event.details.get("card", "yellow")) == "red" else "yellow"
        facts = self._base(snapshot, event.team)
        facts.update(self._player_facts("player", event.player_id, players))
        if "player" not in facts:
            return []
        facts["card"] = colour
        return [
            self._moment(
                MomentKind.CARD, f"card.{colour}", event, snapshot, facts, event.team, [event.player_id]
            )
        ]

    # -------------------------------------------------- better decisions

    def _better_option(self, event, metrics: EventMetrics, snapshot, players) -> list[Moment]:
        bo = metrics.better_option
        if bo is None or not event.team:
            return []
        facts = self._base(snapshot, event.team)
        facts.update(self._player_facts("player", bo.shooter_id, players))
        facts.update(self._player_facts("teammate", bo.teammate_id, players))
        if "player" not in facts or "teammate" not in facts:
            return []
        facts.update(
            shot_xg=r2(bo.shot_chance_quality),
            alt_xg=r2(bo.alt_chance_quality),
            pass_success_pct=pct(bo.pass_success),
            alt_value=r2(bo.alt_value),
            times_better=r1(bo.times_better),
            pass_distance_m=int(round(bo.pass_distance_m)),
            nearest_marker_m=r1(bo.nearest_marker_m),
        )
        return [
            self._moment(
                MomentKind.BETTER_OPTION,
                "better_option",
                event,
                snapshot,
                facts,
                event.team,
                [bo.shooter_id, bo.teammate_id],
                source_ids=list(dict.fromkeys([bo.shot_event_id, event.event_id])),
            )
        ]

    def _unfound_run(self, event, metrics: EventMetrics, snapshot, players) -> list[Moment]:
        ur = metrics.unfound_run
        if ur is None or ur.found or not event.team:
            return []
        facts = self._base(snapshot, event.team)
        facts.update(self._player_facts("player", ur.carrier_id, players))
        facts.update(self._player_facts("runner", ur.runner_id, players))
        if "player" not in facts or "runner" not in facts:
            return []
        facts.update(
            pass_on_clock=ur.pass_on_clock,
            pass_on_at_s=r1(ur.pass_on_at_s),
            clear_of_line_m=r1(ur.clear_of_line_m),
            projected_xg=r2(ur.projected_chance_quality),
            projected_xg_pct=pct(ur.projected_chance_quality),
            one_on_one=ur.one_on_one,
        )
        return [
            self._moment(
                MomentKind.UNFOUND_RUN,
                "unfound_run",
                event,
                snapshot,
                facts,
                event.team,
                [ur.carrier_id, ur.runner_id],
                source_ids=list(dict.fromkeys([ur.run_event_id, event.event_id])),
            )
        ]

    def _hard_pass(self, event, metrics: EventMetrics, snapshot, players) -> list[Moment]:
        if (
            event.type != EventType.PASS
            or event.outcome != Outcome.COMPLETE
            or (metrics.pass_difficulty or 0) < HARD_PASS_DIFFICULTY
            or not event.team
            or not event.player_id
        ):
            return []
        now = _elapsed(event.period, event.clock_s)
        last = self.state.last_hard_pass
        if last is not None and 0 <= now - _elapsed(*last) < HARD_PASS_GAP_S:
            return []
        facts = self._base(snapshot, event.team)
        facts.update(self._player_facts("player", event.player_id, players))
        facts.update(self._player_facts("receiver", event.receiver_id, players))
        if "player" not in facts or "receiver" not in facts:
            return []
        facts.update(
            pass_difficulty=int(metrics.pass_difficulty or 0),
            difficulty_scale=DIFFICULTY_SCALE,
            pass_distance_m=int(round(metrics.pass_distance_m or 0.0)),
            progressive=metrics.progressive,
        )
        if metrics.xt_delta is not None and r2(metrics.xt_delta) > 0:
            facts["xt_delta"] = r2(metrics.xt_delta)
        self.state.last_hard_pass = (event.period, event.clock_s)
        return [
            self._moment(
                MomentKind.HARD_PASS,
                "hard_pass",
                event,
                snapshot,
                facts,
                event.team,
                [event.player_id, event.receiver_id or ""],
            )
        ]

    # ------------------------------------------------------ physical tags

    def _speed_burst(self, event, metrics: EventMetrics, snapshot, players) -> list[Moment]:
        speed = metrics.player_speed_kmh
        if speed is None or speed < SPEED_BURST_KMH or not event.player_id or not event.team:
            return []
        now = _elapsed(event.period, event.clock_s)
        last = self.state.last_burst.get(event.player_id)
        if last is not None and 0 <= now - _elapsed(*last) < SPEED_BURST_GAP_S:
            return []
        facts = self._base(snapshot, event.team)
        facts.update(self._player_facts("player", event.player_id, players))
        if "player" not in facts:
            return []
        facts["speed_kmh"] = r1(speed)
        facts["speed_threshold_kmh"] = int(SPEED_BURST_KMH)
        facts.setdefault("top_speed_kmh", r1(speed))
        facts["top_speed_kmh"] = max(float(facts["top_speed_kmh"]), r1(speed))
        facts.setdefault("sprints", 1)
        self.state.last_burst[event.player_id] = (event.period, event.clock_s)
        return [
            self._moment(
                MomentKind.SPEED_BURST, "speed_burst", event, snapshot, facts, event.team, [event.player_id]
            )
        ]

    def _distance(self, event, snapshot, players: dict[str, PlayerStats]) -> list[Moment]:
        out: list[Moment] = []
        for pid in sorted(players):
            ps = players[pid]
            done = self.state.distance_done.get(pid, 0.0)
            crossed = [km for km in DISTANCE_MILESTONES_KM if done < km <= ps.distance_km]
            if not crossed:
                continue
            km = max(crossed)
            self.state.distance_done[pid] = km
            facts = self._base(snapshot, ps.team)
            facts.update(self._player_facts("player", pid, players))
            if "player" not in facts:
                continue
            facts["milestone_km"] = int(km) if float(km).is_integer() else r1(km)
            out.append(
                self._moment(
                    MomentKind.DISTANCE_MILESTONE,
                    "distance_milestone",
                    event,
                    snapshot,
                    facts,
                    ps.team,
                    [pid],
                    suffix=f"-{pid}-{facts['milestone_km']}",
                )
            )
        return out

    # ---------------------------------------------------------- team flow

    def _team_facts(self, snapshot: MatchStateSnapshot, team_id: str) -> dict[str, FactValue]:
        window = snapshot.home if team_id == snapshot.home_id else snapshot.away
        total_xg = snapshot.xg_home if team_id == snapshot.home_id else snapshot.xg_away
        facts = self._base(snapshot, team_id)
        facts.update(
            team_field_tilt_pct=int(round(window.field_tilt_pct)),
            team_possession_pct=int(round(window.possession_pct)),
            team_shots_5=window.shots,
            team_box_entries_5=window.box_entries,
            team_xg_total=r2(total_xg),
            window_min=int(MOMENTUM_WINDOW_S // 60),
        )
        return facts

    def _momentum(self, event, snapshot: MatchStateSnapshot) -> list[Moment]:
        st = self.state
        now = _elapsed(snapshot.period, snapshot.clock_s)
        st.momentum.append((snapshot.period, snapshot.clock_s, snapshot.momentum))
        past = None
        for period, clock, value in reversed(st.momentum):
            if period == snapshot.period and clock <= snapshot.clock_s - MOMENTUM_WINDOW_S:
                past = value
                break
        if past is None:
            return []
        change = snapshot.momentum - past
        sd = st.momentum_changes.sd
        enough = st.momentum_changes.n >= MOMENTUM_MIN_SAMPLES
        st.momentum_changes.add(change)
        if abs(change) < MOMENTUM_MIN_CHANGE or (enough and abs(change) < MOMENTUM_MIN_SD * sd):
            return []
        if st.last_swing_s is not None and 0 <= now - st.last_swing_s < MOMENTUM_GAP_S:
            return []
        st.last_swing_s = now
        team_id = snapshot.home_id if change > 0 else snapshot.away_id
        facts = self._team_facts(snapshot, team_id)
        facts["momentum_change"] = int(round(abs(change)))
        return [
            self._moment(MomentKind.MOMENTUM_SWING, "momentum_swing", event, snapshot, facts, team_id, [])
        ]

    def _pressure(self, event, snapshot: MatchStateSnapshot) -> list[Moment]:
        out: list[Moment] = []
        st = self.state
        for team_id, window in ((snapshot.home_id, snapshot.home), (snapshot.away_id, snapshot.away)):
            start = st.pressure_start.get(team_id)
            if window.pressure_index < PRESSURE_INDEX and window.field_tilt_pct < PRESSURE_TILT_PCT:
                st.pressure_start[team_id] = None
                st.pressure_fired[team_id] = False
                continue
            if start is None or start[0] != snapshot.period:
                st.pressure_start[team_id] = (snapshot.period, snapshot.clock_s)
                st.pressure_fired[team_id] = False
                continue
            if st.pressure_fired.get(team_id) or snapshot.clock_s - start[1] < PRESSURE_SPELL_S:
                continue
            st.pressure_fired[team_id] = True
            facts = self._team_facts(snapshot, team_id)
            facts["pressure_index"] = int(round(window.pressure_index))
            facts["spell_min"] = int(PRESSURE_SPELL_S // 60)
            out.append(
                self._moment(
                    MomentKind.PRESSURE_SPELL,
                    "pressure_spell",
                    event,
                    snapshot,
                    facts,
                    team_id,
                    [],
                    suffix=f"-{team_id}",
                )
            )
        return out
