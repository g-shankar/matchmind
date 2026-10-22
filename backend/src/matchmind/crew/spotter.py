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

from matchmind.crew.contracts import FactValue, Moment, MomentKind, PlayerRef
from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator import pitch
from matchmind.simulator.teams import Team
from matchmind.stats import metrics as stats_metrics
from matchmind.stats.metrics import DISTANCE_MILESTONES_KM, ROCKET_SHOT_KMH, SPEED_BURST_KMH
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

# Distance milestones and tracking speed bursts need the synthetic tracking
# (stats.physical); without it distance is a sparse lower bound and milestones
# never fire. Texts say the distance is estimated.
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
# Key tackle: won in the tackler's own third (attacking-frame x < 35) where the
# attackers' expected threat at the spot was at least 0.09 (about the last 25 m
# in front of goal). Inside the own box it is "last-ditch". One per 5 minutes.
KEY_TACKLE_OWN_THIRD_U = 35.0
KEY_TACKLE_XT = 0.09
KEY_TACKLE_GAP_S = 300.0

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
    "key_tackle": 62,
    "milestone.kick_off": 50,
    "milestone.half_time": 75,
    "milestone.full_time": 90,
    "milestone.player": 50,
    "correction": 95,
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
    distance_done: dict[str, float] = field(default_factory=dict)  # team -> highest milestone reached
    last_key_tackle: tuple[int, float] | None = None
    prev_event: Event | None = None


def goal_moment_id(shot_event_id: str) -> str:
    """The id the spotter gives the goal moment of a shot."""
    return f"{MomentKind.GOAL.value}-{shot_event_id}"


def _elapsed(period: int, clock_s: float) -> float:
    """Monotonic match time: period 1 stoppage time runs past 2700 s while
    period 2 restarts at 2700 s, so add an offset per period."""
    return (period - 1) * 10_000.0 + clock_s


