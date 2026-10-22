"""Synthetic tracking-to-event benchmark: statistics, splits, gains, pressure, pixel path, API shape.

Everything here runs on short slices of play so the file stays fast; the full
benchmark runs behind `matchmind-autoevent benchmark`.
"""

import json
import math
import shutil
from pathlib import Path

import pytest

from matchmind.autoevent import (
    BENCHMARK_NAME,
    HELD_OUT_SEEDS,
    KINDS,
    LABEL,
    PIXEL_LABEL,
    TUNING_SEEDS,
    detect_events,
    evaluate,
    render_tracking,
)
from matchmind.autoevent import benchmark as bench
from matchmind.autoevent.baseline import baseline_events
from matchmind.autoevent.benchmark import Tally, class_row, pixel_compare
from matchmind.autoevent.cli import main as cli_main
from matchmind.autoevent.clip import write_clip, write_png
from matchmind.autoevent.degrade import Degradation, degrade
from matchmind.autoevent.detect import estimate_noise, smoothing_half_window
from matchmind.autoevent.evalstats import bootstrap_mean_ci, f1, wilson
from matchmind.autoevent.pixels import PixelConfig, PixelPath
from matchmind.autoevent.score import confusion_matrix, match_events, truth_kind
from matchmind.autoevent.svg import render_failure_svg
from matchmind.schema import EventType
from matchmind.simulator.publisher import read_jsonl, write_jsonl

DATA = Path(__file__).resolve().parents[1] / "data" / "matches"


@pytest.fixture(scope="module")
def short():
    """The first 700 events of the demo match (about 13 minutes of play)."""
    events = read_jsonl(DATA / "MM-DEMO-001.jsonl")[:700]
    feed = render_tracking(events)
    return events, feed, detect_events(feed)


# ------------------------------------------------------------- statistics


def test_wilson_interval_matches_reference_values():
    assert wilson(8, 10) == (0.4902, 0.9433)
    assert wilson(50, 100) == (0.4038, 0.5962)
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and lo == pytest.approx(0.7225, abs=1e-4)
    assert wilson(0, 0) is None
    with pytest.raises(ValueError):
        wilson(11, 10)


def test_wilson_narrows_with_more_data():
    small, big = wilson(9, 10), wilson(900, 1000)
    assert big[1] - big[0] < small[1] - small[0]
    assert small[0] < 0.9 < small[1] and big[0] < 0.9 < big[1]


def test_bootstrap_is_seeded_and_brackets_the_mean():
    values = [abs(math.sin(i)) * 3 for i in range(200)]
    a = bootstrap_mean_ci(values)
    assert a == bootstrap_mean_ci(values)
    mean = sum(values) / len(values)
    assert a[0] < mean < a[1]
    assert bootstrap_mean_ci([]) is None
    assert bootstrap_mean_ci([2.0, 2.0, 2.0]) == (2.0, 2.0)


def test_f1_and_class_row():
    assert f1(0.5, 1.0) == pytest.approx(2 / 3, abs=1e-4)
    assert f1(0.0, 0.0) == 0.0
    row = class_row("pass", truth=10, detected=8, matched=8)
    assert row.precision == 1.0 and row.recall == 0.8 and row.support == 10
    assert row.precision_ci == wilson(8, 8) and row.recall_ci == wilson(8, 10)
    empty = class_row("shot", 0, 0, 0)
    assert empty.precision_ci is None and empty.recall_ci is None and empty.f1 == 0.0


# ------------------------------------------------------- confusion matrix


def test_confusion_totals_equal_event_counts(short):
    events, _, found = short
    matches = match_events(events, found)
    m = confusion_matrix(events, found, matches)
    n = len(KINDS)
    for k, kind in enumerate(KINDS):
        assert sum(m[k]) == sum(truth_kind(e) == kind for e in events), kind
        assert sum(row[k] for row in m) == sum(d.kind == kind for d in found), kind
    assert m[n][n] == 0
    assert sum(m[k][k] for k in range(n)) <= len(matches)
    assert all(v >= 0 for row in m for v in row)


def test_tally_adds_up_across_matches(short):
    events, _, found = short
    one, two = Tally.empty(), Tally.empty()
    one.add(events, found)
    two.add(events, found)
    two.add(events, found)
    assert two.truth == {k: 2 * v for k, v in one.truth.items()}
    assert two.confusion == [[2 * v for v in row] for row in one.confusion]
    assert len(two.speed_errors) == 2 * len(one.speed_errors)
    assert two.pressure == [2 * v for v in one.pressure]


# ---------------------------------------------- gains, pressure, baseline


def test_possession_changes_are_detected(short):
    events, feed, found = short
    t = Tally.empty()
    t.add(events, found, len(feed.frames))
    rows = {r.kind: r for r in t.rows()}
    assert rows["interception"].support > 50 and rows["interception"].f1 >= 0.9
    assert rows["tackle"].support > 5 and rows["tackle"].f1 >= 0.75
    assert {d.kind for d in found} >= {"pass", "tackle", "interception", "pressure"}
    for d in found:
        if d.kind in ("tackle", "interception", "recovery"):
            assert d.outcome == "won" and d.ball_speed_mps == 0.0


