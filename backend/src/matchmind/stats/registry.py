"""The metric registry: one place that says what every PitchPulse number is.

Each entry gives the formula in words and symbols, units, the events it is
counted from, the window it covers, its range, a quality flag, its known
limitations and edge cases, and where it appears in the API. `GET /api/metrics`
serves this list and the metric reference in docs/METRICS.md is generated from
it (`python -m matchmind.stats.registry --write`; a test checks they match).

Quality flags:
- counted: a direct count or ratio of events; no model.
- calibrated: a model whose constants were set against stated reference values.
- heuristic: a hand-weighted rule that is reasonable but not fitted to data.
- estimated_from_synthetic_tracking: worked out from the synthetic 25 Hz tracking
  feed, which is rendered from the simulated match (not real tracking, not video).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import metrics, physical, state

Quality = Literal["counted", "calibrated", "heuristic", "estimated_from_synthetic_tracking"]
Scope = Literal["event", "window", "player", "team", "moment"]

QUALITY_TEXT: dict[str, str] = {
    "counted": "Direct count or ratio of events; no model.",
    "calibrated": "Model constants set against stated reference values.",
    "heuristic": "Hand-weighted rule; reasonable, not fitted to data.",
    "estimated_from_synthetic_tracking": "Worked out from the synthetic 25 Hz tracking feed "
    "(rendered from the simulated match; not real tracking, not video).",
}


class MetricDef(BaseModel):
    id: str = Field(description="Stable id; also the API field name where one exists.")
    name: str
    scope: Scope
    formula: str = Field(description="The formula in words.")
    symbols: str = Field(description="The same formula in symbols.")
    units: str
    source_events: list[str] = Field(description="Event types it is counted from.")
    window: str
    range: str
    quality: Quality
    limitations: str
    edge_cases: str
    fields: list[str] = Field(description="Where it appears: payload.field")


class NotComputed(BaseModel):
    id: str
    name: str
    reason: str


SPRINT_KMH = physical.RUN_MAX_KMH
_BANDS = (
    f"walk < {physical.WALK_MAX_KMH:g} km/h, jog {physical.WALK_MAX_KMH:g}-{physical.JOG_MAX_KMH:g}, "
    f"run {physical.JOG_MAX_KMH:g}-{physical.RUN_MAX_KMH:g}, sprint >= {physical.RUN_MAX_KMH:g}"
)
_TRACKING_LIMIT = (
    "Synthetic tracking: off-ball movement follows simple rules, so totals are plausible, "
    "not real. Without tracking the field falls back to the event estimate (physical_source)."
)

METRICS: tuple[MetricDef, ...] = (
    # ------------------------------------------------------------------ per event
    MetricDef(
        id="pass_distance_m",
        name="Pass distance",
        scope="event",
        formula="Straight line from where the pass was played to where it ended.",
        symbols="d = |end - start|",
        units="m",
        source_events=["pass"],
        window="per event",
        range="0-125",
        quality="counted",
        limitations="2D only: no ball height or curve.",
        edge_cases="Passes without an end location have no distance (null).",
        fields=["event.metrics.pass_distance_m"],
    ),
    MetricDef(
        id="progressive",
        name="Progressive pass or carry",
        scope="event",
        formula="Moves the ball at least 10 m forward and ends at least 25% closer to the goal centre.",
        symbols="dx >= 10 and D(end) <= 0.75 D(start)",
        units="yes/no",
        source_events=["pass", "carry"],
        window="per event",
        range="true/false",
        quality="counted",
        limitations="Counted for failed passes too; the flag says nothing about success.",
        edge_cases="Backwards or square moves are never progressive.",
        fields=["event.metrics.progressive"],
    ),
    MetricDef(
        id="pass_difficulty",
        name="Pass difficulty",
        scope="event",
        formula="Weighted average of capped factors: length, pressure on the passer, forward progress, "
        "ending in the final third, cross or through ball, opponents in the lane, angle across the pitch.",
        symbols="PD = 100 * sum(w_i f_i) / sum(w_i), f_i in [0, 1]",
        units="0-100",
        source_events=["pass", "run"],
        window="per event",
        range="0-100",
        quality="heuristic",
        limitations="Opponents in the lane are only known for through balls after a tracked run; the "
        "term is dropped (weights rescaled) otherwise.",
        edge_cases="A pass of zero length scores on pressure and type only.",
        fields=["event.metrics.pass_difficulty"],
    ),
    MetricDef(
        id="xt_delta",
        name="Expected threat added (xT)",
        scope="event",
        formula="Threat of the zone where the ball ends minus the zone where it started (12 x 8 grid); "
        "a failed pass gives up the starting threat.",
        symbols="xT_end - xT_start (complete); -xT_start (failed)",
        units="xT (goal probability)",
        source_events=["pass", "carry"],
        window="per event",
        range="-0.61 to +0.61",
        quality="heuristic",
        limitations="A smoothed, symmetric grid from the team's first build, not fitted to these matches.",
        edge_cases="Moves inside one zone add 0.",
        fields=["event.metrics.xt_delta"],
    ),
    MetricDef(
        id="ball_speed_kmh",
        name="Ball speed",
        scope="event",
        formula="Recorded ball speed of the pass, shot or clearance.",
        symbols="v_ball * 3.6",
        units="km/h",
        source_events=["pass", "shot", "clearance"],
        window="per event",
        range="0-140",
        quality="counted",
        limitations="Synthetic events: the speed is the simulator's, at release.",
        edge_cases="Null when the event has no ball speed.",
        fields=["event.metrics.ball_speed_kmh"],
    ),
    MetricDef(
        id="chance_quality",
        name="Chance quality (xG)",
        scope="event",
        formula="Logistic curve on distance to goal and the angle of the goal mouth, times 0.75 per "
        "defender in the shooting cone, 0.85 for a keeper on the line and 0.6 for a header.",
        symbols="xG = clamp(sigma(a + b d + c theta) * 0.75^n * k_keeper * k_header, 0.01, 0.95)",
        units="probability",
        source_events=["shot"],
        window="per event",
        range="0.01-0.95",
        quality="calibrated",
        limitations="Calibrated to three reference chances (penalty spot about 0.25, 20 m central about "
        "0.07, 6 m central about 0.56), not fitted to match outcomes.",
        edge_cases="Shots without a freeze frame skip the defender and keeper terms.",
        fields=["event.metrics.chance_quality", "state.xg_home", "state.xg_away", "player.xg"],
    ),
    MetricDef(
        id="times_better",
        name="Should he have passed? (better option)",
        scope="moment",
        formula="Best unmarked, onside teammate: chance the pass arrives x that teammate's xG, compared "
        "with the shot's xG. Flagged when at least 0.10 higher and 1.8 times the shot.",
        symbols="alt = P(pass) * xG_mate; flag if alt - xG_shot >= 0.10 and alt / xG_shot >= 1.8",
        units="x (ratio)",
        source_events=["shot"],
        window="per event",
        range=">= 1.8 when flagged",
        quality="calibrated",
        limitations="Thresholds (7 m unmarked, 0.10, 1.8) were set on the five bundled matches.",
        edge_cases="Goals are never flagged.",
        fields=["card.replay.times_better", "moment.facts.times_better"],
    ),
    MetricDef(
        id="projected_chance_quality",
        name="Unfound run",
        scope="moment",
        formula="When a runner was onside then 1.5 m beyond the line with a clear lane, the xG from his "
        "last tracked spot; reported when the ball never came and the chance is at least 0.2.",
        symbols="xG(runner_end) with defenders between runner and goal",
        units="probability",
        source_events=["run"],
        window="3 s run window",
        range="0.2-0.95 when reported",
        quality="heuristic",
        limitations="Runs carry 6 tracking frames (every 0.5 s), not continuous tracking.",
        edge_cases="No defenders between runner and goal counts as one-on-one.",
        fields=["card.replay.projected_chance_quality"],
    ),
    # ----------------------------------------------------------------- window
    MetricDef(
        id="possession_pct",
        name="Possession (rolling)",
        scope="window",
        formula="Team's completed passes over both teams' completed passes in the window.",
        symbols="100 * P_team / (P_home + P_away)",
        units="%",
        source_events=["pass"],
        window=f"rolling {int(state.WINDOW_S // 60)} min of match clock",
        range="0-100",
        quality="counted",
        limitations="A pass share, not time on the ball.",
        edge_cases="50/50 when neither team completed a pass in the window.",
        fields=["state.home.possession_pct", "state.away.possession_pct"],
    ),
    MetricDef(
        id="field_tilt_pct",
        name="Field tilt",
        scope="window",
        formula="Team's completed passes ending in the final third over both teams' final-third passes.",
        symbols="100 * FT_team / (FT_home + FT_away)",
        units="%",
        source_events=["pass"],
        window=f"rolling {int(state.WINDOW_S // 60)} min of match clock",
        range="0-100",
        quality="counted",
        limitations="Final third = the last 35 m; touches other than passes are not counted.",
        edge_cases="50/50 when there are no final-third passes in the window.",
        fields=["state.home.field_tilt_pct", "state.away.field_tilt_pct"],
    ),
    MetricDef(
        id="pressure_index",
        name="Pressure index",
        scope="window",
        formula="Saturating load of final-third passes, box entries, shots and xG.",
        symbols="100 * (1 - exp(-L / 30)), L = FT + 2 BE + 4 S + 20 xG",
        units="0-100",
        source_events=["pass", "carry", "dribble", "shot"],
        window=f"rolling {int(state.WINDOW_S // 60)} min of match clock",
        range="0-100",
        quality="heuristic",
        limitations="Weights are hand-set; it measures attacking pressure, not pressing.",
        edge_cases="0 with no attacking actions.",
        fields=["state.home.pressure_index", "state.away.pressure_index"],
    ),
    MetricDef(
        id="momentum",
        name="Momentum",
        scope="window",
        formula="Time-weighted moving average of home pressure index minus away pressure index.",
        symbols="M += (1 - exp(-dt / 120)) * ((PI_home - PI_away) - M)",
        units="-100 (away on top) to +100 (home on top)",
        source_events=["pass", "carry", "dribble", "shot"],
        window="exponential, 120 s time constant",
        range="-100 to +100",
        quality="heuristic",
        limitations="Follows the pressure index, so it inherits its weights.",
        edge_cases="Starts at 0 on the first event.",
        fields=["state.momentum"],
    ),
    MetricDef(
        id="control_chaos",
        name="Control vs chaos (CCI)",
        scope="window",
        formula="Rises with passes per possession, falls with turnovers per minute and direct, driven "
        "balls. Sign convention: +1 is patient control, -1 is end-to-end chaos.",
        symbols="clamp(0.4 - 1.8 (0.5 T + 0.5 D - 0.6 C), -1, 1); T = turnovers/min / 4, D = direct "
        "share, C = passes per possession / 6",
        units="-1 (chaos) to +1 (control)",
        source_events=["pass", "interception", "tackle", "clearance", "shot"],
        window=f"rolling {int(state.WINDOW_S // 60)} min of match clock",
        range="-1 to +1",
        quality="heuristic",
        limitations="Ported from the team's first build and rescaled; not fitted to outcomes.",
        edge_cases="0 with no events; a long passing spell tends to +1, a turnover-heavy spell to -1 "
        "(tests show both directions).",
        fields=["state.control_chaos", "control_chaos.chaos_index"],
    ),
    # ----------------------------------------------------------------- player
    MetricDef(
        id="pass_accuracy",
        name="Pass accuracy",
        scope="player",
        formula="Completed passes over attempted passes (every pass attempt, out of play included).",
        symbols="100 * completed / attempted",
        units="%",
        source_events=["pass"],
        window="match so far",
        range="0-100",
        quality="counted",
        limitations="Does not weigh pass difficulty.",
        edge_cases="0 when no passes were attempted (the denominator is shown next to it).",
        fields=["player.pass_accuracy", "basic.teams.pass_accuracy_pct", "basic.players.pass_accuracy_pct"],
    ),
    MetricDef(
        id="xa",
        name="Expected assists (xA) and key passes",
        scope="player",
        formula="A completed pass whose receiver shoots in the same possession before anyone else "
        "receives a pass is a key pass; xA adds that shot's xG.",
        symbols="xA = sum xG(shot after key pass)",
        units="xG",
        source_events=["pass", "shot"],
        window="match so far",
        range=">= 0",
        quality="counted",
        limitations="Inherits xG's calibration.",
        edge_cases="One shot per pass: a second shot in the same possession is not credited again.",
        fields=["player.xa", "player.key_passes"],
    ),
    MetricDef(
        id="shots",
        name="Shots and shots on target",
        scope="player",
        formula="Shots taken; on target = goals plus saved shots.",
        symbols="on_target = goals + saved",
        units="count",
        source_events=["shot"],
        window="match so far",
        range=">= 0",
        quality="counted",
        limitations="Blocked shots are not on target.",
        edge_cases="",
        fields=["player.shots", "player.shots_on_target", "basic.teams.shots"],
    ),
    MetricDef(
        id="tackles",
        name="Tackles won, lost and success",
        scope="player",
        formula="Won: tackle events. Lost: the player was dribbled past (a successful dribble names him "
        "as the opponent). Success = won over won plus lost.",
        symbols="success = 100 * won / (won + lost)",
        units="count, %",
        source_events=["tackle", "dribble"],
        window="match so far",
        range="0-100 %",
        quality="counted",
        limitations="The simulator records no other failed challenges, so attempts are a lower bound.",
        edge_cases="Success is 0 with no attempts.",
        fields=["player.tackles_won", "player.tackles_lost", "player.tackle_success_pct"],
    ),
    MetricDef(
        id="interceptions",
        name="Interceptions",
        scope="player",
        formula="Interception events by the player.",
        symbols="count(interception)",
        units="count",
        source_events=["interception"],
        window="match so far",
        range=">= 0",
        quality="counted",
        limitations="",
        edge_cases="",
        fields=["player.interceptions", "basic.teams.interceptions"],
    ),
    MetricDef(
        id="distance_km",
        name="Distance covered",
        scope="player",
        formula="Positions averaged over 0.2 s blocks and smoothed over 1 s; the lengths of the 0.2 s "
        "steps are added up. Steps faster than "
        f"{physical.MAX_STEP_MPS * 3.6:g} km/h are tracking glitches and left out.",
        symbols=f"sum |p_k - p_(k-1)| over 0.2 s steps with |v| <= {physical.MAX_STEP_MPS:g} m/s",
        units="km",
        source_events=["synthetic tracking (25 Hz)"],
        window="match so far (per-second timeline)",
        range="0-14",
        quality="estimated_from_synthetic_tracking",
        limitations=_TRACKING_LIMIT + " Smoothing cuts tight corners (about 3% shorter than raw).",
        edge_cases="A sent-off player stops at the red card; stoppages count (players still move).",
        fields=["player.distance_km", "basic.players.distance_km"],
    ),
    MetricDef(
        id="speed_bands",
        name="Distance by speed band",
        scope="player",
        formula=f"Each 0.2 s step's length goes into the band of its speed: {_BANDS}.",
        symbols="band(v) for each step; bands sum to distance_km",
        units="km",
        source_events=["synthetic tracking (25 Hz)"],
        window="match so far (per-second timeline)",
        range="0-14",
        quality="estimated_from_synthetic_tracking",
        limitations=_TRACKING_LIMIT,
        edge_cases="Rounding to 0.01 km can make the bands differ from the total by 0.01-0.02.",
        fields=["player.walk_km", "player.jog_km", "player.run_km", "player.sprint_km"],
    ),
    MetricDef(
        id="sprints",
        name="Sprints",
        scope="player",
        formula=f"An unbroken spell of at least {physical.SPRINT_MIN_S:g} s at {SPRINT_KMH:g} km/h or more.",
        symbols=f"count(spells with v >= {SPRINT_KMH:g} km/h for >= {physical.SPRINT_MIN_S:g} s)",
        units="count",
        source_events=["synthetic tracking (25 Hz)"],
        window="match so far",
        range=">= 0",
        quality="estimated_from_synthetic_tracking",
        limitations=_TRACKING_LIMIT + " The synthetic players sprint less often than real ones.",
        edge_cases="Without tracking: actions faster than "
        f"{metrics.SPRINT_MS * 3.6:g} km/h (event estimate).",
        fields=["player.sprints"],
    ),
    MetricDef(
        id="top_speed_kmh",
        name="Top speed",
        scope="player",
        formula="Fastest 0.2 s step of the smoothed track.",
        symbols="max v_k * 3.6",
        units="km/h",
        source_events=["synthetic tracking (25 Hz)"],
        window="match so far",
        range=f"0-{physical.MAX_STEP_MPS * 3.6:g}",
        quality="estimated_from_synthetic_tracking",
        limitations=_TRACKING_LIMIT,
        edge_cases="Without tracking: the fastest recorded carry, dribble or run.",
        fields=["player.top_speed_kmh", "basic.players.top_speed_kmh"],
    ),
    # ------------------------------------------------------------------- team
    MetricDef(
        id="match_possession_pct",
        name="Possession (match)",
        scope="team",
        formula="Team's completed passes over both teams' completed passes, whole match so far.",
        symbols="100 * P_team / (P_home + P_away)",
        units="%",
        source_events=["pass"],
        window="match so far",
        range="0-100",
        quality="counted",
        limitations="A pass share, not time on the ball.",
        edge_cases="50/50 before the first completed pass.",
        fields=["basic.teams.possession_pct"],
    ),
    MetricDef(
        id="ppda",
        name="Passes per defensive action (PPDA)",
        scope="team",
        formula="Passes the opponent attempts in their own 60% of the pitch, over this team's tackles, "
        "challenges lost, interceptions and fouls in that same zone. Lower means a more intense press.",
        symbols="PPDA = opp_passes(x_opp < 63 m) / def_actions(x_own >= 42 m)",
        units="passes per action",
        source_events=["pass", "tackle", "dribble", "interception", "foul"],
        window="match so far",
        range="> 0",
        quality="counted",
        limitations="Synthetic events have no pressure or duel events, so the action count is narrower "
        "than a data provider's.",
        edge_cases="Null until the team makes a defensive action in the zone.",
        fields=["basic.teams.ppda"],
    ),
)

NOT_COMPUTED: tuple[NotComputed, ...] = (
    NotComputed(
        id="bps",
        name="Fantasy bonus points (BPS)",
        reason="Needs the official scoring rules and data feed; not built.",
    ),
    NotComputed(
        id="clean_sheet_odds",
        name="Clean-sheet odds",
        reason="Needs a calibrated match-outcome model; not built.",
    ),
    NotComputed(
        id="half_space_occupation",
        name="Half-space occupation",
        reason="Needs continuous team shape analysis; planned on top of the synthetic tracking.",
    ),
    NotComputed(
        id="defensive_line_height",
        name="Defensive line height",
        reason="Planned on top of the synthetic tracking; not computed yet.",
    ),
    NotComputed(
        id="pressures",
        name="Pressures and pressing duels",
        reason="The synthetic events have no pressure events; PPDA is the pressing measure.",
    ),
)


def registry_payload() -> dict:
    """GET /api/metrics."""
    return {
        "quality_flags": QUALITY_TEXT,
        "metrics": [m.model_dump() for m in METRICS],
        "not_computed": [n.model_dump() for n in NOT_COMPUTED],
    }


# ------------------------------------------------------------- generated docs

DOC_BEGIN = "<!-- BEGIN METRIC REGISTRY: generated from backend/src/matchmind/stats/registry.py -->"
DOC_END = "<!-- END METRIC REGISTRY -->"
DOCS = Path(__file__).resolve().parents[4] / "docs" / "METRICS.md"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ") or "-"


def markdown() -> str:
    """The metric reference section of docs/METRICS.md."""
    lines = [
        DOC_BEGIN,
        "<!-- Do not edit by hand: run `python -m matchmind.stats.registry --write` from backend/. -->",
        "",
        "Quality flags:",
        "",
    ]
    lines += [f"- **{k}**: {v}" for k, v in QUALITY_TEXT.items()]
    for scope, title in (
        ("event", "Per event"),
        ("moment", "Moments"),
        ("window", "Rolling window"),
        ("player", "Per player"),
        ("team", "Per team"),
    ):
        lines += ["", f"### {title}", ""]
        for m in (m for m in METRICS if m.scope == scope):
            lines += [
                f"#### {m.name} (`{m.id}`)",
                "",
                "| | |",
                "|---|---|",
                f"| Formula | {_cell(m.formula)} |",
                f"| Symbols | `{_cell(m.symbols)}` |",
                f"| Units | {_cell(m.units)} |",
                f"| Source events | {_cell(', '.join(m.source_events))} |",
                f"| Window | {_cell(m.window)} |",
                f"| Range | {_cell(m.range)} |",
                f"| Quality | {m.quality} |",
                f"| Limitations | {_cell(m.limitations)} |",
                f"| Edge cases | {_cell(m.edge_cases)} |",
                f"| Fields | {_cell(', '.join(f'`{f}`' for f in m.fields))} |",
                "",
            ]
        if lines[-1] == "":
            lines.pop()
    lines += ["", "### Not computed", "", "| Metric | Why not |", "|---|---|"]
    lines += [f"| {n.name} | {_cell(n.reason)} |" for n in NOT_COMPUTED]
    lines += [DOC_END]
    return "\n".join(lines) + "\n"


def replace_section(text: str) -> str:
    start, end = text.index(DOC_BEGIN), text.index(DOC_END) + len(DOC_END)
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:start] + markdown() + text[end:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print or write the metric reference for docs/METRICS.md.")
    parser.add_argument("--write", action="store_true", help="rewrite the section in docs/METRICS.md")
    args = parser.parse_args(argv)
    if args.write:
        DOCS.write_text(replace_section(DOCS.read_text("utf-8")), "utf-8")
        print(f"wrote {DOCS}")
    else:
        sys.stdout.write(markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
