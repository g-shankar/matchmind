"""Decision dataset for ML: one row per shot or pass, features and labels.

Features come from the stats engine and the event itself. For shots the label is
whether a clearly better pass was on ("should he have passed?") and how much
chance quality that pass was worth; for passes it is whether the pass arrived,
was progressive, and led to a shot. Rows carry a split chosen by a hash of the
match id, so no match is shared between training and test.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator import pitch
from matchmind.stats.better_option import shot_alternative
from matchmind.stats.metrics import to_attacking
from matchmind.stats.models import EventMetrics, MatchStateSnapshot

Row = dict[str, Any]

NEAR_DEFENDER_M = 7.0
SHOT_AFTER_PASS_S = 15.0


# The salt only decides which matches land where. It was picked so the five bundled matches
# cover train, validation and test; it never changes, so a match keeps its split as the dataset grows.
SPLIT_SALT = "pitchpulse-split-3"


def split_for(match_id: str) -> str:
    """train 70%, val 20%, test 10%: stable for a given match id."""
    bucket = int(hashlib.sha256(f"{SPLIT_SALT}:{match_id}".encode()).hexdigest(), 16) % 10
    return "train" if bucket < 7 else "val" if bucket < 9 else "test"


def _score_diff(snap: MatchStateSnapshot | None, team: str, home: str) -> int:
    if snap is None:
        return 0
    diff = snap.score_home - snap.score_away
    return diff if team == home else -diff


def decision_rows(
    events: list[Event],
    metrics: list[EventMetrics],
    snaps_before: list[MatchStateSnapshot | None],
    home: str,
) -> list[Row]:
    shots_by_possession: dict[tuple[str, int], list[tuple[int, float, float]]] = defaultdict(list)
    for e, m in zip(events, metrics, strict=True):
        if e.type == EventType.SHOT and e.team and e.possession_id is not None:
            shots_by_possession[(e.team, e.possession_id)].append(
                (e.period, e.clock_s, m.chance_quality or 0.0)
            )

    # Goals a VAR review ruled out: the shot is still a shot, but not a goal (docs/METRICS.md).
    overturned = {
        e.reviewed_event_id
        for e in events
        if e.type == EventType.VAR_REVIEW and e.outcome == Outcome.OVERTURNED and e.reviewed_event_id
    }
    rows: list[Row] = []
    for e, m, before in zip(events, metrics, snaps_before, strict=True):
        if e.type not in (EventType.SHOT, EventType.PASS) or not e.team or not e.start:
            continue
        att = to_attacking((e.start.x, e.start.y), e.team, home)
        row: Row = {
            "match_id": e.match_id,
            "event_id": e.event_id,
            "split": split_for(e.match_id),
            "decision": e.type.value,
            "team_id": e.team,
            "player_id": e.player_id,
            "clock_s": e.clock_s,
            "period": e.period,
            "score_diff": _score_diff(before, e.team, home),
            "att_start_x": round(att[0], 2),
            "att_start_y": round(att[1], 2),
            "pitch_zone": m.pitch_zone,
            "under_pressure": e.under_pressure,
            "pressure_count": len(e.pressure_players),
            "ball_speed_kmh": m.ball_speed_kmh,
        }
        if e.type == EventType.SHOT:
            row.update(_shot_features(e, m, home, att))
            row["label_goal"] = row["label_goal"] and e.event_id not in overturned
        else:
            row.update(_pass_features(e, m, shots_by_possession))
        rows.append(row)
    return rows


def _shot_features(e: Event, m: EventMetrics, home: str, att: tuple[float, float]) -> Row:
    near, keeper_d = None, None
    if e.freeze_frame:
        opp = [(p, to_attacking((p.x, p.y), e.team or "", home)) for p in e.freeze_frame if not p.teammate]
        near = sum(1 for p, xy in opp if not p.keeper and pitch.dist(att, xy) <= NEAR_DEFENDER_M)
        keepers = [pitch.dist(att, xy) for p, xy in opp if p.keeper]
        keeper_d = round(min(keepers), 1) if keepers else None
    alt = shot_alternative(e, home)
    xg = m.chance_quality or 0.0
    return {
        "body_part": e.body_part.value if e.body_part else None,
        "shot_xg": m.chance_quality,
        "distance_to_goal_m": m.distance_to_goal_m,
        "defenders_near": near,
        "keeper_distance_m": keeper_d,
        "best_alt_value": alt.alt_value if alt else None,
        "best_alt_nearest_marker_m": round(alt.nearest_marker_m, 1) if alt else None,
        "label_better_option": m.better_option is not None,
        "label_xg_gain": round(max(0.0, alt.alt_value - xg), 3) if alt else 0.0,
        "label_goal": e.outcome == Outcome.GOAL,
    }


def _pass_features(
    e: Event, m: EventMetrics, shots: dict[tuple[str, int], list[tuple[int, float, float]]]
) -> Row:
    after = [
        xg
        for period, clock, xg in shots.get(
            (e.team or "", e.possession_id if e.possession_id is not None else -1), []
        )
        if period == e.period and 0.0 <= clock - e.clock_s <= SHOT_AFTER_PASS_S
    ]
    return {
        "pass_type": str(e.details["pass_type"]) if "pass_type" in e.details else None,
        "pass_distance_m": m.pass_distance_m,
        "pass_difficulty": m.pass_difficulty,
        "forward_m": m.forward_m,
        "label_completed": e.outcome == Outcome.COMPLETE,
        "label_progressive": m.progressive,
        "label_leads_to_shot": bool(after),
        "label_next_shot_xg": round(after[0], 3) if after else 0.0,
    }
