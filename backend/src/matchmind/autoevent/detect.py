"""Find passes, shots, clearances, possession changes and pressure in a tracking feed.

The detector sees only what a tracking provider delivers (ball and player
positions per frame, a ball-in-play flag, team ids and playing directions). It
never reads the simulator's events or labels.

Method, in plain words:
0. Clean the feed. Estimate the position noise from the ball's own track (the
   spread of its second differences). On a clean feed (under 8 cm) nothing is
   smoothed. On a noisier one, positions are averaged over a short centred
   window sized to bring the noise back to about 5 cm (at most 0.5 s). Short
   gaps in a player's track (up to 2 s) are bridged in a straight line. The
   kick speed is still fitted on the unsmoothed ball.
1. Fill short ball dropouts by straight-line interpolation.
2. Ball velocity from a central difference over about 0.08 s.
3. A player controls the ball in a frame when they are the nearest player,
   within 1 m, and moving with the ball (relative speed under 3 m/s).
4. Between two spells of control the ball was kicked if it reached 8 m/s.
   The kick's speed is fitted from the first 0.24 s of flight.
5. The kick is a pass to a teammate if a teammate controls it next. Otherwise
   it is a shot if it heads for the goal mouth (within 12 m of the centre of
   the goal line) from inside 50 m at 18 m/s or more; a clearance if the ball
   then lies loose with nobody on it for 0.4 s or more; a pass out of play if
   play stops; and an incomplete pass if an opponent controls it.
6. A shot that goes out of play is a goal when play restarts on the centre
   spot, saved when it ended on the goal line between the posts, otherwise off
   target. A shot an opponent controls at once is blocked.
7. Possession changes, between two spells of control with the ball in play:
   - a tackle when control passes to the other team without a kick in between;
   - an interception when the other team takes a pass of the old team in
     flight (no loose spell first);
   - a recovery when someone takes a loose ball (after a clearance, a blocked
     shot or any kick that came to rest for 0.4 s), whichever team they are on.
   The event is placed on the first frame of the new spell of control.
8. Pressure: at the moment of every kick, the kicker is under pressure when an
   opponent has been within 3.5 m of the ball for at least 0.2 s up to the
   kick. 3.5 m is the radius the event data uses for its own pressure flag.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .tracking import TrackingFeed

CONTROL_RADIUS_M = 1.0
CONTROL_REL_SPEED_MPS = 3.0
KICK_SPEED_MPS = 8.0
REST_SPEED_MPS = 3.0
SPEED_FIT_S = 0.24
MAX_GAP_FILL_S = 0.6
LOOSE_S = 0.4
SHOT_RANGE_M = 50.0
SHOT_MIN_SPEED_MPS = 18.0
SHOT_AIM_HALF_WIDTH_M = 12.0
GOAL_HALF_WIDTH_M = 3.66
CENTRE = (52.5, 34.0)
PRESSURE_RADIUS_M = 3.5
PRESSURE_MIN_S = 0.2
RECOVERY_AFTER_SHOT_S = 2.0  # a change of control this soon after a blocked shot is a recovery
NOISE_FLOOR_M = 0.08  # below this estimated noise the feed is used as it is
SMOOTH_TARGET_M = 0.05
MAX_SMOOTH_S = 0.5
MAX_PLAYER_GAP_S = 2.0
SETTLED_S = 0.3  # a spell of control this short, with no kick, is a touch in a duel, not a gain

Kind = Literal["pass", "shot", "clearance", "tackle", "interception", "recovery", "pressure"]
KICK_KINDS = ("pass", "shot", "clearance")
GAIN_KINDS = ("tackle", "interception", "recovery")


@dataclass(frozen=True, slots=True)
class DetectedEvent:
    kind: Kind
    period: int
    clock_s: float
    player_id: str
    team: str
    outcome: str  # pass: complete | incomplete | out; shot: goal | saved | blocked | off_target
    start: tuple[float, float]
    end: tuple[float, float]
    ball_speed_mps: float
    receiver_id: str | None = None  # whoever controlled the ball next, if anyone
    source: str = "synthetic_tracking"
    pressed_by: tuple[str, ...] = ()  # pressure only: the opponents near the ball


@dataclass(slots=True)
class _Control:
    player: int
    first: int
    last: int


def _fill_ball(feed: TrackingFeed, lo: int, hi: int) -> list[tuple[float, float] | None]:
    frames = feed.frames
    out: list[tuple[float, float] | None] = [
        frames[k].ball if frames[k].alive else None for k in range(lo, hi)
    ]
    max_gap = int(MAX_GAP_FILL_S * feed.hz)
    k = 0
    while k < len(out):
        if out[k] is not None or not frames[lo + k].alive:
            k += 1
            continue
        j = k
        while j < len(out) and out[j] is None and frames[lo + j].alive:
            j += 1
        if k > 0 and j < len(out) and out[j] is not None and j - k <= max_gap and out[k - 1] is not None:
            a, b = out[k - 1], out[j]
            for m in range(k, j):
                f = (m - k + 1) / (j - k + 1)
                out[m] = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        k = j
    return out


def _velocity(
    seq: list[tuple[float, float] | None], half: int, dt: float
) -> list[tuple[float, float] | None]:
    n = len(seq)
    vel: list[tuple[float, float] | None] = [None] * n
    for k in range(n):
        a, b = max(0, k - half), min(n - 1, k + half)
        pa, pb = seq[a], seq[b]
        if pa is None or pb is None or b == a or seq[k] is None:
            continue
        span = (b - a) * dt
        vel[k] = ((pb[0] - pa[0]) / span, (pb[1] - pa[1]) / span)
    return vel


def _fit_speed(ball: list, first: int, last: int, dt: float) -> float:
    """Least-squares straight-line fit of position against time."""
    pts = [(k * dt, ball[k]) for k in range(first, last + 1) if ball[k] is not None]
    if len(pts) < 2:
        return 0.0
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    mx = sum(p[0] for _, p in pts) / n
    my = sum(p[1] for _, p in pts) / n
    stt = sum((t - mt) ** 2 for t, _ in pts)
    if stt == 0:
        return 0.0
    vx = sum((t - mt) * (p[0] - mx) for t, p in pts) / stt
    vy = sum((t - mt) * (p[1] - my) for t, p in pts) / stt
    return math.hypot(vx, vy)


def estimate_noise(ball: list[tuple[float, float] | None]) -> float:
    """Robust per-axis position noise (m) from the ball track's second differences.

    For a ball moving at constant velocity the second difference is pure noise
    with standard deviation sqrt(6) x sigma; kicks and stops are rare enough
    that the median ignores them.
    """
    d2 = []
    for k in range(1, len(ball) - 1):
        a, b, c = ball[k - 1], ball[k], ball[k + 1]
        if a is not None and b is not None and c is not None:
            d2.append(abs(c[0] - 2 * b[0] + a[0]))
            d2.append(abs(c[1] - 2 * b[1] + a[1]))
    if len(d2) < 50:
        return 0.0
    return float(1.4826 * np.median(d2) / math.sqrt(6))


def smoothing_half_window(noise_m: float, hz: float) -> int:
    """Half-width (frames) of the moving average that brings noise_m down to about 5 cm."""
    if noise_m <= NOISE_FLOOR_M:
        return 0
    length = (noise_m / SMOOTH_TARGET_M) ** 2
    cap = max(0, round(MAX_SMOOTH_S * hz / 2))
    return int(min(cap, max(1, round((length - 1) / 2))))


def _moving_average(col: np.ndarray, half: int) -> np.ndarray:
    """Centred moving average within each run of finite values (window shrinks at run ends)."""
    out = col.copy()
    ok = np.isfinite(col)
    if half <= 0 or not ok.any():
        return out
    edges = np.flatnonzero(np.diff(np.concatenate(([0], ok.astype(np.int8), [0]))))
    for start, stop in zip(edges[0::2], edges[1::2], strict=True):
        seg = col[start:stop]
        c = np.concatenate(([0.0], np.cumsum(seg)))
        i = np.arange(len(seg))
        lo, hi = np.maximum(0, i - half), np.minimum(len(seg), i + half + 1)
        out[start:stop] = (c[hi] - c[lo]) / (hi - lo)
    return out


def _bridge(col: np.ndarray, max_gap: int) -> np.ndarray:
    """Straight-line fill of NaN gaps up to max_gap frames with values on both sides."""
    bad = ~np.isfinite(col)
    if not bad.any() or bad.all():
        return col
    edges = np.flatnonzero(np.diff(np.concatenate(([0], bad.astype(np.int8), [0]))))
    out = col.copy()
    for start, stop in zip(edges[0::2], edges[1::2], strict=True):
        if start == 0 or stop == len(col) or stop - start > max_gap:
            continue
        a, b = col[start - 1], col[stop]
        f = np.arange(1, stop - start + 1) / (stop - start + 1)
        out[start:stop] = a + (b - a) * f
    return out


def _player_rows(feed: TrackingFeed, lo: int, hi: int, smooth: int) -> list:
    frames = feed.frames[lo:hi]
    if not frames:
        return []
    xy = np.array([f.xy for f in frames], dtype=np.float64)
    gaps = np.isnan(xy).any(axis=0)
    if smooth == 0 and not gaps.any():
        return [f.xy for f in frames]
    max_gap = round(MAX_PLAYER_GAP_S * feed.hz)
    for c in range(xy.shape[1]):
        col = _bridge(xy[:, c], max_gap) if gaps[c] else xy[:, c]
        xy[:, c] = _moving_average(col, smooth) if smooth else col
    return xy.tolist()


def _smooth_ball(ball: list[tuple[float, float] | None], half: int) -> list[tuple[float, float] | None]:
    arr = np.array([(math.nan, math.nan) if b is None else b for b in ball], dtype=np.float64)
    sx, sy = _moving_average(arr[:, 0], half), _moving_average(arr[:, 1], half)
    return [None if b is None else (float(x), float(y)) for b, x, y in zip(ball, sx, sy, strict=True)]


class _Period:
    def __init__(self, feed: TrackingFeed, lo: int, hi: int) -> None:
        self.feed, self.lo, self.hi = feed, lo, hi
        self.dt = 1.0 / feed.hz
        self.half = max(1, round(0.04 * feed.hz))
        self.alive = [feed.frames[k].alive for k in range(lo, hi)]
        self.raw_ball = _fill_ball(feed, lo, hi)
        self.noise_m = estimate_noise(self.raw_ball)
        self.smooth = smoothing_half_window(self.noise_m, feed.hz)
        self.ball = _smooth_ball(self.raw_ball, self.smooth) if self.smooth else self.raw_ball
        self.vel = _velocity(self.ball, self.half, self.dt)
        self.rows = _player_rows(feed, lo, hi, self.smooth)

    def player_xy(self, k: int, n: int) -> tuple[float, float] | None:
        row = self.rows[k]
        x = row[2 * n]
        return None if x != x else (x, row[2 * n + 1])

    def speed(self, k: int) -> float | None:
        v = self.vel[k]
        return None if v is None else math.hypot(v[0], v[1])

    def controller(self, k: int) -> int | None:
        b = self.ball[k]
        if b is None or not self.alive[k]:
            return None
        xy = self.rows[k]
        best, best_d = -1, CONTROL_RADIUS_M
        for n in range(len(xy) // 2):
            x = xy[2 * n]
            if math.isnan(x):
                continue
            d = math.hypot(x - b[0], xy[2 * n + 1] - b[1])
            if d <= best_d:
                best, best_d = n, d
        if best < 0:
            return None
        v = self.vel[k]
        a, c = max(0, k - self.half), min(len(self.ball) - 1, k + self.half)
        pa, pc = self.player_xy(a, best), self.player_xy(c, best)
        if v is None or pa is None or pc is None or c == a:
            return best
        span = (c - a) * self.dt
        pv = ((pc[0] - pa[0]) / span, (pc[1] - pa[1]) / span)
        if math.hypot(v[0] - pv[0], v[1] - pv[1]) > CONTROL_REL_SPEED_MPS:
            return None
        return best

    def controls(self) -> list[_Control]:
        runs: list[_Control] = []
        for k in range(len(self.ball)):
            who = self.controller(k)
            if who is None:
                continue
            if (
                runs
                and runs[-1].player == who
                and k - runs[-1].last <= 2
                and self._alive_between(runs[-1].last, k)
            ):
                runs[-1].last = k
            else:
                runs.append(_Control(who, k, k))
        return runs

    def _alive_between(self, a: int, b: int) -> bool:
        return all(self.alive[a : b + 1])


def _goal_x(feed: TrackingFeed, team: str) -> float:
    return 105.0 if feed.attacks_right[team] else 0.0


def _detect_period(feed: TrackingFeed, lo: int, hi: int) -> list[DetectedEvent]:
    p = _Period(feed, lo, hi)
    frames, ids, teams = feed.frames, feed.player_ids, feed.player_teams
    runs = p.controls()
    out: list[DetectedEvent] = []
    kicks: dict[int, DetectedEvent] = {}  # run index -> the kick that ended it
    loose_after: set[int] = set()  # run indexes whose kick left the ball loose
    n_fit = max(2, round(SPEED_FIT_S * feed.hz))
    for i, run in enumerate(runs):
        nxt = runs[i + 1] if i + 1 < len(runs) else None
        stop = nxt.first if nxt else len(p.ball)
        k0 = run.last + 1
        dead_at = next((k for k in range(k0, stop) if not p.alive[k]), None)
        flight_stop = dead_at if dead_at is not None else stop
        speeds = [s for k in range(k0, flight_stop) if (s := p.speed(k)) is not None]
        if not speeds or max(speeds) < KICK_SPEED_MPS:
            continue  # same player keeps it, or a tackle / scramble, not a kick
        # Launch: the first frame step at kick speed. End of flight: the ball then
        # comes to rest, is controlled or goes out of play.
        launch = next(
            (k + 1 for k in range(run.last, flight_stop - 1) if _step_speed(p, k) >= KICK_SPEED_MPS), k0
        )
        rest = next(
            (
                k
                for k in range(launch + 1, flight_stop)
                if (s := p.speed(k)) is not None and s < REST_SPEED_MPS
            ),
            None,
        )
        end_k = rest if rest is not None else flight_stop - 1
        # Fit only frames that are already in flight.
        fit_hi = min(launch + n_fit - 1, end_k)
        speed = _fit_speed(p.raw_ball, launch, fit_hi, p.dt) if fit_hi > launch else max(speeds)
        start = p.ball[run.last] or p.ball[k0]
        last_seen = next((p.ball[k] for k in range(end_k, run.last, -1) if p.ball[k] is not None), start)
        if start is None or last_seen is None:
            continue
        player, team = ids[run.player], teams[run.player]
        loose = (
            dead_at is None and nxt is not None and rest is not None and (nxt.first - rest) * p.dt >= LOOSE_S
        )

        kind: Kind
        receiver = ids[nxt.player] if nxt is not None and dead_at is None else None
        mate = receiver is not None and teams[nxt.player] == team and nxt.player != run.player
        goal_x = _goal_x(feed, team)
        aim = _aim(start, last_seen, goal_x)
        shooting = (
            aim is not None
            and abs(aim - 34.0) <= SHOT_AIM_HALF_WIDTH_M
            and math.hypot(goal_x - start[0], 34.0 - start[1]) <= SHOT_RANGE_M
            and speed >= SHOT_MIN_SPEED_MPS
        )
        if mate and not loose:
            kind, outcome = "pass", "complete"
        elif shooting:
            kind = "shot"
            if dead_at is None:
                outcome = "blocked"
            elif _restart_on_centre(p, dead_at):
                outcome = "goal"
            elif abs(last_seen[0] - goal_x) <= 2.0 and abs(last_seen[1] - 34.0) <= GOAL_HALF_WIDTH_M + 0.3:
                outcome = "saved"
            else:
                outcome = "off_target"
        elif loose:
            kind, outcome = "clearance", "won" if mate else "lost"
        elif dead_at is not None:
            kind, outcome = "pass", "out"
        elif nxt is not None and nxt.player != run.player:
            kind, outcome = "pass", "incomplete"
        else:
            continue
        if loose:
            loose_after.add(i)
        kick = DetectedEvent(
            kind=kind,
            period=frames[lo + run.last].period,
            clock_s=frames[lo + run.last].clock_s,
            player_id=player,
            team=team,
            outcome=outcome,
            start=(round(start[0], 2), round(start[1], 2)),
            end=(round(last_seen[0], 2), round(last_seen[1], 2)),
            ball_speed_mps=round(speed, 2),
            receiver_id=receiver if nxt is not None and nxt.player != run.player else None,
        )
        kicks[i] = kick
        out.append(kick)
        pressed_by = _pressers(p, run.player, run.last)
        if pressed_by:
            out.append(
                DetectedEvent(
                    kind="pressure",
                    period=kick.period,
                    clock_s=kick.clock_s,
                    player_id=player,
                    team=team,
                    outcome="pressed",
                    start=kick.start,
                    end=kick.start,
                    ball_speed_mps=0.0,
                    pressed_by=tuple(ids[n] for n in pressed_by),
                )
            )
    out.extend(_gains(p, runs, kicks, loose_after))
    out.sort(key=lambda d: (d.period, d.clock_s))
    return out


def _gains(
    p: _Period, runs: list[_Control], kicks: dict[int, DetectedEvent], loose_after: set[int]
) -> list[DetectedEvent]:
    """Tackles, interceptions and recoveries: who takes the ball, and how."""
    feed = p.feed
    frames, ids, teams = feed.frames, feed.player_ids, feed.player_teams
    out: list[DetectedEvent] = []
    settled_n = max(1, round(SETTLED_S * feed.hz))
    # Brief touches in a duel flip the nearest player back and forth; only spells
    # that last, or end in a kick, count as someone having the ball.
    keep = [i for i, r in enumerate(runs) if i in kicks or r.last - r.first + 1 >= settled_n]
    for j in range(1, len(keep)):
        i = keep[j]
        prev, run = runs[keep[j - 1]], runs[i]
        if prev.player == run.player or not p._alive_between(prev.last, run.first):
            continue  # same player again, or play stopped (a restart is not a gain)
        switched = teams[prev.player] != teams[run.player]
        kick = kicks.get(keep[j - 1])
        after_block = False
        if kick is None and j >= 2:
            # The blocker smothers a shot for a moment; whoever takes it from there recovers it.
            shot = kicks.get(keep[j - 2])
            after_block = (
                shot is not None
                and shot.kind == "shot"
                and shot.outcome == "blocked"
                and (run.first - prev.first) * p.dt <= RECOVERY_AFTER_SHOT_S
            )
        kind: Kind
        if (kick is not None and (keep[j - 1] in loose_after or kick.kind == "clearance")) or after_block:
            kind = "recovery"
        elif kick is not None and kick.kind == "shot" and kick.outcome == "blocked":
            # The block itself. The blocker recovers the ball only if they keep it;
            # otherwise whoever takes it from them next recovers it (see after_block).
            nxt = runs[keep[j + 1]] if j + 1 < len(keep) else None
            if nxt is not None and (nxt.first - run.first) * p.dt <= RECOVERY_AFTER_SHOT_S:
                continue
            kind = "recovery"
        elif not switched:
            continue  # a teammate taking a pass is just the pass
        elif kick is None:
            kind = "tackle"
        else:
            kind = "interception"
        b = p.ball[run.first] or (0.0, 0.0)
        f = frames[p.lo + run.first]
        out.append(
            DetectedEvent(
                kind=kind,
                period=f.period,
                clock_s=f.clock_s,
                player_id=ids[run.player],
                team=teams[run.player],
                outcome="won",
                start=(round(b[0], 2), round(b[1], 2)),
                end=(round(b[0], 2), round(b[1], 2)),
                ball_speed_mps=0.0,
            )
        )
    return out


def _pressers(p: _Period, player: int, k: int) -> list[int]:
    """Opponents within the pressure radius of the ball for long enough, up to frame k."""
    ball = p.ball[k]
    if ball is None:
        return []
    teams = p.feed.player_teams
    need = max(1, round(PRESSURE_MIN_S * p.feed.hz))
    out = []
    for n in range(len(teams)):
        if teams[n] == teams[player]:
            continue
        ok = True
        for j in range(k, k - need, -1):
            if j < 0:
                ok = False
                break
            b, q = p.ball[j], p.player_xy(j, n)
            if b is None or q is None or math.hypot(q[0] - b[0], q[1] - b[1]) > PRESSURE_RADIUS_M:
                ok = False
                break
        if ok:
            out.append(n)
    return out


def _step_speed(p: _Period, k: int) -> float:
    a, b = p.ball[k], p.ball[k + 1] if k + 1 < len(p.ball) else None
    if a is None or b is None:
        return 0.0
    return math.hypot(b[0] - a[0], b[1] - a[1]) / p.dt


def _aim(start: tuple[float, float], end: tuple[float, float], goal_x: float) -> float | None:
    """Where the line of the kick crosses the goal line, or None if it heads away."""
    dx = end[0] - start[0]
    if dx == 0 or (goal_x - start[0]) / dx <= 0:
        return None
    return start[1] + (end[1] - start[1]) * (goal_x - start[0]) / dx


def _restart_on_centre(p: _Period, dead_at: int) -> bool:
    k = dead_at
    while k < len(p.alive) and not p.alive[k]:
        k += 1
    while k < len(p.ball) and p.ball[k] is None:
        k += 1
    if k >= len(p.ball):
        return False
    b = p.ball[k]
    return math.hypot(b[0] - CENTRE[0], b[1] - CENTRE[1]) <= 2.0


def detect_events(feed: TrackingFeed) -> list[DetectedEvent]:
    """Every pass, shot, clearance, possession change and pressure the detector finds, in time order."""
    out: list[DetectedEvent] = []
    lo = 0
    frames = feed.frames
    while lo < len(frames):
        hi = lo
        while hi < len(frames) and frames[hi].period == frames[lo].period:
            hi += 1
        out.extend(_detect_period(feed, lo, hi))
        lo = hi
    return out
