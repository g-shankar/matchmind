import inspect
import math
from pathlib import Path

import pytest

from matchmind.autoevent import (
    LABEL,
    DetectedEvent,
    detect_events,
    evaluate,
    match_events,
    render_tracking,
    score,
)
from matchmind.autoevent import detect as detect_module
from matchmind.autoevent.cli import main as cli_main
from matchmind.schema import EventType
from matchmind.simulator import random_script, simulate
from matchmind.simulator.publisher import read_jsonl, write_jsonl

DATA = Path(__file__).resolve().parents[1] / "data" / "matches"
HELD_OUT_SEED = 901  # not one of the published matches (seeds 100-104)


@pytest.fixture(scope="module")
def demo_events():
    return read_jsonl(DATA / "MM-DEMO-001.jsonl")


@pytest.fixture(scope="module")
def demo(demo_events):
    feed = render_tracking(demo_events)
    found = detect_events(feed)
    return feed, found, score(demo_events, found, hz=feed.hz, frames=len(feed.frames))


@pytest.fixture(scope="module")
def held_out():
    events = simulate(random_script("MM-HOLD-901"), HELD_OUT_SEED)
    feed = render_tracking(events)
    found = detect_events(feed)
    return events, score(events, found, hz=feed.hz, frames=len(feed.frames))


def short_match(events, n=250):
    """The first n events of a match: enough play to test, quick to render."""
    return events[:n]


# ------------------------------------------------------------------ feed


def test_feed_covers_both_halves_at_25_hz(demo, demo_events):
    feed, _, _ = demo
    assert feed.source == "synthetic_tracking"
    assert feed.hz == 25.0
    assert len(feed.player_ids) == 22
    periods = {f.period for f in feed.frames}
    assert periods == {1, 2}
    first = [f for f in feed.frames if f.period == 1]
    assert first[1].clock_s - first[0].clock_s == pytest.approx(0.04, abs=1e-3)
    p1_end = max(e.clock_s for e in demo_events if e.period == 1)
    assert first[-1].clock_s == pytest.approx(p1_end, abs=0.05)


def test_positions_stay_on_the_pitch(demo):
    feed, _, _ = demo
    for f in feed.frames[::50]:
        if f.ball is not None:
            assert 0 <= f.ball[0] <= 105 and 0 <= f.ball[1] <= 68
        for v in f.xy[0::2]:
            assert math.isnan(v) or 0 <= v <= 105
        for v in f.xy[1::2]:
            assert math.isnan(v) or 0 <= v <= 68


def test_feed_has_dead_ball_spells_and_ball_dropouts(demo):
    feed, _, _ = demo
    dead = sum(not f.alive for f in feed.frames) / len(feed.frames)
    assert 0.1 < dead < 0.5
    assert any(f.ball is None and f.alive for f in feed.frames)


def test_sent_off_player_leaves_the_feed(demo, demo_events):
    feed, _, _ = demo
    red = next(e for e in demo_events if e.type == EventType.CARD and e.details.get("card") == "red")
    n = feed.player_ids.index(red.player_id)
    after = [f for f in feed.frames if f.period == red.period and f.clock_s > red.clock_s + 1]
    assert after and all(f.player(n) is None for f in after)


def test_ball_is_where_the_events_say(demo, demo_events):
    feed, _, _ = demo
    index = {(f.period, round(f.clock_s * 25)): f for f in feed.frames}
    checked = 0
    for e in demo_events:
        if e.type != EventType.PASS or e.start is None:
            continue
        f = index.get((e.period, round(e.clock_s * 25)))
        if f is None or f.ball is None or not f.alive:
            continue
        assert math.hypot(f.ball[0] - e.start.x, f.ball[1] - e.start.y) < 1.0
        checked += 1
    assert checked > 1000


def test_same_events_and_seed_give_the_same_feed(demo_events):
    a = render_tracking(short_match(demo_events), seed=3)
    b = render_tracking(short_match(demo_events), seed=3)
    c = render_tracking(short_match(demo_events), seed=4)
    assert [(f.clock_s, f.ball, f.xy.tobytes()) for f in a.frames] == [
        (f.clock_s, f.ball, f.xy.tobytes()) for f in b.frames
    ]
    assert [f.ball for f in a.frames] != [f.ball for f in c.frames]


def test_feed_carries_only_what_a_tracking_provider_delivers():
    """Guards the detector against event data leaking in through the feed."""
    from matchmind.autoevent.tracking import Frame, TrackingFeed

    assert set(Frame.__slots__) == {"period", "clock_s", "alive", "ball", "xy"}
    assert set(TrackingFeed.__slots__) == {
        "match_id",
        "hz",
        "player_ids",
        "player_teams",
        "attacks_right",
        "frames",
        "source",
    }


def test_rejects_a_stream_without_lineups(demo_events):
    with pytest.raises(ValueError, match="match_start"):
        render_tracking(demo_events[1:])


# -------------------------------------------------------------- detector


def test_detector_never_reads_events_or_labels():
    source = inspect.getsource(detect_module)
    assert "matchmind.schema" not in source
    assert "matchmind.simulator" not in source
    assert ".labels" not in source
    params = list(inspect.signature(detect_events).parameters)
    assert params == ["feed"]


def test_demo_passes(demo):
    _, _, r = demo
    assert r.passes.precision >= 0.98
    assert r.passes.recall >= 0.98
    assert r.passes.outcome_accuracy >= 0.97
    assert r.receiver_accuracy >= 0.98


def test_demo_shots(demo):
    _, _, r = demo
    assert r.shots.precision >= 0.85
    assert r.shots.recall >= 0.9
    assert r.shots.outcome_accuracy >= 0.85


