"""Spoiler-safe catch-up (docs/PERSONALISATION.md): a viewer with `spoilers: false`
never receives the score, a goal, a VAR outcome or anything that gives them away,
on any surface, until they reveal. Then everything comes back at once.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import FAKE_ENGINES, FakeClock, make_events
from matchmind.api import session as session_mod
from matchmind.api import view as view_mod
from matchmind.api.app import create_app
from matchmind.api.session import MatchSession, load_events
from matchmind.crew.contracts import STUDIO_LANGUAGES, ViewerProfile
from matchmind.crew.spoilers import CATCHUP_ID_PREFIX, SPOILER_FACT_KEYS, SPOILER_KINDS, is_withheld_event

ALLOWED = "http://localhost:5173"
SCORE_KEYS = {"score_home", "score_away", "home_score", "away_score", "goals", "assists"}
SCORELINE = re.compile(r"\b\d+\s?[-–]\s?\d+\b")
EVENT_ID_KEYS = {"event_id", "source_event_id", "shot_event_id", "run_event_id"}
GOAL_POSTS_Y = (30.34, 37.66)  # the goal mouth on a 68 m wide pitch


def in_goal_mouth(point: Any) -> bool:
    if not isinstance(point, dict):
        return False
    x, y = point.get("x"), point.get("y")
    return x is not None and (x <= 0.5 or x >= 104.5) and GOAL_POSTS_Y[0] <= y <= GOAL_POSTS_Y[1]


def leaks(payload: Any, path: str = "") -> list[str]:
    """Every place a spoiler-free payload still carries the result."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if key in SCORE_KEYS and value is not None:
                found.append(f"{here}={value!r}")
            if key == "kind" and value in SPOILER_KINDS:
                found.append(f"{here}={value}")
            if key == "outcome" and value in ("goal", "overturned", "stands"):
                found.append(f"{here}={value}")
            if key in ("retracts", "reviewed_event_id") and value:
                found.append(f"{here}={value!r}")
            if key == "ruled_out" and value:
                found.append(here)
            if key == "scorebug" and value:
                found.append(here)
            # A VAR review in this engine always reviews a goal: the event itself is the spoiler.
            if key == "type" and value == "var_review":
                found.append(f"{here}={value}")
            if key == "review_reason" and value is not None:
                found.append(f"{here}={value!r}")
            # Outcome geometry: where a shot ended says whether it went in.
            if key == "end" and payload.get("type") == "shot" and value is not None:
                found.append(f"{here}={value!r}" + (" (goal mouth)" if in_goal_mouth(value) else ""))
            # Full-feed numbering: a withheld event would leave a gap in seq and in the ids.
            if key == "seq" and "event_id" in payload and value is not None:
                found.append(f"{here}={value!r}")
            if key in EVENT_ID_KEYS and isinstance(value, str) and not value.startswith(CATCHUP_ID_PREFIX):
                found.append(f"{here}={value!r}")
            if key in ("source_event_ids",) and any(not str(v).startswith(CATCHUP_ID_PREFIX) for v in value):
                found.append(f"{here}={value!r}")
            if key == "details" and isinstance(value, dict):
                if "blocked_by" in value:
                    found.append(f"{here}.blocked_by")
                if value.get("pass_type") == "kickoff":  # a restart from the centre spot follows a goal
                    found.append(f"{here}.pass_type=kickoff")
            if (
                key in ("fact_keys", "label_key")
                and set(value if isinstance(value, list) else [value]) & SPOILER_FACT_KEYS
            ):
                found.append(f"{here}={value!r}")
            if key in (
                "headline",
                "body",
                "title",
                "answer",
                "summary_paragraphs",
                "sentence",
            ) and SCORELINE.search(str(value)):
                found.append(f"{here}={value!r}")
            found += leaks(value, here)
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            found += leaks(item, f"{path}[{i}]")
    return found


def recv_all(ws, until: str) -> list[dict]:
    out = []
    while True:
        msg = ws.receive_json()
        out.append(msg)
        if msg["type"] == until:
            return out


# --- Fake match: the transport contract -------------------------------------------------------


