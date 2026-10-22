"""What a first-time visitor meets on the shared match clock (docs/adr/0006-one-shared-match-clock.md):
a readable default speed, a restart that is a fresh start, a jump that lands somewhere
visible, a fresh kick-off after the match sat unwatched, translated error codes and the
API docs switch."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FAKE_ENGINES, FakeClock, make_events
from matchmind.api import app as app_mod
from matchmind.api import session as session_mod
from matchmind.api.app import create_app
from matchmind.api.session import MatchSession

ALLOWED = "http://localhost:3000"


def _session(clock: FakeClock, **kw) -> MatchSession:
    return MatchSession(make_events(), engines=FAKE_ENGINES, clock=clock, base_rate=10, **kw)


def _client(session: MatchSession, clock: FakeClock, tmp_path, **kw) -> TestClient:
    app = create_app(
        session=session,
        tick_interval=None,
        allowed_origins=[ALLOWED],
        static_dir=tmp_path / "none",
        clock=clock,
        **kw,
    )
    return TestClient(app)


def _recv(ws, type_: str) -> dict:
    msg = ws.receive_json()
    while msg["type"] == "CUES" and type_ != "CUES":
        msg = ws.receive_json()
    assert msg["type"] == type_, msg
    return msg["data"]


def test_default_speed_is_1x_so_cards_can_be_read(monkeypatch):
    monkeypatch.delenv("MATCHMIND_DEFAULT_SPEED", raising=False)
    assert _session(FakeClock()).speed == 1


@pytest.mark.parametrize("raw", ["7", "fast", ""])
def test_a_bad_default_speed_setting_falls_back_to_1x(monkeypatch, raw):
    monkeypatch.setenv("MATCHMIND_DEFAULT_SPEED", raw)
    assert _session(FakeClock()).speed == 1


def test_restart_goes_back_to_the_default_speed():
    clock = FakeClock()
    s = _session(clock, default_speed=1)
    s.set_speed(60)
    s.reset()
    assert s.speed == 1 and s.is_running


def test_jumping_back_into_a_finished_match_plays_from_there():
    clock = FakeClock()
    s = _session(clock, default_speed=10)
    clock.t += 100
    s.advance()
    assert s.ended and not s.is_running
    s.seek(30)
    assert s.is_running and not s.ended


def test_jumping_while_paused_mid_match_keeps_the_pause():
    clock = FakeClock()
    s = _session(clock, default_speed=10)
    s.advance()
    s.toggle_pause()
    s.seek(30)
    assert not s.is_running


def test_snapshot_carries_recent_events_so_the_pitch_is_never_empty(tmp_path):
    clock = FakeClock()
    s = _session(clock, default_speed=10)
    s.seek(2800, period=2)
    with _client(s, clock, tmp_path) as client, client.websocket_connect("/ws/match") as ws:
        snap = _recv(ws, "INITIAL_SNAPSHOT")
    events = snap["recent_events"]
    assert events and events[-1]["seq"] == s.last_event.seq
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    assert len(events) <= app_mod.view.SNAPSHOT_EVENTS


def test_catch_up_snapshot_scrubs_recent_events(tmp_path):
    clock = FakeClock()
    s = _session(clock, default_speed=10)
    s.seek(2850, period=2)  # just after the 2800 goal
    with _client(s, clock, tmp_path) as client, client.websocket_connect("/ws/match") as ws:
        _recv(ws, "INITIAL_SNAPSHOT")
        ws.send_json({"action": "set_view", "spoilers": False})
        msg = ws.receive_json()
        while msg["type"] != "INITIAL_SNAPSHOT":
            msg = ws.receive_json()
        snap = msg["data"]
    assert snap["home_score"] is None
    assert all(e.get("outcome") != "goal" for e in snap["recent_events"])


def test_first_visitor_after_an_idle_spell_starts_at_kick_off(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "IDLE_REWIND_S", 300.0)
    clock = FakeClock()
    s = _session(clock, default_speed=10)
    with _client(s, clock, tmp_path) as client:
        with client.websocket_connect("/ws/match") as ws:
            _recv(ws, "INITIAL_SNAPSHOT")
            ws.send_json({"action": "set_speed", "speed_multiplier": 60})
            _recv(ws, "PLAYBACK_CONTROL")
            clock.t += 100
            client.portal.call(client.app.state.hub.pump)
            assert s.ended
        # Back within the idle spell (a reload): the match stays where it was.
        clock.t += 10
        with client.websocket_connect("/ws/match") as ws:
            assert _recv(ws, "INITIAL_SNAPSHOT")["playback"]["ended"] is True
        clock.t += 301
        with client.websocket_connect("/ws/match") as ws:
            snap = _recv(ws, "INITIAL_SNAPSHOT")
    assert snap["playback"]["ended"] is False and snap["playback"]["is_running"] is True
    assert snap["playback"]["speed_multiplier"] == 10  # the default, not the last viewer's 60x
    assert snap["clock"] == "00:00"


def test_no_rewind_while_someone_else_is_watching(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "IDLE_REWIND_S", 300.0)
    clock = FakeClock()
    s = _session(clock, default_speed=10)
    with _client(s, clock, tmp_path) as client, client.websocket_connect("/ws/match") as a:
        _recv(a, "INITIAL_SNAPSHOT")
        s.seek(2800, period=2)
        clock.t += 1000
        with client.websocket_connect("/ws/match") as b:
            snap = _recv(b, "INITIAL_SNAPSHOT")
    assert snap["period"] == 2


def test_rate_limit_errors_carry_a_code_for_translation(tmp_path):
    clock = FakeClock()
    s = _session(clock, default_speed=10)
    with _client(s, clock, tmp_path) as client, client.websocket_connect("/ws/match") as ws:
        _recv(ws, "INITIAL_SNAPSHOT")
        for _ in range(app_mod.VIEW_BURST + 1):
            ws.send_json({"action": "set_view", "language": "es"})
        codes = []
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] == "ERROR":
                codes.append(msg["data"]["code"])
                break
        ws.send_json({"action": "seek", "clock_s": 30})
        ws.send_json({"action": "seek", "clock_s": 40})
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] == "ERROR":
                codes.append(msg["data"]["code"])
                break
    assert codes == ["view_too_fast", "jump_too_fast"]


def test_every_session_message_has_a_code():
    names = ("MATCH_FINISHED", "BAD_SPEED", "BAD_TIME", "NO_SUCH_HALF", "NOT_PLAYED_YET", "AFTER_FULL_TIME")
    for name in names:
        assert getattr(session_mod, name) in app_mod.ERROR_CODES


def test_every_rate_limit_refusal_has_a_code():
    """Pause/speed, jump and view refusals each reach the app as a code it can translate."""
    expected = {
        "CONTROL_TOO_FAST": "control_too_fast",
        "TOO_FAST": "jump_too_fast",
        "VIEW_TOO_FAST": "view_too_fast",
    }
    for name, code in expected.items():
        assert app_mod.ERROR_CODES[getattr(app_mod, name)] == code
    toasts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "toasts.ts").read_text()
    for code in set(app_mod.ERROR_CODES.values()):
        assert f"'{code}'" in toasts, code


@pytest.mark.parametrize(
    ("serves_frontend", "env", "expect"),
    [(False, None, 200), (True, None, 404), (True, "true", 200), (False, "false", 404)],
)
def test_api_docs_off_where_the_app_is_served(tmp_path, monkeypatch, serves_frontend, env, expect):
    if env is None:
        monkeypatch.delenv("MATCHMIND_API_DOCS", raising=False)
    else:
        monkeypatch.setenv("MATCHMIND_API_DOCS", env)
    static = tmp_path / "static"
    if serves_frontend:
        static.mkdir()
        (static / "index.html").write_text("<!doctype html><title>PitchPulse</title>")
    clock = FakeClock()
    app = create_app(
        session=_session(clock), tick_interval=None, allowed_origins=[ALLOWED], static_dir=static, clock=clock
    )
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == expect
        assert client.get("/docs").status_code == expect


def test_built_app_is_compressed_and_hashed_files_cached(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>PitchPulse</title>" + " " * 2000)
    (static / "assets" / "index-abc123.js").write_text("console.log('pitchpulse');" * 200)
    clock = FakeClock()
    app = create_app(
        session=_session(clock), tick_interval=None, allowed_origins=[ALLOWED], static_dir=static, clock=clock
    )
    with TestClient(app) as client:
        js = client.get("/assets/index-abc123.js", headers={"Accept-Encoding": "gzip"})
        page = client.get("/", headers={"Accept-Encoding": "gzip"})
        api = client.get("/api/health")
    assert js.status_code == 200 and js.headers["content-encoding"] == "gzip"
    assert js.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert page.headers["content-encoding"] == "gzip" and page.headers["cache-control"] == "no-cache"
    assert "content-security-policy" in page.headers
    assert api.headers["cache-control"] == "no-store"
