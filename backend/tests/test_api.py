from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import FAKE_ENGINES, FakeClock, make_events
from matchmind.api import app as app_mod
from matchmind.api.app import RateLimiter, create_app
from matchmind.api.session import Engines, MatchSession

ALLOWED = "http://localhost:5173"

SNAPSHOT_KEYS = {
    "match_id",
    "clock",
    "period",
    "home_score",
    "away_score",
    "teams",
    "state",
    "control_chaos",
    "profile",
    "playback",
    "recent_cards",
    "bookmarks",
    "players",
    "crew",
    "languages",
    "auto_eventing",
    "cue_sheet",
}
STATE_KEYS = {
    "match_id",
    "clock_s",
    "match_clock",
    "period",
    "home_id",
    "away_id",
    "score_home",
    "score_away",
    "home",
    "away",
    "momentum",
    "control_chaos",
    "tempo",
    "events_per_min",
    "turnovers_per_min",
    "avg_chain_passes",
    "xg_home",
    "xg_away",
    "shots_home",
    "shots_away",
}
CONTROL_KEYS = {
    "home_control_pct",
    "away_control_pct",
    "chaos_index",
    "current_tempo",
    "rolling_momentum_home",
}
PLAYBACK_KEYS = {"is_running", "speed_multiplier", "clock_s", "ended", "match_clock", "period"}
EVENT_KEYS = {
    "event_id",
    "seq",
    "match_clock",
    "clock_s",
    "period",
    "type",
    "team",
    "player_id",
    "receiver_id",
    "start",
    "end",
    "outcome",
    "under_pressure",
    "details",
    "metrics",
}
METRIC_KEYS = {
    "pass_distance_m",
    "pass_difficulty",
    "progressive",
    "ball_speed_kmh",
    "player_speed_kmh",
    "sprint",
    "fast_shot",
    "chance_quality",
    "distance_to_goal_m",
    "pitch_zone",
    "xt_delta",
}
PLAYER_KEYS = {
    "player_id",
    "team",
    "touches",
    "passes",
    "passes_completed",
    "pass_accuracy",
    "key_passes",
    "shots",
    "shots_on_target",
    "goals",
    "assists",
    "xg",
    "xa",
    "tackles_won",
    "tackles_lost",
    "tackles_attempted",
    "tackle_success_pct",
    "interceptions",
    "top_speed_kmh",
    "sprints",
    "distance_km",
    "walk_km",
    "jog_km",
    "run_km",
    "sprint_km",
    "physical_source",
    "carry_distance_m",
    "name",
    "number",
    "position",
}


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def session(clock) -> MatchSession:
    return MatchSession(make_events(), engines=FAKE_ENGINES, clock=clock, base_rate=10)


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


def pump(client: TestClient, clock: FakeClock | None = None, seconds: float = 0.0) -> None:
    if clock is not None:
        clock.t += seconds
    client.portal.call(client.app.state.hub.pump)


def recv(ws, type_: str) -> dict:
    """The next message of `type_`. CUES (the cue sheet stream that follows each
    tick) is skipped unless asked for; tests/test_cues.py covers it."""
    msg = ws.receive_json()
    while msg["type"] == "CUES" and type_ != "CUES":
        msg = ws.receive_json()
    assert msg["type"] == type_, msg
    return msg["data"]


# --- REST ------------------------------------------------------------------------------------


def test_health(client):
    r = client.get("/api/health")
    assert r.json() == {"status": "ok"}
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_snapshot_shape_matches_contract(client, clock):
    pump(client, clock, 1)  # nobody connected: match holds still
    data = client.get("/api/match/snapshot").json()
    assert set(data) == SNAPSHOT_KEYS
    assert set(data["state"]) == STATE_KEYS
    assert set(data["control_chaos"]) == CONTROL_KEYS
    assert set(data["playback"]) == PLAYBACK_KEYS
    assert data["profile"] == {
        "persona": "casual",
        "language": "en",
        "favourite_team": None,
        "focus_player_id": None,
        "focus_metric": None,
        "spoilers": True,
    }
    assert data["clock"] == "00:00" and data["home_score"] == 0
    assert data["teams"]["home"]["name"] == "Northbridge FC"
    assert {
        "team_id",
        "name",
        "short_name",
        "primary_color",
        "secondary_color",
        "formation",
        "style",
        "players",
    } == set(data["teams"]["home"])
    assert set(data["teams"]["away"]["players"][0]) == {"player_id", "name", "number", "position", "line"}
    assert data["auto_eventing"] is None
    assert data["bookmarks"][0]["moment_id"] == "goal-MM-TEST-001-00003"


