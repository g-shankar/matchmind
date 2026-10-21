"""Synthetic tracking feed rendered from a simulated match.

The simulator writes events; real auto-eventing works the other way round,
from tracking data to events. To test that direction honestly we first render
a tracking feed (ball and all 22 players at a fixed frame rate) from the
simulated match, then hand only the frames to the detector and score what it
finds against the simulator's events.

What the feed is and is not:
- 2D positions only (no ball height), on the 105 x 68 pitch, home team
  attacking towards x = 105 for the whole match (as in the event schema).
- The ball moves in straight lines at the event's recorded speed, so speeds are
  exact before noise. Gaussian measurement noise is added to every position and
  the ball drops out for short spells, as it does behind bodies in real feeds.
- Players other than the ball holder follow a simple team-shape model and run
  to wherever the events say they must be next (receiving a pass, making an
  interception). Their movement is plausible, not a physical model.
- Each frame carries a ball-in-play flag, as real feeds do.

It is synthetic tracking, not video, and nothing here is presented as video.
"""

from __future__ import annotations

import bisect
import math
import random
import zlib
from array import array
from dataclasses import dataclass, field

from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator import pitch
from matchmind.simulator.teams import get_team

DEFAULT_HZ = 25.0
BALL_NOISE_M = 0.05
PLAYER_NOISE_M = 0.05
DROPOUT_RATE_PER_S = 0.05  # ball lost behind bodies roughly every 20 s of play
DROPOUT_S = (0.12, 0.4)
HOLD_OFFSET_M = 0.35  # the holder stands just behind the ball
ANCHOR_LOOKAHEAD_S = 4.0
SHAPE_SPEED_MPS = 7.0
MAX_CATCH_UP_MPS = 12.0

_KICKS = {EventType.PASS, EventType.SHOT, EventType.CLEARANCE}
_MOVES = _KICKS | {EventType.CARRY, EventType.DRIBBLE}
_GAINS = {EventType.RECOVERY, EventType.INTERCEPTION, EventType.TACKLE}


@dataclass(slots=True)
class Frame:
    period: int
    clock_s: float
    alive: bool
    ball: tuple[float, float] | None  # None while the ball is not tracked
    xy: array  # x0, y0, x1, y1, ... in feed.player_ids order; NaN when off the pitch

    def player(self, index: int) -> tuple[float, float] | None:
        x = self.xy[2 * index]
        return None if math.isnan(x) else (x, self.xy[2 * index + 1])


@dataclass(slots=True)
class TrackingFeed:
    """What a tracking provider would deliver: no events, no labels."""

    match_id: str
    hz: float
    player_ids: tuple[str, ...]
    player_teams: tuple[str, ...]
    attacks_right: dict[str, bool]  # team id -> attacks towards x = 105
    frames: list[Frame] = field(default_factory=list)
    source: str = "synthetic_tracking"


@dataclass(slots=True)
class _Key:
    t: float
    pos: tuple[float, float]


@dataclass(slots=True)
class _Period:
    start: float
    end: float
    keys: list[_Key] = field(default_factory=list)
    dead: list[tuple[float, float]] = field(default_factory=list)  # ball out of play
    hold: list[tuple[float, float, str]] = field(default_factory=list)  # (from, to, holder)
    anchors: dict[str, list[tuple[float, tuple[float, float]]]] = field(default_factory=dict)
    team_at: list[tuple[float, str]] = field(default_factory=list)  # possession changes