def test_kick_speed_error_is_small(demo):
    _, _, r = demo
    assert r.speed_mae_kmh <= 2.0
    assert r.shot_speed_mae_kmh <= 3.0


def test_scripted_should_he_have_passed_shot_is_detected(demo, demo_events):
    _, found, _ = demo
    shot = next(
        e
        for e in demo_events
        if e.type == EventType.SHOT and any(lb.startswith("better_option") for lb in e.labels)
    )
    hits = [
        d
        for d in found
        if d.kind == "shot" and d.player_id == shot.player_id and abs(d.clock_s - shot.clock_s) <= 0.5
    ]
    assert len(hits) == 1
    assert hits[0].outcome == shot.outcome
    assert abs(hits[0].ball_speed_mps - shot.ball_speed_mps) * 3.6 <= 3.0


def test_held_out_match_scores_as_well(held_out):
    """Thresholds were set on the published matches; this match was not used."""
    _, r = held_out
    assert r.passes.precision >= 0.97 and r.passes.recall >= 0.97
    assert r.shots.recall >= 0.8 and r.shots.precision >= 0.8
    assert r.speed_mae_kmh <= 2.0
    assert r.interceptions.precision >= 0.9 and r.interceptions.recall >= 0.9
    assert r.tackles.precision >= 0.8 and r.tackles.recall >= 0.8
    assert r.pressure.recall >= 0.85 and r.pressure.precision >= 0.6


def test_every_detection_is_labelled_synthetic(demo):
    _, found, _ = demo
    assert found and all(d.source == "synthetic_tracking" for d in found)


# ---------------------------------------------------------------- scoring


def _found(kind, player, t, period=1, outcome="complete", speed=15.0):
    return DetectedEvent(kind, period, t, player, "NBR", outcome, (50.0, 34.0), (60.0, 34.0), speed)


def test_matching_is_one_to_one_and_time_limited(demo_events):
    passes = [e for e in demo_events if e.type == EventType.PASS][:3]
    p = passes[0]
    found = [
        _found("pass", p.player_id, p.clock_s + 0.1, p.period),
        _found("pass", p.player_id, p.clock_s + 0.2, p.period),  # duplicate: unmatched
        _found("pass", passes[1].player_id, passes[1].clock_s + 0.6, passes[1].period),  # too late
    ]
    matches = match_events(passes, found)
    assert len(matches) == 1
    assert matches[0].truth is p and matches[0].found is found[0]


def test_precision_and_recall_arithmetic(demo_events):
    truth = demo_events[:1] + [e for e in demo_events if e.type == EventType.PASS][:4]
    found = [_found("pass", e.player_id, e.clock_s, e.period, speed=e.ball_speed_mps) for e in truth[1:3]]
    found.append(_found("pass", "NBR-99", 1.0))  # false positive
    r = score(truth, found, hz=25, frames=0)
    assert r.passes.truth == 4 and r.passes.detected == 3 and r.passes.matched == 2
    assert r.passes.precision == pytest.approx(2 / 3, abs=1e-4)
    assert r.passes.recall == 0.5
    assert r.speed_mae_kmh == 0.0


def test_scoring_nothing_is_refused_not_reported_as_perfect(demo_events):
    with pytest.raises(ValueError):
        score([], [], hz=25, frames=0)
    r = score(demo_events[:5], [], hz=25, frames=0)
    assert r.speed_mae_kmh is None


def test_a_pass_and_shot_close_together_keep_their_kinds(demo_events):
    passes = [e for e in demo_events if e.type == EventType.PASS]
    p = passes[10]
    shot = p.model_copy(update={"type": EventType.SHOT, "clock_s": p.clock_s + 0.3, "event_id": "x"})
    found = [
        _found("shot", p.player_id, shot.clock_s - 0.25, p.period),
        _found("pass", p.player_id, p.clock_s, p.period),
    ]
    matches = match_events([p, shot], found)
    assert {(m.truth.type, m.found.kind) for m in matches} == {
        (EventType.PASS, "pass"),
        (EventType.SHOT, "shot"),
    }


def test_evaluate_matches_the_api_contract(demo_events):
    status = evaluate(short_match(demo_events, 600), pixel_seconds=0)
    data = status.model_dump()
    # The original five fields stay; the benchmark only adds optional ones.
    assert {"source", "label", "passes_detected_pct", "speed_mae_kmh", "events_checked"} <= set(data)
    assert data["source"] == "synthetic_tracking"
    assert data["label"] == LABEL == "Detected from synthetic tracking, not video"
    assert 90 <= data["passes_detected_pct"] <= 100
    assert data["events_checked"] > 100
    assert evaluate(short_match(demo_events, 600), pixel_seconds=0) == status


# -------------------------------------------------------------------- CLI


def test_cli_score_frames_and_svg(demo_events, tmp_path, capsys):
    path = write_jsonl(short_match(demo_events), tmp_path / "short.jsonl")
    cli_main(["score", str(path), "--json", str(tmp_path / "r.json")])
    out = capsys.readouterr()
    assert "MM-DEMO-001" in out.out and LABEL in out.err
    assert (tmp_path / "r.json").exists()

    cli_main(["frames", str(path), "--out", str(tmp_path / "f.jsonl.gz"), "--hz", "10"])
    assert (tmp_path / "f.jsonl.gz").stat().st_size > 1000

    cli_main(["svg", str(path), "--at", "02:00", "--seconds", "20", "--out", str(tmp_path / "a.svg")])
    svg = (tmp_path / "a.svg").read_text()
    assert svg.startswith("<svg") and LABEL in svg

    with pytest.raises(SystemExit):
        cli_main(["score", str(path), "--hz", "0"])
