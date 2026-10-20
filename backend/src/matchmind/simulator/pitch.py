"""Pitch geometry. Unless stated otherwise, a position is in a team's own
attacking frame: that team attacks towards x = 105."""

from __future__ import annotations

import math

LENGTH = 105.0
WIDTH = 68.0
CENTRE = (LENGTH / 2, WIDTH / 2)
GOAL_Y = WIDTH / 2
GOAL_HALF_WIDTH = 3.66
BOX_DEPTH = 16.5
BOX_HALF_WIDTH = 20.16

Pos = tuple[float, float]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def clamp_pos(p: Pos, margin: float = 0.0) -> Pos:
    return (clamp(p[0], margin, LENGTH - margin), clamp(p[1], margin, WIDTH - margin))


def dist(a: Pos, b: Pos) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def flip(p: Pos) -> Pos:
    """Switch between the two teams' attacking frames (a 180 degree rotation)."""
    return (LENGTH - p[0], WIDTH - p[1])


def lerp(a: Pos, b: Pos, t: float) -> Pos:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def in_box(p: Pos) -> bool:
    return p[0] >= LENGTH - BOX_DEPTH and abs(p[1] - GOAL_Y) <= BOX_HALF_WIDTH


def distance_to_goal(p: Pos) -> float:
    return dist(p, (LENGTH, GOAL_Y))


def goal_angle(p: Pos) -> float:
    """Angle in radians that the goal mouth subtends at p."""
    a1 = math.atan2(GOAL_Y + GOAL_HALF_WIDTH - p[1], LENGTH - p[0])
    a2 = math.atan2(GOAL_Y - GOAL_HALF_WIDTH - p[1], LENGTH - p[0])
    return abs(a1 - a2)


def project_on_segment(p: Pos, a: Pos, b: Pos) -> tuple[float, Pos]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return 0.0, a
    t = clamp(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_sq, 0.0, 1.0)
    return t, (a[0] + t * dx, a[1] + t * dy)


def segment_distance(p: Pos, a: Pos, b: Pos) -> float:
    return dist(p, project_on_segment(p, a, b)[1])


def in_shot_cone(p: Pos, shooter: Pos, tolerance: float = 0.5) -> bool:
    """True if p stands inside the triangle from the shooter to both posts."""
    if p[0] <= shooter[0] or p[0] > LENGTH:
        return False
    f = (p[0] - shooter[0]) / (LENGTH - shooter[0])
    y_low = shooter[1] + f * (GOAL_Y - GOAL_HALF_WIDTH - shooter[1])
    y_high = shooter[1] + f * (GOAL_Y + GOAL_HALF_WIDTH - shooter[1])
    lo, hi = min(y_low, y_high), max(y_low, y_high)
    return lo - tolerance <= p[1] <= hi + tolerance
