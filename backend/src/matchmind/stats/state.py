"""Live match state: one event in, metrics and an updated state out.

`StatsEngine` is the only place the stats for a match are counted. It is fully
deterministic (no randomness, no wall clock), so replaying the same events
gives the same numbers. Formulas are written out in docs/METRICS.md.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator import pitch
from matchmind.simulator.pitch import Pos
from matchmind.simulator.script import HALF_S, format_clock

from . import metrics
from .better_option import analyse_run, analyse_shot, shot_chance_quality
from .models import (
    EventMetrics,
    MatchStateSnapshot,
    PlayerStats,
    SprintTag,
    TeamTotals,
    TeamWindow,
    VarDecision,
)
from .physical import PhysicalTimeline

WINDOW_S = 300.0  # rolling window: the last five minutes of match clock
MOMENTUM_TAU_S = 120.0  # momentum smoothing time constant
DIRECT_BALL_MS = 18.0  # 65 km/h: a driven, direct ball (chaos driver)
ON_BALL = {
    EventType.PASS,
    EventType.CARRY,
    EventType.DRIBBLE,
    EventType.SHOT,
    EventType.INTERCEPTION,
    EventType.TACKLE,
    EventType.CLEARANCE,
    EventType.RECOVERY,
}
TURNOVER_TYPES = {EventType.INTERCEPTION, EventType.TACKLE}
# PPDA: the opponent's own 60% of the pitch (docs/METRICS.md).
PPDA_ZONE_U = 0.6 * pitch.LENGTH


@dataclass(frozen=True)
class _Mark:
    """What the rolling window needs to remember about one event."""

    t: float
    team: str | None
    possession_id: int | None
    completed_pass: bool
    final_third_pass: bool
    box_entry: bool
    shot: bool
    xg: float
    turnover: bool
    direct: bool


def tempo_label(control_chaos: float) -> str:
    """Name the game's rhythm from the control/chaos index (-1 .. +1)."""
    if control_chaos < -0.4:
        return "Furious Chaos"
    if control_chaos < 0.1:
        return "High-Tempo Transition"
    if control_chaos < 0.5:
        return "Methodical Control"
    return "Total Positional Control"


def pressure_index(final_third_passes: int, box_entries: int, shots: int, xg: float) -> float:
    """0-100. Saturating sum of attacking pressure in the window."""
    load = final_third_passes + 2 * box_entries + 4 * shots + 20 * xg
    return round(100 * (1 - math.exp(-load / 30)), 1)


