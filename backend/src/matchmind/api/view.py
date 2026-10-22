"""Engine output -> the JSON payloads in docs/API-CONTRACT.md.

Only fields listed in the contract leave the server. Ground-truth labels,
freeze frames, tracking frames and line-ups stay inside.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from matchmind.crew.contracts import CrewStatus, MomentBundle, OverlayCard, ViewerProfile
from matchmind.crew.languages import language_list
from matchmind.schema import Event
from matchmind.simulator.teams import Team
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

from .session import Bookmark, MatchSession, Tick

METRIC_KEYS = (
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
)


def _xy(p: Any) -> dict[str, float] | None:
    return {"x": p.x, "y": p.y} if p is not None else None


def metrics_payload(metrics: EventMetrics | None) -> dict[str, Any]:
    data = metrics.model_dump() if metrics is not None else {}
    return {
        k: data.get(k, False if k in ("progressive", "sprint", "fast_shot") else None) for k in METRIC_KEYS
    }


def event_payload(event: Event, metrics: EventMetrics | None) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "seq": event.seq,
        "match_clock": event.match_clock,
        "clock_s": event.clock_s,
        "period": event.period,
        "type": str(event.type),
        "team": event.team,
        "player_id": event.player_id,
        "receiver_id": event.receiver_id,
        "start": _xy(event.start),
        "end": _xy(event.end),
        "outcome": str(event.outcome) if event.outcome is not None else None,
        "under_pressure": event.under_pressure,
        "details": dict(event.details),
        "metrics": metrics_payload(metrics),
    }


def state_payload(snapshot: MatchStateSnapshot) -> dict[str, Any]:
    return snapshot.model_dump()


def control_chaos_payload(snapshot: MatchStateSnapshot) -> dict[str, Any]:
    """Compatibility shape for the existing ControlChaosGauge."""
    return {
        "home_control_pct": snapshot.home.possession_pct,
        "away_control_pct": snapshot.away.possession_pct,
        "chaos_index": snapshot.control_chaos,
        "current_tempo": snapshot.tempo,
        "rolling_momentum_home": snapshot.momentum,
    }


def player_payload(stats: PlayerStats) -> dict[str, Any]:
    data = stats.model_dump()
    data["pass_accuracy"] = stats.pass_accuracy
    return data


def team_payload(team: Team) -> dict[str, Any]:
    return {
        "team_id": team.team_id,
        "name": team.name,
        "short_name": team.short_name or team.team_id,
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "formation": team.formation,
        "style": team.style,
        "players": [
            {
                "player_id": p.player_id,
                "name": p.name,
                "number": p.number,
                "position": p.position,
                "line": p.line,
            }
            for p in team.players
        ],
    }


def teams_payload(session: MatchSession) -> dict[str, Any]:
    return {
        "home": team_payload(session.teams[session.home_id]),
        "away": team_payload(session.teams[session.away_id]),
    }


def card_payload(card: OverlayCard) -> dict[str, Any]:
    return card.model_dump(mode="json")


def bookmark_payload(bookmark: Bookmark) -> dict[str, Any]:
    return asdict(bookmark)


def moment_detail_payload(bundle: MomentBundle, played: bool) -> dict[str, Any]:
    """A spotted moment with the facts and evidence behind it, before any persona voices it."""
    return {
        "moment": bundle.moment.model_dump(mode="json"),
        "explanation": bundle.explanation.model_dump(mode="json"),
        "replay": bundle.replay,
        "played": played,
    }


def languages_payload(status: CrewStatus) -> list[dict[str, Any]]:
    """Every language with its source (studio pack or Azure AI Translator) and
    whether it can be shown right now."""
    return [info.model_dump() for info in language_list(status.translator.available)]


def snapshot_payload(session: MatchSession, profile: ViewerProfile) -> dict[str, Any]:
    """INITIAL_SNAPSHOT.data for one viewer profile."""
    snap = session.snapshot
    home, away = session.score
    crew = session.crew_status()
    return {
        "match_id": session.match_id,
        "clock": session.match_clock,
        "period": session.period,
        "home_score": home,
        "away_score": away,
        "teams": teams_payload(session),
        "state": state_payload(snap),
        "control_chaos": control_chaos_payload(snap),
        "profile": profile.model_dump(),
        "playback": session.playback(),
        "recent_cards": [card_payload(c) for c in session.cards_for(session.recent_bundles(), profile)],
        "bookmarks": [bookmark_payload(b) for b in session.bookmarks],
        "players": [player_payload(p) for p in session.players()],
        "crew": crew.model_dump(),
        "languages": languages_payload(crew),
        "auto_eventing": session.auto_eventing,
    }


def tick_shared(tick: Tick) -> dict[str, Any]:
    """The part of MATCH_TICK.data that is the same for every viewer."""
    return {
        "event": event_payload(tick.event, tick.metrics),
        "clock": tick.event.match_clock,
        "period": tick.event.period,
        "score": {"home": tick.score_home, "away": tick.score_away},
        "state": state_payload(tick.snapshot),
        "control_chaos": control_chaos_payload(tick.snapshot),
        "players_changed": [player_payload(p) for p in tick.players_changed],
    }


def message(type_: str, data: Any) -> dict[str, Any]:
    return {"type": type_, "data": data}