def test_teams_route(client):
    data = client.get("/api/teams").json()
    assert data["home"]["team_id"] == "NBR" and data["away"]["team_id"] == "HCY"


def test_bookmarks_route(client):
    data = client.get("/api/match/bookmarks").json()
    assert [b["match_clock"] for b in data] == ["01:00", "46:40"]
    assert set(data[0]) == {"moment_id", "kind", "match_clock", "clock_s", "period", "title", "ruled_out"}


def test_moment_route_and_404(client):
    r = client.get("/api/match/moment/goal-MM-TEST-001-00007?persona=tactical&lang=fr&favourite_team=HCY")
    card = r.json()
    assert r.status_code == 200 and card["persona"] == "tactical" and card["language"] == "fr"
    assert card["favourite_side"] is True
    r = client.get("/api/match/moment/does-not-exist")
    assert r.status_code == 404 and r.json() == {"detail": "We could not find that moment."}
    r = client.get("/api/match/moment/goal-MM-TEST-001-00007?favourite_team=XYZ")
    assert r.status_code == 400 and r.json()["detail"] == "That club is not in this match."


def test_recap_route(client):
    r = client.get("/api/match/recap?persona=fantasy&lang=ar")
    assert r.status_code == 200
    data = r.json()
    assert data["persona"] == "fantasy" and data["rtl"] is True and data["fact_check"]["ok"] is True


def test_bad_query_gets_plain_400(client):
    r = client.get("/api/match/recap?persona=hacker")
    assert r.status_code == 400
    assert r.json() == {"detail": "Check persona: the value is missing or not allowed."}


def test_players_route(client, clock):
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        pump(client, clock, 1)
    players = client.get("/api/match/players").json()
    assert players and set(players[0]) == PLAYER_KEYS
    assert players[0]["pass_accuracy"] == 100.0


def test_rest_playback_controls(client, clock):
    r = client.post("/api/match/speed", json={"speed_multiplier": 60})
    assert r.json()["speed_multiplier"] == 60
    assert client.post("/api/match/speed", json={"speed_multiplier": 5}).status_code == 400
    r = client.post("/api/match/seek", json={"clock_s": 2800, "period": 2})
    assert r.status_code == 200 and r.json()["clock_s"] == 2700 and r.json()["period"] == 2
    r = client.post("/api/match/seek", json={"clock_s": 99999})
    assert r.status_code == 400
    clock.t += 1  # seeks and resets are throttled to one per half second
    r = client.post("/api/match/seek", json={"clock_s": 9000, "period": 2})
    assert r.status_code == 400 and r.json() == {"detail": "That time is after full time."}
    clock.t += 1
    r = client.post("/api/match/reset")
    assert r.json()["is_running"] is True and r.json()["clock_s"] == 0


def test_crew_routes(client):
    status = client.get("/api/crew/status").json()
    assert status["mode"] == "template"
    assert status["provider"] == "templates" and status["orchestrator"] == "in_process"
    traces = client.get("/api/crew/trace?limit=5").json()
    assert traces[0]["steps"][0]["agent"] == "spotter"
    assert client.get("/api/crew/trace?limit=0").status_code == 400


def test_auto_eventing_404_until_built(client):
    r = client.get("/api/auto-eventing")
    assert r.status_code == 404 and r.json() == {"detail": "Auto-eventing is coming soon."}