@pytest.fixture
def fake():
    clock = FakeClock()
    session = MatchSession(make_events(), engines=FAKE_ENGINES, clock=clock, base_rate=10)
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as c:
        yield c, clock


def test_catch_up_hides_the_result_on_the_websocket_and_reveal_brings_it_back(fake):
    client, clock = fake
    with client.websocket_connect("/ws/match") as ws:
        assert ws.receive_json()["type"] == "INITIAL_SNAPSHOT"
        ws.send_json({"action": "set_view", "spoilers": False})
        msgs = recv_all(ws, "INITIAL_SNAPSHOT")
        assert [m["type"] for m in msgs] == ["PROFILE_CHANGED", "PERSONA_CHANGED", "INITIAL_SNAPSHOT"]
        assert msgs[0]["data"]["spoilers"] is False
        snap = msgs[-1]["data"]
        assert (
            snap["home_score"] is None and snap["state"]["score_home"] is None and snap["cue_sheet"] is None
        )
        assert not leaks(snap)
        clock.t += 1000
        client.portal.call(client.app.state.hub.pump)
        msgs = recv_all(ws, "PLAYBACK_CONTROL")
        ticks = [m for m in msgs if m["type"] == "MATCH_TICK"]
        assert len(ticks) == len(make_events()) and all(t["data"]["score"] is None for t in ticks)
        assert not [m for m in msgs if m["type"] == "CUES"]  # the cue sheet carries the scorebug
        assert not leaks([m for m in msgs if m["type"] != "MATCH_END"])  # the fake crew's recap is not real
        # Reveal: one fresh snapshot with the real score.
        ws.send_json({"action": "set_view", "spoilers": True})
        snap = recv_all(ws, "INITIAL_SNAPSHOT")[-1]["data"]
        assert (snap["home_score"], snap["away_score"]) == (1, 1)
        assert any(c["kind"] == "goal" for c in snap["recent_cards"]) and snap["cue_sheet"] is not None


def test_spoiler_free_events_hide_outcomes_and_scores(fake):
    client, clock = fake
    with client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "set_view", "spoilers": False})
        recv_all(ws, "INITIAL_SNAPSHOT")
        clock.t += 1000
        client.portal.call(client.app.state.hub.pump)
        ticks = [m["data"] for m in recv_all(ws, "PLAYBACK_CONTROL") if m["type"] == "MATCH_TICK"]
    shots = [t["event"] for t in ticks if t["event"]["type"] == "shot"]
    assert shots and all(e["outcome"] is None for e in shots)
    assert all(not {"score_home", "score_away"} & set(t["event"]["details"]) for t in ticks)


def test_rest_snapshot_and_recap_take_the_flag(fake):
    client, clock = fake
    client.post("/api/match/seek", json={"clock_s": 2850, "period": 2})
    snap = client.get("/api/match/snapshot?spoilers=false").json()
    assert snap["home_score"] is None and not leaks(snap)
    assert client.get("/api/match/snapshot").json()["home_score"] == 1
    assert client.get("/api/match/snapshot?spoilers=nope").status_code == 400


def test_bad_spoilers_value_is_refused_on_the_websocket(fake):
    client, _ = fake
    with client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "set_view", "spoilers": "maybe"})
        assert ws.receive_json()["type"] == "ERROR"


# --- The real demo match: every surface, every studio language --------------------------------


@pytest.fixture(scope="module")
def real():
    clock = FakeClock()
    session = MatchSession(load_events(), engines=session_mod.real_engines(), clock=clock)
    return session, clock


def test_story_so_far_has_no_result_in_any_studio_language(real):
    session, _ = real
    for clock_s, period in ((34 * 60, 1), (70 * 60, 2), (95 * 60, 2)):
        session.seek(clock_s, period)
        for lang in (*STUDIO_LANGUAGES, "pt"):
            for persona in ("casual", "tactical", "fantasy"):
                recap = session.recap(ViewerProfile(language=lang, persona=persona, spoilers=False))
                assert recap.spoiler_free and recap.fact_check.ok, (lang, recap.fact_check.reasons)
                assert recap.player_of_the_match is None
                assert not set(recap.stats) & SPOILER_FACT_KEYS
                assert not leaks(recap.model_dump(mode="json")), (lang, persona)
                assert {m.kind for m in recap.key_moments}.isdisjoint(SPOILER_KINDS)


