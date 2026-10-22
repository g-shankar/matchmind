"""The demo match's VAR overturn, end to end: session, seek, reconnect, REST
cue sheet and the WebSocket CUES stream (bug-hunt items 1, 3 and 7)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import FakeClock
from matchmind.api.app import create_app
from matchmind.api.session import Engines, MatchSession, load_events
from matchmind.crew.contracts import MomentKind, ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.cues import Cue, active_cues
from matchmind.crew.llm import TemplateLLM
from matchmind.crew.translator import OffTranslator
from matchmind.schema import EventType
from matchmind.stats.state import StatsEngine


def template_crew(teams):
    return Crew(teams, llm=TemplateLLM(), translator=OffTranslator())


ENGINES = Engines(stats=StatsEngine, crew=template_crew, bookmark_crew=template_crew)


@pytest.fixture(scope="module")
def events():
    return load_events()


@pytest.fixture(scope="module")
def review(events):
    return next(e for e in events if e.type == EventType.VAR_REVIEW)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def demo(events, clock) -> MatchSession:
    return MatchSession(events, engines=ENGINES, clock=clock)


def goal_id(review) -> str:
    return f"goal-{review.reviewed_event_id}"


def play_to(session: MatchSession, clock: FakeClock, index: int):
    """Play straight through (stats only) until events[:index] are done."""
    ticks = []
    while session.next_index < index:
        clock.t += 0.05
        for tick in session.advance(with_crew=False):
            ticks.append(session.crew_tick(tick))
    return ticks


# ------------------------------------------------------------------- session


def test_bookmarks_mark_the_ruled_out_goal(demo, review):
    by_id = {b.moment_id: b for b in demo.bookmarks}
    assert by_id[goal_id(review)].ruled_out is True
    corr = by_id[f"correction-{review.event_id}"]
    assert corr.kind == MomentKind.CORRECTION and not corr.ruled_out
    assert sum(b.ruled_out for b in demo.bookmarks) == 1


def test_seek_past_the_overturn_never_shows_the_goal_as_live(demo, events, review):
    after = events.index(review) + 3
    demo.seek(events[after].clock_s, period=1)
    assert demo.score == (1, 0)
    assert goal_id(review) in demo.retracted_so_far()
    recent = [b.moment.moment_id for b in demo.recent_bundles()]
    assert goal_id(review) not in recent and f"correction-{review.event_id}" in recent
    cards = demo.cards_for(demo.recent_bundles(), ViewerProfile())
    assert goal_id(review) not in {c.moment_id for c in cards}
    state = demo.viewer_state(ViewerProfile())
    on_air = state.cue_active or []
    assert goal_id(review) not in {c.moment_id for c in on_air}
    bugs = [c for c in on_air if c.layer == "scorebug"]
    assert len(bugs) == 1 and (bugs[0].scorebug.score_home, bugs[0].scorebug.score_away) == (1, 0)
    assert goal_id(review) in state.ruled_out  # producer memory knows, so a late card is dropped
    recap = demo.recap(ViewerProfile())
    assert "Asante" not in str(recap.stats.get("goals_line", ""))
    assert all(k.moment_id != goal_id(review) for k in recap.key_moments)


def test_seek_between_goal_and_review_then_play_through_retracts_live(demo, clock, events, review):
    shot = next(e for e in events if e.event_id == review.reviewed_event_id)
    demo.seek(shot.clock_s + 1, period=1)
    assert demo.score == (2, 0)  # true at this moment: the review has not happened yet
    profile = ViewerProfile()
    state = demo.viewer_state(profile)
    ticks = play_to(demo, clock, events.index(review) + 1)
    cues: list[Cue] = []
    for tick in ticks:
        cards = demo.cards_for(tick.bundles, profile, state, tick)
        cues += demo.tick_cues(tick, cards, state)
    ops = [(c.op, c.layer) for c in cues if c.op != "update" or c.layer == "scorebug"]
    assert ("retract", "full_screen") in ops and ("supersede", "full_screen") in ops
    assert ("retract", "scorebug") in ops and ("update", "scorebug") in ops
    assert demo.score == (1, 0)
    # The live stream continued the compiled sheet: the same cues a fresh compile gives.
    compiled = demo.cue_sheet(profile, since_seq=0)["cues"]
    live = [c.model_dump(mode="json") for c in cues]
    assert compiled[-len(live) :] == live


def test_cue_sheet_is_deterministic_bounded_and_pages(demo, clock, events, review):
    play_to(demo, clock, events.index(review) + 50)
    profile = ViewerProfile(persona="tactical", language="ar")
    one = demo.cue_sheet(profile)
    assert json.dumps(one) == json.dumps(demo.cue_sheet(profile))  # idempotent read
    seqs = [c["seq"] for c in one["cues"]]
    assert seqs == list(range(1, len(seqs) + 1)) and one["last_seq"] == seqs[-1]
    assert one["sheet_id"] == "MM-DEMO-001/tactical/ar"
    assert all(c["rtl"] for c in one["cues"] if c["text"])
    page = demo.cue_sheet(profile, since_seq=10, limit=5)
    assert [c["seq"] for c in page["cues"]] == [11, 12, 13, 14, 15]
    assert page["has_more"] and page["next_since_seq"] == 15
    rest = demo.cue_sheet(profile, since_seq=one["last_seq"])
    assert rest["cues"] == [] and not rest["has_more"]
    # Jumping away and back gives byte-identical cues (no stale compile survives a seek).
    demo.seek(100, period=1)
    assert demo.cue_sheet(profile)["last_seq"] < one["last_seq"]
    demo.seek(events[events.index(review) + 50].clock_s, period=1)
    play_to(demo, clock, events.index(review) + 50)
    assert json.dumps(demo.cue_sheet(profile)["cues"]) == json.dumps(one["cues"])


def test_full_match_sheet_shape(demo, clock, events):
    play_to(demo, clock, len(events))
    sheet = demo.cue_sheet(ViewerProfile(), limit=500)
    cues = [Cue.model_validate(c) for c in sheet["cues"]]
    assert not sheet["has_more"] and len(cues) < 500
    ts = [c.start.t_s for c in cues]
    layers = {c.layer for c in cues}
    assert {"scorebug", "momentum_ribbon", "full_screen", "telestration", "all"} <= layers
    assert [c.op for c in cues if c.layer == "all"] == ["clear", "clear"]
    finals = [c for c in cues if c.layer == "scorebug"]
    assert (finals[-1].scorebug.score_home, finals[-1].scorebug.score_away) == (2, 3)
    assert (
        len([c for c in cues if c.op == "retract"]) == 2
        and len([c for c in cues if c.op == "supersede"]) == 1
    )
    # Ordered in time except for cues queued behind a busy layer.
    assert all(b >= a or c.collision == "queue" for a, b, c in zip(ts, ts[1:], cues[1:], strict=False))
    assert {c.start.period for c in cues} == {1, 2}
    second = [c for c in cues if c.start.period == 2]
    assert all(c.start.clock_s >= 2700 for c in second)
    assert active_cues(cues, ts[-1])  # something is on air at the final whistle


# ----------------------------------------------------------------------- API


@pytest.fixture
def api(demo, clock):
    app = create_app(session=demo, tick_interval=None, allowed_origins=[], clock=clock)
    with TestClient(app) as c:
        yield c


def pump(client, clock, seconds):
    clock.t += seconds
    client.portal.call(client.app.state.hub.pump)


def drain(ws, until: str):
    out = []
    while True:
        msg = ws.receive_json()
        out.append(msg)
        if msg["type"] == until:
            return out


def test_cue_sheet_route(api):
    r = api.get("/api/match/cue-sheet", params={"persona": "casual", "lang": "en"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    data = r.json()
    assert set(data) == {
        "schema_version",
        "match_id",
        "sheet_id",
        "persona",
        "language",
        "position",
        "last_seq",
        "since_seq",
        "has_more",
        "next_since_seq",
        "cues",
    }
    for bad in (
        {"persona": "boss"},
        {"since_seq": -1},
        {"limit": 501},
        {"lang": "xx"},
        {"favourite_team": "ZZZ"},
    ):
        assert api.get("/api/match/cue-sheet", params=bad).status_code == 400, bad


def test_ws_streams_cues_after_ticks_and_reconnect_after_the_overturn(api, clock, events, review):
    with api.websocket_connect("/ws/match") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "INITIAL_SNAPSHOT"
        sheet = snap["data"]["cue_sheet"]
        assert sheet["sheet_id"] == "MM-DEMO-001/casual/en" and sheet["last_seq"] == 0
        pump(api, clock, 2)
        msgs = []
        while len(msgs) < 6:
            msgs.append(ws.receive_json())
        types = [m["type"] for m in msgs]
        assert types[0] == "MATCH_TICK" and "CUES" in types
        cues = next(m for m in msgs if m["type"] == "CUES")["data"]
        assert cues["sheet_id"] == sheet["sheet_id"] and "active" not in cues
        assert cues["cues"][0]["seq"] == 1
        # Jump past the overturn: the snapshot is the new truth (bug-hunt item 3).
        clock.t += 1
        ws.send_json({"action": "seek", "clock_s": events[events.index(review) + 2].clock_s, "period": 1})
        snap = drain(ws, "INITIAL_SNAPSHOT")[-1]["data"]
        assert (snap["home_score"], snap["away_score"]) == (1, 0)
        assert goal_id(review) not in {c["moment_id"] for c in snap["recent_cards"]}
        active = snap["cue_sheet"]["active"]
        assert goal_id(review) not in {c["moment_id"] for c in active}
        assert [c["scorebug"]["score_home"] for c in active if c["layer"] == "scorebug"] == [1]
        ruled = [b for b in snap["bookmarks"] if b["ruled_out"]]
        assert [b["moment_id"] for b in ruled] == [goal_id(review)]
    # A brand new connection (reconnect) gets the same corrected picture.
    with api.websocket_connect("/ws/match") as ws2:
        again = ws2.receive_json()["data"]
        assert (again["home_score"], again["away_score"]) == (1, 0)
        assert again["cue_sheet"]["active"] == active
        # A profile change starts a new sheet: the next CUES carries what is on air.
        ws2.send_json({"action": "set_view", "persona": "fantasy"})
        drain(ws2, "PERSONA_CHANGED")
        pump(api, clock, 2)
        msg = drain(ws2, "CUES")[-1]["data"]
        assert msg["sheet_id"] == "MM-DEMO-001/fantasy/en" and "active" in msg
        assert goal_id(review) not in {c["moment_id"] for c in msg["active"]}


def test_event_payload_names_the_reviewed_goal(events, review):
    from matchmind.api.view import event_payload

    data = event_payload(review, None)
    assert data["reviewed_event_id"] == review.reviewed_event_id and data["review_reason"] == "offside"
    assert "reviewed_event_id" not in event_payload(events[0], None)  # other events keep their shape


def test_audit_shows_the_retraction_both_ways(demo, review):
    goal = demo.moment_audit(goal_id(review))
    assert goal is not None and goal.ruled_out_by == f"correction-{review.event_id}"
    corr = demo.moment_audit(f"correction-{review.event_id}")
    assert corr is not None and corr.retracts == [goal_id(review)] and corr.ruled_out_by is None
    assert corr.parity.ok, corr.parity.problems
    assert set(corr.parity.key_facts) >= {"score_home", "score_away"}
    assert all(r.claims for r in corr.renderings)  # the supersede card's sentences carry claims


def test_supersede_cards_carry_claims(demo, clock, events, review):
    play_to(demo, clock, events.index(review) + 1)
    sheet = demo.cue_sheet(ViewerProfile(), since_seq=0, limit=500)
    corr = next(c for c in sheet["cues"] if c["op"] == "supersede" and c["layer"] != "scorebug")
    card = demo.card_for_moment(corr["moment_id"], ViewerProfile())
    assert card is not None and card.retracts == [goal_id(review)] and card.claims
    assert {c.field for c in card.claims} >= {"headline", "body"}


def test_cue_text_carries_the_card_claims(demo, clock, events, review):
    play_to(demo, clock, events.index(review) + 1)
    cues = demo.cue_sheet(ViewerProfile(persona="tactical", language="es"), limit=500)["cues"]
    texted = [c for c in cues if c["text"]]
    assert texted and all(c["text"]["claims"] for c in texted)
    corr = next(c for c in texted if c["kind"] == "correction")
    assert {cl["field"] for cl in corr["text"]["claims"]} >= {"headline", "body"}