class StatsEngine:
    """Counts one match. Feed it events in order with `process`."""

    def __init__(self, match_id: str, home_id: str, away_id: str) -> None:
        self.match_id = match_id
        self.home_id = home_id
        self.away_id = away_id
        self._players: dict[str, PlayerStats] = {}
        self._changed: set[str] = set()
        self._window: deque[_Mark] = deque()
        self._last_pos: dict[str, Pos] = {}
        self._last_pass_in_poss: dict[int, tuple[str, str]] = {}  # possession -> (passer, receiver)
        self._key_pass_poss: set[int] = set()
        self._last_run: Event | None = None
        self._prev_possession: tuple[str | None, int | None] = (None, None)
        self._seen: dict[str, tuple[str, EventMetrics]] = {}  # event_id -> (payload hash, metrics)
        self._last_seq = -1
        self._period = 1
        self._first_half_end_s = HALF_S
        self._t = 0.0
        self._clock_s = 0.0
        self._match_clock = "00:00"
        self._momentum = 0.0
        self._momentum_t: float | None = None
        self._score = {home_id: 0, away_id: 0}
        self._xg = {home_id: 0.0, away_id: 0.0}
        self._shots = {home_id: 0, away_id: 0}
        self._totals = {home_id: TeamTotals(team=home_id), away_id: TeamTotals(team=away_id)}
        self._physical: PhysicalTimeline | None = None
        self._efforts_after: tuple[int, float] | None = None
        # Counted goals by shot event id: (team, scorer, assist or None, clock, period, clock_s).
        self._goals: dict[str, tuple[str, str, str | None, str, int, float]] = {}
        self._overturned: dict[str, str] = {}  # goal shot event id -> review event id

    @classmethod
    def replay(cls, events: Iterable[Event], physical: PhysicalTimeline | None = None) -> StatsEngine:
        """Build an engine and run every event through it."""
        events = list(events)
        if not events:
            raise ValueError("no events to replay")
        start = next((e for e in events if e.type == EventType.MATCH_START), events[0])
        home = str(start.details.get("home", ""))
        away = str(start.details.get("away", ""))
        if not home or not away:
            raise ValueError("the first event must be a match_start naming home and away")
        engine = cls(start.match_id, home, away)
        if physical is not None:
            engine.attach_physical(physical)
        for event in events:
            engine.process(event)
        return engine

    # ----------------------------------------------------------- public

    def attach_physical(self, timeline: PhysicalTimeline) -> None:
        """Take distance, speed bands, sprints and top speed from the synthetic
        tracking timeline (stats.physical) instead of the event-based estimate.
        Attach before the first event."""
        if timeline.match_id != self.match_id:
            raise ValueError("the physical timeline is for another match")
        if self._last_seq >= 0:
            raise ValueError("attach the physical timeline before processing events")
        self._physical = timeline

    @property
    def physical(self) -> PhysicalTimeline | None:
        return self._physical

    def process(self, event: Event) -> EventMetrics:
        """Update the state with one event and return its metrics.

        Delivery can repeat (at-least-once streams, retries): an event already
        processed returns its original metrics and changes nothing. A different
        payload under a used event id, or an event older than the last one,
        is refused rather than silently counted."""
        if event.match_id != self.match_id:
            raise ValueError(f"event {event.event_id} is from another match")
        event = event.model_copy(update={"labels": []})  # ground truth never reaches the stats
        digest = hashlib.sha256(event.to_json().encode()).hexdigest()
        seen = self._seen.get(event.event_id)
        if seen is not None:
            if seen[0] != digest:
                raise ValueError(f"event {event.event_id} was already processed with different content")
            self._changed = set()
            return seen[1].model_copy(deep=True)
        if event.seq <= self._last_seq:
            raise ValueError(f"event {event.event_id} (seq {event.seq}) arrived after seq {self._last_seq}")
        self._last_seq = event.seq
        self._changed = set()
        self._advance_clock(event)

        if event.lineups:
            for p in event.lineups:
                self._player(p.player_id, p.team)

        m = self._event_metrics(event)
        if event.type == EventType.VAR_REVIEW:
            m.var_decision = self._apply_review(event)
        self._count_players(event, m)
        self._count_team(event)
        if self._physical is not None:
            m.sprint_efforts = self._sprints_since_last(event)
            self._apply_physical(event)
        else:
            self._track_distance(event)
        self._window.append(self._mark(event, m))
        self._trim_window()
        self._update_momentum()
        if event.type == EventType.RUN:
            self._last_run = event
        if event.team is not None:
            self._prev_possession = (event.team, event.possession_id)
        self._seen[event.event_id] = (digest, m.model_copy(deep=True))
        return m

    def players(self) -> dict[str, PlayerStats]:
        return {pid: p.model_copy() for pid, p in sorted(self._players.items())}

    def team_totals(self) -> dict[str, TeamTotals]:
        """Whole-match counting stats per team so far (copies)."""
        return {team: t.model_copy() for team, t in self._totals.items()}

    def overturned_goals(self) -> dict[str, str]:
        """Goals a VAR review ruled out: shot event id -> review event id."""
        return dict(self._overturned)

    def changed_players(self) -> list[PlayerStats]:
        """Players whose stats the last processed event changed."""
        return [self._players[pid].model_copy() for pid in sorted(self._changed) if pid in self._players]

    def snapshot(self) -> MatchStateSnapshot:
        marks = list(self._window)
        home, away = self._team_window(marks, self.home_id), self._team_window(marks, self.away_id)
        minutes = self._window_minutes()
        possessions = {m.possession_id for m in marks if m.possession_id is not None}
        completed = sum(m.completed_pass for m in marks)
        avg_chain = completed / len(possessions) if possessions else 0.0
        turnovers = self._turnovers(marks)
        control = self._control_chaos(marks, avg_chain, turnovers / minutes if minutes else 0.0)
        return MatchStateSnapshot(
            match_id=self.match_id,
            clock_s=self._clock_s,
            match_clock=self._match_clock,
            period=self._period,
            home_id=self.home_id,
            away_id=self.away_id,
            score_home=self._score[self.home_id],
            score_away=self._score[self.away_id],
            home=home,
            away=away,
            momentum=round(pitch.clamp(self._momentum, -100, 100), 1),
            control_chaos=control,
            tempo=tempo_label(control),
            events_per_min=round(len(marks) / minutes, 1) if minutes else 0.0,
            turnovers_per_min=round(turnovers / minutes, 2) if minutes else 0.0,
            avg_chain_passes=round(avg_chain, 2),
            xg_home=round(self._xg[self.home_id], 2),
            xg_away=round(self._xg[self.away_id], 2),
            shots_home=self._shots[self.home_id],
            shots_away=self._shots[self.away_id],
        )

    # ------------------------------------------------------- per event

    def _att(self, p: Pos, team: str) -> Pos:
        return metrics.to_attacking(p, team, self.home_id)

    def _event_metrics(self, e: Event) -> EventMetrics:
        m = EventMetrics(event_id=e.event_id)
        team = e.team
        start = (e.start.x, e.start.y) if e.start else None
        end = (e.end.x, e.end.y) if e.end else None
        if team is None or start is None:
            return m
        s = self._att(start, team)
        m.pitch_zone = metrics.zone(*s)
        m.player_speed_kmh = metrics.kmh(e.player_speed_mps)
        m.sprint = (e.player_speed_mps or 0.0) > metrics.SPRINT_MS
        m.ball_speed_kmh = metrics.kmh(e.ball_speed_mps)

        if e.type == EventType.PASS and end is not None:
            t = self._att(end, team)
            pass_type = str(e.details.get("pass_type", "ground"))
            m.pass_distance_m = round(pitch.dist(s, t), 1)
            m.forward_m = round(t[0] - s[0], 1)
            m.progressive = metrics.is_progressive(s, t)
            m.pass_difficulty = metrics.pass_difficulty(
                m.pass_distance_m,
                len(e.pressure_players),
                m.forward_m,
                t[0],
                pass_type,
                lane_opponents=self._lane_from_run(e),
                angle_deg=metrics.pass_angle_deg(s, t),
            )
            m.xt_delta = metrics.xt_delta(s, t, e.outcome == Outcome.COMPLETE)
        elif e.type == EventType.CARRY and end is not None:
            t = self._att(end, team)
            m.forward_m = round(t[0] - s[0], 1)
            m.progressive = metrics.is_progressive(s, t)
            m.xt_delta = metrics.xt_delta(s, t, True)
        elif e.type == EventType.SHOT:
            m.chance_quality = shot_chance_quality(e, self.home_id)
            m.distance_to_goal_m = round(pitch.distance_to_goal(s), 1)
            m.fast_shot = (m.ball_speed_kmh or 0.0) >= metrics.ROCKET_SHOT_KMH
            m.better_option = analyse_shot(e, self.home_id)
        elif e.type == EventType.RUN:
            m.unfound_run = analyse_run(e, self.home_id)
        return m

    def _lane_from_run(self, e: Event) -> int | None:
        """Opponents in the lane of a through ball played straight after a
        tracked run (the only passes we have opponent positions for)."""
        run = self._last_run
        if (
            run is None
            or not run.tracking
            or e.start is None
            or e.end is None
            or e.receiver_id != run.player_id
            or e.player_id != run.details.get("carrier_id")
            or e.possession_id != run.possession_id
        ):
            return None
        offset = e.clock_s - run.clock_s
        frame = min(run.tracking, key=lambda f: abs(f.t_offset_s - offset))
        opps = [(p.x, p.y) for p in frame.players if not p.teammate]
        return metrics.opponents_in_lane((e.start.x, e.start.y), (e.end.x, e.end.y), opps)

    # ---------------------------------------------------------- players

    def _player(self, pid: str, team: str) -> PlayerStats:
        p = self._players.get(pid)
        if p is None:
            p = self._players[pid] = PlayerStats(player_id=pid, team=team)
            if self._physical is not None:
                p.physical_source = "synthetic_tracking"
            self._changed.add(pid)
        return p

    def _count_players(self, e: Event, m: EventMetrics) -> None:
        if e.player_id is None or e.team is None:
            return
        actor = self._player(e.player_id, e.team)
        self._changed.add(actor.player_id)
        if e.type in ON_BALL:
            actor.touches += 1
        if self._physical is None:  # with tracking, speed comes from the tracking instead
            if m.player_speed_kmh is not None:
                actor.top_speed_kmh = max(actor.top_speed_kmh, m.player_speed_kmh)
            if m.sprint:
                actor.sprints += 1

        if e.type == EventType.PASS:
            actor.passes += 1
            if e.outcome == Outcome.COMPLETE:
                actor.passes_completed += 1
                if e.possession_id is not None and e.receiver_id:
                    self._last_pass_in_poss[e.possession_id] = (actor.player_id, e.receiver_id)
        elif e.type in (EventType.CARRY, EventType.DRIBBLE):
            if e.start and e.end and e.outcome != Outcome.INCOMPLETE:
                actor.carry_distance_m = round(
                    actor.carry_distance_m + pitch.dist((e.start.x, e.start.y), (e.end.x, e.end.y)), 1
                )
            beaten = e.details.get("opponent_id")
            if e.type == EventType.DRIBBLE and e.outcome == Outcome.COMPLETE and isinstance(beaten, str):
                # The defender took on the dribbler and lost: a challenge lost.
                defender = self._player(beaten, self._other(e.team))
                defender.tackles_lost += 1
                self._changed.add(defender.player_id)
        elif e.type == EventType.SHOT:
            self._count_shot(e, actor, m.chance_quality or 0.0)
        elif e.type == EventType.TACKLE and e.outcome == Outcome.WON:
            actor.tackles_won += 1
        elif e.type == EventType.INTERCEPTION:
            actor.interceptions += 1

    def _other(self, team: str) -> str:
        return self.away_id if team == self.home_id else self.home_id

    def _count_team(self, e: Event) -> None:
        """Whole-match team totals, PPDA parts included."""
        if e.team not in self._totals:
            return
        mine, theirs = self._totals[e.team], self._totals[self._other(e.team)]
        u = self._att((e.start.x, e.start.y), e.team)[0] if e.start else None
        if e.type == EventType.PASS:
            mine.passes += 1
            mine.passes_completed += e.outcome == Outcome.COMPLETE
            if u is not None and u < PPDA_ZONE_U:
                theirs.ppda_opponent_passes += 1  # a pass the other side allowed in our own 60%
        elif e.type == EventType.SHOT:
            mine.shots += 1
            mine.shots_on_target += e.outcome in (Outcome.GOAL, Outcome.SAVED)
            mine.goals += e.outcome == Outcome.GOAL
        elif e.type == EventType.TACKLE and e.outcome == Outcome.WON:
            mine.tackles_won += 1
        elif e.type == EventType.INTERCEPTION:
            mine.interceptions += 1
        elif e.type == EventType.FOUL:
            mine.fouls += 1
        if e.type == EventType.DRIBBLE and e.outcome == Outcome.COMPLETE and e.details.get("opponent_id"):
            theirs.tackles_lost += 1
            if u is not None and u < PPDA_ZONE_U:
                theirs.ppda_defensive_actions += 1  # their challenge, in our own 60%
        defensive = e.type in (EventType.TACKLE, EventType.INTERCEPTION, EventType.FOUL)
        if defensive and u is not None and u >= pitch.LENGTH - PPDA_ZONE_U:  # in the opponent's own 60%
            mine.ppda_defensive_actions += 1

    def _count_shot(self, e: Event, shooter: PlayerStats, xg: float) -> None:
        team = shooter.team
        shooter.shots += 1
        shooter.shots_on_target += e.outcome in (Outcome.GOAL, Outcome.SAVED)
        shooter.xg = round(shooter.xg + xg, 3)
        self._shots[team] = self._shots.get(team, 0) + 1
        self._xg[team] = self._xg.get(team, 0.0) + xg
        if team in self._totals:
            self._totals[team].xg = round(self._xg[team], 3)
        goal = e.outcome == Outcome.GOAL
        if goal:
            shooter.goals += 1
            self._score[team] = self._score.get(team, 0) + 1
        assist: str | None = None
        # Key pass: the last completed pass of this possession went to the shooter.
        poss = e.possession_id
        last = self._last_pass_in_poss.get(poss) if poss is not None else None
        if last and last[1] == shooter.player_id and last[0] != shooter.player_id:
            passer = self._player(last[0], team)
            passer.key_passes += 1
            passer.xa = round(passer.xa + xg, 3)
            if goal:
                passer.assists += 1
                assist = passer.player_id
            self._changed.add(passer.player_id)
            del self._last_pass_in_poss[poss]  # one shot per pass
        if goal:
            self._goals[e.event_id] = (team, shooter.player_id, assist, e.match_clock, e.period, e.clock_s)

    def _apply_review(self, e: Event) -> VarDecision:
        """A VAR review of an earlier event. `overturned` on a counted goal takes
        it off the score, the scorer's goals and the assister's assists; the shot,
        its xG, the key pass and xA all stay (the chance still happened). A review
        of an unknown event, of something that is not a counted goal, or of a goal
        already ruled out changes nothing (`goal_removed` is False)."""
        target = e.reviewed_event_id or ""
        outcome = "overturned" if e.outcome == Outcome.OVERTURNED else "stands"
        goal = self._goals.get(target)
        removed = False
        if goal is not None and outcome == "overturned" and target not in self._overturned:
            team, scorer, assist, *_ = goal
            self._score[team] = max(0, self._score.get(team, 0) - 1)
            if team in self._totals:
                self._totals[team].goals = max(0, self._totals[team].goals - 1)
            shooter = self._player(scorer, team)
            shooter.goals = max(0, shooter.goals - 1)
            self._changed.add(scorer)
            if assist is not None:
                passer = self._player(assist, team)
                passer.assists = max(0, passer.assists - 1)
                self._changed.add(assist)
            self._overturned[target] = e.event_id
            removed = True
        team, scorer, assist, clock, period, clock_s = goal or (None, None, None, None, None, None)
        return VarDecision(
            review_event_id=e.event_id,
            reviewed_event_id=target,
            outcome=outcome,
            reason=str(e.review_reason) if e.review_reason is not None else None,
            team=team,
            player_id=scorer,
            assist_id=assist if removed else None,
            reviewed_clock=clock,
            reviewed_period=period,
            reviewed_clock_s=clock_s,
            goal_removed=removed,
            score_home=self._score[self.home_id],
            score_away=self._score[self.away_id],
        )

    # ------------------------------------------- tracking (stats.physical)

    def _apply_physical(self, e: Event) -> None:
        """Copy each player's tracking numbers at this clock. A player counts as
        changed only when his distance (to 0.1 km), sprints or top speed move, so
        ticks do not carry all 22 players every time."""
        assert self._physical is not None
        for pid, ph in self._physical.at(e.period, e.clock_s).items():
            p = self._players.get(pid)
            if p is None:
                continue
            if (
                round(p.distance_km, 1) == round(ph.distance_km, 1)
                and p.sprints == ph.sprints
                and p.top_speed_kmh == ph.top_speed_kmh
            ):
                continue
            p.distance_km = ph.distance_km
            p.walk_km, p.jog_km, p.run_km, p.sprint_km = ph.walk_km, ph.jog_km, ph.run_km, ph.sprint_km
            p.sprints = ph.sprints
            p.top_speed_kmh = ph.top_speed_kmh
            self._changed.add(pid)

    def _sprints_since_last(self, e: Event) -> list[SprintTag]:
        assert self._physical is not None
        until = (e.period, e.clock_s)
        if self._efforts_after is not None and until <= self._efforts_after:
            return []
        found = self._physical.efforts_between(self._efforts_after, until)
        self._efforts_after = until
        return [
            SprintTag(
                player_id=f.player_id,
                period=f.period,
                peak_clock_s=f.peak_s,
                peak_kmh=f.peak_kmh,
                distance_m=f.distance_m,
            )
            for f in found
        ]

    # ----------------------------------------------- distance estimate

    def _track_distance(self, e: Event) -> None:
        """Estimated distance covered: straight lines between each player's
        successive known positions (event start/end, freeze frames, tracking
        frames). Players are only seen near the ball, so this is a lower bound."""
        seen: list[tuple[str, str, Pos]] = []
        if e.player_id and e.team and e.start:
            seen.append((e.player_id, e.team, (e.start.x, e.start.y)))
        for frame in sorted(e.tracking or [], key=lambda f: f.t_offset_s):
            seen.extend((p.player_id, p.team, (p.x, p.y)) for p in frame.players)
        if e.freeze_frame:
            seen.extend((p.player_id, p.team, (p.x, p.y)) for p in e.freeze_frame if not p.actor)
        if e.end and e.team:
            if e.type in (EventType.CARRY, EventType.DRIBBLE, EventType.RUN) and e.player_id:
                if e.outcome != Outcome.INCOMPLETE:
                    seen.append((e.player_id, e.team, (e.end.x, e.end.y)))
            elif e.type == EventType.PASS and e.outcome == Outcome.COMPLETE and e.receiver_id:
                seen.append((e.receiver_id, e.team, (e.end.x, e.end.y)))
        for pid, team, pos in seen:
            prev = self._last_pos.get(pid)
            self._last_pos[pid] = pos
            if prev is None:
                continue
            step = pitch.dist(prev, pos)
            if step > 0:
                p = self._player(pid, team)
                p.distance_km = round(p.distance_km + step / 1000, 3)
                self._changed.add(pid)

    # ---------------------------------------------------- rolling window

    def _advance_clock(self, e: Event) -> None:
        """Map (period, clock) onto one timeline that keeps first-half
        stoppage time, so the window never runs backwards at half time."""
        if e.period == 1:
            self._first_half_end_s = max(self._first_half_end_s, e.clock_s)
            t = e.clock_s
        else:
            t = self._first_half_end_s + (e.clock_s - HALF_S)
        self._t = max(self._t, t)
        self._period = e.period
        self._clock_s = e.clock_s
        self._match_clock = e.match_clock or format_clock(e.clock_s, e.period)

    def _mark(self, e: Event, m: EventMetrics) -> _Mark:
        team = e.team
        completed = e.type == EventType.PASS and e.outcome == Outcome.COMPLETE
        ft_pass = box_entry = False
        if team and e.start and e.end:
            s = self._att((e.start.x, e.start.y), team)
            t = self._att((e.end.x, e.end.y), team)
            ft_pass = completed and t[0] >= metrics.FINAL_THIRD_U
            moved = completed or (
                e.type in (EventType.CARRY, EventType.DRIBBLE) and e.outcome != Outcome.INCOMPLETE
            )
            box_entry = moved and pitch.in_box(t) and not pitch.in_box(s)
        prev_team, prev_poss = self._prev_possession
        turnover = e.type in TURNOVER_TYPES or (
            team is not None and prev_team is not None and team != prev_team and e.possession_id != prev_poss
        )
        return _Mark(
            t=self._t,
            team=team,
            possession_id=e.possession_id,
            completed_pass=completed,
            final_third_pass=ft_pass,
            box_entry=box_entry,
            shot=e.type == EventType.SHOT,
            xg=m.chance_quality or 0.0,
            turnover=turnover,
            direct=e.type in (EventType.PASS, EventType.CLEARANCE, EventType.SHOT)
            and (e.ball_speed_mps or 0.0) >= DIRECT_BALL_MS,
        )

    def _trim_window(self) -> None:
        while self._window and self._window[0].t < self._t - WINDOW_S:
            self._window.popleft()

    def _window_minutes(self) -> float:
        return min(WINDOW_S, max(self._t, 60.0)) / 60  # at least one minute, so rates start sane

    def _team_window(self, marks: list[_Mark], team: str) -> TeamWindow:
        mine = [m for m in marks if m.team == team]
        passes_all = sum(m.completed_pass for m in marks)
        ft_all = sum(m.final_third_pass for m in marks)
        passes = sum(m.completed_pass for m in mine)
        ft = sum(m.final_third_pass for m in mine)
        box = sum(m.box_entry for m in mine)
        shots = sum(m.shot for m in mine)
        xg = sum(m.xg for m in mine)
        return TeamWindow(
            possession_pct=round(100 * passes / passes_all, 1) if passes_all else 50.0,
            field_tilt_pct=round(100 * ft / ft_all, 1) if ft_all else 50.0,
            pressure_index=pressure_index(ft, box, shots, xg),
            shots=shots,
            xg=round(xg, 2),
            final_third_passes=ft,
            box_entries=box,
        )

    @staticmethod
    def _turnovers(marks: list[_Mark]) -> int:
        return sum(m.turnover for m in marks)

    @staticmethod
    def _control_chaos(marks: list[_Mark], avg_chain: float, turnovers_per_min: float) -> float:
        """-1 (end-to-end chaos) .. +1 (patient control). Chaos rises with
        turnovers per minute and direct, driven balls; control rises with
        passes per possession."""
        if not marks:
            return 0.0
        turnover_load = min(turnovers_per_min / 4.0, 1.0)
        directness = sum(m.direct for m in marks) / len(marks)
        continuity = min(avg_chain / 6.0, 1.0)
        raw = 0.5 * turnover_load + 0.5 * directness - 0.6 * continuity
        return round(pitch.clamp(0.4 - 1.8 * raw, -1.0, 1.0), 2)

    def _update_momentum(self) -> None:
        """Exponential moving average of (home pressure - away pressure),
        weighted by match time so a busy minute does not count double."""
        marks = list(self._window)
        diff = (
            self._team_window(marks, self.home_id).pressure_index
            - self._team_window(marks, self.away_id).pressure_index
        )
        if self._momentum_t is None:
            self._momentum = 0.0
        else:
            alpha = 1 - math.exp(-max(self._t - self._momentum_t, 0.0) / MOMENTUM_TAU_S)
            self._momentum += alpha * (diff - self._momentum)
        self._momentum_t = self._t
