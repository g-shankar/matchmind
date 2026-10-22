"""Read-only accessors shared by the REST routes (`app.py`) and the MCP tools
(`matchmind.mcp`). Each one returns exactly the JSON-ready payload of
docs/API-CONTRACT.md, so the two surfaces cannot drift apart: REST serialises
it, MCP hands it back as structured content.

Every accessor takes the shared `Hub` (one live session for everybody) and
uses the same locks the routes always used. Problems are raised as
`HTTPException` with a plain-words detail; the MCP layer passes that detail on
as the tool error text.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol, TypeVar

from fastapi import HTTPException

from matchmind.crew.contracts import Language, Persona, ViewerProfile, is_world_language

from . import view
from .session import CUE_PAGE_MAX, MatchSession

T = TypeVar("T")

MOMENT_ID_MAX = 80
NO_MOMENT = "We could not find that moment."
NO_CLUB = "That club is not in this match."
NO_PLAYER = "That player is not in this match."
NO_PLAYER_STATS = "That player has not been involved yet. Try again later in the match."
AUTO_EVENTING_SOON = "Auto-eventing is coming soon."
MAX_EVENTS_WINDOW = 100


class HubLike(Protocol):
    @property
    def session(self) -> MatchSession: ...
    async def run(self, fn: Callable[..., T], *args: Any) -> T: ...
    async def run_crew(self, fn: Callable[..., T], *args: Any) -> T: ...


# --- Match --------------------------------------------------------------------------------------


async def teams(hub: HubLike) -> dict[str, Any]:
    return view.teams_payload(hub.session)


async def snapshot(hub: HubLike, spoilers: bool = True) -> dict[str, Any]:
    """INITIAL_SNAPSHOT.data for the default viewer profile (GET /api/match/snapshot);
    `spoilers=False` is the catch-up view, without the result."""
    return await hub.run_crew(view.snapshot_payload, hub.session, ViewerProfile(spoilers=spoilers))


async def players(hub: HubLike) -> list[dict[str, Any]]:
    session = hub.session
    return await hub.run(lambda: [view.player_payload(p) for p in session.players()])


async def player(hub: HubLike, player_id: str) -> dict[str, Any]:
    """One player's stats so far, by fictional player id."""
    session = hub.session
    if not session.is_known_player(player_id):
        raise HTTPException(status_code=404, detail=NO_PLAYER)
    for p in await players(hub):
        if p["player_id"] == player_id:
            return p
    raise HTTPException(status_code=404, detail=NO_PLAYER_STATS)