def test_cors_allows_listed_origin_and_rejects_others(client):
    ok = client.get("/api/health", headers={"Origin": ALLOWED})
    assert ok.headers["access-control-allow-origin"] == ALLOWED
    assert "access-control-allow-credentials" not in ok.headers
    bad = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
    pre = client.options(
        "/api/match/reset",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert pre.status_code == 400


def test_cors_from_env_drops_wildcard(monkeypatch):
    monkeypatch.setenv("MATCHMIND_ALLOWED_ORIGINS", "https://a.example, *,https://b.example/")
    assert app_mod.allowed_origins_from_env() == ["https://a.example", "https://b.example"]
    monkeypatch.delenv("MATCHMIND_ALLOWED_ORIGINS")
    assert app_mod.allowed_origins_from_env() == ["http://localhost:5173", "http://localhost:3000"]


def test_static_frontend_served_when_built(session, clock, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>PitchPulse</title>")
    app = create_app(
        session=session, tick_interval=None, allowed_origins=[], static_dir=tmp_path, clock=clock
    )
    with TestClient(app) as c:
        assert "PitchPulse" in c.get("/").text
        assert c.get("/api/health").json() == {"status": "ok"}


def test_app_created_at_import_and_loads_lazily():
    assert app_mod.app.state.hub._session is None  # session is built in the lifespan, not on import


# --- WebSocket -------------------------------------------------------------------------------


def test_ws_initial_snapshot_then_ticks_in_order(client, clock):
    with client.websocket_connect("/ws/match") as ws:
        snap = recv(ws, "INITIAL_SNAPSHOT")
        assert set(snap) == SNAPSHOT_KEYS | {"recent_events"}  # the pitch's last events (WS only)
        pump(client, clock, 0.6)  # 60 match seconds at the default 10x
        seqs = []
        for _ in range(4):
            data = recv(ws, "MATCH_TICK")
            assert set(data) == {
                "event",
                "clock",
                "period",
                "score",
                "state",
                "control_chaos",
                "cards",
                "players_changed",
            }
            assert set(data["event"]) == EVENT_KEYS and set(data["event"]["metrics"]) == METRIC_KEYS
            assert "labels" not in data["event"]
            seqs.append(data["event"]["seq"])
        assert seqs == [0, 1, 2, 3]
        assert data["score"] == {"home": 1, "away": 0}
        assert data["cards"][0]["kind"] == "goal" and data["cards"][0]["persona"] == "casual"


def test_ws_set_view_changes_only_that_connection(client, clock):
    with client.websocket_connect("/ws/match") as a, client.websocket_connect("/ws/match") as b:
        recv(a, "INITIAL_SNAPSHOT")
        recv(b, "INITIAL_SNAPSHOT")
        a.send_json({"action": "set_view", "persona": "tactical", "language": "ar", "favourite_team": "HCY"})
        profile = recv(a, "PROFILE_CHANGED")
        assert profile["persona"] == "tactical" and profile["language"] == "ar"
        assert recv(a, "PERSONA_CHANGED") == {"persona": "tactical"}
        pump(client, clock, 0.6)
        last_a = [recv(a, "MATCH_TICK") for _ in range(4)][-1]
        last_b = [recv(b, "MATCH_TICK") for _ in range(4)][-1]  # b got ticks, no PROFILE_CHANGED
        assert last_a["cards"][0]["persona"] == "tactical" and last_a["cards"][0]["rtl"] is True
        assert last_a["cards"][0]["favourite_side"] is False
        assert last_b["cards"][0]["persona"] == "casual" and last_b["cards"][0]["language"] == "en"


def test_ws_set_view_partial_and_clear(client):
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        ws.send_json({"action": "set_view", "focus_player_id": "NBR-9", "focus_metric": "xg"})
        p = recv(ws, "PROFILE_CHANGED")
        assert p["focus_player_id"] == "NBR-9" and p["persona"] == "casual"
        recv(ws, "PERSONA_CHANGED")
        ws.send_json({"action": "set_view", "focus_player_id": None})
        assert recv(ws, "PROFILE_CHANGED")["focus_player_id"] is None
        recv(ws, "PERSONA_CHANGED")
        ws.send_json({"action": "set_persona", "persona": "fantasy"})
        assert recv(ws, "PROFILE_CHANGED")["persona"] == "fantasy"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"action": "explode"}, "Unknown action."),
        ({"nothing": 1}, "Unknown action."),
        ([1, 2], "Unknown action."),
        ({"action": "set_speed", "speed_multiplier": 7}, "Speed must be 1, 10 or 60."),
        ({"action": "set_view", "persona": "admin"}, "That view setting is not valid."),
        ({"action": "set_view", "favourite_team": "XYZ"}, "That club is not in this match."),
        ({"action": "set_view", "focus_player_id": "NBR-99"}, "That player is not in this match."),
        ({"action": "seek", "clock_s": "soon"}, "Seek needs clock_s"),
        ({"action": "seek", "clock_s": 9000, "period": 2}, "That time is after full time."),
        ({"action": "toggle_pause", "extra": "x"}, "toggle_pause takes no other fields."),
    ],
)
def test_ws_bad_action_gets_plain_error(client, payload, message):
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        ws.send_text(json.dumps(payload))
        assert recv(ws, "ERROR")["message"].startswith(message)


