"""MCP vs direct engine reads, across several positions of the seeded demo match.

Every registered tool is called through a real MCP client session (Streamable HTTP over
the ASGI app, in process) and compared with the same value read straight from the
session, the stats engine and the view layer, never a REST route (`api.reads` only builds
the Ask context and the simulator summary). Score, team state, player stats, event metrics
and simulated matches are also recomputed with a fresh `StatsEngine` from kick-off. Numbers must be
exactly equal, type included (an int never matches a float).

The fact-checker is not an MCP tool: the crew calls it in process. What is checked here
is that it gives the same verdict on facts served over MCP as on the engine's own facts.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import anyio
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from matchmind.api import reads, view
from matchmind.api.app import create_app
from matchmind.api.session import MatchSession
from matchmind.crew.contracts import ViewerProfile
from matchmind.crew.fact_checker import check
from matchmind.mcp import REGISTRY
from matchmind.stats.state import StatsEngine

BASE = "http://localhost:8000"
ALLOWED = "http://localhost:5173"
# (clock_s, period): early, late first half, early second half, late, full time (None).
POSITIONS = [(12 * 60, 1), (40 * 60, 1), (52 * 60, 2), (78 * 60, 2), (None, None)]
MOMENTS_PER_POSITION = 4


@pytest.fixture(autouse=True)
def _fresh_sim_guard(monkeypatch):
    monkeypatch.setattr(reads, "SIM_GUARD", reads._SimGuard())


@pytest.fixture(scope="module")
def session() -> MatchSession:
    from matchmind.mcp.__main__ import load

    return load(None, None)  # the bundled seeded demo match, template crew


@asynccontextmanager
async def connected(app):
    async with app.router.lifespan_context(app):
        http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE)
        async with http:
            transport = streamable_http_client(f"{BASE}/mcp", http_client=http, terminate_on_close=False)
            async with Client(transport) as client:
                yield client


def _json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _steady(payload: Any) -> Any:
    """Without the crew's rolling service levels (`health`): wall-clock latencies."""
    if isinstance(payload, dict):
        return {k: _steady(v) for k, v in payload.items() if k != "health"}
    if isinstance(payload, list):
        return [_steady(v) for v in payload]
    return payload


def assert_exact(got: Any, want: Any, path: str = "$") -> None:
    """Deep equality where every number must match in value and in type."""
    if isinstance(want, dict):
        assert isinstance(got, dict), path
        assert set(got) == set(want), (path, set(got) ^ set(want))
        for k in want:
            assert_exact(got[k], want[k], f"{path}.{k}")
    elif isinstance(want, list):
        assert isinstance(got, list) and len(got) == len(want), path
        for i, (g, w) in enumerate(zip(got, want, strict=True)):
            assert_exact(g, w, f"{path}[{i}]")
    else:
        assert type(got) is type(want), (path, got, want)
        assert got == want, (path, got, want)


def replayed(session: MatchSession) -> tuple[Any, list]:
    """A fresh stats engine, with the match's synthetic tracking timeline attached, fed
    every event played so far; and each event's metrics."""
    stats = StatsEngine(session.match_id, session.home_id, session.away_id)
    if session.physical is not None:
        stats.attach_physical(session.physical)
    played = session.events[: session.next_index]
    return stats, [stats.process(e) for e in played]


def _moment_ids(session: MatchSession, n: int = MOMENTS_PER_POSITION) -> list[str]:
    """Up to `n` played moments spread across the match so far."""
    played = [m.moment_id for m in session.moments_so_far()]
    if len(played) <= n:
        return played
    step = len(played) / n
    return [played[int(i * step)] for i in range(n)]


