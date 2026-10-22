"""Physical numbers from the synthetic tracking feed (stats.physical) and how the
stats engine and the session use them."""

from __future__ import annotations

import copy
import math
import random
from array import array

import pytest

from matchmind.autoevent.tracking import Frame, TrackingFeed, render_tracking, reuse_renders
from matchmind.schema import EventType
from matchmind.stats import physical
from matchmind.stats.physical import PhysicalStats, build_timeline, timeline_for
from matchmind.stats.state import StatsEngine


def feed_from(paths: dict[str, list[tuple[float, float] | None]], hz: float = 25.0, period: int = 1, t0=0.0):
    """A tracking feed with the given per-frame positions (None = not on the pitch)."""
    ids = tuple(paths)
    n = max(len(p) for p in paths.values())
    frames = []
    for k in range(n):
        xy = array("f")
        for pid in ids:
            pos = paths[pid][k] if k < len(paths[pid]) else None
            xy.extend((math.nan, math.nan) if pos is None else pos)
        frames.append(Frame(period, round(t0 + k / hz, 3), True, (50.0, 34.0), xy))
    return TrackingFeed("T", hz, ids, tuple("A" for _ in ids), {"A": True}, frames)


def line(speed: float, seconds: float, start=(10.0, 34.0), hz: float = 25.0):
    return [(start[0] + speed * k / hz, start[1]) for k in range(int(seconds * hz) + 1)]


def still(seconds: float, at=(50.0, 34.0), hz: float = 25.0):
    return [at] * (int(seconds * hz) + 1)


# ------------------------------------------------------------------ method


def test_position_noise_adds_almost_no_distance():
    """5 cm of noise at 25 Hz would add about 12 km over a match if steps were
    summed raw. After smoothing, a player standing still covers under 0.3 km."""
    rng = random.Random(1)
    seconds = 95 * 60
    noisy = [(50 + rng.gauss(0, 0.05), 34 + rng.gauss(0, 0.05)) for _ in range(int(seconds * 25))]
    tl = build_timeline(feed_from({"P": noisy}))
    final = tl.final()["P"]
    assert final.distance_km < 0.3
    assert final.sprints == 0 and final.top_speed_kmh < 7.2


def test_steady_run_lands_in_its_band():
    tl = build_timeline(feed_from({"P": still(2) + line(5.0, 20, start=(10, 34))}))
    p = tl.final()["P"]
    assert p.distance_km == pytest.approx(0.1, abs=0.01)  # 5 m/s for 20 s
    assert p.run_km == pytest.approx(p.distance_km, abs=0.015)  # 18 km/h is in the run band (bar the ramp-up)
    assert p.walk_km + p.jog_km + p.run_km + p.sprint_km == pytest.approx(p.distance_km, abs=0.02)
    assert p.top_speed_kmh == pytest.approx(18.0, abs=0.5) and p.sprints == 0


def test_a_sprint_needs_one_second_in_the_band():
    short = still(2) + line(8.0, 0.6) + still(3, at=(14.8, 34.0))
    assert build_timeline(feed_from({"P": short})).final()["P"].sprints == 0
    long = still(2) + line(8.0, 3.0) + still(3, at=(34.0, 34.0))
    tl = build_timeline(feed_from({"P": long}))
    p = tl.final()["P"]
    assert p.sprints == 1 and p.top_speed_kmh == pytest.approx(28.8, abs=0.5)
    (effort,) = tl.efforts
    assert effort.player_id == "P" and effort.peak_kmh >= physical.RUN_MAX_KMH
    assert 2.0 <= effort.start_s < effort.peak_s <= effort.end_s <= 5.5


def test_glitches_and_gaps_are_left_out():
    # A 15 m jump in one frame (a player snapped onto the ball) is not running.
    jump = still(3, at=(20.0, 34.0)) + still(3, at=(35.0, 34.0))
    p = build_timeline(feed_from({"P": jump})).final()["P"]
    assert p.distance_km < 0.005 and p.top_speed_kmh <= physical.MAX_STEP_MPS * 3.6
    # Sent off: no positions after the red card, so nothing more is counted.
    off = line(4.0, 10) + [None] * 250
    q = build_timeline(feed_from({"P": off})).final()["P"]
    assert q.distance_km == pytest.approx(0.04, abs=0.005)


def test_timeline_lookups_follow_the_clock_and_periods():
    first = build_timeline(feed_from({"P": line(4.0, 60)}))
    times = [first.player_at("P", 1, t).distance_km for t in range(0, 61, 5)]
    assert times == sorted(times) and times[0] == 0.0 and times[-1] == pytest.approx(0.24, abs=0.01)
    # Two periods: period 2 starts from the period 1 total, whatever its clock.
    p1 = feed_from({"P": line(4.0, 30)})
    p2 = feed_from({"P": line(4.0, 30, start=(20, 34))}, period=2, t0=2700.0)
    both = build_timeline(TrackingFeed("T", 25.0, ("P",), ("A",), {"A": True}, p1.frames + p2.frames))
    half = both.player_at("P", 1, 10_000).distance_km
    assert both.player_at("P", 2, 2700.0).distance_km == pytest.approx(half, abs=0.001)
    assert both.player_at("P", 2, 9999).distance_km == pytest.approx(2 * half, abs=0.01)
    assert both.player_at("nobody", 2, 9999) == PhysicalStats()
    assert copy.deepcopy(both) is both  # engine checkpoints share the timeline