def test_ws_not_json_and_binary(client):
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        ws.send_text("{not json")
        assert recv(ws, "ERROR")["message"].startswith("We could not read that message.")
        ws.send_bytes(b"\x00\x01")
        assert recv(ws, "ERROR")["message"] == "Send actions as JSON text."


def test_ws_oversize_message_rejected(client):
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        ws.send_text(json.dumps({"action": "set_view", "persona": "casual", "pad": "x" * 5000}))
        assert recv(ws, "ERROR")["message"] == "That message is too big. Actions must be under 4 KB."
        ws.send_json({"action": "set_speed", "speed_multiplier": 60})  # still usable afterwards
        assert recv(ws, "PLAYBACK_CONTROL")["speed_multiplier"] == 60


def test_ws_shared_playback_reaches_everyone(client, clock):
    with client.websocket_connect("/ws/match") as a, client.websocket_connect("/ws/match") as b:
        recv(a, "INITIAL_SNAPSHOT")
        recv(b, "INITIAL_SNAPSHOT")
        a.send_json({"action": "toggle_pause"})
        assert recv(a, "PLAYBACK_CONTROL")["is_running"] is False
        assert recv(b, "PLAYBACK_CONTROL")["is_running"] is False
        clock.t += 1  # pause and speed changes share a 0.3 s throttle
        b.send_json({"action": "set_speed", "speed_multiplier": 1})
        assert recv(a, "PLAYBACK_CONTROL")["speed_multiplier"] == 1
        assert recv(b, "PLAYBACK_CONTROL")["speed_multiplier"] == 1
        pump(client, clock, 100)  # paused: nothing plays
        a.send_json({"action": "seek", "clock_s": 2800, "period": 2})
        snap_a = recv(a, "INITIAL_SNAPSHOT")
        snap_b = recv(b, "INITIAL_SNAPSHOT")
        assert snap_a["home_score"] == 1 and snap_a["away_score"] == 0 and snap_a["period"] == 2
        assert snap_b["playback"]["clock_s"] == 2700
        assert [c["moment_id"] for c in snap_a["recent_cards"]] == ["goal-MM-TEST-001-00003"]
        clock.t += 1  # seeks and resets are throttled to one per half second
        b.send_json({"action": "reset"})
        assert recv(a, "MATCH_RESET") == {}
        assert recv(a, "INITIAL_SNAPSHOT")["home_score"] == 0
        assert recv(b, "MATCH_RESET") == {}
        assert recv(b, "INITIAL_SNAPSHOT")["playback"]["is_running"] is True