def _d(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _xy(p) -> tuple[float, float]:
    return (p.x, p.y)


class _Builder:
    """Turns the event list into ball keyframes, holders and run targets."""

    def __init__(self, events: list[Event]) -> None:
        start = events[0]
        if start.type != EventType.MATCH_START or not start.lineups:
            raise ValueError("The event list must begin with match_start and its lineups.")
        self.home = str(start.details["home"])
        self.away = str(start.details["away"])
        self.events = events
        self.player_ids = tuple(p.player_id for p in start.lineups)
        self.team_of = {p.player_id: p.team for p in start.lineups}
        self.base = {
            p.player_id: (p.base, p.line) for t in (self.home, self.away) for p in get_team(t).players
        }
        self.sent_off: dict[str, tuple[int, float]] = {}
        self.periods: dict[int, _Period] = {}

    def build(self) -> None:
        for period in (1, 2):
            evs = [e for e in self.events if e.period == period]
            if not evs:
                continue
            self.periods[period] = self._period(evs)
        for e in self.events:
            if e.type == EventType.CARD and e.details.get("card") == "red" and e.player_id:
                self.sent_off[e.player_id] = (e.period, e.clock_s)

    def _period(self, evs: list[Event]) -> _Period:
        per = _Period(start=evs[0].clock_s, end=evs[-1].clock_s)
        stopped_at: float | None = per.start  # ball dead until the kick-off
        last_end = per.start
        for i, e in enumerate(evs):
            t = e.clock_s
            if e.team:
                per.team_at.append((t, e.team))
            if e.type in _MOVES and e.start is not None:
                s = _xy(e.start)
                if stopped_at is not None:
                    per.dead.append((stopped_at, t))
                    stopped_at = None
                elif per.keys and _d(per.keys[-1].pos, s) > 4.0 * max(t - last_end, 0.25):
                    per.dead.append((last_end, t))  # ball moved too fast to be in play
                per.keys.append(_Key(t, s))
                if e.player_id:
                    # The actor has the ball from the last keyframe until the kick.
                    per.hold.append((max(last_end, t - 30.0), t, e.player_id))
                    per.anchors.setdefault(e.player_id, []).append((t, s))
                end_t = t
                if e.end is not None:
                    end = _xy(e.end)
                    speed = e.ball_speed_mps or e.player_speed_mps or 6.0
                    end_t = t + max(_d(s, end), 0.01) / speed
                    per.keys.append(_Key(end_t, end))
                    if e.type in (EventType.CARRY, EventType.DRIBBLE) and e.player_id:
                        per.hold.append((t, end_t, e.player_id))
                    receiver = self._receiver(e, evs[i + 1 :])
                    if receiver:
                        per.anchors.setdefault(receiver, []).append((end_t, end))
                        if e.type == EventType.SHOT:
                            per.hold.append((end_t, end_t + 0.3, receiver))  # the blocker smothers it
                last_end = end_t
                if e.type == EventType.PASS and e.outcome == Outcome.OUT:
                    stopped_at = end_t
                if e.type == EventType.SHOT and e.outcome in (
                    Outcome.GOAL,
                    Outcome.SAVED,
                    Outcome.OFF_TARGET,
                ):
                    stopped_at = end_t
            elif e.type in _GAINS and e.start is not None and e.player_id:
                s = _xy(e.start)
                if stopped_at is None:
                    per.keys.append(_Key(max(t, last_end), s))
                    last_end = max(t, last_end)
                per.anchors.setdefault(e.player_id, []).append((max(t, last_end), s))
            elif e.type == EventType.FOUL and stopped_at is None:
                stopped_at = max(t, last_end)
        if stopped_at is not None:
            per.dead.append((stopped_at, per.end + 1.0))
        per.keys.sort(key=lambda k: k.t)
        for lst in per.anchors.values():
            lst.sort()
        per.hold.sort()
        return per

    def _receiver(self, e: Event, rest: list[Event]) -> str | None:
        if e.type == EventType.PASS and e.outcome == Outcome.COMPLETE:
            return e.receiver_id
        if e.type == EventType.SHOT and e.outcome == Outcome.BLOCKED:
            blocker = e.details.get("blocked_by")
            return str(blocker) if blocker else None
        if e.type == EventType.PASS and e.outcome == Outcome.INCOMPLETE and rest:
            nxt = rest[0]
            if nxt.type == EventType.INTERCEPTION:
                return nxt.player_id
        return None


class _BallPath:
    def __init__(self, per: _Period) -> None:
        self.t = [k.t for k in per.keys]
        self.p = [k.pos for k in per.keys]
        self.dead_from = [a for a, _ in per.dead]
        self.dead = per.dead

    def is_dead(self, t: float) -> tuple[float, float] | None:
        i = bisect.bisect_right(self.dead_from, t) - 1
        if i >= 0 and self.dead[i][0] <= t < self.dead[i][1]:
            return self.dead[i]
        return None

    def at(self, t: float) -> tuple[float, float]:
        if not self.t:
            return pitch.CENTRE
        i = bisect.bisect_right(self.t, t)
        if i == 0:
            return self.p[0]
        if i == len(self.t):
            return self.p[-1]
        t0, t1, p0, p1 = self.t[i - 1], self.t[i], self.p[i - 1], self.p[i]
        dead = self.is_dead(t)
        if dead is not None:
            # Out of play: the ball sits where it stopped, then at the restart spot.
            return p0 if t < (dead[0] + dead[1]) / 2 else p1
        if t1 - t0 <= 1e-9:
            return p1
        f = (t - t0) / (t1 - t0)
        return (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)


class _Renderer:
    def __init__(self, b: _Builder, hz: float, seed: int) -> None:
        self.b = b
        self.hz = hz
        self.rng = random.Random(seed)
        self.attacks_right = {b.home: True, b.away: False}

    def _shape(self, pid: str, in_poss: bool, ball: tuple[float, float], jitter) -> tuple[float, float]:
        """Same team-shape idea as the simulator, in absolute coordinates."""
        team = self.b.team_of[pid]
        right = self.attacks_right[team]
        bu, bv = ball if right else pitch.flip(ball)
        (bx, by), line = self.b.base[pid]
        if in_poss:
            back, length, spread = pitch.clamp(bu - 35, 15, 60), 45.0, 1.0
        else:
            back, length, spread = pitch.clamp(bu - 25, 9, 45), 30.0, 0.75
        if line == "GK":
            u, v = pitch.clamp(back - 14, 3, 22), 34 + (bv - 34) * 0.12
        else:
            u = back + (bx - 25) / 50 * length
            v = 34 + (by - 34) * spread + (bv - 34) * 0.3
        u, v = pitch.clamp(u + jitter[0], 1, 104), pitch.clamp(v + jitter[1], 1, 67)
        return (u, v) if right else pitch.flip((u, v))

    def render(self) -> TrackingFeed:
        b = self.b
        feed = TrackingFeed(
            match_id=b.events[0].match_id,
            hz=self.hz,
            player_ids=b.player_ids,
            player_teams=tuple(b.team_of[p] for p in b.player_ids),
            attacks_right=dict(self.attacks_right),
        )
        for period, per in sorted(b.periods.items()):
            feed.frames.extend(self._render_period(period, per))
        return feed

    def _render_period(self, period: int, per: _Period) -> list[Frame]:
        b, rng, dt = self.b, self.rng, 1.0 / self.hz
        ids = b.player_ids
        n_players = len(ids)
        teams = [b.team_of[pid] for pid in ids]
        back = [-HOLD_OFFSET_M if self.attacks_right[t] else HOLD_OFFSET_M for t in teams]
        anchors = [per.anchors.get(pid, []) for pid in ids]
        anchor_idx = [0] * n_players
        off_at = []
        for pid in ids:
            off = b.sent_off.get(pid)
            off_at.append(
                math.inf if not off or off[0] > period else (-math.inf if off[0] < period else off[1])
            )
        index_of = {pid: n for n, pid in enumerate(ids)}
        holds = [(h0, h1, index_of[who]) for h0, h1, who in per.hold]
        team_t = [t for t, _ in per.team_at]
        team0 = per.team_at[0][1] if per.team_at else b.home
        # A fixed table of standard normals keeps the noise cheap and reproducible.
        noise = [rng.gauss(0, 1) for _ in range(9973)]
        nz = 0
        path = _BallPath(per)
        ball0 = path.at(per.start)
        pos = [self._shape(pid, teams[n] == team0, ball0, (0.0, 0.0)) for n, pid in enumerate(ids)]
        targets = list(pos)
        jitter = [(0.0, 0.0)] * n_players
        jitter_poss = None
        shape_every = max(1, round(0.2 * self.hz))
        h = 0

        frames: list[Frame] = []
        dropout_until = -1.0
        n_frames = int(math.floor((per.end - per.start) * self.hz)) + 1
        for k in range(n_frames):
            t = per.start + k * dt
            ball = path.at(t)
            alive = path.is_dead(t) is None
            i = bisect.bisect_right(team_t, t) - 1
            poss = per.team_at[i][1] if i >= 0 else team0
            if poss != jitter_poss:
                jitter_poss = poss
                jitter = [(rng.gauss(0, 1.2), rng.gauss(0, 1.2)) for _ in ids]
            if k % shape_every == 0:
                targets = [self._shape(pid, teams[n] == poss, ball, jitter[n]) for n, pid in enumerate(ids)]
            while h < len(holds) - 1 and holds[h][1] < t:
                h += 1
            holder = holds[h][2] if holds and alive and holds[h][0] <= t <= holds[h][1] else -1

            xy = array("f", [math.nan]) * (2 * n_players)
            for n in range(n_players):
                if t >= off_at[n]:
                    continue
                cx, cy = pos[n]
                if n == holder:
                    nx, ny = ball[0] + back[n], ball[1]
                else:
                    lst, a = anchors[n], anchor_idx[n]
                    while a < len(lst) and lst[a][0] < t:
                        a += 1
                    anchor_idx[n] = a
                    if a < len(lst) and lst[a][0] - t <= ANCHOR_LOOKAHEAD_S:
                        ta, (tx, ty) = lst[a]
                        gap = math.hypot(tx - cx, ty - cy)
                        speed = min(gap / max(ta - t, dt), MAX_CATCH_UP_MPS)
                    else:
                        tx, ty = targets[n]
                        gap = math.hypot(tx - cx, ty - cy)
                        speed = min(SHAPE_SPEED_MPS, gap / 0.6)
                    if gap > 1e-9:
                        f = min(1.0, speed * dt / gap)
                        nx, ny = cx + (tx - cx) * f, cy + (ty - cy) * f
                    else:
                        nx, ny = cx, cy
                pos[n] = (nx, ny)
                nz = (nz + 2) % 9971
                x = nx + noise[nz] * PLAYER_NOISE_M
                y = ny + noise[nz + 1] * PLAYER_NOISE_M
                xy[2 * n] = 0.0 if x < 0 else pitch.LENGTH if x > pitch.LENGTH else x
                xy[2 * n + 1] = 0.0 if y < 0 else pitch.WIDTH if y > pitch.WIDTH else y

            if alive and t >= dropout_until and rng.random() < DROPOUT_RATE_PER_S * dt:
                dropout_until = t + rng.uniform(*DROPOUT_S)
            seen = None
            if t >= dropout_until:
                seen = (
                    pitch.clamp(ball[0] + rng.gauss(0, BALL_NOISE_M), 0, pitch.LENGTH),
                    pitch.clamp(ball[1] + rng.gauss(0, BALL_NOISE_M), 0, pitch.WIDTH),
                )
            frames.append(Frame(period, round(t, 3), alive, seen, xy))
        return frames


def render_tracking(events: list[Event], *, hz: float = DEFAULT_HZ, seed: int | None = None) -> TrackingFeed:
    """Render a synthetic tracking feed for one simulated match.

    The same events and seed always give the same feed. By default the seed
    comes from the match id, so each match has its own fixed noise.
    """
    if hz <= 0:
        raise ValueError("hz must be positive")
    if seed is None:
        seed = zlib.crc32(events[0].match_id.encode())
    builder = _Builder(events)
    builder.build()
    return _Renderer(builder, hz, seed).render()
