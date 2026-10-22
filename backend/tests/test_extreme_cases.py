"""Extreme cases from the pre-launch test round (qa/extreme-cases/report.md).

Each test names the finding it guards (EC-n). The ones marked "held up" passed
before any change and stay as regression guards.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FakeClock, FakeCrew, FakeStats, make_events
from matchmind.api import app as app_mod
from matchmind.api.app import SEND_QUEUE_SHARE_BYTES, Connection, Hub, SendBudget, create_app
from matchmind.api.session import Engines, MatchSession

ALLOWED = "http://localhost:5173"
DEMO = Path(__file__).resolve().parents[1] / "data" / "matches" / "MM-DEMO-001.jsonl"


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


class StuckSocket:
    """A viewer that stopped reading: send_text never returns."""

    def __init__(self) -> None:
        self.closed_with: int | None = None

    async def send_text(self, text: str) -> None:
        await asyncio.Event().wait()

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


class QuickSocket:
    def __init__(self) -> None:
        self.sent = 0

    async def send_text(self, text: str) -> None:
        self.sent += 1


# --- EC-1: viewers that stop reading share one memory budget ---------------------------------


def test_ec1_stalled_viewers_cannot_pin_more_than_the_shared_budget():
    """Before: each stalled viewer could queue 4 MB, so 200 of them pinned about 800 MB
    in a 1 GiB container (measured: RSS 173 -> 795 MB). Now all queues share one budget."""

    async def main() -> None:
        hub = Hub(None)
        hub.send_budget = SendBudget(total=2 * 1024 * 1024)
        stuck = [
            Connection(StuckSocket(), time.monotonic, on_drop=hub.drop, budget=hub.send_budget)
            for _ in range(8)
        ]
        for c in stuck:
            hub.connections.add(c)
            c.start()
        quick_ws = QuickSocket()
        quick = Connection(quick_ws, time.monotonic, on_drop=hub.drop, budget=hub.send_budget)
        hub.connections.add(quick)
        quick.start()
        msg = {"type": "MATCH_TICK", "data": "x" * 20_000}
        for _ in range(60):  # 1.2 MB per viewer: under the 4 MB per-viewer cap
            hub.broadcast(msg)
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)
        used = sum(c.queued_bytes for c in stuck if not c.closed)
        assert used <= hub.send_budget.total + SEND_QUEUE_SHARE_BYTES
        assert hub.send_budget.used == used + quick.queued_bytes
        dropped = [c for c in stuck if c.closed]
        assert dropped and all(c.ws.closed_with == 1013 for c in dropped)  # type: ignore[attr-defined]
        assert all(c not in hub.connections for c in dropped)
        # The viewer that keeps up is never dropped for the others' backlog.
        assert not quick.closed and quick_ws.sent == 60

    asyncio.run(main())


def test_ec1_bytes_go_back_to_the_budget_when_a_viewer_leaves():
    async def main() -> None:
        budget = SendBudget(total=10 * 1024 * 1024)
        conn = Connection(StuckSocket(), time.monotonic, budget=budget)  # type: ignore[arg-type]
        writer = conn.start()
        for _ in range(10):
            conn.send({"type": "X", "data": "x" * 50_000})
        await asyncio.sleep(0.01)
        assert budget.used == conn.queued_bytes > 0
        conn.close()
        writer.cancel()  # what the endpoint does to a writer stuck past its grace period
        conn.drain_queue()
        assert budget.used == 0 and conn.queued_bytes == 0

    asyncio.run(main())


# --- EC-2: pause and speed storms are throttled for everyone ---------------------------------


def test_ec2_pause_storm_changes_playback_once_per_window(client, clock, session):
    """Before: every toggle went through (measured 2,971 in 15 s from one address, each
    broadcast to every viewer, the clock moving 35 s instead of 150 s)."""
    with client.websocket_connect("/ws/match") as ws, client.websocket_connect("/ws/match") as bystander:
        ws.receive_json()
        bystander.receive_json()
        for _ in range(15):
            ws.send_json({"action": "toggle_pause"})
        replies = [ws.receive_json() for _ in range(15)]
        changes = [r for r in replies if r["type"] == "PLAYBACK_CONTROL"]
        errors = [r["data"]["message"] for r in replies if r["type"] == "ERROR"]
        assert len(changes) == 1 and errors == [app_mod.CONTROL_TOO_FAST] * 14
        assert session.is_running is False
        # The bystander saw one change, not fifteen.
        assert bystander.receive_json()["type"] == "PLAYBACK_CONTROL"
        clock.t += app_mod.CONTROL_INTERVAL_S + 0.01
        ws.send_json({"action": "toggle_pause"})
        assert ws.receive_json()["data"]["is_running"] is True
        assert bystander.receive_json()["data"]["is_running"] is True


def test_ec2_double_tap_on_pause_is_one_change(client, clock, session):
    with client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "toggle_pause"})
        ws.send_json({"action": "toggle_pause"})
        assert ws.receive_json()["type"] == "PLAYBACK_CONTROL"
        assert ws.receive_json()["type"] == "ERROR"
    assert session.is_running is False  # paused, not paused-and-resumed


def test_ec2_rest_speed_shares_the_throttle_and_a_retry_is_a_no_op(client, clock, session):
    with client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "toggle_pause"})
        assert ws.receive_json()["type"] == "PLAYBACK_CONTROL"
    assert client.post("/api/match/speed", json={"speed_multiplier": 60}).status_code == 429
    clock.t += app_mod.CONTROL_INTERVAL_S + 0.01
    assert client.post("/api/match/speed", json={"speed_multiplier": 60}).json()["speed_multiplier"] == 60
    # The same request again (a network retry) answers 200 and changes nothing.
    again = client.post("/api/match/speed", json={"speed_multiplier": 60})
    assert again.status_code == 200 and session.speed == 60


# --- EC-4: a stale club in a saved profile must not cancel catch-up ---------------------------


def test_ec4_unknown_club_is_left_out_and_the_rest_of_the_view_applies(client):
    """Before: a saved club from another match made the server refuse the whole set_view,
    so spoilers=false never applied and the catch-up viewer saw the score."""
    with client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "set_view", "favourite_team": "OLD", "spoilers": False, "language": "es"})
        assert ws.receive_json() == {"type": "ERROR", "data": {"message": "That club is not in this match."}}
        changed = ws.receive_json()
        assert changed["type"] == "PROFILE_CHANGED"
        assert changed["data"]["spoilers"] is False and changed["data"]["language"] == "es"
        assert changed["data"]["favourite_team"] is None
        assert ws.receive_json()["type"] == "PERSONA_CHANGED"
        snap = ws.receive_json()
        assert snap["type"] == "INITIAL_SNAPSHOT" and snap["data"]["home_score"] is None


def test_ec4_only_an_unknown_club_changes_nothing(client):
    with client.websocket_connect("/ws/match") as ws:
        ws.receive_json()
        ws.send_json({"action": "set_view", "favourite_team": "OLD"})
        assert ws.receive_json()["type"] == "ERROR"
        ws.send_json({"action": "set_view", "persona": "tactical"})
        assert ws.receive_json()["data"]["persona"] == "tactical"  # no stray PROFILE_CHANGED before it


# --- EC-5: restart or seek before a live match has its second event ---------------------------


def _live_session_with_only_kick_off(clock: FakeClock):
    from matchmind.ingest.live import LiveFeed
    from matchmind.ingest.stream import StreamValidator
    from matchmind.simulator.publisher import read_jsonl

    demo = read_jsonl(DEMO)
    feed = LiveFeed(StreamValidator())
    feed.put(demo[0].model_dump_json())
    start = feed.wait_for_start(1)
    assert start is not None
    s = MatchSession([start], engines=Engines(stats=FakeStats, crew=FakeCrew), clock=clock, live_feed=feed)
    return s, feed, demo


def test_ec5_reset_and_seek_work_on_a_live_match_with_only_its_kick_off(clock):
    """Before: max() of an empty sequence, a 500 for REST and 'Something went wrong' on the
    WebSocket for anyone pressing restart right after a live match started."""
    s, feed, demo = _live_session_with_only_kick_off(clock)
    s.reset()
    s.seek(0)
    assert s.playback()["clock_s"] == 0.0 and not s.ended and s.next_index == 0
    for e in demo[1:40]:
        feed.put(e.model_dump_json())
    for _ in range(50):
        clock.t += 10
        s.advance()
    assert s.next_index == 40  # the match plays on as the stream arrives


# --- EC-6: Ask takes JSON only ----------------------------------------------------------------


@pytest.mark.parametrize("media", ["text/plain", "application/x-www-form-urlencoded", None])
def test_ec6_ask_refuses_bodies_a_cross_site_form_could_send(client, media):
    """Before: a text/plain POST (no CORS preflight) from any page was answered, spending the
    visitor's Ask bucket (and model calls when the AI switch is on)."""
    headers = {"content-type": media} if media else {}
    r = client.post("/api/ask", content=b'{"chip": "score"}', headers=headers)
    assert r.status_code == 415 and r.json() == {"detail": "Send the question as JSON."}
    ok = client.post(
        "/api/ask", content=b'{"chip": "score"}', headers={"content-type": "application/json; charset=utf-8"}
    )
    assert ok.status_code == 200


