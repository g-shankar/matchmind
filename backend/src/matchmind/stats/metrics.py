"""Deterministic football metrics. No randomness, no models: same event in,
same number out. Formulas are documented in docs/METRICS.md.

Functions taking an `attacking frame` position expect the acting team to be
attacking towards x = 105 (see `to_attacking`).
"""

from __future__ import annotations

import math

from matchmind.simulator import pitch
from matchmind.simulator.pitch import Pos

MS_TO_KMH = 3.6
SPRINT_MS = 8.0  # a player moving faster than this counts as a sprint (28.8 km/h)
FAST_SHOT_MS = 28.0
FINAL_THIRD_U = 70.0
LANE_RADIUS_M = 2.0  # an opponent this close to the passing lane is "in the lane"

# Broadcast thresholds used by the Spotter for speed and distance tags.
SPEED_BURST_KMH = 30.0  # player sprint worth a pitch tag
ROCKET_SHOT_KMH = 100.0  # shot speed worth a pitch tag
DISTANCE_MILESTONES_KM = (5.0, 8.0, 10.0)


def to_attacking(p: Pos, team: str, home_id: str) -> Pos:
    """Absolute coordinates -> the acting team's attacking frame."""
    return p if team == home_id else pitch.flip(p)


def kmh(mps: float | None) -> float | None:
    return None if mps is None else round(mps * MS_TO_KMH, 1)


def zone(u: float, v: float) -> str:
    if pitch.in_box((u, v)):
        return "Penalty Box"
    if u >= FINAL_THIRD_U:
        return "Attacking Third"
    if u >= 35.0:
        return "Middle Third"
    return "Defensive Third"


# ------------------------------------------------------------------ passes


def pass_difficulty(
    distance_m: float,
    pressers: int,
    forward_m: float,
    end_u: float,
    pass_type: str,
    *,
    lane_opponents: int | None = None,
    angle_deg: float | None = None,
) -> int:
    """0-100. Weighted sum of capped factors, each between 0 and 1:

    - 25% length (40 m or more is the maximum),
    - 25% pressure on the passer (2+ opponents within 3.5 m),
    - 15% forward progress (30 m or more),
    - 10% ending in the final third,
    - 10% crosses and through balls (lofted or weighted into space),
    - 10% opponents in the passing lane (3+ within 2 m of the line),
    - 5% angle: how far the pass is played across the pitch rather than
      straight, |sin(angle)| scaled by length (a 30 m+ switch is the maximum).

    `angle_deg` is the angle between the pass and straight towards goal. When
    the lane or the angle is unknown, its weight is left out and the rest are
    rescaled, so the score stays on the same 0-100 scale."""
    terms = [
        (0.25, min(distance_m / 40.0, 1.0)),
        (0.25, min(pressers, 2) / 2),
        (0.15, pitch.clamp(forward_m / 30.0, 0.0, 1.0)),
        (0.10, 1.0 if end_u >= FINAL_THIRD_U else 0.0),
        (0.10, 1.0 if pass_type in ("cross", "through_ball") else 0.0),
    ]
    if lane_opponents is not None:
        terms.append((0.10, min(lane_opponents, 3) / 3))
    if angle_deg is not None:
        terms.append((0.05, abs(math.sin(math.radians(angle_deg))) * min(distance_m / 30.0, 1.0)))
    score = sum(w * f for w, f in terms) / sum(w for w, _ in terms)
    return round(100 * pitch.clamp(score, 0.0, 1.0))


