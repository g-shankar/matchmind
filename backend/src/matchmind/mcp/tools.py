"""The PitchPulse MCP tool registry.

Each tool is one `ToolSpec`: a name, a description, a closed pydantic input
model, an output model, and a handler that calls the same accessor the REST
API uses (`matchmind.api.reads`). Adding a tool is one `register(...)` line:

    register(ToolSpec("get_cue_sheet", "Cue sheet", "...", CueSheetIn, CueSheetOut,
                      lambda ctx, a: reads.cue_sheet(ctx.hub, a.persona)))

All tools are read-only. Only `ask_studio` takes free text (see docs/ASK.md).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from matchmind.api import reads

from . import models as m


@dataclass(frozen=True)
class ToolContext:
    """What a handler may use: the shared hub (one live match session)."""

    hub: reads.HubLike


Handler = Callable[[ToolContext, Any], Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Handler


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in REGISTRY:
        raise ValueError(f"MCP tool {spec.name!r} is registered twice")
    REGISTRY[spec.name] = spec
    return spec


# --- Handlers: each one is a thin call into matchmind.api.reads ---------------------------------


async def _snapshot(ctx: ToolContext, a: m.NoInput) -> dict[str, Any]:
    return await reads.snapshot(ctx.hub)


async def _moments(ctx: ToolContext, a: m.ListMomentsIn) -> dict[str, Any]:
    found = reads.bookmarks(ctx.hub, a.kind, a.period, a.from_clock_s, a.to_clock_s, a.played_only, a.limit)
    return {"count": len(found), "moments": found}


async def _moment(ctx: ToolContext, a: m.MomentIn) -> dict[str, Any]:
    return await reads.moment_detail(ctx.hub, a.moment_id)


async def _card(ctx: ToolContext, a: m.CardIn) -> dict[str, Any]:
    return await reads.moment_card(ctx.hub, a.moment_id, a.persona, a.language, a.favourite_team)


async def _recap(ctx: ToolContext, a: m.RecapIn) -> dict[str, Any]:
    return await reads.recap(ctx.hub, a.persona, a.language)


async def _cue_sheet(ctx: ToolContext, a: m.CueSheetIn) -> dict[str, Any]:
    return await reads.cue_sheet(ctx.hub, a.persona, a.language, a.favourite_team, a.since_seq, a.limit)


async def _players(ctx: ToolContext, a: m.PlayerStatsIn) -> dict[str, Any]:
    if a.player_id is None:
        return {"players": await reads.players(ctx.hub)}
    return {"players": [await reads.player(ctx.hub, a.player_id)]}


async def _teams(ctx: ToolContext, a: m.NoInput) -> dict[str, Any]:
    return await reads.teams(ctx.hub)


async def _crew(ctx: ToolContext, a: m.CrewIn) -> dict[str, Any]:
    status = await reads.crew_status(ctx.hub)
    traces = await reads.crew_traces(ctx.hub, a.trace_limit) if a.trace_limit else []
    return {"status": status, "traces": traces}


async def _auto_eventing(ctx: ToolContext, a: m.NoInput) -> dict[str, Any]:
    return reads.auto_eventing(ctx.hub)


async def _events(ctx: ToolContext, a: m.EventsIn) -> dict[str, Any]:
    events = await reads.recent_events(ctx.hub, a.limit)
    return {"count": len(events), "events": events}


async def _metric_registry(ctx: ToolContext, a: m.NoInput) -> dict[str, Any]:
    return reads.metric_registry()


async def _basic_stats(ctx: ToolContext, a: m.NoInput) -> dict[str, Any]:
    return await reads.basic_stats(ctx.hub)


async def _simulate(ctx: ToolContext, a: m.SimulateIn) -> dict[str, Any]:
    return await reads.simulate(a.seed, a.home)


async def _ask(ctx: ToolContext, a: m.AskIn) -> dict[str, Any]:
    if (a.question is None) == (a.chip is None):
        raise HTTPException(status_code=400, detail="Send a question or a chip.")
    return await reads.ask(ctx.hub, a.question, a.chip, a.language, a.spoilers)


# --- The tools ----------------------------------------------------------------------------------

_SYNTHETIC = " All clubs, players and matches are fictional and synthetic."

register(ToolSpec(
    "get_match_snapshot", "Match snapshot",
    "The live match as a viewer joining now sees it: clock, score, rolling team state, "
    "control/chaos, playback, recent overlay cards, moment bookmarks, player stats, crew status, "
    "languages and the auto-eventing check. Same payload as GET /api/match/snapshot." + _SYNTHETIC,
    m.NoInput, m.SnapshotOut, _snapshot,
))  # fmt: skip
register(ToolSpec(
    "list_moments", "List moments",
    "Bookmarked moments of the match (goals, cards, big chances, better options, unfound runs, "
    "momentum swings, pressure spells, milestones), earliest first, filtered by kind, half or "
    "match clock. Bookmarks cover the whole match; set played_only for moments already played.",
    m.ListMomentsIn, m.MomentsOut, _moments,
))  # fmt: skip
register(ToolSpec(
    "get_moment", "Get moment facts",
    "One moment with its facts (the only numbers any agent may state about it), the analyst's "
    "evidence and the source event ids it was spotted from. No persona, no model call.",
    m.MomentIn, m.MomentDetailOut, _moment,
))  # fmt: skip
register(ToolSpec(
    "get_overlay_card", "Get overlay card",
    "The fact-checked overlay card for one moment, voiced for a persona and language. "
    "Same payload as GET /api/match/moment/{moment_id}.",
    m.CardIn, m.OverlayCard, _card,
))  # fmt: skip
register(ToolSpec(
    "get_recap", "Get recap",
    "The fact-checked match recap so far for a persona and language. Same payload as "
    "GET /api/match/recap.",
    m.RecapIn, m.Recap, _recap,
))  # fmt: skip
register(ToolSpec(
    "get_cue_sheet", "Cue sheet",
    "The broadcast cue sheet so far for a persona and language: numbered show, update, retract, "
    "supersede and clear cues per graphics layer, including VAR corrections. Page with since_seq. "
    "Same payload as GET /api/match/cue-sheet.",
    m.CueSheetIn, m.CueSheetOut, _cue_sheet,
))  # fmt: skip
register(ToolSpec(
    "get_player_stats", "Player stats",
    "Stats engine numbers so far for one fictional player (by id, e.g. NBR-9) or for everyone "
    "involved, home side first. Same rows as GET /api/match/players.",
    m.PlayerStatsIn, m.PlayersOut, _players,
))  # fmt: skip
register(ToolSpec(
    "get_basic_stats", "Basic match stats",
    "Counting stats so far per team and per fictional player: possession, pass accuracy with its "
    "denominator, shots and on target, tackles, interceptions, PPDA, and distance and top speed "
    "estimated from synthetic tracking. Same payload as GET /api/match/stats/basic.",
    m.NoInput, m.BasicStatsOut, _basic_stats,
))  # fmt: skip
register(ToolSpec(
    "get_metric_registry", "Metric registry",
    "Every metric the stats engine computes: formula, units, source events, window, range, "
    "quality flag and limitations, plus the metrics it does not compute. Same payload as "
    "GET /api/metrics.",
    m.NoInput, m.MetricRegistryOut, _metric_registry,
))  # fmt: skip
register(ToolSpec(
    "get_team_rosters", "Team rosters",
    "Both fictional clubs: names, colours, formation, style and squad. Same payload as GET /api/teams.",
    m.NoInput, m.TeamsOut, _teams,
))  # fmt: skip
register(ToolSpec(
    "get_crew_status", "Crew status and traces",
    "The studio crew's mode (template or AI), breakers, counts and translator state, plus the "
    "latest per-moment agent traces. Same as GET /api/crew/status and GET /api/crew/trace.",
    m.CrewIn, m.CrewOut, _crew,
))  # fmt: skip
register(ToolSpec(
    "get_auto_eventing", "Auto-eventing scorecard",
    "How well events detected from synthetic tracking (not video) match the simulator's own "
    "events. Same payload as GET /api/auto-eventing.",
    m.NoInput, m.AutoEventingStatus, _auto_eventing,
))  # fmt: skip
register(ToolSpec(
    "get_recent_events", "Recent events",
    "The latest events played at the live position, oldest first, each with its stats engine "
    "metrics, in the MATCH_TICK event shape.",
    m.EventsIn, m.EventsOut, _events,
))  # fmt: skip
register(ToolSpec(
    "simulate_match", "Simulate a synthetic match",
    "Simulate a new seeded match between the two fictional clubs and summarise it with the "
    "stats engine: score, goals and the full-time state. Same seed, same match. Results are "
    "cached; new seeds are rate limited." + _SYNTHETIC,
    m.SimulateIn, m.SimulationOut, _simulate,
))  # fmt: skip

register(ToolSpec(
    "ask_studio", "Ask the studio",
    "Ask one question about this match in plain words (or pick a suggested chip) and get a short "
    "answer built from stats engine numbers as of the playback clock, with its facts, evidence, "
    "claims and source event ids. Questions that are off-topic, about real people, or try to change "
    "the rules are refused in one sentence. Set spoilers false for catch-up mode. Same payload as "
    "POST /api/ask." + _SYNTHETIC,
    m.AskIn, m.AskAnswer, _ask,
))  # fmt: skip

# Planned (not built here; each will be one register(...) line when its accessor lands):
# export_dataset, audit_claims. See docs/MCP.md.
PLANNED_TOOLS: tuple[str, ...] = ("export_dataset", "audit_claims")