def test_full_match_through_the_websocket_never_leaks(real):
    session, clock = real
    session.reset()
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client, client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "set_view", "spoilers": False, "language": "es", "favourite_team": "HCY"})
        recv_all(ws, "INITIAL_SNAPSHOT")
        seen: list[dict] = []
        for _ in range(200):
            clock.t += 30
            client.portal.call(client.app.state.hub.pump)
            if session.ended:
                break
        seen = recv_all(ws, "MATCH_END")
    assert sum(m["type"] == "MATCH_TICK" for m in seen) > 2000
    problems = leaks(seen)
    assert not problems, problems[:10]
    recap = seen[-1]["data"]["recap"]
    assert recap["spoiler_free"] is True and recap["language"] == "es"


def test_scrub_event_hides_outcome_geometry():
    from matchmind.crew.spoilers import is_withheld_event, scrub_event

    goal = {
        "type": "shot",
        "event_id": "M-00411",
        "seq": 411,
        "start": {"x": 93.2, "y": 35.6},
        "end": {"x": 105.0, "y": 34.4},
        "outcome": "goal",
        "details": {"score_home": 1, "assist_id": "NBR-7"},
    }
    blocked = {
        **goal,
        "end": {"x": 96.0, "y": 30.0},
        "outcome": "blocked",
        "details": {"blocked_by": "HCY-4"},
    }
    for shot in (goal, blocked):
        out = scrub_event(shot)
        assert out["end"] is None and out["outcome"] is None and out["details"] == {}
        assert out["start"] == shot["start"]  # where it was taken from stays: that is the chance
    kickoff = {
        "type": "pass",
        "event_id": "M-00412",
        "seq": 412,
        "start": {"x": 52.5, "y": 34.0},
        "end": {"x": 61.0, "y": 30.1},
        "outcome": "complete",
        "details": {"pass_type": "kickoff"},
    }
    # Every restart after the first whistle follows a goal: the kick-off is withheld, not
    # scrubbed (a scrubbed one was the only pass without a start point).
    assert is_withheld_event(kickoff)
    assert not is_withheld_event({**kickoff, "details": {"pass_type": "ground"}})
    review = {
        "type": "var_review",
        "outcome": "overturned",
        "reviewed_event_id": "E-1",
        "review_reason": "offside",
    }
    assert is_withheld_event(review)
    out = scrub_event({**review, "event_id": "M-00413", "seq": 413})
    assert out["review_reason"] is None and out["reviewed_event_id"] is None and out["outcome"] is None
    assert not leaks({"event": scrub_event(goal)}) and not leaks({"event": scrub_event(blocked)})


def test_full_match_catch_up_has_no_var_review_and_no_shot_end(real):
    """Every shot in the demo ends inside the goal mouth iff it went in, so `end` must go."""
    session, clock = real
    session.reset()
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client, client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "set_view", "spoilers": False})
        recv_all(ws, "INITIAL_SNAPSHOT")
        for _ in range(400):
            clock.t += 30
            client.portal.call(client.app.state.hub.pump)
            if session.ended:
                break
        seen = recv_all(ws, "MATCH_END")
    events = [m["data"]["event"] for m in seen if m["type"] == "MATCH_TICK"]
    shots = [e for e in events if e["type"] == "shot"]
    assert len(shots) > 20 and all(e["end"] is None and e["outcome"] is None for e in shots)
    assert not any(in_goal_mouth(e["end"]) for e in shots)
    assert not [e for e in events if e["type"] == "var_review"]
    assert not [e for e in events if e["details"].get("pass_type") == "kickoff"]