def pass_angle_deg(start: Pos, end: Pos) -> float:
    """Angle in degrees between the pass and straight towards goal (attacking
    frame): 0 = straight forward, 90 = square, 180 = straight back."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return 0.0
    return abs(math.degrees(math.atan2(dy, dx)))


def opponents_in_lane(start: Pos, end: Pos, opponents: list[Pos], radius: float = LANE_RADIUS_M) -> int:
    """Opponents within `radius` of the passing lane, ignoring anyone level
    with or behind the passer (first 10% of the lane) or at the receiver."""
    count = 0
    for o in opponents:
        t, proj = pitch.project_on_segment(o, start, end)
        if 0.1 <= t <= 0.97 and pitch.dist(o, proj) <= radius:
            count += 1
    return count


def is_progressive(start: Pos, end: Pos) -> bool:
    """Moves the ball at least 10 m forward and at least 25% closer to goal."""
    forward = end[0] - start[0]
    return forward >= 10.0 and pitch.distance_to_goal(end) <= 0.75 * pitch.distance_to_goal(start)


# ------------------------------------------------------------------- shots

# Logistic chance model on distance and goal-mouth angle, fitted so that a
# shot from the penalty spot is ~0.25, from 20 m central ~0.07 and from 6 m
# central ~0.55. Each defender inside the shooting cone (within 12 m)
# multiplies by 0.75; a keeper on the shot line multiplies by 0.85; headers
# by 0.6.
_A, _B, _C = -0.407, -0.1298, 1.149


def chance_quality(
    p: Pos,
    *,
    header: bool = False,
    blockers: int = 0,
    keeper_on_line: bool = False,
) -> float:
    d = pitch.distance_to_goal(p)
    z = _A + _B * d + _C * pitch.goal_angle(p)
    q = 1.0 / (1.0 + math.exp(-z))
    q *= 0.75**blockers
    q *= 0.85 if keeper_on_line else 1.0
    q *= 0.6 if header else 1.0
    return round(pitch.clamp(q, 0.01, 0.95), 3)


def blockers_in_cone(shooter: Pos, opponents: list[Pos], max_range: float = 12.0) -> int:
    return sum(1 for o in opponents if pitch.in_shot_cone(o, shooter) and pitch.dist(o, shooter) <= max_range)


def keeper_on_line(shooter: Pos, keeper: Pos | None) -> bool:
    if keeper is None:
        return False
    return (
        pitch.segment_distance(keeper, shooter, (pitch.LENGTH, pitch.GOAL_Y)) <= 1.5
        and pitch.distance_to_goal(keeper) <= 6.0
    )


def pass_success_probability(start: Pos, end: Pos, opponents: list[Pos]) -> tuple[float, float]:
    """Chance a ground pass from start reaches end, plus the closest opponent
    to the passing lane (metres). Opponents level with or behind the passer
    (projection in the first 10% of the lane) do not count as lane blockers."""
    d = pitch.dist(start, end)
    lane = 99.0
    for o in opponents:
        t, proj = pitch.project_on_segment(o, start, end)
        if 0.1 <= t <= 0.97:
            lane = min(lane, pitch.dist(o, proj))
    p = 0.92 - 0.006 * max(0.0, d - 10.0) - 0.45 * math.exp(-((lane / 1.8) ** 2))
    return round(pitch.clamp(p, 0.05, 0.97), 3), round(lane, 2)


# ------------------------------------------------------------ expected threat

# 12 x 8 expected-threat grid: the chance that possession in a zone ends in a
# goal. 12 columns along the pitch (own goal -> opponent goal), 8 rows across.
XT_GRID: tuple[tuple[float, ...], ...] = (
    (0.001, 0.002, 0.004, 0.007, 0.011, 0.015, 0.021, 0.029, 0.042, 0.065, 0.108, 0.257),
    (0.001, 0.002, 0.004, 0.008, 0.012, 0.017, 0.023, 0.033, 0.049, 0.078, 0.142, 0.320),
    (0.002, 0.003, 0.005, 0.009, 0.013, 0.019, 0.027, 0.038, 0.058, 0.098, 0.201, 0.445),
    (0.002, 0.003, 0.006, 0.010, 0.015, 0.022, 0.031, 0.045, 0.072, 0.135, 0.295, 0.612),
    (0.002, 0.003, 0.006, 0.010, 0.015, 0.022, 0.031, 0.045, 0.072, 0.135, 0.295, 0.612),
    (0.002, 0.003, 0.005, 0.009, 0.013, 0.019, 0.027, 0.038, 0.058, 0.098, 0.201, 0.445),
    (0.001, 0.002, 0.004, 0.008, 0.012, 0.017, 0.023, 0.033, 0.049, 0.078, 0.142, 0.320),
    (0.001, 0.002, 0.004, 0.007, 0.011, 0.015, 0.021, 0.029, 0.042, 0.065, 0.108, 0.257),
)


def xt(u: float, v: float) -> float:
    """Expected threat of having the ball at (u, v) in the attacking frame."""
    col = int(pitch.clamp(u / pitch.LENGTH * 12, 0, 11))
    row = int(pitch.clamp(v / pitch.WIDTH * 8, 0, 7))
    return XT_GRID[row][col]


def xt_delta(start: Pos, end: Pos, completed: bool) -> float:
    """Threat added by moving the ball from start to end (attacking frame).
    A failed action gives up the threat the team had at the start."""
    gained = xt(*end) - xt(*start) if completed else -xt(*start)
    return round(gained, 3)
