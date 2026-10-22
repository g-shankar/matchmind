"""A naive detector, scored the same way as the real one.

It answers "does the detector add anything over the obvious rule?". From the
frames alone, like the detector:
- every ball-speed spike (the ball moving at 8 m/s or more between two frames,
  after at least 0.2 s below that) is a pass by the player nearest the ball;
- every time the team of the player nearest the ball (within 1 m) changes, the
  new player made a tackle;
- a spike is under pressure when an opponent is within 3.5 m of the ball at
  that frame (no duration rule).
It never calls shots, clearances, interceptions or recoveries.
"""

from __future__ import annotations

import math

from .detect import KICK_SPEED_MPS, PRESSURE_RADIUS_M, DetectedEvent
from .tracking import TrackingFeed

BASELINE_NAME = "Naive baseline: every ball-speed spike is a pass, every change of nearest team is a tackle"
QUIET_S = 0.2
NEAR_M = 1.0


def _nearest(frame, ball, teams, skip_team: str | None = None) -> tuple[int, float]:
    best, best_d = -1, math.inf
    for n in range(len(teams)):
        if skip_team is not None and teams[n] == skip_team:
            continue
        x = frame.xy[2 * n]
        if math.isnan(x):
            continue
        d = math.hypot(x - ball[0], frame.xy[2 * n + 1] - ball[1])
        if d < best_d:
            best, best_d = n, d
    return best, best_d


def baseline_events(feed: TrackingFeed) -> list[DetectedEvent]:
    ids, teams = feed.player_ids, feed.player_teams
    dt = 1.0 / feed.hz
    quiet_need = max(1, round(QUIET_S * feed.hz))
    out: list[DetectedEvent] = []
    prev = None
    quiet = quiet_need
    last_team: str | None = None
    for k, f in enumerate(feed.frames):
        if prev is not None and prev.period != f.period:
            prev, quiet, last_team = None, quiet_need, None
        ball = f.ball if f.alive else None
        if ball is None:
            prev = None if not f.alive else prev
            if not f.alive:
                last_team = None
            continue
        if prev is not None and prev.ball is not None and k > 0:
            speed = math.hypot(ball[0] - prev.ball[0], ball[1] - prev.ball[1]) / dt
            if speed >= KICK_SPEED_MPS and quiet >= quiet_need:
                n, _ = _nearest(prev, prev.ball, teams)
                if n >= 0:
                    b = prev.ball
                    out.append(
                        DetectedEvent(
                            "pass",
                            prev.period,
                            prev.clock_s,
                            ids[n],
                            teams[n],
                            "complete",
                            (round(b[0], 2), round(b[1], 2)),
                            (round(ball[0], 2), round(ball[1], 2)),
                            round(speed, 2),
                            source="naive_baseline",
                        )
                    )
                    _, d_opp = _nearest(prev, b, teams, skip_team=teams[n])
                    if d_opp <= PRESSURE_RADIUS_M:
                        out.append(
                            DetectedEvent(
                                "pressure",
                                prev.period,
                                prev.clock_s,
                                ids[n],
                                teams[n],
                                "pressed",
                                b,
                                b,
                                0.0,
                                source="naive_baseline",
                            )
                        )
                quiet = 0
            elif speed < KICK_SPEED_MPS:
                quiet += 1
            else:
                quiet = 0
        n, d = _nearest(f, ball, teams)
        if n >= 0 and d <= NEAR_M:
            if last_team is not None and teams[n] != last_team:
                out.append(
                    DetectedEvent(
                        "tackle",
                        f.period,
                        f.clock_s,
                        ids[n],
                        teams[n],
                        "won",
                        (round(ball[0], 2), round(ball[1], 2)),
                        (round(ball[0], 2), round(ball[1], 2)),
                        0.0,
                        source="naive_baseline",
                    )
                )
            last_team = teams[n]
        prev = f
    return out