def test_basic_stats_take_the_flag(real):
    """The Lab's counting stats carry goals per team and player: none in catch-up mode."""
    session, clock = real
    session.reset()
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client:
        client.post("/api/match/seek", json={"clock_s": 85 * 60, "period": 2})
        full = client.get("/api/match/stats/basic").json()
        assert sum(t["goals"] for t in full["teams"].values()) >= 4
        free = client.get("/api/match/stats/basic?spoilers=false").json()
        assert client.get("/api/match/stats/basic?spoilers=nope").status_code == 400
    assert len(free["teams"]) == 2 and all(t["goals"] is None for t in free["teams"].values())
    assert free["players"] and all(p["goals"] is None for p in free["players"])
    assert not leaks(free)
    # Everything else tells the same story.
    assert [t["shots"] for t in free["teams"].values()] == [t["shots"] for t in full["teams"].values()]


def test_catch_up_snapshot_recent_events_hide_the_var_review_and_shot_ends(real):
    session, clock = real
    session.reset()
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client:
        client.post("/api/match/seek", json={"clock_s": 40 * 60 + 30, "period": 1})
        with client.websocket_connect("/ws/match") as ws:
            full = ws.receive_json()["data"]["recent_events"]
            ws.send_json({"action": "set_view", "spoilers": False})
            free = recv_all(ws, "INITIAL_SNAPSHOT")[-1]["data"]["recent_events"]
    assert any(e["type"] == "var_review" for e in full)  # the jump lands just after the review
    assert free and not any(e["type"] == "var_review" for e in free)
    assert all(e["end"] is None for e in free if e["type"] == "shot")
    assert not leaks({"recent_events": free})


# --- Catch-up inference: nothing in the stream marks a goal by itself ---------------------------

# Fields unique to each event, so trivially "separating": they say nothing about outcomes.
IDENTITY_FIELDS = {"event_id", "match_clock", "clock_s", "player_id", "receiver_id"}


def _flat(payload: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, dict) and value:
            out.update(_flat(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def separating_fields(goals: list[dict], others: list[dict]) -> list[str]:
    """Fields one rule on a single value tells goals from other shots with: a number
    with every goal above (or below) every other shot, or a value no other shot has."""
    found = []
    flat_g, flat_o = [_flat(e) for e in goals], [_flat(e) for e in others]
    for key in sorted({k for e in flat_g + flat_o for k in e} - IDENTITY_FIELDS):
        g = [e.get(key) for e in flat_g]
        o = [e.get(key) for e in flat_o]
        nums = [v for v in g + o if isinstance(v, int | float) and not isinstance(v, bool)]
        if len(nums) == len(g + o):
            if min(g) > max(o) or max(g) < min(o):
                found.append(key)
        elif not {repr(v) for v in g} & {repr(v) for v in o}:
            found.append(key)
    return found


def test_catch_up_stream_has_no_goal_marker(real):
    """Replay the whole demo as a catch-up viewer and try to tell the goals apart."""
    session, clock = real
    session.reset()
    goal_ids = {e.event_id for e in session.events if str(e.type) == "shot" and str(e.outcome) == "goal"}
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client, client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "set_view", "spoilers": False})
        recv_all(ws, "INITIAL_SNAPSHOT")
        for _ in range(400):
            clock.t += 30
            client.portal.call(client.app.state.hub.pump)
            if session.ended:
                break
        seen = recv_all(ws, "MATCH_END")
    events = [m["data"]["event"] for m in seen if m["type"] == "MATCH_TICK"]
    # No pass is shaped differently from the others (kick-offs were the only ones without a start).
    passes = [e for e in events if e["type"] == "pass"]
    assert passes and all(e["start"] is not None and e["details"].get("pass_type") for e in passes)
    assert not [e for e in passes if e["details"]["pass_type"] == "kickoff"]
    # No numbering to find gaps in: no seq, and unordered, unique ids.
    assert all(e["seq"] is None for e in events)
    ids = [e["event_id"] for e in events]
    assert len(set(ids)) == len(ids) and all(i.startswith(CATCHUP_ID_PREFIX) for i in ids)
    assert not {e.event_id for e in session.events} & set(ids)
    assert ids != sorted(ids)
    # Shots: no single field of the shot itself separates the goals.
    from matchmind.crew.spoilers import catchup_event_id

    goals_free = {catchup_event_id(g) for g in goal_ids}
    shots = [e for e in events if e["type"] == "shot"]
    goals = [e for e in shots if e["event_id"] in goals_free]
    others = [e for e in shots if e["event_id"] not in goals_free]
    assert len(goals) == len(goal_ids) >= 5 and len(others) > 20
    assert separating_fields(goals, others) == []
    # Known and documented (docs/THREAT-MODEL.md): the clock gap after a goal and where play
    # restarts still let someone reading the raw feed infer it. The screen shows neither.


