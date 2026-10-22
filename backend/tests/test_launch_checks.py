"""Findings from the launch checks (qa/launch-checks/report.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import FakeClock, FakeCrew, FakeStats, make_events
from matchmind.api import app as app_mod
from matchmind.api.app import create_app
from matchmind.api.session import Engines, MatchSession

READS = [
    "/api/teams",
    "/api/match/snapshot",
    "/api/match/players",
    "/api/match/bookmarks",
    "/api/crew/status",
    "/api/languages",
    "/api/crew/trace",
    "/api/metrics",
    "/api/match/stats/basic",
    "/api/auto-eventing",
    "/api/source",
]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(clock, tmp_path):
    session = MatchSession(
        make_events(), engines=Engines(stats=FakeStats, crew=FakeCrew), clock=clock, base_rate=10
    )
    app = create_app(
        session=session,
        tick_interval=None,
        allowed_origins=["http://localhost:5173"],
        static_dir=tmp_path / "none",
        clock=clock,
    )
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", READS)
def test_lc1_one_address_cannot_loop_on_the_open_read_routes(client, clock, path):
    # LC-1: one address looping on a read route (each builds a JSON payload) slowed every
    # other viewer on a single core. Reads now have their own generous per-IP bucket.
    codes = [client.get(path).status_code for _ in range(app_mod.READ_BURST + 5)]
    # (The test match has no auto-eventing benchmark, so that route answers 404, not 200.)
    assert 429 not in codes[: app_mod.READ_BURST]
    assert set(codes[app_mod.READ_BURST :]) == {429}
    assert client.get(path).json() == {"detail": app_mod.TOO_MANY}
    clock.t += 1
    assert client.get(path).status_code != 429


def test_lc1_reads_share_one_bucket_and_health_stays_open(client, clock):
    for i in range(app_mod.READ_BURST):
        assert client.get(READS[i % len(READS)]).status_code != 429
    assert client.get("/api/match/players").status_code == 429
    # The platform's health probes must never be refused, and the paid-path bucket is separate.
    assert all(client.get("/api/health").status_code == 200 for _ in range(app_mod.READ_BURST * 2))
    assert client.get("/api/match/recap").status_code == 200


def test_lc1_other_addresses_keep_their_own_bucket(client, clock, monkeypatch):
    monkeypatch.setattr(app_mod, "TRUST_FORWARDED_FOR", True)
    flood = {"x-forwarded-for": "203.0.113.7"}
    for _ in range(app_mod.READ_BURST):
        client.get("/api/match/snapshot", headers=flood)
    assert client.get("/api/match/snapshot", headers=flood).status_code == 429
    # A spoofed left entry buys nothing; a different real address is unaffected.
    spoof = {"x-forwarded-for": "198.51.100.1, 203.0.113.7"}
    assert client.get("/api/match/snapshot", headers=spoof).status_code == 429
    other = {"x-forwarded-for": "203.0.113.8"}
    assert client.get("/api/match/snapshot", headers=other).status_code == 200
