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
SPRINT_MS = 8.0
FAST_SHOT_MS = 28.0
FINAL_THIRD_U = 70.0


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


def pass_difficulty(distance_m: float, pressers: int, forward_m: float, end_u: float, pass_type: str) -> int:
    """0-100. Weighted sum of five capped factors:
    30% length (40 m+), 25% pressure (2+ opponents within 3.5 m),
    20% forward progress (30 m+), 15% ending in the final third,
    10% for crosses and through balls."""
    score = (
        0.30 * min(distance_m / 40.0, 1.0)
        + 0.25 * min(pressers, 2) / 2
        + 0.20 * pitch.clamp(forward_m / 30.0, 0.0, 1.0)
        + 0.15 * (1.0 if end_u >= FINAL_THIRD_U else 0.0)
        + 0.10 * (1.0 if pass_type in ("cross", "through_ball") else 0.0)
    )
    return round(100 * pitch.clamp(score, 0.0, 1.0))


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