def test_catch_up_cards_and_answers_use_catch_up_event_ids(real):
    session, clock = real
    session.reset()
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client:
        client.post("/api/match/seek", json={"clock_s": 70 * 60, "period": 2})
        snap = client.get("/api/match/snapshot?spoilers=false").json()
        full = client.get("/api/match/snapshot").json()
        answer = client.post("/api/ask", json={"chip": "better_option", "spoilers": False}).json()
        answer_full = client.post("/api/ask", json={"chip": "better_option"}).json()
    raw_sources = [
        e["source_event_id"] for c in full["recent_cards"] for e in c["evidence"] if e["source_event_id"]
    ]
    assert raw_sources, "the check needs cards with event evidence"
    assert not leaks(snap), leaks(snap)[:5]
    assert answer_full["source_event_ids"] and answer["source_event_ids"]
    assert not leaks(answer), leaks(answer)[:5]


# --- Catch-up from the first frame: the WebSocket URL carries the choice -------------------------


def test_catch_up_on_the_websocket_url_means_the_first_snapshot_never_has_the_score(fake):
    client, clock = fake
    client.post("/api/match/seek", json={"clock_s": 2850, "period": 2})
    with client.websocket_connect("/ws/match?spoilers=0&persona=tactical&lang=es") as ws:
        first = ws.receive_json()
    assert first["type"] == "INITIAL_SNAPSHOT"
    snap = first["data"]
    assert snap["home_score"] is None and snap["profile"]["spoilers"] is False and not leaks(snap)
    assert (snap["profile"]["persona"], snap["profile"]["language"]) == ("tactical", "es")
    # Without it, the default is unchanged: the full picture.
    with client.websocket_connect("/ws/match?spoilers=1") as ws:
        assert ws.receive_json()["data"]["home_score"] == 1
    with client.websocket_connect("/ws/match") as ws:
        assert ws.receive_json()["data"]["home_score"] == 1


@pytest.mark.parametrize(
    "query", ["spoilers=maybe", "spoilers=", "persona=boss", "lang=xx", "spoilers=0&spoilers=1"]
)
def test_bad_view_on_the_websocket_url_is_refused(fake, query):
    from starlette.websockets import WebSocketDisconnect

    client, _ = fake
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/ws/match?{query}") as ws:
        ws.receive_json()


# --- Moment and card ids: no full-feed numbering either (security review round 5) --------------

FEED_NUMBER = re.compile(r"MM-[A-Z0-9-]+-\d{5}")


def _ids(payload: Any, key: str) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k == key and isinstance(v, str):
                found.append(v)
            found += _ids(v, key)
    elif isinstance(payload, list):
        for v in payload:
            found += _ids(v, key)
    return found


def anchor_gaps(seen: list[dict], full_ids: list[str]) -> list[tuple[int, int, int]]:
    """The reviewer's classifier: any full-feed event number visible on a card anchors the
    card's tick to the full feed; between two anchors, fewer catch-up ticks than feed events
    means something was withheld there (a goal's kick-off, a VAR review)."""
    number = {eid: i for i, eid in enumerate(full_ids)}
    ticks = [m for m in seen if m["type"] == "MATCH_TICK"]
    anchors: dict[int, int] = {}
    for i, m in enumerate(ticks):
        for raw in FEED_NUMBER.findall(json.dumps(m["data"].get("cards", []))):
            if raw in number:
                anchors.setdefault(number[raw], i)
    pairs = sorted(anchors.items())
    steps = zip(pairs, pairs[1:], strict=False)
    return [(n1, n2, (n2 - n1) - (i2 - i1)) for (n1, i1), (n2, i2) in steps if n2 - n1 > i2 - i1]