# --- EC-7 and held up: names from feeds in any script ------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["Amá Kofi", "Zoë Angélique", "محمد العلي", "李 小龙", "O’Neil", "Zoë Ångström"],
)
def test_ec7_invented_names_in_other_scripts_and_decomposed_accents_are_accepted(name):
    """Before: 'Amá' typed as a + combining accent was refused while the same name with a
    single 'á' passed."""
    import unicodedata

    from matchmind.ingest.roster import check_name

    assert check_name(name, "Player name") == unicodedata.normalize("NFC", name)


@pytest.mark.parametrize(
    "name",
    ["Ama‮evil", "Jo​hn", "A" * 41, "Robert<script>", "x", "Name‏"],
)
def test_held_up_bidi_zero_width_markup_and_huge_names_are_refused(name):
    from matchmind.ingest.roster import check_name

    with pytest.raises(ValueError):
        check_name(name, "Player name")


# --- Held up: wall-clock time (UTC, midnight, DST, leap day) -----------------------------------

EXAMPLES = DEMO.parents[1] / "examples"


def _csv_feed_with_kickoff(tmp_path, kickoff: str):
    import json as _json

    import yaml

    from matchmind.ingest.feed import load_feed

    mapping = yaml.safe_load((EXAMPLES / "mapping.yaml").read_text(encoding="utf-8"))
    mapping["kickoff"] = kickoff
    path = tmp_path / "mapping.json"
    path.write_text(_json.dumps(mapping, default=str), encoding="utf-8")
    return load_feed(EXAMPLES / "feed.csv", roster=EXAMPLES / "roster.yaml", mapping=path)