# ------------------------------------------------------- the real matches


@pytest.fixture(scope="module")
def demo():
    from matchmind.api.session import load_events

    events = load_events()
    return events, timeline_for(events)


def test_demo_totals_are_plausible(demo):
    events, tl = demo
    final = tl.final()
    keepers = {p.player_id for p in events[0].lineups if p.position == "GK"}
    sent_off = {e.player_id for e in events if e.type == EventType.CARD and e.details.get("card") == "red"}
    outfield = [s.distance_km for pid, s in final.items() if pid not in keepers | sent_off]
    assert min(outfield) >= 9.0 and max(outfield) <= 12.5
    assert all(4.0 <= final[k].distance_km <= 7.5 for k in keepers)
    assert all(s.top_speed_kmh <= physical.MAX_STEP_MPS * 3.6 for s in final.values())
    assert all(0 <= s.sprint_km < 1.0 for s in final.values())
    assert tl.label == "Estimated from synthetic tracking" and tl.source == "synthetic_tracking"
    assert timeline_for(events) is tl  # cached per match


def test_engine_takes_physical_numbers_from_the_timeline(demo):
    events, tl = demo
    engine = StatsEngine(events[0].match_id, "NBR", "HCY")
    engine.attach_physical(tl)
    changed = []
    for e in events:
        engine.process(e)
        changed.append(len(engine.changed_players()))
    last = events[-1]
    for pid, p in engine.players().items():
        assert p.physical_source == "synthetic_tracking"
        want = tl.player_at(pid, last.period, last.clock_s)
        assert round(p.distance_km, 1) == round(want.distance_km, 1)
        assert p.sprints == want.sprints and p.top_speed_kmh == want.top_speed_kmh
    # Ticks do not carry all 22 players every time.
    assert sum(changed) / len(changed) < 5
    with pytest.raises(ValueError):
        engine.attach_physical(tl)  # only before the first event


def test_engine_without_tracking_keeps_the_event_estimate(demo):
    events, _ = demo
    engine = StatsEngine.replay(events)
    players = engine.players()
    assert all(p.physical_source == "event_estimate" for p in players.values())
    assert max(p.distance_km for p in players.values()) < 5


def test_sprint_efforts_reach_each_event_once(demo):
    events, tl = demo
    engine = StatsEngine(events[0].match_id, "NBR", "HCY")
    engine.attach_physical(tl)
    seen = []
    for e in events:
        m = engine.process(e)
        seen += [(s.player_id, s.period, s.peak_clock_s) for s in m.sprint_efforts or []]
        again = engine.process(e)  # a repeated delivery returns the same, adds nothing
        assert again.sprint_efforts == m.sprint_efforts
    last = events[-1]
    expected = [
        (f.player_id, f.period, f.peak_s)
        for f in tl.efforts
        if (f.period, f.peak_s) <= (last.period, last.clock_s)
    ]
    assert sorted(seen) == sorted(expected) and len(seen) == len(set(seen))


def test_session_seek_gives_the_same_physical_numbers_as_watching(demo):
    from conftest import FakeCrew
    from matchmind.api.session import Engines, MatchSession

    events, tl = demo
    session = MatchSession(events, engines=Engines(stats=StatsEngine, crew=FakeCrew), physical=tl)
    session.seek(4000.0, period=2)
    jumped = {p.player_id: p for p in session.players()}
    straight = StatsEngine.replay(events[: session.next_index], physical=tl).players()
    assert {pid: p.model_dump() for pid, p in jumped.items()} == {
        pid: straight[pid].model_dump() for pid in jumped
    }
    # A timeline for another match is ignored rather than mixed in.
    other = build_timeline(feed_from({"P": still(1)}))
    assert (
        MatchSession(events, engines=Engines(stats=StatsEngine, crew=FakeCrew), physical=other).physical
        is None
    )


def test_reuse_renders_draws_the_feed_once():
    from matchmind.api.session import DEFAULT_MATCH_FILE
    from matchmind.simulator.publisher import read_jsonl

    events = read_jsonl(DEFAULT_MATCH_FILE)
    short = [e for e in events if e.period == 1 and e.clock_s < 120]
    with reuse_renders():
        a = render_tracking(short)
        b = render_tracking(short)
        c = render_tracking(short, seed=7)
    assert a is b and c is not a
    assert render_tracking(short) is not a  # outside the block every call draws afresh