def test_catch_up_stream_has_no_feed_numbering_in_moment_or_card_ids(real):
    from matchmind.crew.spoilers import CATCHUP_CARD_PREFIX, CATCHUP_MOMENT_PREFIX

    session, clock = real
    session.reset()
    full_ids = [e.event_id for e in session.events]
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client, client.websocket_connect("/ws/match?spoilers=0") as ws:
        seen = recv_all(ws, "INITIAL_SNAPSHOT")
        for _ in range(400):
            clock.t += 30
            client.portal.call(client.app.state.hub.pump)
            if session.ended:
                break
        seen += recv_all(ws, "MATCH_END")
        client.post("/api/match/seek", json={"clock_s": 75 * 60, "period": 2})
        seen += recv_all(ws, "INITIAL_SNAPSHOT")  # bookmarks, recent cards and events
    ticks = [m for m in seen if m["type"] == "MATCH_TICK"]
    assert len(ticks) > 2000 and sum(len(m["data"]["cards"]) for m in ticks) > 30
    text = json.dumps(seen)
    assert not FEED_NUMBER.findall(text), FEED_NUMBER.findall(text)[:5]
    moment_ids = _ids(seen, "moment_id")
    card_ids = _ids(seen, "card_id")
    assert moment_ids and all(m.startswith(CATCHUP_MOMENT_PREFIX) for m in moment_ids)
    assert card_ids and all(c.startswith(CATCHUP_CARD_PREFIX) for c in card_ids)
    assert anchor_gaps(seen, full_ids) == []
    snap = seen[-1]["data"]
    marks = snap["bookmarks"]
    assert marks and all(b["moment_id"].startswith(CATCHUP_MOMENT_PREFIX) for b in marks)
    recap = next(m for m in seen if m["type"] == "MATCH_END")["data"]["recap"]
    assert recap["key_moments"] and all(
        m["moment_id"].startswith(CATCHUP_MOMENT_PREFIX) for m in recap["key_moments"]
    )


def test_anchor_gap_classifier_finds_the_gaps_in_full_feed_ids():
    """The classifier itself works: raw ids on cards, with ticks withheld, show the gaps."""
    full = [f"MM-DEMO-001-{i:05d}" for i in range(1, 11)]
    kept = [1, 2, 3, 6, 7, 8, 9, 10]  # 4 and 5 withheld
    seen = [
        {"type": "MATCH_TICK", "data": {"cards": [{"moment_id": f"pressure_wave-MM-DEMO-001-{n:05d}"}]}}
        for n in kept
    ]
    assert anchor_gaps(seen, full) == [(2, 5, 2)]


def test_catch_up_ids_look_up_moments_cards_audits_and_answers(real):
    from matchmind.api import reads
    from matchmind.crew.spoilers import CATCHUP_MOMENT_PREFIX, catchup_moment_id, is_spoiler_moment

    session, clock = real
    session.reset()
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with TestClient(app) as client:

        def get(url: str):
            clock.t += 5  # stay under the per-IP read limit
            return client.get(url)

        client.post("/api/match/seek", json={"clock_s": 80 * 60, "period": 2})
        snap = client.get("/api/match/snapshot?spoilers=false").json()
        full = client.get("/api/match/snapshot").json()
        opaque = [b["moment_id"] for b in snap["bookmarks"]]
        assert opaque and all(i.startswith(CATCHUP_MOMENT_PREFIX) for i in opaque)
        raw = {catchup_moment_id(b["moment_id"]): b["moment_id"] for b in full["bookmarks"]}
        for mid in opaque[:6]:
            card = get(f"/api/match/moment/{mid}?lang=es")
            assert card.status_code == 200, mid
            body = card.json()
            assert body["moment_id"] == mid and body["card_id"].startswith("cd-")
            assert not FEED_NUMBER.search(json.dumps(body)) and not leaks(body)
            audit = get(f"/api/match/moment/{mid}/audit")
            assert audit.status_code == 200, mid
            assert audit.json()["moment_id"] == mid and not FEED_NUMBER.search(audit.text)
            detail = client.portal.call(reads.moment_detail, client.app.state.hub, mid)  # MCP get_moment
            assert detail["moment"]["moment_id"] == mid and not FEED_NUMBER.search(json.dumps(detail))
            # The full id still answers in full ids.
            assert get(f"/api/match/moment/{raw[mid]}").json()["moment_id"] == raw[mid]
        # A catch-up id that names nothing, or a goal, is "not found".
        assert get("/api/match/moment/mo-0000000000000000").status_code == 404
        assert get("/api/match/moment/mo-0000000000000000/audit").status_code == 404
        goal = next(b for b in full["bookmarks"] if is_spoiler_moment(session.bundle(b["moment_id"]).moment))
        assert get(f"/api/match/moment/{catchup_moment_id(goal['moment_id'])}").status_code == 404
        assert get(f"/api/match/moment/{catchup_moment_id(goal['moment_id'])}/audit").status_code == 404
        recap = get("/api/match/recap?spoilers=false").json()
        assert recap["key_moments"] and not FEED_NUMBER.search(json.dumps(recap))
        for m in recap["key_moments"]:
            assert get(f"/api/match/moment/{m['moment_id']}").status_code == 200
        answer = client.post("/api/ask", json={"chip": "better_option", "spoilers": False}).json()
        assert answer["moment_ids"] and not FEED_NUMBER.search(json.dumps(answer))
        assert all(get(f"/api/match/moment/{m}").status_code == 200 for m in answer["moment_ids"])


