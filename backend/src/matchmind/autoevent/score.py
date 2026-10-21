"""Score auto-eventing against the simulator's ground truth.

Ground truth is the simulator's own event list: every pass, shot and
clearance it recorded. A detection matches a true event when it is the same
player, in the same period, within 0.5 s. Each true event matches at most one
detection and the other way round.
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

_TRUTH_KIND = {EventType.PASS: "pass", EventType.SHOT: "shot", EventType.CLEARANCE: "clearance"}


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
    receiver_accuracy: float | None = Field(description="Matched complete passes with the right receiver.")
    speed_mae_kmh: float | None = Field(
        description="Kick speed error over matched passes and shots, km/h; None when nothing matched."
    )
    shot_speed_mae_kmh: float | None


class AutoEventingStatus(BaseModel):
    """The shape served at GET /api/auto-eventing (see docs/API-CONTRACT.md)."""

    source: Literal["synthetic_tracking"] = "synthetic_tracking"
    label: str = LABEL
    passes_detected_pct: float = Field(description="Recall on passes, in percent.")
    speed_mae_kmh: float
    events_checked: int = Field(description="True passes and shots the detections were checked against.")


@dataclass(frozen=True, slots=True)
class Match:
    truth: Event
    found: DetectedEvent


def match_events(truth: list[Event], found: list[DetectedEvent]) -> list[Match]:
    """Greedy one-to-one matching by time, same player and period."""
    kicks = [e for e in truth if e.type in _TRUTH_KIND and e.player_id]
    pairs = []
    for ti, e in enumerate(kicks):
        for fi, d in enumerate(found):
            if d.period == e.period and d.player_id == e.player_id:
                gap = abs(d.clock_s - e.clock_s)
                if gap <= MATCH_WINDOW_S:
                    # Same-kind pairs go first, so a pass and a shot close together keep their own kind.
                    pairs.append((d.kind != _TRUTH_KIND[e.type], gap, ti, fi))
    pairs.sort()
    used_t, used_f, out = set(), set(), []
    for _, _, ti, fi in pairs:
        if ti in used_t or fi in used_f:
            continue
        used_t.add(ti)
        used_f.add(fi)
        out.append(Match(kicks[ti], found[fi]))
    return out


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
    outcomes = [m for m in same if kind != "clearance"]
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
    kick_errors = [
        abs(m.found.ball_speed_mps - m.truth.ball_speed_mps)
        for m in matches
        if m.truth.type in (EventType.PASS, EventType.SHOT) and m.found.kind == _TRUTH_KIND[m.truth.type]
    ]
    return AutoEventingReport(
        match_id=truth[0].match_id,
        hz=hz,
        frames=frames,
        passes=passes,
        shots=shots,
        clearances=clearances,
        receiver_accuracy=(
            _ratio(sum(m.found.receiver_id == m.truth.receiver_id for m in complete), len(complete))
            if complete
            else None
        ),
        speed_mae_kmh=round(MPS_TO_KMH * sum(kick_errors) / len(kick_errors), 2) if kick_errors else None,
        shot_speed_mae_kmh=round(MPS_TO_KMH * shots.speed_mae_mps, 2)
        if shots.speed_mae_mps is not None
        else None,
    )


def report(events: list[Event], *, hz: float = DEFAULT_HZ, seed: int | None = None) -> AutoEventingReport:
    """Render tracking for a simulated match, detect events from it, score them."""
    feed = render_tracking(events, hz=hz, seed=seed)
    found = detect_events(feed)
    return score(events, found, hz=hz, frames=len(feed.frames))


def evaluate(events: list[Event], *, hz: float = DEFAULT_HZ, seed: int | None = None) -> AutoEventingStatus:
    """Headline numbers for the API. Pure: same events in, same numbers out."""
    r = report(events, hz=hz, seed=seed)
    if r.speed_mae_kmh is None:
        # Never report a perfect error when nothing was checked.
        raise ValueError("No passes or shots were matched, so there is nothing to report.")
    return AutoEventingStatus(
        passes_detected_pct=round(100 * r.passes.recall, 1),
        speed_mae_kmh=r.speed_mae_kmh,
        events_checked=r.passes.truth + r.shots.truth,
    )