def test_ws_match_end_sends_recap_for_the_viewer(client, clock):
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        ws.send_json({"action": "set_view", "persona": "tactical", "language": "es"})
        recv(ws, "PROFILE_CHANGED")
        recv(ws, "PERSONA_CHANGED")
        pump(client, clock, 100)
        ticks = [recv(ws, "MATCH_TICK") for _ in range(9)]
        assert ticks[-1]["event"]["type"] == "match_end"
        recap = recv(ws, "MATCH_END")["recap"]
        assert recap["persona"] == "tactical" and recap["language"] == "es" and recap["headline"] == "1-1"
        assert recv(ws, "PLAYBACK_CONTROL")["ended"] is True
        ws.send_json({"action": "toggle_pause"})
        assert "finished" in recv(ws, "ERROR")["message"]


def test_ws_rejects_unlisted_origin(client):
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/match", headers={"Origin": "https://evil.example"}) as ws,
    ):
        ws.receive_json()


def ws_refused(client: TestClient, headers: dict[str, str]) -> int:
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect("/ws/match", headers=headers) as ws,
    ):
        ws.receive_json()
    return exc.value.code


def test_ws_allows_listed_origin_and_never_trusts_host(client):
    with client.websocket_connect("/ws/match", headers={"Origin": ALLOWED}) as ws:
        recv(ws, "INITIAL_SNAPSHOT")
    # A matching Host header proves nothing: the attacker controls both.
    assert ws_refused(client, {"Origin": "http://evil.test", "Host": "evil.test"}) == 1008
    assert ws_refused(client, {"Origin": "http://testserver"}) == 1008