def test_pressure_is_scored_against_the_event_flag(short):
    events, _, found = short
    t = Tally.empty()
    t.add(events, found)
    truth_n = sum(
        e.under_pressure
        for e in events
        if e.type in (EventType.PASS, EventType.SHOT, EventType.CLEARANCE) and e.player_id
    )
    p = t.pressure_row()
    assert p.support == truth_n > 20
    assert p.recall >= 0.85
    calls = [d for d in found if d.kind == "pressure"]
    assert calls and all(d.pressed_by and d.team for d in calls)


def test_detector_beats_the_naive_baseline(short):
    events, feed, found = short
    real, base = Tally.empty(), Tally.empty()
    real.add(events, found)
    base.add(events, baseline_events(feed))
    r, b = {x.kind: x for x in real.rows()}, {x.kind: x for x in base.rows()}
    assert r["pass"].f1 > b["pass"].f1 + 0.1
    assert r["tackle"].f1 > b["tackle"].f1 + 0.3
    assert real.pressure_row().f1 > base.pressure_row().f1


# ----------------------------------------------------------------- splits


def test_held_out_seeds_were_never_tuning_seeds():
    manifest = json.loads((DATA / "manifest.json").read_text())
    published = {m["seed"] for m in manifest}
    assert set(TUNING_SEEDS) == published
    assert not set(HELD_OUT_SEEDS) & published
    assert len(HELD_OUT_SEEDS) >= 10


def test_held_out_match_is_new_and_reproducible():
    a = bench.held_out_match(HELD_OUT_SEEDS[0])
    assert a[0].match_id == f"MM-HOLD-{HELD_OUT_SEEDS[0]}"
    b = bench.held_out_match(HELD_OUT_SEEDS[0])
    assert [e.event_id for e in a[:50]] == [e.event_id for e in b[:50]]


# ------------------------------------------------------------- robustness


def test_noise_estimate_and_smoothing(short):
    _, feed, _ = short
    p = feed.frames[:3000]
    from matchmind.autoevent.tracking import TrackingFeed

    part = TrackingFeed(feed.match_id, feed.hz, feed.player_ids, feed.player_teams, feed.attacks_right, p)
    base = estimate_noise([f.ball if f.alive else None for f in part.frames])
    assert base == pytest.approx(0.05, abs=0.015)
    assert smoothing_half_window(base, 25) == 0  # the clean feed is used as it is
    noisy = degrade(part, Degradation("15 cm", noise_m=0.15))
    est = estimate_noise([f.ball if f.alive else None for f in noisy.frames])
    assert est == pytest.approx(0.15, abs=0.03)
    assert 1 <= smoothing_half_window(est, 25) <= 6


def test_degrade_is_deterministic_and_worse_but_graceful(short):
    events, feed, found = short
    d = Degradation("15 cm noise", noise_m=0.15, player_occlusion_per_s=0.1)
    a, b = degrade(feed, d), degrade(feed, d)
    assert [f.xy.tobytes() for f in a.frames[:500]] == [f.xy.tobytes() for f in b.frames[:500]]
    clean, noisy = Tally.empty(), Tally.empty()
    clean.add(events, found)
    noisy.add(events, detect_events(a))
    c, n = {x.kind: x for x in clean.rows()}, {x.kind: x for x in noisy.rows()}
    assert n["pass"].f1 <= c["pass"].f1
    assert n["pass"].f1 >= 0.9  # graceful, not a cliff
    assert n["interception"].f1 >= 0.8


# -------------------------------------------------------------- pixel path


@pytest.fixture(scope="module")
def pixel_slice(short):
    _, feed, _ = short
    path = PixelPath(feed)
    lo, hi = 1000, 1100  # 4 s of play
    rec, stats = path.recover(lo, hi)
    return feed, lo, hi, rec, stats


def test_pixel_path_recovers_positions_within_bounds(pixel_slice):
    feed, lo, hi, rec, stats = pixel_slice
    s = stats.summary()
    assert s["frames"] == hi - lo == len(rec.frames)
    assert s["player_error_m"] < 0.15
    assert s["player_error_p95_m"] < 0.6
    assert s["ball_found_pct"] >= 95
    assert s["ball_error_m"] < 0.2
    # Same timestamps and play flag, positions from the pixels.
    assert [f.clock_s for f in rec.frames] == [f.clock_s for f in feed.frames[lo:hi]]
    assert [f.alive for f in rec.frames] == [f.alive for f in feed.frames[lo:hi]]


def test_pixel_path_is_deterministic(short, pixel_slice):
    feed, lo, hi, rec, _ = pixel_slice
    again, _ = PixelPath(feed).recover(lo, hi)
    assert [f.xy.tobytes() for f in again.frames] == [f.xy.tobytes() for f in rec.frames]
    assert [f.ball for f in again.frames] == [f.ball for f in rec.frames]
    other, _ = PixelPath(feed, PixelConfig(seed=8)).recover(lo, hi)
    assert [f.ball for f in other.frames] != [f.ball for f in rec.frames]