@pytest.mark.parametrize(
    "kickoff, first_day, last_day",
    [
        ("2028-02-29T23:30:00Z", "2028-02-29", "2028-03-01"),  # leap day, across midnight
        ("2026-12-31T23:15:00Z", "2026-12-31", "2027-01-01"),  # new year
        # UK clocks go back at 01:00 UTC on 25 Oct 2026: a local +01:00 kick-off at 01:30 is
        # 00:30 UTC, and the match runs on in UTC with no repeated hour.
        ("2026-10-25T01:30:00+01:00", "2026-10-25", "2026-10-25"),
        ("2026-03-29T00:30:00+00:00", "2026-03-29", "2026-03-29"),  # clocks go forward
    ],
)
def test_held_up_feed_timestamps_stay_utc_and_ordered_across_midnight_dst_and_leap_day(
    tmp_path, kickoff, first_day, last_day
):
    from datetime import UTC

    feed = _csv_feed_with_kickoff(tmp_path, kickoff)
    ts = [e.ts for e in feed.events]
    assert all(t.utcoffset().total_seconds() == 0 for t in ts)  # type: ignore[union-attr]
    assert ts == sorted(ts)
    assert ts[0].astimezone(UTC).date().isoformat() == first_day
    assert ts[-1].astimezone(UTC).date().isoformat() == last_day


def test_held_up_mixed_offsets_across_dst_are_ordered_in_utc_not_by_local_text():
    """01:59+01:00 then 01:00+00:00 reads backwards on a wall clock but is one minute later
    in UTC: accepted. The reverse (later local text, earlier instant) is refused."""
    from datetime import datetime

    from matchmind.ingest import IngestError, validate_events
    from matchmind.simulator.publisher import read_jsonl

    demo = read_jsonl(DEMO)
    i = 50
    a = demo[i - 1].model_copy(update={"ts": datetime.fromisoformat("2026-10-25T01:59:00+01:00")})
    b = demo[i].model_copy(update={"ts": datetime.fromisoformat("2026-10-25T01:00:00+00:00")})
    early = [
        e.model_copy(update={"ts": datetime.fromisoformat("2026-10-25T00:00:00+00:00")})
        for e in demo[: i - 1]
    ]
    late = [
        e.model_copy(update={"ts": datetime.fromisoformat("2026-10-25T03:00:00+00:00")})
        for e in demo[i + 1 :]
    ]
    validate_events([*early, a, b, *late])
    b_bad = demo[i].model_copy(
        update={"ts": datetime.fromisoformat("2026-10-25T02:30:00+02:00")}
    )  # 00:30 UTC
    with pytest.raises(IngestError, match="ts runs backwards"):
        validate_events([*early, a, b_bad, *late])


# --- Held up: per-connection isolation ---------------------------------------------------------


def test_held_up_one_viewers_choices_never_reach_another(client, clock):
    with client.websocket_connect("/ws/match") as a, client.websocket_connect("/ws/match") as b:
        a.receive_json()
        b.receive_json()
        a.send_json({"action": "set_view", "spoilers": False, "language": "ar", "persona": "tactical"})
        types_a = [a.receive_json()["type"] for _ in range(3)]
        assert types_a == ["PROFILE_CHANGED", "PERSONA_CHANGED", "INITIAL_SNAPSHOT"]
        clock.t += 1
        b.send_json({"action": "seek", "clock_s": 2800, "period": 2})
        snap_b = b.receive_json()  # b's next message is the seek snapshot: nothing of a's
        assert snap_b["type"] == "INITIAL_SNAPSHOT"
        assert snap_b["data"]["profile"]["spoilers"] is True and snap_b["data"]["profile"]["language"] == "en"
        assert snap_b["data"]["home_score"] == 1
        snap_a = a.receive_json()
        assert snap_a["data"]["home_score"] is None and snap_a["data"]["profile"]["language"] == "ar"