def bookmarks(
    hub: HubLike,
    kind: str | None = None,
    period: int | None = None,
    from_clock_s: float | None = None,
    to_clock_s: float | None = None,
    played_only: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Every bookmarkable moment of the match, earliest first (GET /api/match/bookmarks),
    optionally narrowed. With no filters this is the REST list as-is."""
    session = hub.session
    out = []
    for b in session.bookmarks:
        if kind is not None and b.kind != kind:
            continue
        if period is not None and b.period != period:
            continue
        if from_clock_s is not None and b.clock_s < from_clock_s:
            continue
        if to_clock_s is not None and b.clock_s > to_clock_s:
            continue
        if played_only and not session.is_played(b.moment_id):
            continue
        out.append(view.bookmark_payload(b))
        if limit is not None and len(out) >= limit:
            break
    return out


async def recent_events(hub: HubLike, limit: int) -> list[dict[str, Any]]:
    """The last `limit` events played (oldest first), in the MATCH_TICK `event` shape."""
    session = hub.session
    limit = max(1, min(int(limit), MAX_EVENTS_WINDOW))
    window = await hub.run(session.recent_events, limit)
    return [view.event_payload(event, metrics) for event, metrics in window]


# --- Moments, cards and recaps ------------------------------------------------------------------


def _check_moment_id(moment_id: str) -> None:
    if len(moment_id) > MOMENT_ID_MAX:
        raise HTTPException(status_code=404, detail=NO_MOMENT)


def profile_for(hub: HubLike, persona: Persona, lang: Language, favourite_team: str | None) -> ViewerProfile:
    if favourite_team is not None and not hub.session.is_known_team(favourite_team):
        raise HTTPException(status_code=400, detail=NO_CLUB)
    return ViewerProfile(persona=persona, language=lang, favourite_team=favourite_team)


async def cue_sheet(
    hub: HubLike,
    persona: Persona,
    lang: Language,
    favourite_team: str | None,
    since_seq: int = 0,
    limit: int = CUE_PAGE_MAX,
) -> dict[str, Any]:
    """The compiled cue sheet so far for one audience (docs/CUE-SHEET.md). Template text only,
    so it never calls a paid service; compiled off the event loop and cached per position."""
    profile = profile_for(hub, persona, lang, favourite_team)
    return await asyncio.to_thread(hub.session.cue_sheet, profile, since_seq, limit)


async def moment_detail(hub: HubLike, moment_id: str) -> dict[str, Any]:
    """A moment with its facts, evidence and source event ids (no persona, no model call)."""
    _check_moment_id(moment_id)
    session = hub.session
    bundle = session.bundle(moment_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail=NO_MOMENT)
    played = await hub.run(session.is_played, moment_id)
    return view.moment_detail_payload(bundle, played)


async def moment_card(
    hub: HubLike,
    moment_id: str,
    persona: Persona = "casual",
    lang: Language = "en",
    favourite_team: str | None = None,
) -> dict[str, Any]:
    """GET /api/match/moment/{id}: the overlay card for one persona and language."""
    _check_moment_id(moment_id)
    profile = profile_for(hub, persona, lang, favourite_team)
    # Moments are fixed at load and the crew is thread-safe: no lock, so a slow
    # model answer here holds up nobody else.
    card = await asyncio.to_thread(hub.session.card_for_moment, moment_id, profile)
    if card is None:
        raise HTTPException(status_code=404, detail=NO_MOMENT)
    return view.card_payload(card)


async def recap(
    hub: HubLike, persona: Persona = "casual", lang: Language = "en", spoilers: bool = True
) -> dict[str, Any]:
    """GET /api/match/recap. `spoilers=False`: the spoiler-free story so far."""
    session = hub.session
    profile = ViewerProfile(persona=persona, language=lang, spoilers=spoilers)
    if not is_world_language(lang):
        result = await hub.run_crew(session.recap, profile)
        return result.model_dump(mode="json")
    # World language: the English recap under the crew lock (quick), then the
    # Translator call with no lock held, so a slow translator never stalls playback.
    english, moments, snap = await hub.run_crew(session.recap_source, profile)
    result = await asyncio.to_thread(session.translate_recap, english, moments, snap, profile)
    return result.model_dump(mode="json")


# --- Crew and checks ----------------------------------------------------------------------------


async def crew_status(hub: HubLike) -> dict[str, Any]:
    return (await hub.run(hub.session.crew_status)).model_dump()


async def crew_traces(hub: HubLike, limit: int) -> list[dict[str, Any]]:
    traces = await hub.run(hub.session.crew_traces, limit)
    return [t.model_dump() for t in traces]


async def languages(hub: HubLike) -> dict[str, Any]:
    status = await hub.run(hub.session.crew_status)
    return {"languages": view.languages_payload(status), "translator": status.translator.model_dump()}


# --- Metric registry and basic stats ------------------------------------------------------------


def metric_registry() -> dict[str, Any]:
    """GET /api/metrics: every metric we compute, how, and the ones we do not."""
    from matchmind.stats.registry import registry_payload

    return registry_payload()


async def basic_stats(hub: HubLike, spoilers: bool = True) -> dict[str, Any]:
    """GET /api/match/stats/basic: counting stats per team and per player, match so far.
    In catch-up mode (`spoilers` false) goals are null: team goals are the score."""
    return await hub.run(view.basic_stats_payload, hub.session, spoilers)


def auto_eventing(hub: HubLike) -> dict[str, Any]:
    result = hub.session.auto_eventing
    if result is None:
        raise HTTPException(status_code=404, detail=AUTO_EVENTING_SOON)
    return result


# --- Ask the studio (docs/ASK.md) -------------------------------------------------------------


def ask_context(session: MatchSession):
    """The match as of the live position, copied so the answer can be composed (and a
    model consulted) with no session lock held. Nothing after the clock is included."""
    from matchmind.ask import AskContext

    players = [p.model_copy() for p in session.players()]
    tracked = any(p.physical_source == "synthetic_tracking" for p in players)
    return AskContext(
        match_id=session.match_id,
        clock=session.match_clock,
        clock_s=session.clock_s,
        period=session.period,
        ended=bool(session.playback().get("ended")),
        home_id=session.home_id,
        away_id=session.away_id,
        teams=dict(session.teams),
        snapshot=session.snapshot.model_copy(deep=True),
        players=players,
        moments=session.moments_so_far(),
        team_totals=view.basic_stats_payload(session)["teams"],
        physical_source="synthetic_tracking" if tracked else "event_estimate",
    )


def _metric_info() -> dict[str, Any]:
    from matchmind.ask.service import MetricInfo
    from matchmind.stats.registry import registry_payload

    return {
        m["id"]: MetricInfo(id=m["id"], name=m["name"], formula=m["formula"], quality=m["quality"])
        for m in registry_payload()["metrics"]
    }


async def ask(
    hub: HubLike,
    question: str | None,
    chip: str | None,
    lang: Language = "en",
    spoilers: bool = True,
    client: str = "local",
) -> dict[str, Any]:
    """POST /api/ask and the `ask_studio` MCP tool: one answer as of the playback clock.
    `client` keys the optional model path's per-client quota (docs/ASK.md)."""
    from matchmind.ask import ask as ask_studio
    from matchmind.crew.llm import ai_enabled

    session = hub.session
    ctx = await hub.run(ask_context, session)
    llm = getattr(session.crew, "llm", None) if ai_enabled() else None
    ctx = replace(ctx, ai_crew=llm is not None)
    answer = await asyncio.to_thread(
        lambda: ask_studio(
            ctx,
            question=question,
            chip=chip,
            language=lang,
            spoilers=spoilers,
            llm=llm,
            metric_info=_metric_info(),
            client=client,
        )
    )
    return answer.model_dump(mode="json")


# --- A fresh synthetic match --------------------------------------------------------------------

SIM_SEED_MIN, SIM_SEED_MAX = 1, 99_999
SIM_MAX_EVENTS = 10_000  # a simulated match has about 2,300; anything past this is refused
SIM_CACHE_SIZE = 64
SIM_BURST, SIM_PER_SECOND = 4, 0.5  # new simulations (cache misses) for the whole process
SIM_BUSY = "The match simulator is busy. Try again in a few seconds."


class _SimGuard:
    """Bounds the cost of simulating: one at a time, a small process-wide rate for new
    seeds, and an LRU cache so repeated seeds cost nothing."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.lock = threading.Lock()
        self.cache: OrderedDict[tuple[int, str], dict[str, Any]] = OrderedDict()
        self.tokens = float(SIM_BURST)
        self.last = clock()

    def cached(self, key: tuple[int, str]) -> dict[str, Any] | None:
        with self.lock:
            hit = self.cache.get(key)
            if hit is not None:
                self.cache.move_to_end(key)
            return hit

    def take(self) -> bool:
        with self.lock:
            now = self.clock()
            self.tokens = min(SIM_BURST, self.tokens + (now - self.last) * SIM_PER_SECOND)
            self.last = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    def store(self, key: tuple[int, str], value: dict[str, Any]) -> None:
        with self.lock:
            self.cache[key] = value
            self.cache.move_to_end(key)
            while len(self.cache) > SIM_CACHE_SIZE:
                self.cache.popitem(last=False)


SIM_GUARD = _SimGuard()
_SIM_RUN_LOCK = threading.Lock()  # one simulation at a time per process


def simulate_summary(seed: int, home: str = "NBR") -> dict[str, Any]:
    """Simulate a new seeded synthetic match (fictional clubs) and summarise it with the
    stats engine. Pure for a given seed and home side; cached; rate limited on new seeds."""
    from matchmind.schema import EventType
    from matchmind.simulator.engine import MatchEngine
    from matchmind.simulator.script import random_script
    from matchmind.simulator.teams import TEAMS
    from matchmind.stats.state import StatsEngine

    if not (SIM_SEED_MIN <= seed <= SIM_SEED_MAX):
        raise HTTPException(status_code=400, detail=f"Pick a seed from {SIM_SEED_MIN} to {SIM_SEED_MAX}.")
    if home not in TEAMS:
        raise HTTPException(status_code=400, detail=NO_CLUB)
    key = (seed, home)
    hit = SIM_GUARD.cached(key)
    if hit is not None:
        return hit
    if not SIM_GUARD.take():
        raise HTTPException(status_code=429, detail=SIM_BUSY)
    if not _SIM_RUN_LOCK.acquire(timeout=5):
        raise HTTPException(status_code=429, detail=SIM_BUSY)
    try:
        away = next(t for t in TEAMS if t != home)
        match_id = f"MM-SIM-{seed:05d}-{home}"
        events = MatchEngine(random_script(match_id, home=home, away=away), seed).run()
        if len(events) > SIM_MAX_EVENTS:
            raise HTTPException(status_code=500, detail="That simulation ran too long. Try another seed.")
        stats = StatsEngine(match_id, home, away)
        for event in events:
            stats.process(event)
        final = stats.snapshot()
        goals = [
            {
                "event_id": e.event_id,
                "match_clock": e.match_clock,
                "period": e.period,
                "team": e.team,
                "player_id": e.player_id,
            }
            for e in events
            if e.type == EventType.SHOT and e.outcome is not None and str(e.outcome) == "goal"
        ]
        summary = {
            "source": "synthetic_simulator",
            "match_id": match_id,
            "seed": seed,
            "home": view.team_payload(TEAMS[home]),
            "away": view.team_payload(TEAMS[away]),
            "score_home": final.score_home,
            "score_away": final.score_away,
            "events": len(events),
            "goals": goals,
            "final_state": view.state_payload(final),
        }
    finally:
        _SIM_RUN_LOCK.release()
    SIM_GUARD.store(key, summary)
    return summary


async def simulate(seed: int, home: str = "NBR") -> dict[str, Any]:
    """`simulate_summary` off the event loop."""
    return await asyncio.to_thread(simulate_summary, seed, home)