def test_ws_allows_own_public_origin_only_when_serving_the_frontend(session, clock, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>PitchPulse</title>")
    own = "https://pitchpulse.example"
    for static_dir, allowed in ((static, True), (tmp_path / "none", False)):
        app = create_app(
            session=session,
            tick_interval=None,
            allowed_origins=[ALLOWED],
            static_dir=static_dir,
            clock=clock,
            public_origin=own,
        )
        with TestClient(app) as c:
            if allowed:
                with c.websocket_connect("/ws/match", headers={"Origin": own + "/"}) as ws:
                    recv(ws, "INITIAL_SNAPSHOT")
            else:
                assert ws_refused(c, {"Origin": own}) == 1008


def test_public_origin_from_env(monkeypatch, session, clock, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>PitchPulse</title>")
    monkeypatch.setenv("MATCHMIND_PUBLIC_ORIGIN", "https://pitchpulse.example")
    app = create_app(session=session, tick_interval=None, allowed_origins=[], static_dir=static, clock=clock)
    with (
        TestClient(app) as c,
        c.websocket_connect("/ws/match", headers={"Origin": "https://pitchpulse.example"}) as ws,
    ):
        recv(ws, "INITIAL_SNAPSHOT")


def _static_app(session, clock, tmp_path, public_origin, origins=()):
    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    (static / "index.html").write_text("<!doctype html><title>PitchPulse</title>")
    return create_app(
        session=session,
        tick_interval=None,
        allowed_origins=list(origins),
        static_dir=static,
        clock=clock,
        public_origin=public_origin,
    )


def test_pages_carry_a_content_security_policy_and_api_routes_do_not(session, clock, tmp_path):
    app = _static_app(
        session, clock, tmp_path, "", origins=["https://api.pitchpulse.example", "bad; script-src *"]
    )
    with TestClient(app) as c:
        page = c.get("/")
        api = c.get("/api/health")
    csp = page.headers["content-security-policy"]
    directives = dict(d.strip().split(" ", 1) for d in csp.split(";"))
    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["img-src"] == "'self' data:"
    assert directives["media-src"] == "'self'"
    assert directives["style-src"] == "'self' 'unsafe-inline'"
    connect = directives["connect-src"].split()
    assert connect[:3] == ["'self'", "ws:", "wss:"]
    assert "https://api.pitchpulse.example" in connect and "wss://api.pitchpulse.example" in connect
    assert "*" not in csp and "bad" not in csp  # a malformed origin never widens the policy
    assert "content-security-policy" not in api.headers
    assert page.headers["x-content-type-options"] == "nosniff"


def test_hsts_only_when_the_public_origin_is_https(session, clock, tmp_path):
    for own, expected in (
        ("https://pitchpulse.example", True),
        ("http://localhost:8000", False),
        ("", False),
    ):
        app = _static_app(session, clock, tmp_path, own)
        with TestClient(app) as c:
            for path in ("/", "/api/health"):
                hsts = c.get(path).headers.get("strict-transport-security")
                assert (hsts == "max-age=31536000; includeSubDomains") if expected else hsts is None


def test_ws_rate_limit(client):
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        for _ in range(25):  # the fake clock does not move, so the bucket never refills
            ws.send_json({"action": "nope"})
        messages = [recv(ws, "ERROR")["message"] for _ in range(25)]
        assert messages.count("Too many actions at once. Wait a moment and try again.") == 5


def test_rate_limiter_refills():
    t = FakeClock()
    rl = RateLimiter(burst=2, per_second=1, clock=t)
    assert rl.allow() and rl.allow() and not rl.allow()
    t.t += 1
    assert rl.allow() and not rl.allow()


def test_no_viewers_holds_the_match(client, clock, session):
    pump(client, clock, 100)
    assert session.next_index == 0


# --- With the real stats engine --------------------------------------------------------------


def test_demo_match_with_real_stats_engine(clock):
    from conftest import FakeCrew
    from matchmind.api.session import load_events
    from matchmind.stats.state import StatsEngine

    s = MatchSession(load_events(), engines=Engines(stats=StatsEngine, crew=FakeCrew), clock=clock)
    app = create_app(session=s, tick_interval=None, allowed_origins=[], clock=clock)
    with TestClient(app) as c, c.websocket_connect("/ws/match") as ws:
        snap = recv(ws, "INITIAL_SNAPSHOT")
        assert set(snap["state"]) == STATE_KEYS
        ws.send_json({"action": "seek", "clock_s": 2700, "period": 2})
        snap = recv(ws, "INITIAL_SNAPSHOT")
        assert snap["period"] == 2 and len(snap["players"]) > 10
        assert set(snap["players"][0]) == PLAYER_KEYS
        pump(c, clock, 100)
        assert recv(ws, "MATCH_TICK")["state"]["period"] == 2
    assert s.ended and s.score == (2, 3)


# --- Languages -------------------------------------------------------------------------------


def test_languages_route_lists_studio_and_world_languages(client):
    data = client.get("/api/languages").json()
    assert data["translator"]["mode"] == "off" and data["translator"]["available"] is False
    by_code = {lang["code"]: lang for lang in data["languages"]}
    assert list(by_code)[:5] == ["en", "es", "fr", "ar", "ja"] and len(by_code) == 13
    assert by_code["es"] == {
        "code": "es",
        "name": "Español",
        "english_name": "Spanish",
        "source": "studio",
        "available": True,
        "rtl": False,
        "reason": None,
    }
    assert by_code["zh-Hans"]["source"] == "translator" and by_code["zh-Hans"]["available"] is False
    assert by_code["zh-Hans"]["reason"] == "translator_off"
    snapshot = client.get("/api/match/snapshot").json()
    assert snapshot["languages"] == data["languages"]
    assert snapshot["crew"]["translator"]["mode"] == "off"


def test_world_language_is_accepted_in_rest_and_set_view(client):
    r = client.get("/api/match/moment/goal-MM-TEST-001-00007?lang=zh-Hans")
    assert r.status_code == 200 and r.json()["language"] == "zh-Hans"
    assert client.get("/api/match/recap?lang=sw").status_code == 200
    assert client.get("/api/match/recap?lang=xx").status_code == 400
    with client.websocket_connect("/ws/match") as ws:
        recv(ws, "INITIAL_SNAPSHOT")
        ws.send_json({"action": "set_view", "language": "pt"})
        assert recv(ws, "PROFILE_CHANGED")["language"] == "pt"
        recv(ws, "PERSONA_CHANGED")
        ws.send_json({"action": "set_view", "language": "klingon"})
        message = recv(ws, "ERROR")["message"]
        assert "zh-Hans" in message and "ko" in message
