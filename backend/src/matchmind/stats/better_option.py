"""The two "Should he have passed?" decision triggers.

Both functions read only what is inside one event (a shot's freeze frame or a
run's tracking window) and are fully deterministic. Geometry is worked out in
the acting team's attacking frame (towards x = 105); every position written to
the output models is converted back to absolute pitch coordinates.
"""

from __future__ import annotations

from typing import NamedTuple

from matchmind.schema import BodyPart, Event, EventType, FramePlayer, Outcome
from matchmind.simulator import pitch
from matchmind.simulator.pitch import Pos
from matchmind.simulator.script import format_clock

from . import metrics
from .models import XY, BetterOption, DecisionOption, UnfoundRun

# Trigger 1: the best pass must beat the shot by an absolute margin AND a ratio,
# so a 0.02 shot versus a 0.05 pass (2.5x, but tiny) is not flagged.
MIN_GAIN = 0.10
MIN_RATIO = 1.8
MIN_MARKER_M = 7.0  # "unmarked": no opponent within 7 m (see docs/METRICS.md for why not 3 m)

# The scoring method behind every option list (shown on the replay with its version).
OPTION_METHOD = "pass_value"
OPTION_METHOD_VERSION = 1

# Trigger 2: a run in behind where the through ball was on.
ONSIDE_TOLERANCE_M = 0.3
LOOKAHEAD_S = 1.0
MIN_CLEAR_M = 1.5
MIN_LANE_SUCCESS = 0.6
MIN_PROJECTED_CHANCE = 0.2


def _xy(p: Pos) -> XY:
    return XY(x=round(p[0], 2), y=round(p[1], 2))


def _frame(players: list[FramePlayer], team: str, home_id: str) -> dict[str, Pos]:
    return {p.player_id: metrics.to_attacking((p.x, p.y), team, home_id) for p in players}


def _second_last_u(opponents_u: list[float], fallback: float) -> float:
    """Offside line: the second-last opponent (keeper included). If the frame
    holds fewer than two opponents, the second-last one is outside it, so the
    line can be no further forward than `fallback`."""
    ordered = sorted(opponents_u, reverse=True)
    return ordered[1] if len(ordered) >= 2 else fallback


class _ShotScene:
    """A shot's freeze frame in the shooter's attacking frame."""

    def __init__(self, shot: Event, home_id: str) -> None:
        team = shot.team or ""
        self.frame = _frame(shot.freeze_frame or [], team, home_id)
        self.shooter = metrics.to_attacking((shot.start.x, shot.start.y), team, home_id)
        keeper_id = next((p.player_id for p in shot.freeze_frame or [] if p.keeper and not p.teammate), None)
        self.keeper = self.frame.get(keeper_id) if keeper_id else None
        opps = [p for p in shot.freeze_frame or [] if not p.teammate]
        self.outfield_opps = [self.frame[p.player_id] for p in opps if not p.keeper]
        self.all_opps = [self.frame[p.player_id] for p in opps]

    def chance_from(self, spot: Pos, header: bool = False) -> float:
        return metrics.chance_quality(
            spot,
            header=header,
            blockers=metrics.blockers_in_cone(spot, self.outfield_opps),
            keeper_on_line=metrics.keeper_on_line(spot, self.keeper),
        )


def shot_chance_quality(shot: Event, home_id: str) -> float | None:
    """Chance quality (xG) of a shot: distance and angle, outfield defenders
    in the shooting cone, keeper on the shot line, header."""
    if shot.type != EventType.SHOT or shot.start is None or shot.team is None:
        return None
    scene = _ShotScene(shot, home_id)
    return scene.chance_from(scene.shooter, header=shot.body_part == BodyPart.HEAD)


class ShotAlternative(NamedTuple):
    """The best pass on in a shot's freeze frame, before any threshold is applied."""

    shot_chance_quality: float
    teammate_id: str
    alt_chance_quality: float
    pass_success: float
    alt_value: float
    nearest_marker_m: float


def _best_pass(shot: Event, scene: _ShotScene, shot_cq: float) -> ShotAlternative | None:
    """Best onside, unmarked outfield teammate by pass success x chance quality."""
    shooter = scene.shooter
    line_u = max(shooter[0], _second_last_u([o[0] for o in scene.all_opps], metrics.FINAL_THIRD_U))
    best: ShotAlternative | None = None
    for p in sorted(shot.freeze_frame or [], key=lambda fp: fp.player_id):
        if not p.teammate or p.actor or p.keeper or p.player_id == shot.player_id:
            continue
        mate = scene.frame[p.player_id]
        if mate[0] > line_u:
            continue  # offside
        marker = min((pitch.dist(mate, o) for o in scene.all_opps), default=99.0)
        if marker < MIN_MARKER_M:
            continue
        success, _lane = metrics.pass_success_probability(shooter, mate, scene.all_opps)
        alt_cq = scene.chance_from(mate)
        value = round(success * alt_cq, 3)
        if best is None or value > best.alt_value:
            best = ShotAlternative(shot_cq, p.player_id, alt_cq, success, value, marker)
    return best