class Spotter:
    def __init__(self, teams: dict[str, Team]) -> None:
        self.teams = teams
        self._names: dict[str, tuple[str, str]] = {}
        self._refs: dict[str, PlayerRef] = {}
        for team in teams.values():
            for p in team.players:
                self._names[p.player_id] = (p.name, team.team_id)
                self._refs[p.player_id] = PlayerRef(
                    player_id=p.player_id,
                    name=p.name,
                    number=p.number,
                    team=team.team_id,
                    position=p.position,
                )
        self.state = _State()

    def reset(self) -> None:
        self.state = _State()

    def restore(self, moments: list[Moment]) -> None:
        """After a reset for a jump: remember the once-only and rate-limited
        moments already made, so playing on does not repeat them."""
        st = self.state
        for m in moments:
            when = (m.period, m.clock_s)
            if m.kind == MomentKind.DISTANCE_MILESTONE and m.team:
                km = m.facts.get("milestone_km")
                if isinstance(km, int | float) and not isinstance(km, bool):
                    st.distance_done[m.team] = max(st.distance_done.get(m.team, 0.0), float(km))
            elif m.kind == MomentKind.SPEED_BURST and m.player_ids:
                st.last_burst[m.player_ids[0]] = when
            elif m.kind == MomentKind.KEY_TACKLE:
                st.last_key_tackle = when
            elif m.kind == MomentKind.HARD_PASS:
                st.last_hard_pass = when

    def player_refs(self, player_ids: list[str]) -> list[PlayerRef]:
        """Name, shirt number, team and position of each known player, in order."""
        return [self._refs[p].model_copy() for p in player_ids if p in self._refs]

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
                    p_tackles_won=ps.tackles_won,
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
        ids = [p for p in player_ids if p]
        return Moment(
            moment_id=f"{kind.value}{suffix}-{event.event_id}",
            kind=kind,
            clock_s=event.clock_s,
            match_clock=event.match_clock,
            period=event.period,
            team=team_id,
            player_ids=ids,
            players=self.player_refs(ids),
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
        out += self._correction(event, metrics, snapshot, players)
        out += self._card(event, snapshot, players)
        out += self._better_option(event, metrics, snapshot, players)
        out += self._unfound_run(event, metrics, snapshot, players)
        out += self._hard_pass(event, metrics, snapshot, players)
        out += self._key_tackle(event, snapshot, players)
        if metrics.sprint_efforts is not None:
            out += self._tracked_bursts(event, metrics, snapshot, players)
        else:
            out += self._speed_burst(event, metrics, snapshot, players)
        out += self._distance(event, snapshot, players)
        out += self._momentum(event, snapshot)
        out += self._pressure(event, snapshot)
        self.state.prev_event = event
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

    def _correction(self, event, metrics: EventMetrics, snapshot, players) -> list[Moment]:
        """A VAR review that took a goal off the score: one correction moment that
        rules the goal moment out. A review that changed nothing (the goal stands,
        or it was already ruled out, or it names an unknown event) says nothing."""
        vd = metrics.var_decision
        if vd is None or not vd.goal_removed or not vd.team or not vd.player_id:
            return []
        facts = self._base(snapshot, vd.team)
        facts.update(self._player_facts("player", vd.player_id, players))
        if "player" not in facts:
            return []
        facts.update(
            decision=vd.outcome,
            reason=vd.reason or "offside",
            score_home=vd.score_home,
            score_away=vd.score_away,
        )
        if vd.reviewed_clock:
            facts["ruled_out_clock"] = vd.reviewed_clock
        moment = self._moment(
            MomentKind.CORRECTION,
            "correction",
            event,
            snapshot,
            facts,
            vd.team,
            [vd.player_id] + ([vd.assist_id] if vd.assist_id else []),
            source_ids=[event.event_id, vd.reviewed_event_id],
        )
        moment.retracts = [goal_moment_id(vd.reviewed_event_id)]
        return [moment]

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

    def _tracked_bursts(self, event, metrics: EventMetrics, snapshot, players) -> list[Moment]:
        """Speed bursts from the synthetic tracking: a sprint that peaked at or
        over the burst line since the last event, at most one per player per
        20 minutes."""
        out: list[Moment] = []
        for sprint in metrics.sprint_efforts or []:
            pid = sprint.player_id
            known = self._names.get(pid)
            if known is None or sprint.peak_kmh < SPEED_BURST_KMH:
                continue
            now = _elapsed(sprint.period, sprint.peak_clock_s)
            last = self.state.last_burst.get(pid)
            if last is not None and 0 <= now - _elapsed(*last) < SPEED_BURST_GAP_S:
                continue
            team = known[1]
            facts = self._base(snapshot, team)
            facts.update(self._player_facts("player", pid, players))
            facts["speed_kmh"] = r1(sprint.peak_kmh)
            facts["speed_threshold_kmh"] = int(SPEED_BURST_KMH)
            facts["top_speed_kmh"] = max(float(facts.get("top_speed_kmh", 0.0)), r1(sprint.peak_kmh))
            facts["sprints"] = max(int(facts.get("sprints", 0)), 1)
            facts["sprint_m"] = int(round(sprint.distance_m))
            facts["source"] = "synthetic_tracking"
            self.state.last_burst[pid] = (sprint.period, sprint.peak_clock_s)
            out.append(
                self._moment(
                    MomentKind.SPEED_BURST,
                    "speed_burst",
                    event,
                    snapshot,
                    facts,
                    team,
                    [pid],
                    suffix=f"-{pid}",
                )
            )
        return out

    def _distance(self, event, snapshot, players: dict[str, PlayerStats]) -> list[Moment]:
        """The first player in each team to pass each distance milestone (5 and
        10 km, from synthetic tracking)."""
        out: list[Moment] = []
        for team_id in sorted({ps.team for ps in players.values()}):
            squad = [
                ps
                for ps in players.values()
                if ps.team == team_id and ps.physical_source == "synthetic_tracking"
            ]
            if not squad:
                continue
            leader = max(squad, key=lambda ps: (ps.distance_km, ps.player_id))
            done = self.state.distance_done.get(team_id, 0.0)
            crossed = [km for km in DISTANCE_MILESTONES_KM if done < km <= leader.distance_km]
            if not crossed:
                continue
            km = max(crossed)
            self.state.distance_done[team_id] = km
            facts = self._base(snapshot, team_id)
            facts.update(self._player_facts("player", leader.player_id, players))
            if "player" not in facts:
                continue
            facts["milestone_km"] = int(km) if float(km).is_integer() else r1(km)
            facts["distance_km"] = r1(leader.distance_km)
            facts["team_first"] = True
            facts["source"] = "synthetic_tracking"
            out.append(
                self._moment(
                    MomentKind.DISTANCE_MILESTONE,
                    "distance_milestone",
                    event,
                    snapshot,
                    facts,
                    team_id,
                    [leader.player_id],
                    suffix=f"-{leader.player_id}-{facts['milestone_km']}",
                )
            )
        return out

    # --------------------------------------------------------- defending

    def _key_tackle(self, event: Event, snapshot, players) -> list[Moment]:
        """A tackle won in the tackler's own third that stops a dangerous attack
        (the attackers' expected threat at the spot is at least KEY_TACKLE_XT)."""
        if (
            event.type != EventType.TACKLE
            or event.outcome != Outcome.WON
            or not event.team
            or not event.player_id
            or event.start is None
        ):
            return []
        spot = (event.start.x, event.start.y)
        attackers = self._opponent(event.team, snapshot)
        own = stats_metrics.to_attacking(spot, event.team, snapshot.home_id)
        theirs = stats_metrics.to_attacking(spot, attackers, snapshot.home_id)
        threat = stats_metrics.xt(*theirs)
        if own[0] >= KEY_TACKLE_OWN_THIRD_U or threat < KEY_TACKLE_XT:
            return []
        now = _elapsed(event.period, event.clock_s)
        last = self.state.last_key_tackle
        if last is not None and 0 <= now - _elapsed(*last) < KEY_TACKLE_GAP_S:
            return []
        facts = self._base(snapshot, event.team)
        facts.update(self._player_facts("player", event.player_id, players))
        if "player" not in facts:
            return []
        ids = [event.player_id]
        prev = self.state.prev_event
        if (
            prev is not None
            and prev.type == EventType.DRIBBLE
            and prev.outcome == Outcome.INCOMPLETE
            and prev.team == attackers
            and prev.player_id
        ):
            facts.update(self._player_facts("victim", prev.player_id, players))
            if "victim" in facts:
                ids.append(prev.player_id)
        facts.update(
            xt_stopped=r2(threat),
            own_goal_distance_m=int(round(pitch.distance_to_goal(theirs))),
            last_ditch=pitch.in_box(theirs),
        )
        self.state.last_key_tackle = (event.period, event.clock_s)
        return [self._moment(MomentKind.KEY_TACKLE, "key_tackle", event, snapshot, facts, event.team, ids)]

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
