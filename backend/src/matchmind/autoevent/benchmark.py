"""Synthetic tracking-to-event benchmark.

One place that runs the whole evaluation and writes it down:
- a tuning split (the five published matches, seeds 100-104, which the
  detector's thresholds were set on) and a held-out split (seeds 900 and up,
  never run while tuning);
- per class precision, recall and F1 with 95% Wilson intervals and support
  counts, a full confusion matrix (with missed and spurious), kick-speed MAE
  with a bootstrap interval, and a naive baseline scored the same way;
- a robustness sweep over position noise, ball dropouts and player occlusion;
- the pixel path: the same detector on positions recovered from rendered
  synthetic top-down video frames, scored on the same frames as the
  coordinate path;
- a few failure examples, drawn as SVG.

The circularity caveat applies to every number here: the tracking feed is
rendered from the same simulated events that serve as ground truth, so the
detector and the truth share the simulator's assumptions (straight-line ball
flight, a holder 0.35 m behind the ball, pressers placed where the event data
says they were). These numbers measure the detection and classification rules
on clean synthetic data. They are not a claim about real tracking or real video.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from matchmind.schema import Event
from matchmind.simulator import random_script, simulate
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.script import format_clock

from .baseline import BASELINE_NAME, baseline_events
from .degrade import Degradation, degrade
from .detect import DetectedEvent, detect_events
from .evalstats import bootstrap_mean_ci, f1, wilson
from .pixels import PixelConfig, PixelPath
from .score import (
    BENCHMARK_NAME,
    KINDS,
    LABEL,
    PIXEL_LABEL,
    AutoEventingStatus,
    BaselineRow,
    ClassRow,
    Confusion,
    Match,
    PixelPathRow,
    confusion_matrix,
    kick_speed_errors_kmh,
    match_events,
    match_pressure,
    truth_kind,
)
from .tracking import DEFAULT_HZ, TrackingFeed, render_tracking

CAVEAT = (
    "Circular by construction: the tracking is rendered from the same simulated events used as ground"
    " truth, so detector and truth share the simulator's assumptions. Synthetic data only; not real"
    " tracking and not video."
)
TUNING_SEEDS = (100, 101, 102, 103, 104)  # the published matches in data/matches
HELD_OUT_SEEDS = tuple(range(900, 910))
TUNED_THRESHOLDS = (
    "CONTROL_RADIUS_M",
    "CONTROL_REL_SPEED_MPS",
    "KICK_SPEED_MPS",
    "REST_SPEED_MPS",
    "SPEED_FIT_S",
    "LOOSE_S",
    "SHOT_RANGE_M",
    "SHOT_MIN_SPEED_MPS",
    "SHOT_AIM_HALF_WIDTH_M",
    "PRESSURE_MIN_S",
    "SETTLED_S",
    "RECOVERY_AFTER_SHOT_S",
)
SWEEP = (
    Degradation("base feed (5 cm noise)"),
    Degradation("15 cm noise", noise_m=0.15),
    Degradation("30 cm noise", noise_m=0.30),
    Degradation("ball dropouts 0.5/s", ball_dropout_per_s=0.5),
    Degradation("player occlusion 0.1/s", player_occlusion_per_s=0.1),
    Degradation("player occlusion 0.3/s", player_occlusion_per_s=0.3),
    Degradation(
        "30 cm + dropouts 0.5/s + occlusion 0.3/s",
        noise_m=0.30,
        ball_dropout_per_s=0.5,
        player_occlusion_per_s=0.3,
    ),
)
API_PIXEL_SECONDS = 30.0
BOOTSTRAP_RESAMPLES = 1000


# ------------------------------------------------------------------ data


def held_out_match(seed: int) -> list[Event]:
    """A match no threshold was ever set on (seeds 900 and up)."""
    home, away = ("NBR", "HCY") if seed % 2 == 0 else ("HCY", "NBR")
    return simulate(random_script(f"MM-HOLD-{seed}", home=home, away=away), seed)


def tuning_matches(data_dir: str | Path) -> list[list[Event]]:
    return [read_jsonl(p) for p in sorted(Path(data_dir).glob("*.jsonl"))]


# --------------------------------------------------------------- tallies


@dataclass(slots=True)
class Tally:
    """Counts that add up across matches."""

    truth: dict[str, int]
    detected: dict[str, int]
    matched: dict[str, int]
    pressure: list[int]  # truth, detected, matched
    confusion: list[list[int]]
    speed_errors: list[float]
    receivers: list[int]  # right, checked
    matches: int = 0
    frames: int = 0

    @classmethod
    def empty(cls) -> Tally:
        n = len(KINDS) + 1
        z = dict.fromkeys(KINDS, 0)
        return cls(dict(z), dict(z), dict(z), [0, 0, 0], [[0] * n for _ in range(n)], [], [0, 0])

    def add(self, truth: list[Event], found: list[DetectedEvent], frames: int = 0) -> list[Match]:
        matches = match_events(truth, found)
        for kind in KINDS:
            self.truth[kind] += sum(truth_kind(e) == kind for e in truth)
            self.detected[kind] += sum(d.kind == kind for d in found)
            self.matched[kind] += sum(m.found.kind == kind and truth_kind(m.truth) == kind for m in matches)
        for i, v in enumerate(match_pressure(truth, found)):
            self.pressure[i] += v
        for r, row in enumerate(confusion_matrix(truth, found, matches)):
            for c, v in enumerate(row):
                self.confusion[r][c] += v
        self.speed_errors.extend(kick_speed_errors_kmh(matches))
        complete = [
            m
            for m in matches
            if m.found.kind == "pass" and truth_kind(m.truth) == "pass" and m.truth.outcome == "complete"
        ]
        self.receivers[0] += sum(m.found.receiver_id == m.truth.receiver_id for m in complete)
        self.receivers[1] += len(complete)
        self.matches += 1
        self.frames += frames
        return matches

    def rows(self, kinds: Iterable[str] = KINDS) -> list[ClassRow]:
        return [class_row(k, self.truth[k], self.detected[k], self.matched[k]) for k in kinds]

    def pressure_row(self) -> ClassRow:
        t, d, m = self.pressure
        return class_row("pressure", t, d, m)

    def confusion_table(self) -> Confusion:
        return Confusion(
            rows=[*KINDS, "spurious"], columns=[*KINDS, "missed"], counts=[list(r) for r in self.confusion]
        )

    def speed(self, resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[float | None, tuple[float, float] | None]:
        e = self.speed_errors
        if not e:
            return None, None
        ci = bootstrap_mean_ci(e, resamples=resamples) if resamples > 0 else None
        return round(sum(e) / len(e), 2), ci


def class_row(kind: str, truth: int, detected: int, matched: int) -> ClassRow:
    p = round(matched / detected, 4) if detected else 0.0
    r = round(matched / truth, 4) if truth else 0.0
    return ClassRow(
        kind=kind,
        support=truth,
        detected=detected,
        matched=matched,
        precision=p,
        recall=r,
        f1=f1(p, r),
        precision_ci=wilson(matched, detected),
        recall_ci=wilson(matched, truth),
    )


# --------------------------------------------------------------- windows


def window(feed: TrackingFeed, events: list[Event], seconds: float) -> tuple[int, float, list[Event]]:
    """Frames [0, hi) covering `seconds` from kick-off, and the true events inside them.

    Events in the last second are left out of both truth and detections, so a
    kick whose flight the window cuts off does not count for or against.
    """
    hi = min(len(feed.frames), max(2, round(seconds * feed.hz)))
    period = feed.frames[0].period
    end = feed.frames[hi - 1].clock_s - 1.0
    return hi, end, [e for e in events if e.period == period and e.clock_s <= end]


def _clip(found: list[DetectedEvent], period: int, end: float) -> list[DetectedEvent]:
    return [d for d in found if d.period == period and d.clock_s <= end]


def _slice(feed: TrackingFeed, lo: int, hi: int) -> TrackingFeed:
    return TrackingFeed(
        feed.match_id,
        feed.hz,
        feed.player_ids,
        feed.player_teams,
        dict(feed.attacks_right),
        feed.frames[lo:hi],
    )


def pixel_compare(
    feed: TrackingFeed, events: list[Event], seconds: float, cfg: PixelConfig | None = None, *, on_image=None
) -> tuple[Tally, Tally, dict]:
    """Coordinate path and pixel path on the same window; returns both tallies and pixel stats."""
    hi, end, truth = window(feed, events, seconds)
    period = feed.frames[0].period
    coord_feed = _slice(feed, 0, hi)
    pix_feed, stats = PixelPath(feed, cfg).recover(0, hi, on_image=on_image)
    coord, pix = Tally.empty(), Tally.empty()
    coord.add(truth, _clip(detect_events(coord_feed), period, end), hi)
    pix.add(truth, _clip(detect_events(pix_feed), period, end), hi)
    return coord, pix, stats.summary()


# ------------------------------------------------------------------ models


class SplitResult(BaseModel):
    matches: list[str]
    seeds: list[int]
    frames: int
    classes: list[ClassRow]
    pressure: ClassRow
    confusion: Confusion
    speed_mae_kmh: float | None
    speed_mae_ci_kmh: tuple[float, float] | None
    speed_samples: int
    receiver_accuracy: float | None
    baseline: BaselineRow


class SweepRow(BaseModel):
    name: str
    noise_m: float
    ball_dropout_per_s: float
    player_occlusion_per_s: float
    classes: list[ClassRow]
    pressure: ClassRow
    speed_mae_kmh: float | None


class PixelResult(BaseModel):
    label: str = PIXEL_LABEL
    matches: list[str]
    window_s: float
    width_px: int
    height_px: int
    px_per_m: float
    frames: int
    player_error_m: float | None
    player_error_p95_m: float | None
    ball_error_m: float | None
    ball_found_pct: float
    coordinate: list[ClassRow]
    pixels: list[ClassRow]
    coordinate_pressure: ClassRow
    pixels_pressure: ClassRow
    speed_mae_kmh_coordinate: float | None
    speed_mae_kmh_pixels: float | None
    seconds_per_match: float = Field(description="Wall time for the vision step, per match window.")


class FailureExample(BaseModel):
    match_id: str
    period: int
    clock_s: float
    match_clock: str
    what: str
    truth_kind: str | None
    detected_kind: str | None
    image: str | None


class BenchmarkResult(BaseModel):
    name: str = BENCHMARK_NAME
    label: str = LABEL
    caveat: str = CAVEAT
    tuned_thresholds: list[str]
    tuning_note: str
    tuning: SplitResult
    held_out: SplitResult
    robustness: list[SweepRow]
    robustness_matches: list[str]
    pixel: PixelResult | None
    failures: list[FailureExample]
    runtime_s: float


# ------------------------------------------------------------------- runs


def _split(matches: list[list[Event]], seeds: list[int]) -> tuple[SplitResult, list]:
    real, base = Tally.empty(), Tally.empty()
    runs = []
    for events in matches:
        feed = render_tracking(events)
        found = detect_events(feed)
        pairs = real.add(events, found, len(feed.frames))
        base.add(events, baseline_events(feed), len(feed.frames))
        runs.append((events, feed, found, pairs))
    mae, ci = real.speed()
    right, checked = real.receivers
    return (
        SplitResult(
            matches=[m[0].match_id for m in matches],
            seeds=seeds,
            frames=real.frames,
            classes=real.rows(),
            pressure=real.pressure_row(),
            confusion=real.confusion_table(),
            speed_mae_kmh=mae,
            speed_mae_ci_kmh=ci,
            speed_samples=len(real.speed_errors),
            receiver_accuracy=round(right / checked, 4) if checked else None,
            baseline=BaselineRow(name=BASELINE_NAME, classes=[*base.rows(), base.pressure_row()]),
        ),
        runs,
    )


def _sweep(runs) -> list[SweepRow]:
    rows = []
    for d in SWEEP:
        t = Tally.empty()
        for events, feed, _, _ in runs:
            t.add(events, detect_events(degrade(feed, d)), len(feed.frames))
        mae, _ = t.speed(resamples=0)
        rows.append(
            SweepRow(
                name=d.name,
                noise_m=d.noise_m,
                ball_dropout_per_s=d.ball_dropout_per_s,
                player_occlusion_per_s=d.player_occlusion_per_s,
                classes=t.rows(),
                pressure=t.pressure_row(),
                speed_mae_kmh=mae,
            )
        )
    return rows


def _pixel(runs, seconds: float, cfg: PixelConfig) -> PixelResult:
    coord, pix = Tally.empty(), Tally.empty()
    stats: list[dict] = []
    t0 = time.perf_counter()
    for events, feed, _, _ in runs:
        c, p, s = pixel_compare(feed, events, seconds, cfg)
        for src, dst in ((c, coord), (p, pix)):
            _merge(dst, src)
        stats.append(s)
    wall = (time.perf_counter() - t0) / max(1, len(runs))
    frames = sum(s["frames"] for s in stats)

    def mean_of(key: str) -> float | None:
        vals = [s[key] for s in stats if s[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    return PixelResult(
        matches=[r[0][0].match_id for r in runs],
        window_s=seconds,
        width_px=cfg.width,
        height_px=cfg.height,
        px_per_m=cfg.px_per_m,
        frames=frames,
        player_error_m=mean_of("player_error_m"),
        player_error_p95_m=mean_of("player_error_p95_m"),
        ball_error_m=mean_of("ball_error_m"),
        ball_found_pct=mean_of("ball_found_pct") or 0.0,
        coordinate=coord.rows(),
        pixels=pix.rows(),
        coordinate_pressure=coord.pressure_row(),
        pixels_pressure=pix.pressure_row(),
        speed_mae_kmh_coordinate=coord.speed()[0],
        speed_mae_kmh_pixels=pix.speed()[0],
        seconds_per_match=round(wall, 1),
    )


def _merge(dst: Tally, src: Tally) -> None:
    for k in KINDS:
        dst.truth[k] += src.truth[k]
        dst.detected[k] += src.detected[k]
        dst.matched[k] += src.matched[k]
    for i in range(3):
        dst.pressure[i] += src.pressure[i]
    for r, row in enumerate(src.confusion):
        for c, v in enumerate(row):
            dst.confusion[r][c] += v
    dst.speed_errors.extend(src.speed_errors)
    dst.receivers[0] += src.receivers[0]
    dst.receivers[1] += src.receivers[1]
    dst.matches += src.matches
    dst.frames += src.frames


def failure_examples(runs, limit: int = 5) -> list[tuple[str, list[Event], TrackingFeed, list, object]]:
    """Pick up to `limit` distinct kinds of mistake from scored runs, first of each kind."""
    picked: dict[str, tuple] = {}
    for events, feed, found, pairs in runs:
        matched_t = {id(m.truth) for m in pairs}
        matched_f = {id(m.found) for m in pairs}
        for m in pairs:
            tk, dk = truth_kind(m.truth), m.found.kind
            if tk != dk:
                picked.setdefault(
                    f"confused:{tk}->{dk}", (events, feed, found, ("confused", m.truth, m.found))
                )
        for e in events:
            k = truth_kind(e)
            if k and id(e) not in matched_t:
                picked.setdefault(f"missed:{k}", (events, feed, found, ("missed", e, None)))
        for d in found:
            if d.kind != "pressure" and id(d) not in matched_f:
                picked.setdefault(f"spurious:{d.kind}", (events, feed, found, ("spurious", None, d)))
    # Take turns between missed, spurious and confused, so the examples show each kind of mistake.
    groups = {
        what: sorted(k for k in picked if k.startswith(what)) for what in ("missed", "spurious", "confused")
    }
    order: list[str] = []
    seen: list[tuple[str, int, float]] = []  # one example per incident

    def where(key: str) -> tuple[str, int, float]:
        _, feed, _, (_, t, d) = picked[key]
        ref = t if t is not None else d
        return feed.match_id, ref.period, ref.clock_s

    while len(order) < limit and any(groups.values()):
        for what in ("missed", "spurious", "confused"):
            while groups[what] and len(order) < limit:
                key = groups[what].pop(0)
                m, p, t = where(key)
                if any(m == m2 and p == p2 and abs(t - t2) < 5.0 for m2, p2, t2 in seen):
                    continue
                seen.append((m, p, t))
                order.append(key)
                break
    return [(key, *picked[key]) for key in order]


def run_benchmark(
    data_dir: str | Path,
    *,
    held_out_seeds: Iterable[int] = HELD_OUT_SEEDS,
    robustness_matches: int = 3,
    pixel_matches: int = 3,
    pixel_seconds: float = 180.0,
    pixel_cfg: PixelConfig | None = None,
    images_dir: str | Path | None = None,
    image_prefix: str = "benchmark-failure",
    progress=None,
) -> BenchmarkResult:
    say = progress or (lambda _msg: None)
    t0 = time.perf_counter()
    seeds = list(held_out_seeds)
    say("tuning split (published matches, seeds 100-104)")
    tuning, _ = _split(tuning_matches(data_dir), list(TUNING_SEEDS))
    say(f"held-out split ({len(seeds)} matches, seeds {seeds[0]}-{seeds[-1]})" if seeds else "no held-out")
    held_matches = [held_out_match(s) for s in seeds]
    held, runs = _split(held_matches, seeds)
    say(f"robustness sweep on {min(robustness_matches, len(runs))} held-out matches")
    sweep_runs = runs[:robustness_matches]
    sweep = _sweep(sweep_runs)
    pixel = None
    if pixel_matches > 0 and pixel_seconds > 0 and runs:
        say(f"pixel path: {min(pixel_matches, len(runs))} held-out matches x {pixel_seconds:g} s")
        pixel = _pixel(runs[:pixel_matches], pixel_seconds, pixel_cfg or PixelConfig())
    failures = []
    for n, (key, events, feed, found, (what, truth, det)) in enumerate(failure_examples(runs), start=1):
        ref = truth if truth is not None else det
        image = None
        if images_dir is not None:
            from .svg import render_failure_svg

            out = Path(images_dir) / f"{image_prefix}-{n}.svg"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_failure_svg(feed, events, found, what=what, truth=truth, found_event=det))
            image = out.name
        failures.append(
            FailureExample(
                match_id=feed.match_id,
                period=ref.period,
                clock_s=ref.clock_s,
                match_clock=format_clock(ref.clock_s, ref.period),
                what=key,
                truth_kind=truth_kind(truth) if truth is not None else None,
                detected_kind=det.kind if det is not None else None,
                image=image,
            )
        )
    return BenchmarkResult(
        tuned_thresholds=list(TUNED_THRESHOLDS),
        tuning_note=(
            "Every threshold in detect.py was set while looking only at the tuning split (the five"
            " published matches, seeds 100-104). The held-out seeds were first run after the thresholds"
            " were frozen and were never used to change them."
        ),
        tuning=tuning,
        held_out=held,
        robustness=sweep,
        robustness_matches=[r[0][0].match_id for r in sweep_runs],
        pixel=pixel,
        failures=failures,
        runtime_s=round(time.perf_counter() - t0, 1),
    )


# -------------------------------------------------------------------- API


def evaluate(
    events: list[Event],
    *,
    hz: float = DEFAULT_HZ,
    seed: int | None = None,
    pixel_seconds: float = API_PIXEL_SECONDS,
    pixel_cfg: PixelConfig | None = None,
) -> AutoEventingStatus:
    """What GET /api/auto-eventing serves. Pure: same events in, same numbers out.

    The API computes this once per match and keeps it; a small in-process
    cache also stops a rebuilt session from paying for it twice. The pixel row
    covers only the first `pixel_seconds` of play (a small sample, labelled as
    such); the full benchmark lives behind `matchmind-autoevent benchmark`.
    """
    key = (
        events[0].match_id if events else "",
        len(events),
        events[-1].event_id if events else "",
        hz,
        seed,
        pixel_seconds,
        pixel_cfg,
    )
    hit = _CACHE.get(key)
    if hit is None:
        hit = _evaluate(events, hz=hz, seed=seed, pixel_seconds=pixel_seconds, pixel_cfg=pixel_cfg)
        if len(_CACHE) >= _CACHE_SIZE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = hit
    return hit.model_copy(deep=True)


_CACHE: dict[tuple, AutoEventingStatus] = {}
_CACHE_SIZE = 4


def _evaluate(
    events: list[Event],
    *,
    hz: float,
    seed: int | None,
    pixel_seconds: float,
    pixel_cfg: PixelConfig | None,
) -> AutoEventingStatus:
    feed = render_tracking(events, hz=hz, seed=seed)
    found = detect_events(feed)
    real, base = Tally.empty(), Tally.empty()
    real.add(events, found, len(feed.frames))
    base.add(events, baseline_events(feed), len(feed.frames))
    mae, ci = real.speed()
    if mae is None:
        # Never report a perfect error when nothing was checked.
        raise ValueError("No passes or shots were matched, so there is nothing to report.")
    pixel_row = None
    if pixel_seconds > 0:
        cfg = pixel_cfg or PixelConfig()
        coord, pix, stats = pixel_compare(feed, events, pixel_seconds, cfg)
        pixel_row = PixelPathRow(
            window_s=pixel_seconds,
            frames=stats["frames"],
            width_px=cfg.width,
            height_px=cfg.height,
            player_error_m=stats["player_error_m"],
            ball_error_m=stats["ball_error_m"],
            ball_found_pct=stats["ball_found_pct"],
            coordinate=[*coord.rows(), coord.pressure_row()],
            pixels=[*pix.rows(), pix.pressure_row()],
            speed_mae_kmh_coordinate=coord.speed()[0],
            speed_mae_kmh_pixels=pix.speed()[0],
        )
    passes = real.rows(["pass"])[0]
    return AutoEventingStatus(
        passes_detected_pct=round(100 * passes.recall, 1),
        speed_mae_kmh=mae,
        events_checked=real.truth["pass"] + real.truth["shot"],
        match_id=events[0].match_id,
        speed_mae_ci_kmh=ci,
        classes=real.rows(),
        pressure=real.pressure_row(),
        confusion=real.confusion_table(),
        baseline=BaselineRow(
            name=BASELINE_NAME, classes=[*base.rows(["pass", "tackle"]), base.pressure_row()]
        ),
        pixel_path=pixel_row,
        caveat=CAVEAT,
    )


__all__ = [
    "CAVEAT",
    "HELD_OUT_SEEDS",
    "SWEEP",
    "TUNING_SEEDS",
    "BenchmarkResult",
    "Tally",
    "class_row",
    "evaluate",
    "held_out_match",
    "pixel_compare",
    "run_benchmark",
]