class RankedOption(NamedTuple):
    """One option in the attacking frame, before conversion to absolute coordinates."""

    kind: str
    player_id: str
    pos: Pos
    score: float
    chance_quality: float
    pass_success: float | None
    pass_distance_m: float | None
    nearest_marker_m: float | None
    onside: bool
    open: bool


def rank_options(
    shooter_id: str,
    shooter: Pos,
    shot_cq: float,
    mates: list[tuple[str, Pos]],
    all_opps: list[Pos],
    outfield_opps: list[Pos],
    keeper: Pos | None,
    line_u: float,
) -> list[RankedOption]:
    """Every option at the decision moment, ranked by the pass value model.

    The shot scores its chance quality; each outfield teammate scores pass
    success x chance quality from his spot. Eligible options (the shot, and
    passes to onside, unmarked teammates: the ones the trigger compares) come
    first by score; offside or marked teammates follow by score. Ties break on
    player id, so the order is deterministic."""
    out = [RankedOption("shot", shooter_id, shooter, shot_cq, shot_cq, None, None, None, True, True)]
    for pid, mate in sorted(mates):
        marker = min((pitch.dist(mate, o) for o in all_opps), default=99.0)
        success, _lane = metrics.pass_success_probability(shooter, mate, all_opps)
        cq = metrics.chance_quality(
            mate,
            blockers=metrics.blockers_in_cone(mate, outfield_opps),
            keeper_on_line=metrics.keeper_on_line(mate, keeper),
        )
        out.append(
            RankedOption(
                "pass",
                pid,
                mate,
                round(success * cq, 3),
                cq,
                success,
                round(pitch.dist(shooter, mate), 1),
                round(marker, 1),
                mate[0] <= line_u,
                marker >= MIN_MARKER_M,
            )
        )
    return sorted(out, key=lambda o: (not (o.onside and o.open), -o.score, o.kind != "shot", o.player_id))


def _options(shot: Event, scene: _ShotScene, shot_cq: float, to_abs) -> list[DecisionOption]:  # noqa: ANN001
    shooter = scene.shooter
    line_u = max(shooter[0], _second_last_u([o[0] for o in scene.all_opps], metrics.FINAL_THIRD_U))
    mates = [
        (p.player_id, scene.frame[p.player_id])
        for p in shot.freeze_frame or []
        if p.teammate and not p.actor and not p.keeper and p.player_id != shot.player_id
    ]
    ranked = rank_options(
        shot.player_id or "",
        shooter,
        shot_cq,
        mates,
        scene.all_opps,
        scene.outfield_opps,
        scene.keeper,
        line_u,
    )
    return [
        DecisionOption(
            rank=i + 1,
            kind=o.kind,  # type: ignore[arg-type]
            player_id=o.player_id,
            taken=o.kind == "shot",
            score=o.score,
            chance_quality=o.chance_quality,
            pass_success=o.pass_success,
            pass_distance_m=o.pass_distance_m,
            nearest_marker_m=o.nearest_marker_m,
            onside=o.onside,
            open=o.open,
            eligible=o.onside and o.open,
            pos=_xy(to_abs(o.pos)),
        )
        for i, o in enumerate(ranked)
    ]


def shot_alternative(shot: Event, home_id: str) -> ShotAlternative | None:
    """The best pass that was on when a shot was taken, whether or not it clears
    the "should have passed" thresholds. Used for analytics and training labels;
    `analyse_shot` applies the thresholds on top of the same search."""
    if shot.type != EventType.SHOT or not shot.freeze_frame or shot.start is None or shot.team is None:
        return None
    scene = _ShotScene(shot, home_id)
    shot_cq = scene.chance_from(scene.shooter, header=shot.body_part == BodyPart.HEAD)
    return _best_pass(shot, scene, shot_cq)


def analyse_shot(shot: Event, home_id: str) -> BetterOption | None:
    """Compare the shot taken with the best pass available in its freeze frame.

    Shot value = `shot_chance_quality`. For each onside, unmarked outfield
    teammate: value = pass success x chance quality from the teammate's spot.
    Flag when the best value is at least MIN_GAIN above the shot value and at
    least MIN_RATIO times it. Goals are never flagged: the decision paid off.
    """
    if shot.outcome == Outcome.GOAL:
        return None
    if shot.type != EventType.SHOT or not shot.freeze_frame or shot.start is None or shot.team is None:
        return None
    team = shot.team
    scene = _ShotScene(shot, home_id)
    frame, shooter, keeper = scene.frame, scene.shooter, scene.keeper
    shot_cq = scene.chance_from(shooter, header=shot.body_part == BodyPart.HEAD)
    best = _best_pass(shot, scene, shot_cq)
    if best is None:
        return None
    _, mate_id, alt_cq, success, value, marker = best
    if value < shot_cq + MIN_GAIN or value < MIN_RATIO * shot_cq:
        return None

    to_abs = lambda p: metrics.to_attacking(p, team, home_id)  # noqa: E731 (frame swap is self-inverse)
    return BetterOption(
        shot_event_id=shot.event_id,
        shooter_id=shot.player_id or "",
        teammate_id=mate_id,
        shot_chance_quality=shot_cq,
        alt_chance_quality=alt_cq,
        pass_success=success,
        alt_value=value,
        times_better=round(value / shot_cq, 1),
        pass_distance_m=round(pitch.dist(shooter, frame[mate_id]), 1),
        nearest_marker_m=round(marker, 1),
        shooter_pos=_xy(to_abs(shooter)),
        teammate_pos=_xy(to_abs(frame[mate_id])),
        defenders=[_xy(to_abs(o)) for o in scene.outfield_opps],
        keeper=_xy(to_abs(keeper)) if keeper else None,
        options=_options(shot, scene, shot_cq, to_abs),
        method=OPTION_METHOD,
        method_version=OPTION_METHOD_VERSION,
    )


