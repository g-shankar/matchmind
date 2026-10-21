"""Auto-eventing from synthetic tracking (not video).

`render_tracking` turns a simulated match into a tracking feed,
`detect_events` finds passes, shots and clearances in that feed using the
frames alone, and `evaluate` / `report` score the detections against the
simulator's own events.
"""

from .detect import DetectedEvent, detect_events
from .score import (
    LABEL,
    AutoEventingReport,
    AutoEventingStatus,
    KindScore,
    evaluate,
    match_events,
    report,
    score,
)
from .tracking import DEFAULT_HZ, Frame, TrackingFeed, render_tracking

__all__ = [
    "DEFAULT_HZ",
    "LABEL",
    "AutoEventingReport",
    "AutoEventingStatus",
    "DetectedEvent",
    "Frame",
    "KindScore",
    "TrackingFeed",
    "detect_events",
    "evaluate",
    "match_events",
    "render_tracking",
    "report",
    "score",
]
