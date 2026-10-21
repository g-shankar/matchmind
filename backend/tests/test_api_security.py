"""API fixes from the security review: jump throttle, POST limits, send queue,
connection caps and model calls kept off the playback lock."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import FakeClock, FakeCrew, FakeStats, make_events
from matchmind.api import app as app_mod
from matchmind.api.app import Connection, Hub, create_app
from matchmind.api.session import Engines, MatchSession

ALLOWED = "http://localhost:5173"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def session(clock) -> MatchSession:
    return MatchSession(
        make_events(), engines=Engines(stats=FakeStats, crew=FakeCrew), clock=clock, base_rate=10
    )


@pytest.fixture
def client(session, clock, tmp_path):
    app = create_app(
        session=session,
        tick_interval=None,
        allowed_origins=[ALLOWED],
        static_dir=tmp_path / "none",
        clock=clock,
    )
    with TestClient(app) as c:
        yield c


def pump(client: TestClient, clock: FakeClock, seconds: float) -> None:
    clock.t += seconds
    client.portal.call(client.app.state.hub.pump)


# --- seek / reset throttle ---------------------------------------------------------------------


def test_ws_seek_burst_runs_once_and_playback_goes_on(client, clock):
    with client.websocket_connect("/ws/match") as ws:
        assert ws.receive_json()["type"] == "INITIAL_SNAPSHOT"
        for _ in range(50):
            ws.send_json({"action": "seek", "clock_s": 30})
        replies = [ws.receive_json() for _ in range(50)]
        snapshots = [r for r in replies if r["type"] == "INITIAL_SNAPSHOT"]
        errors = [r["data"]["message"] for r in replies if r["type"] == "ERROR"]
        assert len(snapshots) == 1 and len(errors) == 49
        assert app_mod.TOO_FAST in errors
        pump(client, clock, 1)
        tick = ws.receive_json()
        assert tick["type"] == "MATCH_TICK" and tick["data"]["event"]["clock_s"] == 60


def test_rest_seek_burst_gets_429_and_shares_the_throttle_with_ws(client, clock):
    codes = [client.post("/api/match/seek", json={"clock_s": 30}).status_code for _ in range(50)]
    assert codes.count(200) == 1 and codes.count(429) == 49
    assert client.post("/api/match/reset").status_code == 429  # same window, other route
    with client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "reset"})
        assert ws.receive_json() == {"type": "ERROR", "data": {"message": app_mod.TOO_FAST}}
    clock.t += app_mod.JUMP_INTERVAL_S
    assert client.post("/api/match/reset").status_code == 200


def test_post_routes_are_limited_per_ip(client, clock):
    codes = [client.post("/api/match/speed", json={"speed_multiplier": 10}).status_code for _ in range(15)]
    assert codes[: app_mod.POST_BURST] == [200] * app_mod.POST_BURST
    assert set(codes[app_mod.POST_BURST :]) == {429}
    r = client.post("/api/match/speed", json={"speed_multiplier": 10})
    assert r.json() == {"detail": app_mod.TOO_MANY}
    assert client.get("/api/match/players").status_code == 200  # reads are not limited
    clock.t += 1
    assert client.post("/api/match/speed", json={"speed_multiplier": 10}).status_code == 200


@pytest.mark.parametrize(
    "path", ["/api/match/moment/goal-MM-TEST-001-00007?lang=pt", "/api/match/recap?lang=pt"]
)
def test_routes_that_can_call_the_translator_are_limited_per_ip(client, clock, path):
    # Moments and recaps in a world language may spend Translator characters: an
    # anonymous caller must not be able to drain the budget by looping on them.
    codes = [client.get(path).status_code for _ in range(app_mod.GET_BURST + 5)]
    assert codes[: app_mod.GET_BURST] == [200] * app_mod.GET_BURST
    assert set(codes[app_mod.GET_BURST :]) == {429}
    assert client.get(path).json() == {"detail": app_mod.TOO_MANY}
    assert client.post("/api/match/speed", json={"speed_multiplier": 10}).status_code == 200  # own bucket
    clock.t += 1
    assert client.get(path).status_code == 200


def test_spoofed_forwarded_for_does_not_buy_a_fresh_bucket(client, clock, monkeypatch):
    # Behind the ingress the real caller is the last X-Forwarded-For entry; a caller
    # rotating the entries to its left must still share one bucket.
    monkeypatch.setattr(app_mod, "TRUST_FORWARDED_FOR", True)
    codes = [
        client.get(
            "/api/match/recap?lang=pt", headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"}
        ).status_code
        for i in range(app_mod.GET_BURST + 10)
    ]
    assert codes[: app_mod.GET_BURST] == [200] * app_mod.GET_BURST
    assert set(codes[app_mod.GET_BURST :]) == {429}
    other = client.get("/api/match/recap?lang=pt", headers={"X-Forwarded-For": "203.0.113.10"})
    assert other.status_code == 200  # a different real caller has its own bucket


def test_world_language_recap_is_translated_without_the_crew_lock(client):
    hub = client.app.state.hub
    seen: list[bool] = []
    crew = hub.session.crew
    original = crew.translate_recap

    def watch(*args, **kwargs):
        seen.append(hub._crew_lock.locked())
        return original(*args, **kwargs)

    crew.translate_recap = watch
    r = client.get("/api/match/recap?lang=hi&persona=tactical")
    assert r.status_code == 200 and r.json()["language"] == "hi"
    assert seen == [False]  # a slow Translator never holds up playback
    assert client.get("/api/match/recap?lang=es").json()["language"] == "es"  # studio path unchanged
    assert seen == [False]


def test_public_payloads_carry_no_translator_spend_counters(client):
    public = {"mode", "available", "breaker_open", "cache_hits", "translated", "fallbacks", "rejections"}
    assert set(client.get("/api/languages").json()["translator"]) == public
    assert set(client.get("/api/crew/status").json()["translator"]) == public
    assert set(client.get("/api/match/snapshot").json()["crew"]["translator"]) == public


# --- send queue ---------------------------------------------------------------------------------


class StuckSocket:
    """A viewer whose network never drains: send_text never returns."""

    def __init__(self) -> None:
        self.sent = 0
        self.closed_with: int | None = None

    async def send_text(self, text: str) -> None:
        self.sent += 1
        await asyncio.Event().wait()

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


def test_send_queue_overflow_really_closes_the_connection():
    async def main() -> None:
        hub = Hub(None)
        ws = StuckSocket()
        conn = Connection(ws, time.monotonic, on_drop=hub.drop)  # type: ignore[arg-type]
        hub.connections.add(conn)
        writer = conn.start()
        big = {"type": "X", "data": "x" * 100_000}
        conn.send(big)
        await asyncio.sleep(0.01)  # the writer is now stuck in send_text
        for _ in range(60):  # 6 MB queued > 4 MB
            conn.send(big)
        await asyncio.sleep(0.01)
        assert conn.closed and writer.cancelled()
        assert ws.closed_with == 1013
        assert conn not in hub.connections
        assert conn.queue.empty() and conn.queued_bytes == 0
        assert ws.sent == 1
        conn.send(big)  # later sends are dropped, not queued
        assert conn.queue.empty()

    asyncio.run(main())


def test_send_queue_counts_bytes_and_frees_them_when_sent():
    async def main() -> None:
        sent: list[str] = []

        class Socket:
            async def send_text(self, text: str) -> None:
                sent.append(text)

        conn = Connection(Socket(), time.monotonic)  # type: ignore[arg-type]
        conn.send({"type": "A", "data": 1})
        assert conn.queued_bytes == len('{"type":"A","data":1}')
        conn.start()
        await asyncio.sleep(0.01)
        assert sent and conn.queued_bytes == 0 and not conn.closed

    asyncio.run(main())


# --- connection caps ----------------------------------------------------------------------------


def test_connections_are_capped_per_ip(client, monkeypatch):
    monkeypatch.setattr(app_mod, "MAX_CONN_PER_IP", 2)
    with client.websocket_connect("/ws/match") as a, client.websocket_connect("/ws/match") as b:
        a.receive_json()
        b.receive_json()
        with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect("/ws/match") as c:
            c.receive_json()
        assert exc.value.code == 1008
    with client.websocket_connect("/ws/match") as again:  # slots come back on close
        assert again.receive_json()["type"] == "INITIAL_SNAPSHOT"


def test_slots_are_reserved_before_accept(monkeypatch):
    monkeypatch.setattr(app_mod, "MAX_CONNECTIONS", 3)
    monkeypatch.setattr(app_mod, "MAX_CONN_PER_IP", 2)
    hub = Hub(None)
    # Reservations count even though nothing has been accepted or added yet.
    assert hub.reserve("1.1.1.1") and hub.reserve("1.1.1.1")
    assert not hub.reserve("1.1.1.1")  # per-IP cap
    assert hub.reserve("2.2.2.2")
    assert not hub.reserve("3.3.3.3")  # total cap
    assert hub.connections == set()
    hub.release("1.1.1.1")
    assert hub.reserve("3.3.3.3")
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        hub.release(ip)
    assert hub._slots == 0 and hub._slots_per_ip == {}


# --- model calls never hold the playback lock --------------------------------------------------


class Quiet:
    async def send_text(self, text: str) -> None:
        return None


def test_slow_crew_work_does_not_block_playback_controls(clock):
    entered, gate = threading.Event(), threading.Event()

    class SlowCrew(FakeCrew):
        def cards_for(self, bundles, profile, state):
            if bundles:  # stands in for a slow model call while voicing a goal
                entered.set()
                gate.wait(5)
            return super().cards_for(bundles, profile, state)

    session = MatchSession(make_events(), engines=Engines(stats=FakeStats, crew=SlowCrew), clock=clock)

    async def main() -> None:
        hub = Hub(session, clock=clock)
        hub.connections.add(Connection(Quiet(), clock))  # type: ignore[arg-type]
        clock.t += 1  # the goal at 1:00 is due
        task = asyncio.create_task(hub.pump())
        assert await asyncio.to_thread(entered.wait, 5)
        try:
            playback = await asyncio.wait_for(hub.set_speed(1), timeout=1)
            players = await asyncio.wait_for(hub.run(session.players), timeout=1)
        finally:
            gate.set()
            await task
        assert playback["speed_multiplier"] == 1 and players

    asyncio.run(main())