def analyse_run(run: Event, home_id: str) -> UnfoundRun | None:
    """Find the moment a through ball was on during a run in behind.

    For each tracking frame: the line is the second-last defender (keeper
    included). The pass is "on" at the first frame where the runner is onside
    (within ONSIDE_TOLERANCE_M of the line) and LOOKAHEAD_S later is at least
    MIN_CLEAR_M beyond the line, with a clear lane from the carrier to where
    the runner will be (pass success >= MIN_LANE_SUCCESS). Projected chance =
    chance quality at the runner's last tracked spot, counting outfield
    defenders between him and goal; one-on-one when there are none. Reported
    only for runs that were not found and with a projected chance >= 0.2.
    """
    if run.type != EventType.RUN or not run.tracking or run.team is None or run.player_id is None:
        return None
    if run.outcome != Outcome.NOT_FOUND:
        return None
    team, runner_id = run.team, run.player_id
    carrier_id = str(run.details.get("carrier_id", ""))

    frames = sorted(run.tracking, key=lambda f: f.t_offset_s)
    scenes = [_frame(f.players, team, home_id) for f in frames]
    if any(runner_id not in s for s in scenes):
        return None
    opp_ids = [p.player_id for p in frames[0].players if not p.teammate]
    keeper_id = next((p.player_id for p in frames[0].players if p.keeper and not p.teammate), None)
    outfield_ids = [pid for pid in opp_ids if pid != keeper_id]

    def line_at(scene: dict[str, Pos]) -> float:
        return _second_last_u([scene[pid][0] for pid in opp_ids if pid in scene], pitch.LENGTH)

    lines = [line_at(s) for s in scenes]
    clear = max(s[runner_id][0] - line for s, line in zip(scenes, lines, strict=True))

    found_at: tuple[int, int] | None = None
    for i, (frame, scene) in enumerate(zip(frames, scenes, strict=True)):
        if scene[runner_id][0] > lines[i] + ONSIDE_TOLERANCE_M:
            continue
        later = next(
            (j for j, f in enumerate(frames) if f.t_offset_s >= frame.t_offset_s + LOOKAHEAD_S - 1e-6), None
        )
        if later is None:
            break
        if scenes[later][runner_id][0] - lines[later] < MIN_CLEAR_M:
            continue
        carrier = scene.get(carrier_id) or metrics.to_attacking((frame.ball.x, frame.ball.y), team, home_id)
        opps = [scene[pid] for pid in opp_ids if pid in scene]
        success, _lane = metrics.pass_success_probability(carrier, scenes[later][runner_id], opps)
        if success >= MIN_LANE_SUCCESS:
            found_at = (i, later)
            break
    if found_at is None:
        return None
    on_index, later = found_at

    last = scenes[-1]
    end = last[runner_id]
    defenders_end = [last[pid] for pid in outfield_ids if pid in last]
    blockers = metrics.blockers_in_cone(end, defenders_end, max_range=pitch.LENGTH)
    keeper = last.get(keeper_id) if keeper_id else None
    projected = metrics.chance_quality(
        end, blockers=blockers, keeper_on_line=metrics.keeper_on_line(end, keeper)
    )
    if projected < MIN_PROJECTED_CHANCE:
        return None

    to_abs = lambda p: metrics.to_attacking(p, team, home_id)  # noqa: E731
    at = scenes[on_index]
    carrier = at.get(carrier_id) or metrics.to_attacking(
        (frames[on_index].ball.x, frames[on_index].ball.y), team, home_id
    )
    pass_on_s = frames[on_index].t_offset_s
    return UnfoundRun(
        run_event_id=run.event_id,
        runner_id=runner_id,
        carrier_id=carrier_id,
        found=False,
        pass_on_at_s=pass_on_s,
        pass_on_clock=format_clock(run.clock_s + pass_on_s, run.period),
        clear_of_line_m=round(clear, 1),
        projected_chance_quality=projected,
        one_on_one=blockers == 0,
        carrier_pos=_xy(to_abs(carrier)),
        runner_path=[_xy(to_abs(s[runner_id])) for s in scenes],
        target=_xy(to_abs(scenes[later][runner_id])),
        defenders_at_pass=[_xy(to_abs(at[pid])) for pid in outfield_ids if pid in at],
    )