def test_pixel_frames_are_images_of_the_pitch(short):
    _, feed, _ = short
    path = PixelPath(feed)
    (k, img), *_ = list(path.images(0, 2))
    assert img.shape == (208, 320, 3) and str(img.dtype) == "uint8"
    assert img[..., 1].mean() > img[..., 0].mean()  # mostly grass


def test_pixel_and_coordinate_paths_score_the_same_window(short):
    events, feed, _ = short
    coord, pix, stats = pixel_compare(feed, events, 20.0)
    assert coord.truth == pix.truth  # same truth, same frames
    assert coord.truth["pass"] >= 3
    assert stats["frames"] == 500
    rc, rp = {r.kind: r for r in coord.rows()}, {r.kind: r for r in pix.rows()}
    assert rp["pass"].recall >= rc["pass"].recall - 0.5
    with pytest.raises(ValueError):
        PixelPath(feed).recover(10, 5)


# --------------------------------------------------------- API (evaluate)


def test_evaluate_keeps_the_old_fields_and_adds_the_benchmark(short):
    events, _, _ = short
    status = evaluate(events, pixel_seconds=8.0)
    data = status.model_dump(mode="json")
    assert {"source", "label", "passes_detected_pct", "speed_mae_kmh", "events_checked"} <= set(data)
    assert data["source"] == "synthetic_tracking" and data["label"] == LABEL
    assert data["name"] == BENCHMARK_NAME == "Synthetic tracking-to-event benchmark"
    assert [c["kind"] for c in data["classes"]] == list(KINDS)
    lo, hi = data["speed_mae_ci_kmh"]
    assert lo <= data["speed_mae_kmh"] <= hi
    conf = data["confusion"]
    assert conf["rows"][-1] == "spurious" and conf["columns"][-1] == "missed"
    assert len(conf["counts"]) == len(KINDS) + 1
    assert data["pressure"]["kind"] == "pressure"
    assert data["baseline"]["classes"][0]["kind"] == "pass"
    px = data["pixel_path"]
    assert px["label"] == PIXEL_LABEL and px["window_s"] == 8.0 and px["frames"] == 200
    assert "circular" in data["caveat"].lower()
    assert evaluate(events, pixel_seconds=8.0) == status
    # Cached once per match, but callers get their own copy.
    status.classes[0].matched = -1
    assert evaluate(events, pixel_seconds=8.0).classes[0].matched != -1
    assert evaluate(events, pixel_seconds=0).pixel_path is None


# ------------------------------------------------------- outputs and CLI


def test_failure_svg_rings_the_event(short):
    events, feed, found = short
    miss = next(e for e in events if e.type == EventType.INTERCEPTION)
    svg = render_failure_svg(feed, events, found, what="missed", truth=miss)
    assert svg.startswith("<svg") and LABEL in svg and "missed" in svg
    with pytest.raises(ValueError):
        render_failure_svg(feed, events, found, what="missed")


def test_png_writer_and_clip(short, tmp_path):
    _, feed, _ = short
    import numpy as np

    png = write_png(tmp_path / "x.png", np.zeros((4, 6, 3), np.uint8))
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    out = write_clip(feed, 500, 0.4, tmp_path / "c.mp4", still=tmp_path / "s.png")
    assert out["frames"] == 10 and Path(out["still"]).exists()
    if shutil.which("ffmpeg"):
        assert out["format"] == "mp4" and (tmp_path / "c.mp4").stat().st_size > 1000
    else:
        assert out["format"] == "png-strip"


def test_cli_benchmark_writes_json_and_markdown(short, tmp_path, monkeypatch, capsys):
    events, _, _ = short
    data = tmp_path / "matches"
    write_jsonl(events[:300], data / "MM-DEMO-001.jsonl")
    held = events[:300]
    monkeypatch.setattr(bench, "held_out_match", lambda seed: held)
    cli_main(
        [
            "benchmark",
            "--data", str(data),
            "--held-out", "900-901",
            "--robustness-matches", "1",
            "--pixel-matches", "1",
            "--pixel-seconds", "6",
            "--images", str(tmp_path / "img"),
            "--json", str(tmp_path / "b.json"),
            "--md", str(tmp_path / "b.md"),
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "b.json").read_text())
    assert result["name"] == BENCHMARK_NAME and result["held_out"]["seeds"] == [900, 901]
    assert len(result["robustness"]) == len(bench.SWEEP)
    assert result["pixel"]["label"] == PIXEL_LABEL
    md = (tmp_path / "b.md").read_text()
    assert "95% CI" in md
    assert "spurious" in md and "missed" in md and PIXEL_LABEL in md and "Circular" in md
    for f in result["failures"]:
        assert (tmp_path / "img" / f["image"]).exists()
    assert "held-out pass" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli_main(["benchmark", "--held-out", "nine"])