def direct_cases(session: MatchSession) -> list[tuple[str, dict, Any]]:
    """(tool, arguments, direct-read function) for every tool at the current position."""
    from matchmind.ask import ask as ask_studio
    from matchmind.stats.registry import registry_payload

    fresh, metrics = replayed(session)
    player_id = session.players()[0].player_id
    profile = ViewerProfile()

    def players_direct():
        by_id = fresh.players()
        return [view.player_payload(by_id[p.player_id]) for p in session.players()]

    def moment(mid):
        def go():
            b = session.bundle(mid)
            return view.moment_detail_payload(b, session.is_played(mid))

        return go

    def card(mid):
        def go():
            p = ViewerProfile(persona="tactical", language="es")
            return view.card_payload(session.card_for_moment(mid, p))

        return go

    def ask(**kw):
        def go():
            ctx = replace(reads.ask_context(session), ai_crew=False)
            info = reads._metric_info()
            return ask_studio(ctx, llm=None, metric_info=info, client="mcp", **kw).model_dump(mode="json")

        return go

    def simulate():
        from matchmind.simulator.engine import MatchEngine
        from matchmind.simulator.script import random_script

        events = MatchEngine(random_script("MM-SIM-00007-HCY", home="HCY", away="NBR"), 7).run()
        engine = StatsEngine("MM-SIM-00007-HCY", "HCY", "NBR")
        for e in events:
            engine.process(e)
        final = engine.snapshot()
        out = reads.simulate_summary(7, "HCY")
        assert (out["score_home"], out["score_away"], out["events"]) == (
            final.score_home,
            final.score_away,
            len(events),
        )
        assert_exact(_json(out["final_state"]), _json(view.state_payload(final)))
        return out

    def basic_stats():
        out = view.basic_stats_payload(session)
        totals = fresh.team_totals()
        for team_id, row in out["teams"].items():
            t = totals[team_id]
            assert (row["passes_completed"], row["passes_attempted"], row["shots"], row["goals"]) == (
                t.passes_completed,
                t.passes,
                t.shots,
                t.goals,
            )
        return out

    def snapshot():
        snap = fresh.snapshot()
        out = view.snapshot_payload(session, profile)
        assert (out["home_score"], out["away_score"]) == (snap.score_home, snap.score_away)
        assert_exact(_json(out["state"]), _json(view.state_payload(snap)))
        assert_exact(_json(out["players"]), _json(players_direct()))
        return out

    played_ids = {m.moment_id for m in session.moments_so_far()}
    cases: list[tuple[str, dict, Any]] = [
        ("get_match_snapshot", {}, snapshot),
        ("list_moments", {}, lambda: {"count": len(session.bookmarks),
                                      "moments": [view.bookmark_payload(b) for b in session.bookmarks]}),
        ("list_moments", {"played_only": True}, lambda: (lambda rows: {"count": len(rows), "moments": rows})(
            [view.bookmark_payload(b) for b in session.bookmarks if b.moment_id in played_ids])),
        ("get_recap", {"persona": "fantasy", "language": "fr"},
         lambda: view.recap_payload(session.recap(ViewerProfile(persona="fantasy", language="fr")))),
        ("get_cue_sheet", {"persona": "tactical", "language": "es", "since_seq": 0, "limit": 20},
         lambda: session.cue_sheet(ViewerProfile(persona="tactical", language="es"), 0, 20)),
        ("get_player_stats", {}, lambda: {"players": players_direct()}),
        ("get_player_stats", {"player_id": player_id},
         lambda: {"players": [p for p in players_direct() if p["player_id"] == player_id]}),
        ("get_team_rosters", {}, lambda: view.teams_payload(session)),
        ("get_basic_stats", {}, basic_stats),
        ("get_basic_stats", {"spoilers": False}, lambda: view.basic_stats_payload(session, False)),
        ("get_metric_registry", {}, registry_payload),
        ("get_crew_status", {"trace_limit": 5}, lambda: {
            "status": session.crew_status().model_dump(),
            "traces": [t.model_dump() for t in session.crew_traces(5)]}),
        ("get_auto_eventing", {}, lambda: session.auto_eventing),
        ("get_recent_events", {"limit": 5}, lambda: {"count": min(5, len(metrics)), "events": [
            view.event_payload(e, mm) for e, mm in
            zip(session.events[: session.next_index][-5:], metrics[-5:], strict=True)]}),
        ("simulate_match", {"seed": 7, "home": "HCY"}, simulate),
        ("ask_studio", {"question": "Who has the most passes?", "language": "es"},
         ask(question="Who has the most passes?", language="es")),
        ("ask_studio", {"chip": "score", "language": "en", "spoilers": False},
         ask(chip="score", language="en", spoilers=False)),
    ]  # fmt: skip
    for mid in _moment_ids(session):
        cases.append(("get_moment", {"moment_id": mid}, moment(mid)))
        cases.append(
            ("get_overlay_card", {"moment_id": mid, "persona": "tactical", "language": "es"}, card(mid))
        )
    return cases


async def _compare_at(session: MatchSession, app) -> set[str]:
    seen: set[str] = set()
    async with connected(app) as client:
        for name, args, direct in direct_cases(session):
            result = await client.call_tool(name, args)
            assert not result.is_error, (name, args, result.content)
            want = _json(_steady(await anyio.to_thread.run_sync(direct)))
            assert_exact(_steady(result.structured_content), want, f"{name}{args}")
            seen.add(name)
    return seen


@pytest.mark.parametrize(("clock_s", "period"), POSITIONS, ids=lambda v: str(v))
def test_every_tool_matches_direct_engine_reads(session, clock_s, period):
    if clock_s is None:
        session.play_to_end()
    else:
        session.seek(clock_s, period)
    session.is_running = False
    assert session.moments_so_far(), "each position has played moments"
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED])
    seen = anyio.run(_compare_at, session, app)
    assert seen == set(REGISTRY), "every registered tool needs a direct-read case"


def test_fact_checker_verdicts_match_on_mcp_served_facts(session):
    """The checker run on facts fetched over `get_moment` gives the same verdict, reason
    for reason, as on the engine's own facts: for the shown text and for tampered text."""
    session.seek(78 * 60, 2)
    session.is_running = False
    app = create_app(session=session, tick_interval=None, allowed_origins=[ALLOWED])
    ids = _moment_ids(session, 10)  # stays inside the per-client read burst
    roster = session.crew.protected_names

    async def fetch():
        async with connected(app) as client:
            return {mid: (await client.call_tool("get_moment", {"moment_id": mid})).structured_content
                    for mid in ids}  # fmt: skip

    served = anyio.run(fetch)
    rejected = 0
    for mid in ids:
        bundle = session.bundle(mid)
        mcp_facts = served[mid]["moment"]["facts"]
        texts = [bundle.explanation.why, f"{bundle.explanation.why} It was 9137 metres out."]
        for text in filter(None, texts):
            for strict in (False, True):
                direct = check(text, bundle.moment.facts, "en", "why", strict_words=strict, roster=roster)
                via_mcp = check(text, mcp_facts, "en", "why", strict_words=strict, roster=roster)
                assert via_mcp == direct, (mid, text)
                rejected += not direct.ok
    assert rejected, "the tampered text must be rejected on both paths"
