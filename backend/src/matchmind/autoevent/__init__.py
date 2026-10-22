"""Synthetic tracking-to-event benchmark (detected from synthetic tracking, not video).

`render_tracking` turns a simulated match into a tracking feed,
`detect_events` finds passes, shots, clearances, tackles, interceptions,
recoveries and pressure in that feed using the frames alone, and
`report` / `evaluate` / `run_benchmark` score the detections against the
simulator's own events. `pixels` renders the feed as synthetic top-down video
frames and recovers positions from the pixels, so the same detector can be
scored on both paths. None of it is real tracking or real video.
"""

from .benchmark import CAVEAT, HELD_OUT_SEEDS, TUNING_SEEDS, BenchmarkResult, evaluate, run_benchmark
from .detect import DetectedEvent, detect_events
from .score import (
    BENCHMARK_NAME,
    KINDS,
    LABEL,
    PIXEL_LABEL,
    AutoEventingReport,
    AutoEventingStatus,
    ClassRow,
    KindScore,
    match_events,
    report,
    score,
)
from .tracking import DEFAULT_HZ, Frame, TrackingFeed, render_tracking

__all__ = [
    "BENCHMARK_NAME",
    "CAVEAT",
    "DEFAULT_HZ",
    "HELD_OUT_SEEDS",
    "KINDS",
    "LABEL",
    "PIXEL_LABEL",
    "TUNING_SEEDS",
    "AutoEventingReport",
    "AutoEventingStatus",
    "BenchmarkResult",
    "ClassRow",
    "DetectedEvent",
    "Frame",
    "KindScore",
    "TrackingFeed",
    "detect_events",
    "evaluate",
    "match_events",
    "render_tracking",
    "report",
    "run_benchmark",
    "score",
]