def test_catch_up_viewer_pumped_tick_by_tick_gets_every_card(real):
    """A withheld tick (kick-off, VAR review) that ends a playback step keeps its cards for the
    next tick, even when that tick is played in a later step (security review round 5)."""
    from matchmind.crew.spoilers import catchup_card_id

    session, clock = real
    session.reset()
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED], clock=clock)
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/match") as full_ws,
        client.websocket_connect("/ws/match?spoilers=0") as free_ws,
    ):
        full_ws.receive_json()
        free_ws.receive_json()
        steps = 0
        while not session.ended and steps < 20_000:
            clock.t += 1  # about one event per step at 1x
            client.portal.call(client.app.state.hub.pump)
            steps += 1
        full = recv_all(full_ws, "MATCH_END")
        free = recv_all(free_ws, "MATCH_END")
    assert session.ended
    full_ticks = [m["data"] for m in full if m["type"] == "MATCH_TICK"]
    withheld = [t for t in full_ticks if is_withheld_event(t["event"])]
    assert len(withheld) >= 6  # kick-offs after goals and VAR reviews
    expected = {
        catchup_card_id(c["card_id"])
        for t in full_ticks
        for c in t["cards"]
        if not view_mod._is_spoiler_card(session, c)
    }
    got = {c["card_id"] for m in free if m["type"] == "MATCH_TICK" for c in m["data"]["cards"]}
    assert expected, "the check needs cards"
    assert expected - got == set(), sorted(expected - got)[:5]


@pytest.mark.parametrize("jump", ["seek", "reset", "set_view"])
def test_held_catch_up_cards_are_dropped_on_a_jump_or_a_new_view(fake, jump):
    client, clock = fake
    hub = client.app.state.hub
    with client.websocket_connect("/ws/match?spoilers=0") as ws:
        ws.receive_json()
        (conn,) = list(hub.connections)
        conn.view_state.held_cards = [{"card_id": "cd-held"}]
        if jump == "seek":
            client.post("/api/match/seek", json={"clock_s": 600, "period": 1})
            recv_all(ws, "INITIAL_SNAPSHOT")
        elif jump == "reset":
            assert client.post("/api/match/reset", json={}, headers={"origin": ALLOWED}).status_code == 200
            recv_all(ws, "INITIAL_SNAPSHOT")
        else:
            ws.send_json({"action": "set_view", "persona": "tactical"})
            recv_all(ws, "PERSONA_CHANGED")
        assert conn.view_state.held_cards == []
        clock.t += 1000
        client.portal.call(hub.pump)
        seen = recv_all(ws, "PLAYBACK_CONTROL")
    assert "cd-held" not in json.dumps(seen)
