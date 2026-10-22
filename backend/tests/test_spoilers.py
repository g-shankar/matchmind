"""Spoiler-safe catch-up (docs/PERSONALISATION.md): a viewer with `spoilers: false`
never receives the score, a goal, a VAR outcome or anything that gives them away,
on any surface, until they reveal. Then everything comes back at once.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import FAKE_ENGINES, FakeClock, make_events
from matchmind.api import session as session_mod
from matchmind.api.app import create_app
from matchmind.api.session import MatchSession, load_events
from matchmind.crew.contracts import STUDIO_LANGUAGES, ViewerProfile
from matchmind.crew.spoilers import SPOILER_FACT_KEYS, SPOILER_KINDS

ALLOWED = "http://localhost:5173"
SCORE_KEYS = {"score_home", "score_away", "home_score", "away_score", "goals", "assists"}
SCORELINE = re.compile(r"\b\d+\s?[-–]\s?\d+\b")


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
