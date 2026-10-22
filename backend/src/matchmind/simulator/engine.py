"""Seeded, scriptable football match engine.

The engine walks a possession-chain model: whoever has the ball picks an
action (pass, carry, dribble, cross, shot, clearance or a run in behind) with
probabilities that depend on pitch zone, pressure and match state. Player
positions come from a simple team-shape model so that shots can carry a
freeze frame of everyone around the box, and runs in behind can carry a short
tracking window. Script beats force the story moments the demo relies on.

Same script + same seed = byte-identical output.
"""

from __future__ import annotations

import math
import random
from datetime import timedelta

from matchmind.schema import (
    BodyPart,
    Event,
    EventType,
    FramePlayer,
    LineupPlayer,
    Outcome,
    Point,
    ReviewReason,
    TrackingFrame,
)

from . import pitch
from .pitch import Pos
from .script import FULL_S, HALF_S, Beat, MatchScript, format_clock
from .teams import Player, get_team

FINAL_THIRD_X = 70.0  # freeze frames keep everyone from here to the goal line
RUN_WINDOW_S = 3.0
RUN_FRAME_STEP_S = 0.5
HALF_TIME_BREAK_S = 900.0
PRESSURE_RADIUS_M = 3.5


class MatchEngine:
    def __init__(self, script: MatchScript, seed: int) -> None:
        self.script = script
        self.seed = seed
        self.rng = random.Random(seed)
        self.home = get_team(script.home)
        self.away = get_team(script.away)
        self.teams = {self.home.team_id: self.home, self.away.team_id: self.away}
        self.player_by_id: dict[str, Player] = {
            p.player_id: p for t in self.teams.values() for p in t.players
        }
        self.team_of = {p.player_id: t.team_id for t in self.teams.values() for p in t.players}

        self.events: list[Event] = []
        self.warnings: list[str] = []
        self.clock = 0.0
        self.period = 1
        self.poss_team = self.home.team_id
        self.poss_id = 0
        self.ball: Pos = pitch.CENTRE
        self.sent_off: set[str] = set()
        self.carrier = self._striker(self.home.team_id)
        self.score = {self.home.team_id: 0, self.away.team_id: 0}
        self.booked: set[str] = set()
        self.run_cooldown_until = 0.0

        stoppage = script.stoppage_minutes or (self.rng.randint(1, 3), self.rng.randint(3, 6))
        self.period_end = {
            1: HALF_S + 60 * stoppage[0] + self.rng.uniform(0, 40),
            2: FULL_S + 60 * stoppage[1] + self.rng.uniform(0, 40),
        }
        self.first_half_length = HALF_S
        instant = [b for b in script.beats if b.type != "pressure_spell"]
        self.pending: list[Beat] = sorted(instant, key=lambda b: b.at_s)
        self.spells = [b for b in script.beats if b.type == "pressure_spell"]

    # ------------------------------------------------------------------ run

    def run(self) -> list[Event]:
        self._emit(
            EventType.MATCH_START,
            lineups=self._lineups(),
            details={"home": self.home.team_id, "away": self.away.team_id, "seed": self.seed},
        )
        for period in (1, 2):
            self._start_period(period)
            while self.clock < self.period_end[period]:
                beat = self._due_beat()
                if beat is not None:
                    self.pending.remove(beat)
                    getattr(self, f"_beat_{beat.type}")(beat)
                else:
                    self._step()
            self._drop_missed_beats(period)
            self._emit(EventType.PERIOD_END, details=self._score_details())
            if period == 1:
                self.first_half_length = self.clock
        self._emit(EventType.MATCH_END, details=self._score_details())
        return self.events

    def _start_period(self, period: int) -> None:
        self.period = period
        self.clock = 0.0 if period == 1 else HALF_S
        self._emit(EventType.PERIOD_START)
        self._kickoff(self.home.team_id if period == 1 else self.away.team_id)

    def _due_beat(self) -> Beat | None:
        for beat in self.pending:
            if beat.period == self.period and beat.at_s <= self.clock:
                return beat
        return None

    def _drop_missed_beats(self, period: int) -> None:
        for beat in [b for b in self.pending if b.period == period]:
            self.warnings.append(f"Beat {beat.type} at {beat.at} never fired (period ended)")
            self.pending.remove(beat)

    # ------------------------------------------------------------- helpers

    def _opp(self, team_id: str) -> str:
        return self.away.team_id if team_id == self.home.team_id else self.home.team_id

    def _f(self, team_id: str, p: Pos) -> Pos:
        """Absolute <-> team attacking frame (the transform is its own inverse)."""
        return p if team_id == self.home.team_id else pitch.flip(p)

    def _active(self, team_id: str) -> list[Player]:
        return [p for p in self.teams[team_id].players if p.player_id not in self.sent_off]

    def _keeper_id(self, team_id: str) -> str:
        return self.teams[team_id].keeper.player_id

    def _striker(self, team_id: str) -> str:
        active = self._active(team_id)
        for wanted in ("ST", None):
            for p in active:
                if (wanted and p.position == wanted) or (not wanted and p.line in ("FWD", "MID")):
                    return p.player_id
        return active[-1].player_id

    def _pick_line(self, team_id: str, lines: set[str], exclude: set[str]) -> str:
        options = [p.player_id for p in self._active(team_id) if p.line in lines]
        options = [pid for pid in options if pid not in exclude]
        if not options:
            options = [
                p.player_id for p in self._active(team_id) if p.line != "GK" and p.player_id not in exclude
            ]
        return self.rng.choice(options)

    def _change_possession(self, new_carrier: str) -> None:
        self.poss_team = self.team_of[new_carrier]
        self.carrier = new_carrier
        self.poss_id += 1

    def _nearest(self, pos: dict[str, Pos], team_id: str, target: Pos, exclude=()) -> str:
        options = [pid for pid in pos if self.team_of[pid] == team_id and pid not in exclude]
        return min(options, key=lambda pid: pitch.dist(pos[pid], target))

    def _spell_boost(self, team_id: str) -> float:
        return max(
            (
                s.intensity
                for s in self.spells
                if s.team == team_id and s.period == self.period and s.at_s <= self.clock < s.until_s
            ),
            default=0.0,
        )

    def _modifier(self, team_id: str) -> float:
        opp = self._opp(team_id)
        missing = 11 - len(self._active(team_id))
        opp_missing = 11 - len(self._active(opp))
        return (
            (self.teams[team_id].strength - 0.5) * 0.2
            + 0.07 * self._spell_boost(team_id)
            - 0.07 * self._spell_boost(opp)
            - 0.035 * missing
            + 0.02 * opp_missing
        )

    def _score_details(self) -> dict[str, int]:
        return {
            "score_home": self.score[self.home.team_id],
            "score_away": self.score[self.away.team_id],
        }

    def _lineups(self) -> list[LineupPlayer]:
        return [
            LineupPlayer(
                player_id=p.player_id,
                team=t.team_id,
                name=p.name,
                number=p.number,
                position=p.position,
            )
            for t in (self.home, self.away)
            for p in t.players
        ]

    # ------------------------------------------------------------ positions

    def _shape(self, team_id: str, in_possession: bool, ball_f: Pos) -> dict[str, Pos]:
        """Team shape in the team's own frame for a given ball position."""
        bu, bv = ball_f
        if in_possession:
            back, length, spread = pitch.clamp(bu - 35, 15, 60), 45.0, 1.0
        else:
            back, length, spread = pitch.clamp(bu - 25, 9, 45), 30.0, 0.75
        out: dict[str, Pos] = {}
        for p in self._active(team_id):
            if p.line == "GK":
                u = pitch.clamp(back - 14, 3, 22)
                v = 34 + (bv - 34) * 0.12
            else:
                u = back + (p.base[0] - 25) / 50 * length
                v = 34 + (p.base[1] - 34) * spread + (bv - 34) * 0.3
            u += self.rng.gauss(0, 1.2)
            v += self.rng.gauss(0, 1.2)
            out[p.player_id] = (pitch.clamp(u, 1, 104), pitch.clamp(v, 1, 67))
        return out

    def _positions(self) -> dict[str, Pos]:
        """Absolute positions of every player on the pitch right now."""
        att, dfn = self.poss_team, self._opp(self.poss_team)
        ball_a = self._f(att, self.ball)
        a = self._shape(att, True, ball_a)
        d = self._shape(dfn, False, pitch.flip(ball_a))
        keeper_d = self._keeper_id(dfn)
        line = max(
            (pitch.LENGTH - u for pid, (u, _) in d.items() if pid != keeper_d),
            default=pitch.LENGTH - 10,
        )
        cap = max(line, ball_a[0])  # attackers stay onside unless behind the ball
        keeper_a = self._keeper_id(att)
        for pid, (u, v) in a.items():
            if pid not in (keeper_a, self.carrier) and u > cap:
                a[pid] = (cap - abs(self.rng.gauss(0, 0.6)), v)
        pos = {pid: self._f(att, p) for pid, p in a.items()}
        pos.update({pid: self._f(dfn, p) for pid, p in d.items()})
        pos[self.carrier] = self.ball
        return pos

    def _pressers(self, pos: dict[str, Pos]) -> list[str]:
        opp = self._opp(self.poss_team)
        return sorted(
            pid
            for pid, p in pos.items()
            if self.team_of[pid] == opp and pitch.dist(p, self.ball) <= PRESSURE_RADIUS_M
        )

    # ------------------------------------------------------------- emitting

    def _real_offset_s(self) -> float:
        if self.period == 1:
            return self.clock
        return self.first_half_length + HALF_TIME_BREAK_S + (self.clock - HALF_S)

    def _labels(self) -> list[str]:
        return [
            f"pressure_spell:{s.team}"
            for s in self.spells
            if s.period == self.period and s.at_s <= self.clock < s.until_s
        ]

    @staticmethod
    def _pt(p: Pos) -> Point:
        q = pitch.clamp_pos(p)
        return Point(x=round(q[0], 2), y=round(q[1], 2))

    def _emit(self, etype: EventType, *, labels=(), **fields) -> Event:
        seq = len(self.events)
        event = Event(
            event_id=f"{self.script.match_id}-{seq:05d}",
            match_id=self.script.match_id,
            seq=seq,
            ts=self.script.kickoff + timedelta(seconds=round(self._real_offset_s(), 3)),
            period=self.period,
            clock_s=round(self.clock, 2),
            match_clock=format_clock(self.clock, self.period),
            type=etype,
            possession_id=self.poss_id if fields.get("team") else None,
            labels=[*labels, *self._labels()],
            **fields,
        )
        self.events.append(event)
        return event

    def _frame_players(self, pos: dict[str, Pos], actor: str, ids) -> list[FramePlayer]:
        actor_team = self.team_of[actor]
        out = []
        for pid in sorted(ids):
            p = pitch.clamp_pos(pos[pid])
            out.append(
                FramePlayer(
                    player_id=pid,
                    team=self.team_of[pid],
                    x=round(p[0], 2),
                    y=round(p[1], 2),
                    teammate=self.team_of[pid] == actor_team,
                    keeper=self.player_by_id[pid].line == "GK",
                    actor=pid == actor,
                )
            )
        return out

    def _freeze_frame(self, pos: dict[str, Pos], shooter: str) -> list[FramePlayer]:
        team = self.team_of[shooter]
        ids = [pid for pid, p in pos.items() if pid == shooter or self._f(team, p)[0] >= FINAL_THIRD_X]
        return self._frame_players(pos, shooter, ids)

    # ---------------------------------------------------------------- steps

    def _step(self) -> None:
        team = self.poss_team
        if self.carrier in self.sent_off or self.team_of[self.carrier] != team:
            self.carrier = self._nearest(self._positions(), team, self.ball)
        pos = self._positions()
        pressers = self._pressers(pos)
        ball_f = self._f(team, self.ball)

        if not pitch.in_box(ball_f):
            if pressers and self.rng.random() < 0.035:
                return self._foul(pos, self.rng.choice(pressers))
            if self.rng.random() < 0.006:
                return self._foul(pos, self._nearest(pos, self._opp(team), self.ball))

        action = self._choose_action(team, ball_f, bool(pressers))
        {
            "pass": lambda: self._pass(pos),
            "carry": lambda: self._carry(pos),
            "dribble": lambda: self._dribble(pos),
            "cross": lambda: self._cross(pos),
            "shot": lambda: self._shot(pos),
            "clearance": lambda: self._clearance(pos),
            "run": lambda: self._random_run(pos),
        }[action]()

    def _choose_action(self, team: str, ball_f: Pos, pressed: bool) -> str:
        u, v = ball_f
        if u < 30:
            w = {"pass": 0.82, "carry": 0.13, "clearance": 0.03 + (0.15 if pressed else 0.0)}
        elif u < 70:
            w = {"pass": 0.72, "carry": 0.17, "dribble": 0.07, "shot": 0.012 if u > 62 else 0.0}
        else:
            wide = abs(v - 34) > 18
            w = {
                "pass": 0.48,
                "carry": 0.12,
                "dribble": 0.12,
                "cross": 0.14 if wide else 0.02,
                "shot": 0.17 if pitch.in_box(ball_f) else 0.035,
            }
        boost = self._spell_boost(team)
        if boost:
            w["shot"] = w.get("shot", 0.0) * (1 + boost)
            if "dribble" in w:
                w["dribble"] *= 1 + boost / 2
        if 45 <= u <= 80 and self.clock >= self.run_cooldown_until:
            w["run"] = 0.035
        actions = list(w)
        return self.rng.choices(actions, weights=[w[a] for a in actions])[0]

    def _pick_receiver(self, pos: dict[str, Pos], sideways: bool = False, exclude=()) -> str:
        team = self.poss_team
        cu, cv = self._f(team, self.ball)
        opps = [self._f(team, p) for pid, p in pos.items() if self.team_of[pid] != team]
        keeper = self._keeper_id(team)
        candidates, weights = [], []
        for pid, p in pos.items():
            if self.team_of[pid] != team or pid == self.carrier or pid in exclude:
                continue
            u, v = self._f(team, p)
            d = math.hypot(u - cu, v - cv)
            if d < 4 or d > 50:
                continue
            space = min(math.hypot(u - ou, v - ov) for ou, ov in opps)
            w = math.exp(-(((d - 17) / 14) ** 2)) * (1 + min(space, 8) / 4)
            w *= math.exp(-abs(u - cu) / 6) if sideways else math.exp((u - cu) / 22)
            if pid == keeper and cu > 30:
                w *= 0.05
            candidates.append(pid)
            weights.append(w)
        if not candidates:
            return self._nearest(pos, team, self.ball, exclude={self.carrier, *exclude})
        return self.rng.choices(candidates, weights=weights)[0]

    def _pass(
        self,
        pos: dict[str, Pos],
        *,
        receiver: str | None = None,
        end: Pos | None = None,
        force: bool | None = None,
        decide: float | None = None,
        kind: str = "ground",
        labels=(),
    ) -> bool:
        team, passer, start = self.poss_team, self.carrier, self.ball
        receiver = receiver or self._pick_receiver(pos)
        if end is None:
            r = pos[receiver]
            end = (r[0] + self.rng.gauss(0, 0.6), r[1] + self.rng.gauss(0, 0.6))
        end = pitch.clamp_pos(end, 0.5)
        d = max(pitch.dist(start, end), 1.0)
        pressers = self._pressers(pos)
        self.clock += self.rng.uniform(0.7, 2.4) if decide is None else decide

        opp = self._opp(team)
        lane = min(
            (pitch.segment_distance(p, start, end) for pid, p in pos.items() if self.team_of[pid] == opp),
            default=10.0,
        )
        forward = self._f(team, end)[0] - self._f(team, start)[0]
        p_ok = 0.93 - 0.007 * max(0.0, d - 15) - (0.1 if pressers else 0.0)
        p_ok -= 0.18 if lane < 1.2 else 0.06 if lane < 2.5 else 0.0
        p_ok -= 0.04 if forward > 15 else 0.0
        p_ok -= 0.25 if kind == "cross" else 0.0
        p_ok = pitch.clamp(p_ok + self._modifier(team), 0.2, 0.97)
        success = (self.rng.random() < p_ok) if force is None else force

        speed = pitch.clamp(9 + 0.45 * d + self.rng.gauss(0, 1.2), 10, 25)
        if kind == "cross":
            speed = pitch.clamp(speed + 2, 10, 25)
        common = dict(
            team=team,
            player_id=passer,
            receiver_id=receiver,
            start=self._pt(start),
            ball_speed_mps=round(speed, 1),
            under_pressure=bool(pressers),
            pressure_players=pressers,
            details={"pass_type": kind},
            labels=labels,
        )

        if success:
            self._emit(EventType.PASS, end=self._pt(end), outcome=Outcome.COMPLETE, **common)
            self.clock += d / speed
            self.ball, self.carrier = end, receiver
            return True

        if d > 25 and self.rng.random() < 0.3:  # overhit, out of play
            far = (end[0] + (end[0] - start[0]) * 0.3, end[1] + (end[1] - start[1]) * 0.3)
            out_end = pitch.clamp_pos(far)
            self._emit(EventType.PASS, end=self._pt(out_end), outcome=Outcome.OUT, **common)
            self.clock += pitch.dist(start, out_end) / speed + self.rng.uniform(8, 20)
            self.ball = pitch.clamp_pos(out_end, 1.0)
            self._change_possession(self._nearest(pos, opp, self.ball))
            return False

        candidates = [pid for pid in pos if self.team_of[pid] == opp]
        interceptor = min(candidates, key=lambda pid: pitch.segment_distance(pos[pid], start, end))
        t, point = pitch.project_on_segment(pos[interceptor], start, end)
        if t < 0.25:
            point = pitch.lerp(start, end, 0.25)
        self._emit(EventType.PASS, end=self._pt(point), outcome=Outcome.INCOMPLETE, **common)
        self.clock += pitch.dist(start, point) / speed
        self.ball = point
        self._change_possession(interceptor)
        self._emit(
            EventType.INTERCEPTION,
            team=opp,
            player_id=interceptor,
            start=self._pt(point),
            outcome=Outcome.WON,
        )
        return False

    def _carry(self, pos: dict[str, Pos], *, target: Pos | None = None, labels=()) -> None:
        team = self.poss_team
        u, v = self._f(team, self.ball)
        if target is None:
            to_goal = math.atan2(34 - v, 105 - u)
            angle = 0.5 * to_goal + self.rng.gauss(0, 0.45)
            d = self.rng.uniform(4, 14)
            end_f = (
                pitch.clamp(u + d * math.cos(angle), 1, 102),
                pitch.clamp(v + d * math.sin(angle), 2, 66),
            )
        else:
            end_f = self._f(team, target)
        speed = pitch.clamp(self.rng.gauss(6.0, 1.6), 3.0, 9.5)
        pressers = self._pressers(pos)
        self.clock += self.rng.uniform(0.3, 1.0)
        end = self._f(team, end_f)
        self._emit(
            EventType.CARRY,
            team=team,
            player_id=self.carrier,
            start=self._pt(self.ball),
            end=self._pt(end),
            player_speed_mps=round(speed, 1),
            under_pressure=bool(pressers),
            pressure_players=pressers,
            labels=labels,
        )
        self.clock += pitch.dist(self.ball, end) / speed
        self.ball = end

    def _dribble(self, pos: dict[str, Pos]) -> None:
        team, opp = self.poss_team, self._opp(self.poss_team)
        defender = self._nearest(pos, opp, self.ball)
        pressers = self._pressers(pos)
        p_ok = pitch.clamp(0.52 + self._modifier(team) - (0.05 if len(pressers) > 1 else 0), 0.2, 0.85)
        u, v = self._f(team, self.ball)
        end = self._f(
            team,
            (pitch.clamp(u + self.rng.uniform(3, 6), 1, 102), pitch.clamp(v + self.rng.gauss(0, 2), 2, 66)),
        )
        self.clock += self.rng.uniform(0.4, 1.2)
        success = self.rng.random() < p_ok
        self._emit(
            EventType.DRIBBLE,
            team=team,
            player_id=self.carrier,
            start=self._pt(self.ball),
            end=self._pt(end if success else self.ball),
            outcome=Outcome.COMPLETE if success else Outcome.INCOMPLETE,
            player_speed_mps=round(pitch.clamp(self.rng.gauss(6.5, 1.2), 3, 9.5), 1),
            under_pressure=bool(pressers),
            pressure_players=pressers,
            details={"opponent_id": defender},
        )
        if success:
            self.clock += 1.0
            self.ball = end
            return
        self.clock += 0.4
        self._change_possession(defender)
        self._emit(
            EventType.TACKLE, team=opp, player_id=defender, start=self._pt(self.ball), outcome=Outcome.WON
        )

    def _cross(self, pos: dict[str, Pos]) -> None:
        team = self.poss_team
        in_box = [
            pid
            for pid, p in pos.items()
            if self.team_of[pid] == team and pid != self.carrier and pitch.in_box(self._f(team, p))
        ]
        if not in_box:
            self._pass(pos)
            return
        receiver = self.rng.choice(in_box)
        if self._pass(pos, receiver=receiver, kind="cross") and self.rng.random() < 0.5:
            self._shot(self._positions(), body_part=BodyPart.HEAD, decide=0.1)

    def _clearance(self, pos: dict[str, Pos]) -> None:
        team, opp = self.poss_team, self._opp(self.poss_team)
        u, v = self._f(team, self.ball)
        end = self._f(
            team,
            (
                pitch.clamp(u + self.rng.uniform(35, 55), 30, 100),
                pitch.clamp(v + self.rng.gauss(0, 12), 3, 65),
            ),
        )
        speed = self.rng.uniform(18, 25)
        pressers = self._pressers(pos)
        self.clock += self.rng.uniform(0.2, 0.8)
        self._emit(
            EventType.CLEARANCE,
            team=team,
            player_id=self.carrier,
            start=self._pt(self.ball),
            end=self._pt(end),
            ball_speed_mps=round(speed, 1),
            under_pressure=bool(pressers),
            pressure_players=pressers,
        )
        self.clock += pitch.dist(self.ball, end) / speed + self.rng.uniform(1, 3)
        self.ball = end
        if self.rng.random() < 0.55:
            winner = self._nearest(pos, opp, end)
            self._change_possession(winner)
        else:
            winner = self._nearest(pos, team, end, exclude={self.carrier})
            self.carrier = winner
        self._emit(
            EventType.RECOVERY,
            team=self.team_of[winner],
            player_id=winner,
            start=self._pt(end),
            outcome=Outcome.WON,
        )

    def _foul(self, pos: dict[str, Pos], fouler: str, *, labels=(), card: str | None = None) -> None:
        team = self.team_of[fouler]
        self.clock += self.rng.uniform(0.2, 0.8)
        self._emit(
            EventType.FOUL,
            team=team,
            player_id=fouler,
            start=self._pt(self.ball),
            details={"fouled_id": self.carrier},
            labels=labels,
        )
        self.clock += self.rng.uniform(15, 40)
        if card is None and fouler not in self.booked and self.rng.random() < 0.13:
            card = "yellow"
        if card == "yellow":
            self.booked.add(fouler)
        if card:
            self._emit(
                EventType.CARD,
                team=team,
                player_id=fouler,
                details={"card": card},
                labels=labels,
            )
        if card == "red":
            self.sent_off.add(fouler)

    # ---------------------------------------------------------------- shots

    def _internal_quality(self, s: Pos, blockers: int, header: bool) -> float:
        """Hidden chance model used only to roll random goals. The stats engine
        computes its own chance quality from the event data."""
        d = pitch.distance_to_goal(s)
        q = (0.05 + 0.75 * math.exp(-d / 7)) * pitch.clamp(pitch.goal_angle(s) / 0.6, 0.15, 1.2)
        q *= 0.7**blockers
        q *= 0.6 if header else 1.0
        return pitch.clamp(q, 0.01, 0.8)

    def _shot(
        self,
        pos: dict[str, Pos],
        *,
        forced: Outcome | None = None,
        body_part: BodyPart | None = None,
        decide: float | None = None,
        labels=(),
        details: dict | None = None,
        restart: bool = True,
    ) -> Event:
        team, shooter, opp = self.poss_team, self.carrier, self._opp(self.poss_team)
        s = self._f(team, self.ball)
        opp_keeper = self._keeper_id(opp)
        blockers = [
            pid
            for pid, p in pos.items()
            if self.team_of[pid] == opp
            and pid != opp_keeper
            and pitch.in_shot_cone(self._f(team, p), s)
            and pitch.dist(self._f(team, p), s) < 12
        ]
        header = body_part == BodyPart.HEAD
        if forced is not None:
            outcome = forced
        else:
            q = self._internal_quality(s, len(blockers), header)
            r = self.rng.random()
            p_block = min(0.55, 0.12 + 0.18 * len(blockers)) if blockers else 0.0
            if self.script.random_goals and r < q:
                outcome = Outcome.GOAL
            else:
                r = self.rng.random()
                if r < p_block:
                    outcome = Outcome.BLOCKED
                elif r < p_block + (1 - p_block) * 0.42:
                    outcome = Outcome.SAVED
                else:
                    outcome = Outcome.OFF_TARGET
        if body_part is None:
            body_part = BodyPart.RIGHT_FOOT if self.rng.random() < 0.7 else BodyPart.LEFT_FOOT
        if header:
            speed = pitch.clamp(self.rng.gauss(21.5, 1.0), 20, 24)
        else:
            speed = pitch.clamp(self.rng.gauss(27, 3.5), 20, 35)

        blocker = None
        if outcome == Outcome.GOAL:
            end_f = (105.0, 34 + self.rng.uniform(-3.2, 3.2))
        elif outcome == Outcome.SAVED:
            end_f = (104.6, 34 + self.rng.uniform(-3.0, 3.0))
        elif outcome == Outcome.OFF_TARGET:
            end_f = (105.0, 34 + self.rng.choice((-1, 1)) * self.rng.uniform(4.2, 11))
        else:
            pool = blockers or [pid for pid in pos if self.team_of[pid] == opp and pid != opp_keeper]
            blocker = min(pool, key=lambda pid: pitch.dist(pos[pid], self.ball))
            end_f = self._f(team, pos[blocker])
        end = self._f(team, end_f)

        if outcome == Outcome.GOAL:
            self.score[team] += 1
        info = dict(details or {})
        if outcome == Outcome.GOAL:
            info.update(self._score_details())
        if blocker:
            info["blocked_by"] = blocker
        pressers = self._pressers(pos)
        self.clock += self.rng.uniform(0.3, 1.0) if decide is None else decide
        event = self._emit(
            EventType.SHOT,
            team=team,
            player_id=shooter,
            start=self._pt(self.ball),
            end=self._pt(end),
            outcome=outcome,
            ball_speed_mps=round(speed, 1),
            under_pressure=bool(pressers),
            pressure_players=pressers,
            body_part=body_part,
            freeze_frame=self._freeze_frame(pos, shooter),
            details=info,
            labels=labels,
        )
        self.clock += pitch.dist(self.ball, end) / speed
        if restart:
            self._after_shot(outcome, pos, blocker)
        return event

    def _after_shot(self, outcome: Outcome, pos: dict[str, Pos], blocker: str | None) -> None:
        team, opp = self.poss_team, self._opp(self.poss_team)
        if outcome == Outcome.GOAL:
            self.clock += self.rng.uniform(40, 70)
            self._kickoff(opp)
        elif outcome == Outcome.SAVED:
            self.clock += self.rng.uniform(3, 8)
            self.ball = self._f(opp, (5.0, 34.0))
            self._change_possession(self._keeper_id(opp))
        elif outcome == Outcome.OFF_TARGET:
            self.clock += self.rng.uniform(20, 35)
            self.ball = self._f(opp, (6.0, 34 + self.rng.uniform(-6, 6)))
            self._change_possession(self._keeper_id(opp))
        else:
            self.ball = pos[blocker]
            if self.rng.random() < 0.5:
                winner = blocker
                self._change_possession(winner)
            else:
                winner = self._nearest(pos, team, self.ball, exclude={self.carrier})
                self.carrier = winner
            self.clock += self.rng.uniform(0.5, 1.5)
            self._emit(
                EventType.RECOVERY,
                team=self.team_of[winner],
                player_id=winner,
                start=self._pt(self.ball),
                outcome=Outcome.WON,
            )

    def _kickoff(self, team: str) -> None:
        self.ball = pitch.CENTRE
        self._change_possession(self._striker(team))
        receiver = self._pick_line(team, {"MID"}, exclude={self.carrier})
        spot = self._f(team, (44.0, 34 + self.rng.uniform(-8, 8)))
        pos = self._positions()
        pos[receiver] = spot
        self._pass(pos, receiver=receiver, end=spot, force=True, decide=0.0, kind="kickoff")

    # ----------------------------------------------------------------- runs

    def _random_run(self, pos: dict[str, Pos]) -> None:
        team = self.poss_team
        runners = [
            pid
            for pid in pos
            if self.team_of[pid] == team and pid != self.carrier and self.player_by_id[pid].line == "FWD"
        ]
        if not runners:
            return self._pass(pos)
        self._run_window(pos, self.rng.choice(runners), found=self.rng.random() < 0.5)

    def _run_window(
        self,
        pos: dict[str, Pos],
        runner: str,
        *,
        found: bool,
        scripted: bool = False,
        labels=(),
    ) -> None:
        """A forward runs in behind. Records 3 s of positions for the runner,
        the ball carrier, the opposition back line and keeper. If found, the
        through ball is played after 1 s; if not, the carrier recycles it."""
        team, opp, carrier = self.poss_team, self._opp(self.poss_team), self.carrier
        f = {pid: self._f(team, p) for pid, p in pos.items()}
        opp_keeper = self._keeper_id(opp)
        outfield = [pid for pid in f if self.team_of[pid] == opp and pid != opp_keeper]
        back_line = sorted(outfield, key=lambda pid: f[pid][0], reverse=True)[:4]
        line_u = f[back_line[0]][0] if back_line else 95.0

        r0 = (min(f[runner][0], line_u - 0.6), f[runner][1])
        speed = 8.2 if scripted else self.rng.uniform(7.0, 9.2)
        target = (min(r0[0] + speed * RUN_WINDOW_S * 0.95, 100.0), r0[1] + (34 - r0[1]) * 0.4)
        span = max(pitch.dist(r0, target), 0.1)
        retreat = {pid: (5.2 if scripted else self.rng.uniform(4.6, 6.0)) for pid in back_line}
        c0, k0 = f[carrier], f[opp_keeper]

        def runner_at(t: float) -> Pos:
            return pitch.lerp(r0, target, min(speed * t / span, 1.0))

        def carrier_at(t: float) -> Pos:
            return (c0[0] + 1.2 * t, c0[1])

        def scene_at(t: float) -> dict[str, Pos]:
            r = runner_at(t)
            out = dict(f)
            out[runner], out[carrier] = r, carrier_at(t)
            for pid in back_line:
                u, v = f[pid]
                out[pid] = (min(u + retreat[pid] * t, 103.0), v + (r[1] - v) * 0.08 * t)
            out[opp_keeper] = (min(k0[0] + 0.8 * t, 103.5), k0[1] + (r[1] - k0[1]) * 0.1 * t)
            return out

        pass_t = 1.0
        pass_end = runner_at(2.0)
        pass_d = pitch.dist(carrier_at(pass_t), pass_end)

        def ball_at(t: float) -> Pos:
            if found and t >= pass_t:
                return pitch.lerp(carrier_at(pass_t), pass_end, min((t - pass_t) * 18 / pass_d, 1.0))
            return carrier_at(t)

        in_frame = [runner, carrier, *back_line, opp_keeper]
        frames = []
        for k in range(int(RUN_WINDOW_S / RUN_FRAME_STEP_S) + 1):
            t = k * RUN_FRAME_STEP_S
            scene = {pid: self._f(team, p) for pid, p in scene_at(t).items()}
            frames.append(
                TrackingFrame(
                    t_offset_s=t,
                    ball=self._pt(self._f(team, ball_at(t))),
                    players=self._frame_players(scene, runner, in_frame),
                )
            )

        start_clock = self.clock + self.rng.uniform(0.3, 0.8)
        self.clock = start_clock
        self._emit(
            EventType.RUN,
            team=team,
            player_id=runner,
            start=self._pt(self._f(team, r0)),
            end=self._pt(self._f(team, runner_at(RUN_WINDOW_S))),
            outcome=Outcome.FOUND if found else Outcome.NOT_FOUND,
            player_speed_mps=round(speed, 1),
            tracking=frames,
            details={"carrier_id": carrier},
            labels=labels,
        )
        self.run_cooldown_until = start_clock + 45

        if found:
            scene = {pid: self._f(team, p) for pid, p in scene_at(pass_t).items()}
            self.ball = self._f(team, carrier_at(pass_t))
            self._pass(
                scene,
                receiver=runner,
                end=self._f(team, pass_end),
                force=True if scripted else self.rng.random() < 0.72,
                decide=pass_t,
                kind="through_ball",
                labels=labels,
            )
        else:
            scene = {pid: self._f(team, p) for pid, p in scene_at(RUN_WINDOW_S).items()}
            self.ball = self._f(team, carrier_at(RUN_WINDOW_S))
            scene[carrier] = self.ball
            receiver = self._pick_receiver(scene, sideways=True, exclude={runner})
            self._pass(
                scene,
                receiver=receiver,
                force=True if scripted else None,
                decide=RUN_WINDOW_S,
                labels=labels,
            )

    # ---------------------------------------------------------------- beats

    def _take_possession(self, team: str) -> None:
        if self.poss_team == team:
            return
        pos = self._positions()
        winner = self._nearest(pos, team, self.ball)
        self.clock += self.rng.uniform(0.5, 1.5)
        self._change_possession(winner)
        self._emit(
            EventType.RECOVERY, team=team, player_id=winner, start=self._pt(self.ball), outcome=Outcome.WON
        )

    def _move_ball_to(self, team: str, holder: str, spot_f: Pos, exclude: set[str], labels) -> None:
        """Forced build-up: work the ball to `holder` standing at `spot_f`."""
        u = self._f(team, self.ball)[0]
        waypoints = []
        if u < 40:
            waypoints.append(({"DEF", "MID"}, (self.rng.uniform(44, 50), 34 + self.rng.uniform(-14, 14))))
        if u < 66 and spot_f[0] > 70:
            waypoints.append(({"MID"}, (self.rng.uniform(60, 68), 34 + self.rng.uniform(-16, 16))))
        for lines, wp in waypoints:
            receiver = self._pick_line(team, lines, exclude={*exclude, holder, self.carrier})
            pos = self._positions()
            pos[receiver] = self._f(team, wp)
            self._pass(pos, receiver=receiver, end=pos[receiver], force=True, labels=labels)
        spot = self._f(team, spot_f)
        if self.carrier == holder:
            self._carry(self._positions(), target=spot, labels=labels)
        else:
            pos = self._positions()
            pos[holder] = spot
            self._pass(pos, receiver=holder, end=spot, force=True, labels=labels)

    def _beat_goal(self, beat: Beat) -> None:
        self._scripted_goal(beat, ["scripted:goal"])

    def _scripted_goal(self, beat: Beat, labels: list[str], restart: bool = True) -> Event:
        team, scorer = beat.team, beat.player
        assister = beat.assist or self._pick_line(team, {"MID", "FWD"}, exclude={scorer})
        self._take_possession(team)
        side_v = self.teams[team].player(assister).base[1] - 34
        side = (1 if side_v > 0 else -1) if abs(side_v) > 1 else self.rng.choice((-1, 1))
        cross = abs(side_v) > 15
        if cross:
            a_spot = (self.rng.uniform(88, 93), 34 + side * self.rng.uniform(19, 24))
            s_spot = (self.rng.uniform(93, 97), 34 + self.rng.uniform(-4, 4))
        else:
            a_spot = (self.rng.uniform(80, 86), 34 + self.rng.uniform(-10, 10))
            s_spot = (self.rng.uniform(88, 95), 34 + self.rng.uniform(-6, 6))
        self._move_ball_to(team, assister, a_spot, exclude={scorer}, labels=labels)
        pos = self._positions()
        pos[scorer] = self._f(team, s_spot)
        self._pass(
            pos,
            receiver=scorer,
            end=pos[scorer],
            force=True,
            kind="cross" if cross else "through_ball",
            labels=labels,
        )
        return self._shot(
            self._positions(),
            forced=Outcome.GOAL,
            body_part=BodyPart.HEAD if cross else None,
            decide=0.3 if cross else None,
            labels=labels,
            details={"assist_id": assister},
            restart=restart,
        )

    def _beat_disallowed_goal(self, beat: Beat) -> None:
        """A goal that a VAR review rules out (offside in the build-up, a handball
        or a foul) `review_s` seconds later, before the restart. The shot stays a
        shot; the goal comes off the score."""
        team = beat.team
        shot = self._scripted_goal(beat, ["scripted:disallowed_goal"], restart=False)
        self.clock += beat.review_s
        self.score[team] -= 1
        self._emit(
            EventType.VAR_REVIEW,
            team=team,
            player_id=beat.player,
            outcome=Outcome.OVERTURNED,
            reviewed_event_id=shot.event_id,
            review_reason=ReviewReason(beat.reason),
            details=self._score_details(),
            labels=["scripted:var_review"],
        )
        # Restart: a free kick to the defending side, deep in its own half.
        opp = self._opp(team)
        self.ball = self._f(opp, (self.rng.uniform(14, 22), 34 + self.rng.uniform(-12, 12)))
        self._change_possession(self._pick_line(opp, {"DEF"}, exclude=set()))
        self.clock += self.rng.uniform(8, 15)

    def _beat_missed_option(self, beat: Beat) -> None:
        """Trigger 1: the shooter goes for goal from a tight angle while a
        teammate stands unmarked in a far better spot."""
        team, shooter, open_pid = beat.team, beat.player, beat.open_player
        labels = ["scripted:missed_option"]
        side = 1 if self.teams[team].player(shooter).base[1] >= 34 else -1
        s_spot = (97.5, 34 + side * 13.5)
        o_spot = (94.0, 34 - side * 2.5)
        feeder_spot = (86.0, 34 + side * 19.0)

        self._take_possession(team)
        feeder = self._pick_line(team, {"MID", "DEF"}, exclude={shooter, open_pid})
        if self.carrier not in (shooter, open_pid):
            feeder = self.carrier if self.player_by_id[self.carrier].line != "GK" else feeder
        self._move_ball_to(team, feeder, feeder_spot, exclude={shooter, open_pid}, labels=labels)
        pos = self._positions()
        pos[shooter] = self._f(team, s_spot)
        self._pass(pos, receiver=shooter, end=pos[shooter], force=True, labels=labels)

        scene = self._missed_option_scene(team, shooter, open_pid, side, s_spot, o_spot)
        self._shot(
            scene,
            forced=Outcome(beat.outcome),
            labels=[*labels, f"better_option:{open_pid}"],
        )

    def _missed_option_scene(
        self, team: str, shooter: str, open_pid: str, side: int, s_spot: Pos, o_spot: Pos
    ) -> dict[str, Pos]:
        opp = self._opp(team)
        f = {pid: self._f(team, p) for pid, p in self._positions().items()}
        f[shooter], f[open_pid] = s_spot, o_spot
        order = {"DEF": 0, "MID": 1, "FWD": 2}
        cover = sorted(
            (p for p in self._active(opp) if p.line != "GK"),
            key=lambda p: (order[p.line], p.number),
        )
        slots = [
            (99.6, 34 + side * 10.6),  # goal-side, in the shooting lane
            (96.3, 34 + side * 14.6),  # closing the shooter down
            (102.0, 34 + side * 4.8),  # covering the near post
            (92.5, 34 - side * 13.0),  # marking the far-side runner
        ]
        assigned = set()
        for p, slot in zip(cover, slots, strict=False):
            f[p.player_id] = slot
            assigned.add(p.player_id)
        f[self._keeper_id(opp)] = (103.2, 34 + side * 2.4)
        assigned.add(self._keeper_id(opp))
        far = [
            p.player_id
            for p in self._active(team)
            if p.line in ("FWD", "MID") and p.player_id not in (shooter, open_pid)
        ]
        if far:
            f[far[0]] = (93.5, 34 - side * 12.0)
        for pid, p in f.items():
            if self.team_of[pid] == opp and pid not in assigned and pitch.dist(p, o_spot) < 9:
                f[pid] = (min(p[0], o_spot[0] - 9.5), p[1])
        return {pid: self._f(team, p) for pid, p in f.items()}

    def _beat_run_not_found(self, beat: Beat) -> None:
        """Trigger 2: a forward is clean through but the ball never comes."""
        team, runner = beat.team, beat.player
        labels = ["scripted:run_not_found"]
        carrier = beat.carrier or self._pick_line(team, {"MID"}, exclude={runner})
        self._take_possession(team)
        self._move_ball_to(team, carrier, (60.0, 36.0), exclude={runner}, labels=labels)

        opp = self._opp(team)
        f = {pid: self._f(team, p) for pid, p in self._positions().items()}
        defenders = [p.player_id for p in self._active(opp) if p.line == "DEF"]
        for pid, v in zip(defenders, (16.0, 27.0, 41.0, 52.0), strict=False):
            f[pid] = (79.0, v)
        for p in self._active(opp):
            if p.line in ("MID", "FWD"):
                f[p.player_id] = (min(f[p.player_id][0], 72.0), f[p.player_id][1])
        f[self._keeper_id(opp)] = (100.5, 34.0)
        f[runner] = (78.2, 31.0)
        f[carrier] = (60.0, 36.0)
        scene = {pid: self._f(team, p) for pid, p in f.items()}
        self.ball = scene[carrier]
        self._run_window(scene, runner, found=False, scripted=True, labels=labels)

    def _beat_red_card(self, beat: Beat) -> None:
        player, team = beat.player, beat.team
        labels = ["scripted:red_card"]
        if player in self.sent_off:
            return
        if self.poss_team == team:
            pos = self._positions()
            winner = self._nearest(pos, self._opp(team), self.ball)
            self.clock += self.rng.uniform(0.5, 1.5)
            self._change_possession(winner)
            self._emit(
                EventType.TACKLE,
                team=self.poss_team,
                player_id=winner,
                start=self._pt(self.ball),
                outcome=Outcome.WON,
            )
        self._foul(self._positions(), player, labels=labels, card="red")
        self.clock += self.rng.uniform(40, 80)

    def _beat_milestone(self, beat: Beat) -> None:
        self._emit(
            EventType.MILESTONE,
            team=beat.team,
            player_id=beat.player,
            details={"label": beat.label},
            labels=["scripted:milestone"],
        )


def simulate(script: MatchScript, seed: int) -> list[Event]:
    return MatchEngine(script, seed).run()
