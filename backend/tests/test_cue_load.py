"""Cue-sheet compile cost under load (security review round 2): incremental compiles,
a per-step budget for new audiences, a view-change rate limit, and no stale sheet when
a view change lands mid-step."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from conftest import FAKE_ENGINES, FakeClock
from matchmind.api import app as app_mod
from matchmind.api.app import Connection, Hub, create_app
from matchmind.api.session import MatchSession, load_events
from matchmind.crew.contracts import ViewerProfile
from matchmind.crew.producer import ViewerState


@pytest.fixture(scope="module")
def events():
    return load_events()


def session(events, clock=None) -> MatchSession:
    return MatchSession(events, engines=FAKE_ENGINES, clock=clock or FakeClock())


class FakeWS:
    async def send_text(self, text):
        pass

    async def close(self, code=1000):
        pass


def test_compile_grows_from_the_nearest_position_and_matches_a_fresh_compile(events):
    s = session(events)
    profile = ViewerProfile(persona="tactical", language="es")
    s._compile(profile, 800)
    fed = s.cue_events_fed
    grown = s._compile(profile, 1200)
    assert s.cue_events_fed - fed == 400  # only the new events, not 1,200 from kick-off
    fresh = session(events)._compile(profile, 1200)
    assert [c.model_dump() for c in grown.sheet] == [c.model_dump() for c in fresh.sheet]
    assert s.compile_cost(profile, 1200) == 0 and s.compile_cost(profile, 1300) == 100
    s.seek(events[500].clock_s, period=events[500].period)  # a seek keeps what was compiled
    assert s.compile_cost(profile, 1200) == 0


def _hub_with_viewers(s: MatchSession, n: int):
    hub = Hub(s)
    conns = []
    for _ in range(n):
        c = Connection(FakeWS(), time.monotonic)
        hub.connections.add(c)
        conns.append(c)
    return hub, conns


def test_many_new_views_before_one_step_stay_within_the_compile_budget(events):
    clock = FakeClock()
    s = session(events, clock)
    late = events[1500]
    s.seek(late.clock_s, period=late.period)
    hub, conns = _hub_with_viewers(s, 20)
    players = sorted(s._player_ids)

    async def go():
        for i, c in enumerate(conns):  # what _set_view does, 20 distinct audiences
            c.profile = c.profile.model_copy(update={"focus_player_id": players[i], "language": "fr"})
            c.view_state = ViewerState()
        fed = s.cue_events_fed
        clock.t += 0.05
        await hub.pump()
        first = s.cue_events_fed - fed
        assert 0 < first <= app_mod.COMPILE_BUDGET + 50  # one cold audience, not twenty
        waiting = sum(c.view_state.cues is None for c in conns)
        assert waiting >= 18
        steps = 1
        for _ in range(40):  # the rest get their sheets over the next steps
            clock.t += 0.05
            await hub.pump()
            steps += 1
            if all(c.view_state.cues is not None for c in conns):
                break
        assert all(c.view_state.cues is not None for c in conns), (steps, s.ended)
        assert {c.view_state.cues.sheet_id for c in conns} == {
            f"{s.match_id}/casual/fr/focus={p}" for p in players[:20]
        }

    asyncio.run(go())


def test_a_view_change_during_a_step_is_not_overwritten_with_the_old_sheet(events):
    clock = FakeClock()
    s = session(events, clock)
    hub, (conn,) = _hub_with_viewers(s, 1)

    async def go():
        await hub.send_snapshots([conn])
        orig = hub.run

        async def run(fn, *args):
            out = await orig(fn, *args)
            if getattr(fn, "__name__", "") == "advance":  # set_view lands while the step plays
                conn.profile = conn.profile.model_copy(update={"language": "fr", "persona": "tactical"})
                conn.view_state = ViewerState()
            return out

        hub.run = run
        clock.t += 30
        await hub.pump()
        hub.run = orig
        for _ in range(3):
            clock.t += 30
            await hub.pump()
        assert conn.view_state.cues is not None
        assert conn.view_state.cues.sheet_id == f"{s.match_id}/tactical/fr"

    asyncio.run(go())


def test_set_view_is_rate_limited_per_connection(events):
    clock = FakeClock()
    app = create_app(session=session(events, clock), tick_interval=None, allowed_origins=[], clock=clock)
    with TestClient(app) as client, client.websocket_connect("/ws/match") as ws:
        ws.receive_json()  # snapshot
        errors = 0
        for lang in ["fr", "es", "ar", "ja", "en"]:
            ws.send_json({"action": "set_view", "language": lang})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "ERROR":
                    errors += 1
                    assert "too fast" in msg["data"]["message"]
                    break
                if msg["type"] == "PERSONA_CHANGED":
                    break
        assert errors == 2  # a burst of three goes through, then about one a second
        clock.t += 1.1
        ws.send_json({"action": "set_view", "language": "es"})
        assert ws.receive_json()["type"] == "PROFILE_CHANGED"
