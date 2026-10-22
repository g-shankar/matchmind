"""The metric registry, the basic stats layer (tackles, PPDA, possession) and the
direction of the control/chaos index."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import FakeClock, FakeCrew
from matchmind.api import view
from matchmind.api.app import create_app
from matchmind.api.session import Engines, MatchSession, load_events
from matchmind.schema import Event, EventType, Outcome, Point
from matchmind.stats import registry
from matchmind.stats.models import MatchStateSnapshot, PlayerStats
from matchmind.stats.physical import timeline_for
from matchmind.stats.state import StatsEngine

# ------------------------------------------------------------------ helpers

_seq = iter(range(1, 1_000_000))


def ev(t: float, type_: EventType, team: str | None = None, **kw) -> Event:
    n = next(_seq)
    return Event(
        event_id=f"R-{n:06d}",
        match_id="R",
        seq=n,
        ts=datetime(2026, 10, 24, 15, tzinfo=UTC),
        period=1,
        clock_s=t,
        match_clock=f"{int(t // 60):02d}:{int(t % 60):02d}",
        type=type_,
        team=team,
        **kw,
    )


def engine() -> StatsEngine:
    e = StatsEngine("R", "NBR", "HCY")
    e.process(ev(0.0, EventType.MATCH_START, details={"home": "NBR", "away": "HCY"}))
    return e


def pt(x: float, y: float = 34.0) -> Point:
    return Point(x=x, y=y)


# ------------------------------------------------------------------ registry


def test_docs_metric_reference_is_generated_from_the_registry():
    text = registry.DOCS.read_text("utf-8")
    assert registry.DOC_BEGIN in text and registry.DOC_END in text
    assert registry.replace_section(text) == text, "run `python -m matchmind.stats.registry --write`"


def test_registry_entries_are_complete_and_point_at_real_fields():
    ids = [m.id for m in registry.METRICS]
    assert len(ids) == len(set(ids))
    player_keys = set(PlayerStats(player_id="a", team="b").model_dump())
    snapshot_keys = set(MatchStateSnapshot.model_fields)
    window_keys = {"home." + k for k in ("possession_pct", "field_tilt_pct", "pressure_index")} | {
        "away." + k for k in ("possession_pct", "field_tilt_pct", "pressure_index")
    }
    for m in registry.METRICS:
        assert m.formula and m.symbols and m.units and m.window and m.range and m.limitations is not None
        assert m.source_events and m.fields
        for field in m.fields:
            where, _, key = field.partition(".")
            if where == "player":
                assert key in player_keys, field
            elif where == "event":
                assert key.removeprefix("metrics.") in view.METRIC_KEYS, field
            elif where == "state":
                assert key in snapshot_keys or key in window_keys, field
    # The quality flags the brief asks for are all in use, with tracking marked as such.
    flags = {m.quality for m in registry.METRICS}
    assert {"heuristic", "estimated_from_synthetic_tracking", "calibrated", "counted"} == flags
    tracked = {m.id for m in registry.METRICS if m.quality == "estimated_from_synthetic_tracking"}
    assert tracked == {"distance_km", "speed_bands", "sprints", "top_speed_kmh"}
    assert {n.id for n in registry.NOT_COMPUTED} >= {"bps", "clean_sheet_odds"}


# --------------------------------------------------------- tackles and PPDA


def test_tackles_lost_are_dribbles_past_the_defender():
    e = engine()
    e.process(
        ev(
            10,
            EventType.DRIBBLE,
            "NBR",
            player_id="NBR-9",
            start=pt(60),
            end=pt(64),
            outcome=Outcome.COMPLETE,
            details={"opponent_id": "HCY-4"},
        )
    )
    e.process(
        ev(
            20,
            EventType.DRIBBLE,
            "NBR",
            player_id="NBR-9",
            start=pt(66),
            end=pt(66),
            outcome=Outcome.INCOMPLETE,
            details={"opponent_id": "HCY-4"},
        )
    )
    e.process(ev(20.4, EventType.TACKLE, "HCY", player_id="HCY-4", start=pt(66), outcome=Outcome.WON))
    hcy4 = e.players()["HCY-4"]
    assert (hcy4.tackles_won, hcy4.tackles_lost, hcy4.tackles_attempted, hcy4.tackle_success_pct) == (
        1,
        1,
        2,
        50.0,
    )
    totals = e.team_totals()
    assert totals["HCY"].tackles_won == 1 and totals["HCY"].tackles_lost == 1


def test_ppda_counts_opponent_passes_in_their_own_60_percent():
    e = engine()
    # HCY attack towards x = 0, so their own 60% is x > 42. Six passes there, two higher up.
    for i, x in enumerate([90, 80, 70, 60, 50, 45, 30, 20]):
        e.process(
            ev(
                10 + i,
                EventType.PASS,
                "HCY",
                player_id="HCY-5",
                start=pt(x),
                end=pt(x - 5),
                outcome=Outcome.COMPLETE,
            )
        )
    # NBR defensive actions: two in HCY's own 60% (x >= 42 for NBR), one deep in their own half.
    e.process(ev(30, EventType.INTERCEPTION, "NBR", player_id="NBR-6", start=pt(70)))
    e.process(ev(31, EventType.FOUL, "NBR", player_id="NBR-8", start=pt(50)))
    e.process(ev(32, EventType.TACKLE, "NBR", player_id="NBR-5", start=pt(20), outcome=Outcome.WON))
    nbr = e.team_totals()["NBR"]
    assert (nbr.ppda_opponent_passes, nbr.ppda_defensive_actions, nbr.ppda) == (6, 2, 3.0)
    assert e.team_totals()["HCY"].ppda is None  # no HCY defensive actions yet


def test_basic_stats_route_and_metrics_route():
    events = load_events()
    tl = timeline_for(events)
    clock = FakeClock()
    s = MatchSession(events, engines=Engines(stats=StatsEngine, crew=FakeCrew), clock=clock, physical=tl)
    app = create_app(session=s, tick_interval=None, allowed_origins=[], clock=clock)
    with TestClient(app) as c:
        reg = c.get("/api/metrics")
        assert reg.status_code == 200 and reg.headers["cache-control"] == "no-store"
        body = reg.json()
        assert {m["id"] for m in body["metrics"]} == {m.id for m in registry.METRICS}
        assert body["quality_flags"]["estimated_from_synthetic_tracking"]
        s.seek(5000.0, period=2)
        basic = c.get("/api/match/stats/basic").json()
    assert basic["physical_source"] == "synthetic_tracking"
    assert basic["physical_label"] == "Estimated from synthetic tracking"
    assert basic["pass_accuracy_denominator"].startswith("every pass attempt")
    nbr, hcy = basic["teams"]["NBR"], basic["teams"]["HCY"]
    assert nbr["possession_pct"] + hcy["possession_pct"] == pytest.approx(100.0, abs=0.11)
    assert nbr["pass_accuracy_pct"] == round(100 * nbr["passes_completed"] / nbr["passes_attempted"], 1)
    assert nbr["shots_on_target"] <= nbr["shots"] and nbr["tackles_won"] <= nbr["tackles_attempted"]
    assert 50 < nbr["distance_km"] < 130 and nbr["ppda"] is not None
    p = next(x for x in basic["players"] if x["player_id"] == "NBR-9")
    assert (p["name"], p["number"], p["position"]) == ("Adam Kerrigan", 9, "ST")
    assert p["distance_km"] > 5 and p["top_speed_kmh"] > 20
    assert sum(x["shots"] for x in basic["players"] if x["team"] == "NBR") == nbr["shots"]


# ------------------------------------------------------- control vs chaos


def test_control_chaos_points_to_control_for_a_long_passing_spell():
    e = engine()
    t = 1.0
    for i in range(50):  # five minutes of one NBR possession, soft passes, no turnovers
        e.process(
            ev(
                t,
                EventType.PASS,
                "NBR",
                player_id=f"NBR-{2 + i % 9}",
                possession_id=7,
                start=pt(40 + i % 10),
                end=pt(42 + i % 10),
                outcome=Outcome.COMPLETE,
                ball_speed_mps=10.0,
            )
        )
        t += 6.0
    snap = e.snapshot()
    assert snap.control_chaos > 0.5 and snap.tempo in ("Methodical Control", "Total Positional Control")


def test_control_chaos_points_to_chaos_for_a_turnover_heavy_spell():
    e = engine()
    t, poss = 1.0, 1
    for i in range(75):  # the ball changes hands every 4 seconds: tackles, interceptions, clearances
        team = "NBR" if i % 2 == 0 else "HCY"
        poss += 1
        kind = (EventType.TACKLE, EventType.INTERCEPTION, EventType.CLEARANCE)[i % 3]
        extra = (
            {"outcome": Outcome.WON}
            if kind == EventType.TACKLE
            else {"end": pt(80), "ball_speed_mps": 24.0}
            if kind == EventType.CLEARANCE
            else {}
        )
        e.process(ev(t, kind, team, player_id=f"{team}-5", possession_id=poss, start=pt(50), **extra))
        t += 4.0
    snap = e.snapshot()
    assert snap.control_chaos < -0.4 and snap.tempo == "Furious Chaos"
