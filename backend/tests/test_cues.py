"""Corrections (VAR overturns) through the stats engine, spotter, producer and
recap, and the cue sheet compiler (docs/CUE-SHEET.md, docs/METRICS.md)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from matchmind.crew.contracts import (
    Evidence,
    Explanation,
    Moment,
    MomentBundle,
    MomentKind,
    OverlayCard,
    ViewerProfile,
    without_retracted,
)
from matchmind.crew.crew import Crew
from matchmind.crew.cues import (
    LAYER_POLICY,
    Cue,
    CueCompiler,
    CueTime,
    RibbonSample,
    active_cues,
    cue_schema_text,
    sheet_id,
    telestration,
)
from matchmind.crew.llm import TemplateLLM
from matchmind.crew.producer import ViewerState, select
from matchmind.crew.translator import OffTranslator
from matchmind.schema import Event, Outcome
from matchmind.simulator.teams import get_team
from matchmind.stats.state import StatsEngine

SCHEMA = Path(__file__).resolve().parents[1] / "schema" / "cue.schema.json"
TEAMS = {t: get_team(t) for t in ("NBR", "HCY")}


def ev(seq: int, type_: str, t: float, period: int = 1, **kw) -> Event:
    m, s = divmod(int(t), 60)
    return Event(
        event_id=f"V-{seq:05d}",
        match_id="V",
        seq=seq,
        ts=datetime(2026, 10, 24, 15, tzinfo=UTC),
        period=period,
        clock_s=t,
        match_clock=kw.pop("match_clock", f"{m:02d}:{s:02d}"),
        type=type_,
        **kw,
    )


def goal_stream() -> list[Event]:
    """NBR-10 finds NBR-11, who scores at 39:11; VAR rules it out for offside at 40:22."""
    return [
        ev(0, "match_start", 0, details={"home": "NBR", "away": "HCY"}),
        ev(1, "period_start", 0),
        ev(
            2,
            "pass",
            2348,
            team="NBR",
            player_id="NBR-10",
            receiver_id="NBR-11",
            possession_id=7,
            start={"x": 80, "y": 30},
            end={"x": 94, "y": 32},
            outcome="complete",
        ),
        ev(
            3,
            "shot",
            2351,
            team="NBR",
            player_id="NBR-11",
            possession_id=7,
            start={"x": 94, "y": 32},
            end={"x": 105, "y": 34},
            outcome="goal",
            details={"assist_id": "NBR-10", "score_home": 1, "score_away": 0},
        ),
        ev(
            4,
            "var_review",
            2422,
            team="NBR",
            player_id="NBR-11",
            possession_id=7,
            outcome="overturned",
            reviewed_event_id="V-00003",
            review_reason="offside",
            details={"score_home": 0, "score_away": 0},
        ),
    ]


# ------------------------------------------------------------------ contract


def test_published_cue_schema_is_up_to_date():
    """backend/schema/cue.schema.json is generated from the Cue model:
    `python -m matchmind.crew.cues > schema/cue.schema.json`."""
    assert SCHEMA.read_text(encoding="utf-8") == cue_schema_text()
    schema = json.loads(cue_schema_text())
    assert set(schema["properties"]["op"]["enum"]) == {"show", "update", "retract", "supersede", "clear"}
    layers = schema["$defs"]["CueTime"]["properties"]
    assert {"period", "clock_s", "match_clock", "t_s"} <= set(layers)
    assert schema["additionalProperties"] is False


def test_every_layer_has_a_collision_policy():
    assert set(LAYER_POLICY) == {
        "lower_third",
        "side_panel",
        "pitch_tag",
        "metric_alert",
        "full_screen",
        "scorebug",
        "momentum_ribbon",
        "telestration",
    }


# ------------------------------------------------------------------- stats


def test_overturned_goal_leaves_the_score_but_the_shot_still_counts():
    events = goal_stream()
    before = StatsEngine.replay(events[:4])
    assert before.snapshot().score_home == 1
    shots, xg = before.snapshot().shots_home, before.snapshot().xg_home
    engine = StatsEngine.replay(events)
    snap = engine.snapshot()
    assert snap.score_home == 0 and snap.score_away == 0
    assert snap.shots_home == shots == 1 and snap.xg_home == xg > 0
    players = engine.players()
    assert players["NBR-11"].goals == 0 and players["NBR-11"].shots == 1
    assert players["NBR-10"].assists == 0 and players["NBR-10"].key_passes == 1
    assert players["NBR-10"].xa > 0  # the chance was still created
    assert engine.overturned_goals() == {"V-00003": "V-00004"}


def test_var_decision_metrics_and_changed_players():
    engine = StatsEngine("V", "NBR", "HCY")
    for e in goal_stream()[:4]:
        engine.process(e)
    m = engine.process(goal_stream()[4])
    vd = m.var_decision
    assert vd is not None and vd.goal_removed and vd.outcome == "overturned" and vd.reason == "offside"
    assert (vd.team, vd.player_id, vd.assist_id) == ("NBR", "NBR-11", "NBR-10")
    assert (vd.reviewed_clock, vd.score_home, vd.score_away) == ("39:11", 0, 0)
    assert {p.player_id for p in engine.changed_players()} >= {"NBR-10", "NBR-11"}


def test_duplicate_var_delivery_changes_nothing():
    engine = StatsEngine("V", "NBR", "HCY")
    for e in goal_stream():
        engine.process(e)
    again = engine.process(goal_stream()[4])  # at-least-once stream: same event twice
    assert again.var_decision.goal_removed is True  # the original answer, not a second removal
    assert engine.snapshot().score_home == 0 and engine.players()["NBR-11"].goals == 0


def test_second_review_of_the_same_goal_and_unknown_targets_are_no_ops():
    events = goal_stream()
    engine = StatsEngine.replay(events)
    twice = ev(
        5,
        "var_review",
        2430,
        team="NBR",
        outcome="overturned",
        reviewed_event_id="V-00003",
        review_reason="foul",
    )
    m = engine.process(twice)
    assert m.var_decision.goal_removed is False and engine.snapshot().score_home == 0
    unknown = ev(6, "var_review", 2440, outcome="overturned", reviewed_event_id="V-99999")
    assert engine.process(unknown).var_decision.goal_removed is False
    assert engine.snapshot().score_home == 0 and engine.players()["NBR-11"].goals == 0


def test_review_that_stands_keeps_the_goal():
    events = goal_stream()
    events[4] = events[4].model_copy(update={"outcome": Outcome.STANDS})
    engine = StatsEngine.replay(events)
    assert engine.snapshot().score_home == 1 and engine.players()["NBR-11"].goals == 1
    assert engine.overturned_goals() == {}


def test_review_before_its_goal_is_refused_or_ignored():
    """Out of order: a review arriving before the goal it names is older-seq
    (refused) or names an event not seen yet (ignored); it never removes a goal
    that has not been counted."""
    events = goal_stream()
    engine = StatsEngine.replay(events[:3])
    early = events[4].model_copy(update={"seq": 3, "event_id": "V-00003b"})
    assert engine.process(early).var_decision.goal_removed is False
    with pytest.raises(ValueError):
        engine.process(events[3])  # seq 3 arrives after seq 3: refused, never double counted
    assert engine.snapshot().score_home == 0


# ----------------------------------------------------------------- spotter/crew


@pytest.fixture(scope="module")
def crewed():
    crew = Crew(TEAMS, llm=TemplateLLM(), translator=OffTranslator())
    engine = StatsEngine("V", "NBR", "HCY")
    bundles: list[MomentBundle] = []
    for e in goal_stream():
        m = engine.process(e)
        bundles += crew.process(e, m, engine.snapshot(), engine.players())
    return crew, engine, bundles


def test_spotter_emits_one_correction_that_rules_the_goal_out(crewed):
    _, _, bundles = crewed
    kinds = [b.moment.kind for b in bundles]
    assert MomentKind.GOAL in kinds
    (corr,) = [b.moment for b in bundles if b.moment.kind == MomentKind.CORRECTION]
    assert corr.retracts == ["goal-V-00003"] and corr.source_event_ids == ["V-00004", "V-00003"]
    assert corr.facts["score_home"] == 0 and corr.facts["ruled_out_clock"] == "39:11"
    assert corr.facts["reason"] == "offside" and corr.facts["p_goals"] == 0
    assert without_retracted([b.moment for b in bundles]) == [
        b.moment for b in bundles if b.moment.moment_id != "goal-V-00003"
    ]


def test_correction_card_text_is_fact_checked_in_every_studio_language(crewed):
    crew, _, bundles = crewed
    corr = next(b for b in bundles if b.moment.kind == MomentKind.CORRECTION)
    for lang in ("en", "es", "fr", "ar", "ja"):
        for persona in ("casual", "tactical", "fantasy", "player_spotlight"):
            card = crew.render(corr, ViewerProfile(persona=persona, language=lang))
            assert card is not None, (persona, lang)
            assert card.slot == "full_screen" and card.retracts == ["goal-V-00003"]
            assert card.headline and card.body and card.why
            assert card.rtl == (lang == "ar")
    en = crew.render(corr, ViewerProfile())
    assert "39:11" in en.body and "offside" in en.body and "0-0" in en.body
    sources = {e.label_key: e.source_event_id for e in en.evidence}
    assert sources["ruled_out_clock"] == "V-00003" and sources["score_home"] == "V-00004"


def test_recap_no_longer_counts_the_ruled_out_goal(crewed):
    crew, engine, bundles = crewed
    recap = crew.recap(engine.snapshot(), engine.players(), ViewerProfile(), [b.moment for b in bundles])
    assert "goals_line" not in recap.stats and recap.stats["score_home"] == 0
    ids = [k.moment_id for k in recap.key_moments]
    assert "goal-V-00003" not in ids and "correction-V-00004" in ids
    assert recap.fact_check.ok


def card(moment_id: str, kind="goal", slot="full_screen", priority=95, t=100.0, retracts=(), dur=8.0):
    return OverlayCard(
        card_id=f"{moment_id}:casual:en",
        moment_id=moment_id,
        kind=kind,
        slot=slot,
        priority=priority,
        show_at_s=t,
        duration_s=dur,
        persona="casual",
        language="en",
        headline=f"h {moment_id}",
        body="b",
        why="w",
        tactical_tag="t",
        evidence=[Evidence(label="Home score", label_key="score_home", value=1)],
        produced_by="template",
        retracts=list(retracts),
    )


def test_producer_keeps_corrections_and_drops_late_or_repeated_ruled_out_cards():
    state = ViewerState()
    profile = ViewerProfile(persona="fantasy")
    corr = card("correction-X", kind="correction", retracts=["goal-X"], t=170)
    assert [c.moment_id for c in select([corr], profile, state)] == ["correction-X"]
    late = card("goal-X", t=100)  # out of order: the goal's card arrives after its correction
    assert select([late], profile, state) == []
    assert select([corr], profile, state) == []  # repeated delivery
    both = ViewerState()
    out = select(
        [card("goal-Y"), card("correction-Y", kind="correction", retracts=["goal-Y"])], profile, both
    )
    assert [c.moment_id for c in out] == ["correction-Y"]


# ------------------------------------------------------------------- compiler


def at(t: float, period: int = 1) -> CueTime:
    m, s = divmod(int(t), 60)
    return CueTime(period=period, clock_s=t, match_clock=f"{m:02d}:{s:02d}", t_s=t)


def bundle(moment_id: str, kind=MomentKind.GOAL, t=100.0, facts=None, retracts=()) -> MomentBundle:
    m = Moment(
        moment_id=moment_id,
        kind=kind,
        clock_s=t,
        match_clock="01:40",
        period=1,
        team="NBR",
        player_ids=["NBR-11"],
        facts=facts if facts is not None else {"score_home": 1, "score_away": 0},
        source_event_ids=[f"e-{moment_id}"],
        priority=95,
        retracts=list(retracts),
    )
    expl = Explanation(moment_id=moment_id, why="", tactical_tag="t", evidence=[], produced_by="template")
    return MomentBundle(moment=m, explanation=expl)


def compiler() -> CueCompiler:
    return CueCompiler.for_profile("V", "NBR", "HCY", ViewerProfile())


def test_goal_then_overturn_compiles_retract_supersede_and_scorebug_revert():
    c = compiler()
    goal = bundle("goal-X", t=100)
    corr = bundle(
        "correction-X",
        MomentKind.CORRECTION,
        t=170,
        facts={"score_home": 0, "score_away": 0, "reason": "offside"},
        retracts=["goal-X"],
    )
    first = c.feed(5, at(100), "shot", [goal], [card("goal-X")])
    assert [(q.op, q.layer, q.cue_id) for q in first] == [
        ("show", "full_screen", "goal-X@full_screen"),
        ("show", "scorebug", "scorebug@goal-X"),
    ]
    second = c.feed(
        9, at(170), "var_review", [corr], [card("correction-X", "correction", t=170, retracts=["goal-X"])]
    )
    assert [(q.op, q.layer) for q in second] == [
        ("retract", "full_screen"),
        ("retract", "scorebug"),
        ("supersede", "full_screen"),
        ("update", "scorebug"),
    ]
    retract_card, retract_bug, supersede, bug = second
    assert retract_card.retracts == ["goal-X@full_screen"] and retract_card.reason == "var_offside"
    assert retract_bug.retracts == ["scorebug@goal-X"]
    assert supersede.supersedes == ["goal-X@full_screen", "scorebug@goal-X"]
    assert bug.scorebug.score_home == 0 and bug.supersedes == ["scorebug@goal-X"]
    assert [q.seq for q in first + second] == [1, 2, 3, 4, 5, 6]
    on_air = active_cues(first + second, 171)
    assert "goal-X@full_screen" not in {q.cue_id for q in on_air}
    assert [q.scorebug.score_home for q in on_air if q.layer == "scorebug"] == [0]


def test_compiler_ignores_duplicates_and_never_airs_a_ruled_out_moment():
    c = compiler()
    corr = bundle("correction-X", MomentKind.CORRECTION, t=170, facts={"score_home": 0, "score_away": 0},
                  retracts=["goal-X"])  # fmt: skip
    out = c.feed(9, at(170), "var_review", [corr], [card("correction-X", "correction", retracts=["goal-X"])])
    assert [q.op for q in out] == ["supersede", "show"] and out[
        0
    ].supersedes == []  # nothing aired to retract
    assert c.feed(9, at(170), "var_review", [corr], []) == []  # the same tick twice
    late = c.feed(10, at(171), "shot", [bundle("goal-X")], [card("goal-X")])
    assert late == []  # the goal arrives after its correction: never on air, no scorebug either


def test_collision_rules_replace_queue_drop_and_stack():
    c = compiler()
    big = c.feed(1, at(100), "shot", [], [card("a", priority=95)])
    assert big[0].collision == "replace"
    queued = c.feed(2, at(103), "shot", [], [card("b", priority=60)])
    assert queued[0].collision == "queue" and queued[0].start.t_s == 108  # waits for "a" to end
    dropped = c.feed(3, at(104), "shot", [], [card("c", priority=50, dur=8)])
    assert dropped == []  # it would wait 12 s behind the queued cue: more than 8 s, so dropped
    took_over = c.feed(4, at(105), "shot", [], [card("d", priority=99)])
    assert took_over[0].collision == "replace" and took_over[0].start.t_s == 105
    tags = [
        c.feed(10 + i, at(200 + i), "pass", [], [card(f"t{i}", "speed_burst", "pitch_tag", 40, dur=4)])[0]
        for i in range(4)
    ]
    assert {q.collision for q in tags} == {"stack"}
    on_air = active_cues(big + queued + took_over + tags, 203.5)
    assert [q.cue_id for q in on_air if q.layer == "pitch_tag"] == [
        "t1@pitch_tag",
        "t2@pitch_tag",
        "t3@pitch_tag",
    ]


def test_lower_third_waits_and_far_away_waits_are_dropped():
    c = compiler()
    c.feed(1, at(100), "pass", [], [card("x", "milestone", "lower_third", 50, dur=7)])
    nxt = c.feed(2, at(101), "pass", [], [card("y", "card", "lower_third", 40, dur=7)])
    assert nxt[0].collision == "queue" and nxt[0].start.t_s == 107 and nxt[0].end.t_s == 114
    assert nxt[0].start.match_clock == "01:47"
    long = compiler()
    long.feed(1, at(100), "pass", [], [card("x", "goal", "full_screen", 99, dur=20)])
    assert long.feed(2, at(101), "pass", [], [card("y", "card", "full_screen", 40, dur=7)]) == []


def test_period_end_clears_transient_layers_and_ribbon_updates_once_a_minute():
    c = compiler()
    out = []
    for i, t in enumerate([10.0, 50.0, 70.0, 130.0]):
        out += c.feed(i, at(t), "pass", [], [], RibbonSample(5.0 * i, 20.0, 30.0))
    ribbons = [q for q in out if q.layer == "momentum_ribbon"]
    assert [q.op for q in ribbons] == ["show", "update", "update"] and ribbons[-1].ribbon.momentum == 15.0
    end = c.feed(9, at(2760), "period_end", [], [])
    assert end[0].op == "clear" and end[0].reason == "period_end" and "full_screen" in end[0].clears
    assert "scorebug" not in end[0].clears


def test_telestration_comes_from_the_replay_geometry():
    bo = {
        "shot_event_id": "s",
        "shooter_pos": {"x": 97.5, "y": 47.5},
        "teammate_pos": {"x": 94.0, "y": 31.5},
        "nearest_marker_m": 9.5,
        "defenders": [{"x": 99.6, "y": 44.6}],
        "keeper": {"x": 103.2, "y": 36.4},
    }
    drawing = telestration(bo, "NBR", "NBR")
    roles = [s.role for s in drawing.shapes]
    assert roles == ["shooter", "shot_taken", "pass_on", "open_player", "defender", "keeper"]
    assert drawing.shapes[1].points[1].x == 105.0  # home attacks x = 105
    assert telestration(bo, "HCY", "NBR").shapes[1].points[1].x == 0.0
    assert drawing.shapes[3].radius_m == 9.5
    run = {
        "run_event_id": "r",
        "carrier_pos": {"x": 60, "y": 36},
        "runner_path": [{"x": 78, "y": 31}, {"x": 84, "y": 30}],
        "target": {"x": 85, "y": 34},
        "defenders_at_pass": [{"x": 79, "y": 27}],
    }
    assert [s.role for s in telestration(run, "HCY", "NBR").shapes] == [
        "carrier",
        "runner_path",
        "through_ball",
        "target",
        "defender",
    ]
    assert telestration({"bogus": 1}, "NBR", "NBR") is None
    assert telestration({"shot_event_id": "s", "shooter_pos": {"x": "a"}}, "NBR", "NBR") is None


def test_cards_with_replays_get_a_telestration_cue():
    c = compiler()
    replay = {
        "run_event_id": "r",
        "carrier_pos": {"x": 60, "y": 36},
        "runner_path": [{"x": 78, "y": 31}],
        "target": {"x": 85, "y": 34},
        "defenders_at_pass": [],
    }
    side = card("unfound_run-1", "unfound_run", "side_panel", 80, dur=12).model_copy(
        update={"replay": replay}
    )
    out = c.feed(1, at(300), "run", [], [side])
    assert [(q.layer, q.op) for q in out] == [("side_panel", "show"), ("telestration", "show")]
    assert out[1].end.t_s == out[0].end.t_s == 312


def test_sheet_ids_name_the_audience():
    assert sheet_id("M", ViewerProfile()) == "M/casual/en"
    full = ViewerProfile(persona="fantasy", language="ar", favourite_team="HCY", focus_metric="xg")
    assert sheet_id("M", full) == "M/fantasy/ar/club=HCY/metric=xg"


def test_cue_model_refuses_unknown_fields():
    with pytest.raises(ValueError):
        Cue.model_validate(
            {
                "cue_id": "x",
                "seq": 1,
                "op": "show",
                "layer": "lower_third",
                "start": at(1).model_dump(),
                "priority": 1,
                "collision": "queue",
                "persona": "casual",
                "language": "en",
                "html": "<b>no</b>",
            }
        )
