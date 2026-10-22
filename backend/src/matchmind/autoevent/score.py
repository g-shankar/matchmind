"""Score the detector against the simulator's ground truth.

Ground truth is the simulator's own event list: every pass, shot, clearance,
tackle, interception and recovery it recorded, and the `under_pressure` flag on
its passes, shots and clearances. A detection matches a true event when it is
the same player, in the same period, within 0.5 s. Each true event matches at
most one detection and the other way round; pairs of the same kind are taken
first, so a mismatched kind only pairs up when nothing better is there (that is
what the confusion matrix counts off the diagonal).

Pressure is scored on its own, with the same rule: a true pressure is a kick
the event data flags `under_pressure`; a detected pressure is the detector's
pressure call on a kick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from matchmind.schema import Event, EventType

from .detect import DetectedEvent, detect_events
from .tracking import DEFAULT_HZ, render_tracking

MATCH_WINDOW_S = 0.5
MPS_TO_KMH = 3.6
LABEL = "Detected from synthetic tracking, not video"

BENCHMARK_NAME = "Synthetic tracking-to-event benchmark"
PIXEL_LABEL = "Rendered synthetic top-down video, not broadcast footage; no real-video model"

_TRUTH_KIND = {
    EventType.PASS: "pass",
    EventType.SHOT: "shot",
    EventType.CLEARANCE: "clearance",
    EventType.TACKLE: "tackle",
    EventType.INTERCEPTION: "interception",
    EventType.RECOVERY: "recovery",
}
KINDS = ("pass", "shot", "clearance", "tackle", "interception", "recovery")
_KICK_TYPES = (EventType.PASS, EventType.SHOT, EventType.CLEARANCE)


class KindScore(BaseModel):
    truth: int = Field(description="True events of this kind in the match.")
    detected: int = Field(description="Detections of this kind.")
    matched: int = Field(description="Detections of this kind that match a true event of this kind.")
    precision: float
    recall: float
    speed_mae_mps: float | None = Field(description="Mean absolute error of the kick speed, matched events.")
    outcome_accuracy: float | None = Field(description="Share of matched events with the right outcome.")


class AutoEventingReport(BaseModel):
    source: Literal["synthetic_tracking"] = "synthetic_tracking"
    label: str = LABEL
    match_id: str
    hz: float
    frames: int
    passes: KindScore
    shots: KindScore
    clearances: KindScore
    tackles: KindScore | None = None
    interceptions: KindScore | None = None
    recoveries: KindScore | None = None
    pressure: KindScore | None = Field(
        default=None, description="Pressure on kicks, scored against the event data's under_pressure flag."
    )
    confusion: list[list[int]] | None = Field(
        default=None,
        description=(
            "Rows: true kind in KINDS order, then 'spurious' (no true event). Columns: detected kind in"
            " KINDS order, then 'missed' (no detection)."
        ),
    )
    receiver_accuracy: float | None = Field(description="Matched complete passes with the right receiver.")
    speed_mae_kmh: float | None = Field(
        description="Kick speed error over matched passes and shots, km/h; None when nothing matched."
    )
    shot_speed_mae_kmh: float | None


class ClassRow(BaseModel):
    """One class of the benchmark: counts, rates and 95% Wilson intervals."""

    kind: str
    support: int = Field(description="True events of this kind (the recall denominator).")
    detected: int
    matched: int
    precision: float
    recall: float
    f1: float
    precision_ci: tuple[float, float] | None = Field(
        description="95% Wilson interval; None if nothing detected."
    )
    recall_ci: tuple[float, float] | None = Field(description="95% Wilson interval; None if no true events.")


class Confusion(BaseModel):
    """Rows are true kinds then 'spurious'; columns are detected kinds then 'missed'."""

    rows: list[str]
    columns: list[str]
    counts: list[list[int]]


class BaselineRow(BaseModel):
    """A naive detector scored the same way, to show what the real one adds."""

    name: str
    classes: list[ClassRow]


class PixelPathRow(BaseModel):
    """The same detector run on positions recovered from rendered top-down video frames."""

    label: str = PIXEL_LABEL
    window_s: float = Field(description="Seconds of match clock rendered to pixels (from kick-off).")
    frames: int
    width_px: int
    height_px: int
    player_error_m: float | None = Field(
        description="Median distance from recovered to true player position."
    )
    ball_error_m: float | None = Field(description="Median distance from recovered to true ball position.")
    ball_found_pct: float = Field(description="Frames with the ball tracked where the ball was recovered.")
    coordinate: list[ClassRow] = Field(description="The coordinate path scored on the same window.")
    pixels: list[ClassRow]
    speed_mae_kmh_coordinate: float | None
    speed_mae_kmh_pixels: float | None


class AutoEventingStatus(BaseModel):
    """The shape served at GET /api/auto-eventing (see docs/API-CONTRACT.md).

    The first five fields are the original contract; everything after them is
    optional and was added by the benchmark, so older clients keep working.
    """

    source: Literal["synthetic_tracking"] = "synthetic_tracking"
    label: str = LABEL
    passes_detected_pct: float = Field(description="Recall on passes, in percent.")
    speed_mae_kmh: float
    events_checked: int = Field(description="True passes and shots the detections were checked against.")
    name: str = BENCHMARK_NAME
    match_id: str | None = None
    speed_mae_ci_kmh: tuple[float, float] | None = Field(
        default=None, description="95% bootstrap interval for speed_mae_kmh."
    )
    classes: list[ClassRow] | None = None
    pressure: ClassRow | None = None
    confusion: Confusion | None = None
    baseline: BaselineRow | None = None
    pixel_path: PixelPathRow | None = None
    caveat: str | None = None


@dataclass(frozen=True, slots=True)
class Match:
    truth: Event
    found: DetectedEvent


def truth_kind(e: Event) -> str | None:
    return _TRUTH_KIND.get(e.type) if e.player_id else None


def _pairs(
    truth: list[Event], found: list[DetectedEvent], kind_of_truth, kind_of_found
) -> list[tuple[int, int]]:
    """Greedy one-to-one pairs (truth index, found index) by time, same player and period."""
    by_key: dict[tuple[int, str], list[int]] = {}
    for fi, d in enumerate(found):
        by_key.setdefault((d.period, d.player_id), []).append(fi)
    pairs = []
    for ti, e in enumerate(truth):
        for fi in by_key.get((e.period, e.player_id or ""), ()):
            d = found[fi]
            gap = abs(d.clock_s - e.clock_s)
            if gap <= MATCH_WINDOW_S:
                # Same-kind pairs go first, so a pass and a shot close together keep their own kind.
                pairs.append((kind_of_found(d) != kind_of_truth(e), gap, ti, fi))
    pairs.sort()
    used_t, used_f, out = set(), set(), []
    for _, _, ti, fi in pairs:
        if ti in used_t or fi in used_f:
            continue
        used_t.add(ti)
        used_f.add(fi)
        out.append((ti, fi))
    return out


def match_events(truth: list[Event], found: list[DetectedEvent]) -> list[Match]:
    """Greedy one-to-one matching of events (not pressure) by time, same player and period."""
    kicks = [e for e in truth if truth_kind(e)]
    events = [d for d in found if d.kind != "pressure"]
    return [
        Match(kicks[ti], events[fi])
        for ti, fi in _pairs(kicks, events, lambda e: _TRUTH_KIND[e.type], lambda d: d.kind)
    ]


def match_pressure(truth: list[Event], found: list[DetectedEvent]) -> tuple[int, int, int]:
    """(true pressures, detected pressures, matched) on kicks."""
    pressed = [e for e in truth if e.type in _KICK_TYPES and e.player_id and e.under_pressure]
    calls = [d for d in found if d.kind == "pressure"]
    matched = _pairs(pressed, calls, lambda e: "pressure", lambda d: "pressure")
    return len(pressed), len(calls), len(matched)


def confusion_matrix(truth: list[Event], found: list[DetectedEvent], matches: list[Match]) -> list[list[int]]:
    """Counts by (true kind or spurious) x (detected kind or missed); see AutoEventingReport.confusion."""
    n = len(KINDS)
    m = [[0] * (n + 1) for _ in range(n + 1)]
    for x in matches:
        m[KINDS.index(_TRUTH_KIND[x.truth.type])][KINDS.index(x.found.kind)] += 1
    for k, kind in enumerate(KINDS):
        m[k][n] = sum(truth_kind(e) == kind for e in truth) - sum(m[k][:n])
        m[n][k] = sum(d.kind == kind for d in found) - sum(row[k] for row in m[:n])
    return m


def kick_speed_errors_kmh(matches: list[Match]) -> list[float]:
    """Absolute kick-speed errors (km/h) over matched passes and shots of the right kind."""
    return [
        MPS_TO_KMH * abs(m.found.ball_speed_mps - m.truth.ball_speed_mps)
        for m in matches
        if m.truth.type in (EventType.PASS, EventType.SHOT)
        and m.found.kind == _TRUTH_KIND[m.truth.type]
        and m.truth.ball_speed_mps is not None
    ]


def _ratio(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


def _kind_score(kind: str, truth: list[Event], found: list[DetectedEvent], matches: list[Match]) -> KindScore:
    same = [m for m in matches if m.found.kind == kind and _TRUTH_KIND[m.truth.type] == kind]
    n_truth = sum(_TRUTH_KIND.get(e.type) == kind and e.player_id is not None for e in truth)
    n_found = sum(d.kind == kind for d in found)
    errors = [
        abs(m.found.ball_speed_mps - m.truth.ball_speed_mps)
        for m in same
        if m.truth.ball_speed_mps is not None
    ]
    outcomes = [m for m in same if kind in ("pass", "shot")]
    return KindScore(
        truth=n_truth,
        detected=n_found,
        matched=len(same),
        precision=_ratio(len(same), n_found),
        recall=_ratio(len(same), n_truth),
        speed_mae_mps=round(sum(errors) / len(errors), 3) if errors else None,
        outcome_accuracy=(
            _ratio(sum(m.found.outcome == m.truth.outcome for m in outcomes), len(outcomes))
            if outcomes
            else None
        ),
    )


def score(truth: list[Event], found: list[DetectedEvent], *, hz: float, frames: int) -> AutoEventingReport:
    if not truth:
        raise ValueError("There are no true events to score against.")
    matches = match_events(truth, found)
    passes = _kind_score("pass", truth, found, matches)
    shots = _kind_score("shot", truth, found, matches)
    clearances = _kind_score("clearance", truth, found, matches)
    complete = [
        m
        for m in matches
        if m.found.kind == "pass" and m.truth.type == EventType.PASS and m.truth.outcome == "complete"
    ]
    kick_errors = kick_speed_errors_kmh(matches)
    p_truth, p_found, p_matched = match_pressure(truth, found)
    return AutoEventingReport(
        match_id=truth[0].match_id,
        hz=hz,
        frames=frames,
        passes=passes,
        shots=shots,
        clearances=clearances,
        tackles=_kind_score("tackle", truth, found, matches),
        interceptions=_kind_score("interception", truth, found, matches),
        recoveries=_kind_score("recovery", truth, found, matches),
        pressure=KindScore(
            truth=p_truth,
            detected=p_found,
            matched=p_matched,
            precision=_ratio(p_matched, p_found),
            recall=_ratio(p_matched, p_truth),
            speed_mae_mps=None,
            outcome_accuracy=None,
        ),
        confusion=confusion_matrix(truth, found, matches),
        receiver_accuracy=(
            _ratio(sum(m.found.receiver_id == m.truth.receiver_id for m in complete), len(complete))
            if complete
            else None
        ),
        speed_mae_kmh=round(sum(kick_errors) / len(kick_errors), 2) if kick_errors else None,
        shot_speed_mae_kmh=round(MPS_TO_KMH * shots.speed_mae_mps, 2)
        if shots.speed_mae_mps is not None
        else None,
    )


def report(events: list[Event], *, hz: float = DEFAULT_HZ, seed: int | None = None) -> AutoEventingReport:
    """Render tracking for a simulated match, detect events from it, score them."""
    feed = render_tracking(events, hz=hz, seed=seed)
    found = detect_events(feed)
    return score(events, found, hz=hz, frames=len(feed.frames))
