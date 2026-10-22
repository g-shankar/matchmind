"""Engine output -> the JSON payloads in docs/API-CONTRACT.md.

Only fields listed in the contract leave the server. Ground-truth labels,
freeze frames, tracking frames and line-ups stay inside.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from matchmind.crew.contracts import CrewStatus, OverlayCard, ViewerProfile
from matchmind.crew.languages import language_list
from matchmind.schema import Event
from matchmind.simulator.teams import Team, get_team
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


def player_identity(player_id: str, team_id: str) -> dict[str, Any]:
    """Name, shirt number and position from our fictional squads (None when unknown)."""
    try:
        p = get_team(team_id).player(player_id)
    except KeyError:
        return {"name": None, "number": None, "position": None}
    return {"name": p.name, "number": p.number, "position": p.position}


def player_payload(stats: PlayerStats) -> dict[str, Any]:
    data = stats.model_dump()
    data["pass_accuracy"] = stats.pass_accuracy
    data.update(player_identity(stats.player_id, stats.team))
    return data


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def basic_stats_payload(session: MatchSession) -> dict[str, Any]:
    """GET /api/match/stats/basic: plain counting stats per team and per player,
    with the denominators beside the percentages (docs/METRICS.md)."""
    from matchmind.stats.physical import LABEL as TRACKING_LABEL

    totals = session.team_totals()
    players = session.players()
    completed = {t: tt.passes_completed for t, tt in totals.items()}
    all_completed = sum(completed.values())
    tracked = any(p.physical_source == "synthetic_tracking" for p in players)
    teams: dict[str, Any] = {}
    for team_id in (session.home_id, session.away_id):
        t = totals.get(team_id)
        squad = [p for p in players if p.team == team_id]
        if t is None:
            continue
        teams[team_id] = {
            "team_id": team_id,
            "name": session.teams[team_id].name,
            "possession_pct": _pct(completed[team_id], all_completed) if all_completed else 50.0,
            "passes_completed": t.passes_completed,
            "passes_attempted": t.passes,
            "pass_accuracy_pct": _pct(t.passes_completed, t.passes),
            "shots": t.shots,
            "shots_on_target": t.shots_on_target,
            "goals": t.goals,
            "tackles_won": t.tackles_won,
            "tackles_attempted": t.tackles_won + t.tackles_lost,
            "interceptions": t.interceptions,
            "fouls": t.fouls,
            "ppda": t.ppda,
            "ppda_opponent_passes": t.ppda_opponent_passes,
            "ppda_defensive_actions": t.ppda_defensive_actions,
            "distance_km": round(sum(p.distance_km for p in squad), 1),
            "top_speed_kmh": max((p.top_speed_kmh for p in squad), default=0.0),
        }
    return {
        "match_id": session.match_id,
        "clock": session.match_clock,
        "period": session.period,
        "pass_accuracy_denominator": "every pass attempt (passes out of play included)",
        "physical_source": "synthetic_tracking" if tracked else "event_estimate",
        "physical_label": TRACKING_LABEL if tracked else "Estimated from event positions (lower bound)",
        "teams": teams,
        "players": [
            {
                "player_id": p.player_id,
                "team": p.team,
                **player_identity(p.player_id, p.team),
                "passes_completed": p.passes_completed,
                "passes_attempted": p.passes,
                "pass_accuracy_pct": _pct(p.passes_completed, p.passes),
                "shots": p.shots,
                "shots_on_target": p.shots_on_target,
                "goals": p.goals,
                "tackles_won": p.tackles_won,
                "tackles_attempted": p.tackles_attempted,
                "interceptions": p.interceptions,
                "distance_km": round(p.distance_km, 2),
                "sprints": p.sprints,
                "top_speed_kmh": p.top_speed_kmh,
            }
            for p in players
        ],
    }


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
