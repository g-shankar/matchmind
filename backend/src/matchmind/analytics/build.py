"""Turn one match's events into star-schema rows.

The stats engine runs over the events in order (its numbers become the metric and
state columns), and the rule-based Spotter reads the same numbers to produce the
moments. No model is called, so the output is a pure function of the events.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from matchmind.crew.spotter import Spotter
from matchmind.schema import Event, EventType
from matchmind.simulator.teams import Team, get_team
from matchmind.stats.metrics import to_attacking
from matchmind.stats.models import EventMetrics, MatchStateSnapshot
from matchmind.stats.state import StatsEngine

from .labels import decision_rows
from .schema import BY_NAME, MATCHES, TEAMS

Row = dict[str, Any]


def jdump(value: Any) -> str:
    """Compact JSON with sorted keys: the same value always gives the same text."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class MatchRows:
    match_id: str
    home: str
    away: str
    tables: dict[str, list[Row]] = field(default_factory=dict)


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(float(x), nd)


def _clock_label(e: Event) -> int:
    return int(e.clock_s // 60)


def _event_row(e: Event, m: EventMetrics, snap: MatchStateSnapshot, home: str, away: str) -> Row:
    team = e.team
    att = to_attacking((e.start.x, e.start.y), team, home) if team and e.start else None
    return {
        "match_id": e.match_id,
        "event_id": e.event_id,
        "seq": e.seq,
        "ts": e.ts,
        "period": e.period,
        "clock_s": e.clock_s,
        "match_clock": e.match_clock,
        "minute": _clock_label(e),
        "five_min_bucket": int(e.clock_s // 300) * 5,
        "type": e.type.value,
        "team_id": team,
        "opponent_id": (away if team == home else home) if team else None,
        "is_home": (team == home) if team else None,
        "player_id": e.player_id,
        "receiver_id": e.receiver_id,
        "possession_id": e.possession_id,
        "start_x": e.start.x if e.start else None,
        "start_y": e.start.y if e.start else None,
        "end_x": e.end.x if e.end else None,
        "end_y": e.end.y if e.end else None,
        "att_start_x": _r(att[0], 2) if att else None,
        "att_start_y": _r(att[1], 2) if att else None,
        "outcome": e.outcome.value if e.outcome else None,
        "body_part": e.body_part.value if e.body_part else None,
        "ball_speed_mps": e.ball_speed_mps,
        "player_speed_mps": e.player_speed_mps,
        "under_pressure": e.under_pressure,
        "pressure_count": len(e.pressure_players),
        "pass_type": str(e.details["pass_type"]) if "pass_type" in e.details else None,
        "details_json": jdump(e.details),
        "truth_labels": "|".join(e.labels) if e.labels else None,
        "pitch_zone": m.pitch_zone,
        "pass_distance_m": m.pass_distance_m,
        "pass_difficulty": m.pass_difficulty,
        "progressive": m.progressive,
        "forward_m": m.forward_m,
        "ball_speed_kmh": m.ball_speed_kmh,
        "player_speed_kmh": m.player_speed_kmh,
        "sprint": m.sprint,
        "fast_shot": m.fast_shot,
        "xg": m.chance_quality,
        "distance_to_goal_m": m.distance_to_goal_m,
        "xt_delta": m.xt_delta,
        "has_better_option": m.better_option is not None,
        "has_unfound_run": m.unfound_run is not None,
        "score_home": snap.score_home,
        "score_away": snap.score_away,
        "xg_home": snap.xg_home,
        "xg_away": snap.xg_away,
        "shots_home": snap.shots_home,
        "shots_away": snap.shots_away,
        "momentum": snap.momentum,
        "pressure_home": snap.home.pressure_index,
        "pressure_away": snap.away.pressure_index,
        "possession_home_pct": snap.home.possession_pct,
        "control_chaos": snap.control_chaos,
        "tempo": snap.tempo,
    }


def _better_option_rows(e: Event, m: EventMetrics) -> list[Row]:
    rows: list[Row] = []
    base = {"match_id": e.match_id, "event_id": e.event_id, "clock_s": e.clock_s}
    base.update(match_clock=e.match_clock, period=e.period, team_id=e.team)
    bo, ur = m.better_option, m.unfound_run
    if bo is not None:
        rows.append(
            {
                **base,
                "trigger": "shot_vs_pass",
                "player_id": bo.shooter_id,
                "teammate_id": bo.teammate_id,
                "shot_xg": bo.shot_chance_quality,
                "alt_xg": bo.alt_chance_quality,
                "pass_success": bo.pass_success,
                "alt_value": bo.alt_value,
                "times_better": bo.times_better,
                "xg_gain": round(bo.alt_value - bo.shot_chance_quality, 3),
                "pass_distance_m": bo.pass_distance_m,
                "nearest_marker_m": bo.nearest_marker_m,
                "shooter_x": bo.shooter_pos.x,
                "shooter_y": bo.shooter_pos.y,
                "teammate_x": bo.teammate_pos.x,
                "teammate_y": bo.teammate_pos.y,
                "keeper_x": bo.keeper.x if bo.keeper else None,
                "keeper_y": bo.keeper.y if bo.keeper else None,
                "defenders_json": jdump([d.model_dump() for d in bo.defenders]),
            }
        )
    if ur is not None:
        rows.append(
            {
                **base,
                "trigger": "unfound_run",
                "player_id": ur.carrier_id,
                "teammate_id": ur.runner_id,
                "pass_on_clock": ur.pass_on_clock,
                "pass_on_at_s": ur.pass_on_at_s,
                "clear_of_line_m": ur.clear_of_line_m,
                "projected_xg": ur.projected_chance_quality,
                "one_on_one": ur.one_on_one,
                "shooter_x": ur.carrier_pos.x,
                "shooter_y": ur.carrier_pos.y,
                "teammate_x": ur.target.x,
                "teammate_y": ur.target.y,
                "defenders_json": jdump([d.model_dump() for d in ur.defenders_at_pass]),
                "runner_path_json": jdump([p.model_dump() for p in ur.runner_path]),
            }
        )
    return rows


def _moment_rows(match_id: str, moments) -> tuple[list[Row], list[Row]]:
    rows: list[Row] = []
    facts: list[Row] = []
    for mo in moments:
        rows.append(
            {
                "match_id": match_id,
                "moment_id": mo.moment_id,
                "kind": mo.kind.value,
                "event_id": mo.source_event_ids[0] if mo.source_event_ids else None,
                "clock_s": mo.clock_s,
                "match_clock": mo.match_clock,
                "period": mo.period,
                "team_id": mo.team,
                "player_id": mo.player_ids[0] if mo.player_ids else None,
                "priority": mo.priority,
                "player_ids_json": jdump(mo.player_ids),
                "source_event_ids_json": jdump(mo.source_event_ids),
                "facts_json": jdump(mo.facts),
            }
        )
        for key in sorted(mo.facts):
            v = mo.facts[key]
            facts.append(
                {
                    "match_id": match_id,
                    "moment_id": mo.moment_id,
                    "fact_key": key,
                    "value_text": str(v).lower() if isinstance(v, bool) else str(v),
                    "value_num": None if isinstance(v, str) else float(v),
                }
            )
    return rows, facts


def _sum(rows: list[Row], col: str) -> float:
    return sum(r[col] for r in rows if r[col] is not None)


def _player_rows(match_id: str, engine: StatsEngine, ev: list[Row]) -> list[Row]:
    by_player: dict[str, list[Row]] = defaultdict(list)
    for r in ev:
        if r["player_id"]:
            by_player[r["player_id"]].append(r)
    out: list[Row] = []
    for pid, p in engine.players().items():
        mine = by_player.get(pid, [])
        passes = [r for r in mine if r["type"] == EventType.PASS.value]
        diffs = [r["pass_difficulty"] for r in passes if r["pass_difficulty"] is not None]
        out.append(
            {
                "match_id": match_id,
                "player_id": pid,
                "team_id": p.team,
                "touches": p.touches,
                "passes": p.passes,
                "passes_completed": p.passes_completed,
                "pass_accuracy": p.pass_accuracy,
                "key_passes": p.key_passes,
                "shots": p.shots,
                "goals": p.goals,
                "assists": p.assists,
                "xg": p.xg,
                "xa": p.xa,
                "tackles_won": p.tackles_won,
                "interceptions": p.interceptions,
                "top_speed_kmh": p.top_speed_kmh,
                "sprints": p.sprints,
                "carry_distance_m": p.carry_distance_m,
                "distance_km": p.distance_km,
                "progressive_actions": sum(
                    1 for r in mine if r["progressive"] and r["type"] in ("pass", "carry")
                ),
                "avg_pass_difficulty": round(sum(diffs) / len(diffs), 1) if diffs else None,
                "xt_total": round(_sum(mine, "xt_delta"), 3),
                "better_option_shots": sum(1 for r in mine if r["has_better_option"]),
                "unfound_runs": sum(1 for r in mine if r["has_unfound_run"]),
            }
        )
    return out


def _team_rows(
    match_id: str, home: str, away: str, ev: list[Row], final: MatchStateSnapshot, moments
) -> list[Row]:
    goals = {home: final.score_home, away: final.score_away}
    out: list[Row] = []
    completed_all = sum(1 for r in ev if r["type"] == "pass" and r["outcome"] == "complete")
    for team, opp in ((home, away), (away, home)):
        mine = [r for r in ev if r["team_id"] == team]
        passes = [r for r in mine if r["type"] == "pass"]
        done = [r for r in passes if r["outcome"] == "complete"]
        shots = [r for r in mine if r["type"] == "shot"]
        pressure_col = "pressure_home" if team == home else "pressure_away"
        pressure = [r[pressure_col] for r in ev]
        cards = [r for r in mine if r["type"] == "card"]
        gf, ga = goals[team], goals[opp]
        out.append(
            {
                "match_id": match_id,
                "team_id": team,
                "opponent_id": opp,
                "is_home": team == home,
                "goals": gf,
                "goals_against": ga,
                "points": 3 if gf > ga else 1 if gf == ga else 0,
                "shots": len(shots),
                "xg": round(_sum(shots, "xg"), 3),
                "xg_against": round(
                    _sum([r for r in ev if r["team_id"] == opp and r["type"] == "shot"], "xg"), 3
                ),
                "passes": len(passes),
                "passes_completed": len(done),
                "pass_accuracy": round(100 * len(done) / len(passes), 1) if passes else 0.0,
                "possession_pct": round(100 * len(done) / completed_all, 1) if completed_all else 50.0,
                "progressive_passes": sum(1 for r in passes if r["progressive"]),
                "sprints": sum(1 for r in mine if r["sprint"]),
                "tackles_won": sum(1 for r in mine if r["type"] == "tackle" and r["outcome"] == "won"),
                "interceptions": sum(1 for r in mine if r["type"] == "interception"),
                "fouls": sum(1 for r in mine if r["type"] == "foul"),
                "yellow_cards": sum(1 for r in cards if '"card":"yellow"' in r["details_json"]),
                "red_cards": sum(1 for r in cards if '"card":"red"' in r["details_json"]),
                "peak_pressure_index": max(pressure, default=0.0),
                "avg_pressure_index": round(sum(pressure) / len(pressure), 1) if pressure else 0.0,
                "better_option_shots": sum(1 for r in mine if r["has_better_option"]),
                "moments": sum(1 for mo in moments if mo.team == team),
            }
        )
    return out


def process_match(events: list[Event]) -> MatchRows:
    """Run the stats engine and the Spotter over one match; return every table's rows."""
    if not events:
        raise ValueError("no events")
    events = sorted(events, key=lambda e: e.seq)
    start = next((e for e in events if e.type == EventType.MATCH_START), events[0])
    home, away = str(start.details.get("home", "")), str(start.details.get("away", ""))
    if not home or not away:
        raise ValueError(f"{start.match_id}: the first event must be a match_start naming home and away")
    teams = {t: get_team(t) for t in (home, away)}
    match_id = start.match_id

    engine = StatsEngine(match_id, home, away)
    spotter = Spotter(teams)
    ev_rows: list[Row] = []
    metrics_list: list[EventMetrics] = []
    snaps_before: list[MatchStateSnapshot | None] = []
    moments = []
    better: list[Row] = []
    prev: MatchStateSnapshot | None = None
    snap: MatchStateSnapshot | None = None
    for e in events:
        m = engine.process(e)
        snap = engine.snapshot()
        moments += spotter.spot(e, m, snap, engine.players())
        ev_rows.append(_event_row(e, m, snap, home, away))
        better += _better_option_rows(e, m)
        metrics_list.append(m)
        snaps_before.append(prev)
        prev = snap
    assert snap is not None

    moment_rows, fact_rows = _moment_rows(match_id, moments)
    scripted = any(label.startswith("scripted:") for e in events for label in e.labels)
    seed = start.details.get("seed")
    match_row: Row = {
        "match_id": match_id,
        "home_team_id": home,
        "away_team_id": away,
        "kickoff_utc": events[0].ts,
        "seed": int(seed) if isinstance(seed, int | float) else None,
        "scripted": scripted,
        "score_home": snap.score_home,
        "score_away": snap.score_away,
        "xg_home": snap.xg_home,
        "xg_away": snap.xg_away,
        "events": len(events),
        "moments": len(moments),
    }
    assert set(match_row) == set(MATCHES.names)
    tables = {
        "matches": [match_row],
        "events": ev_rows,
        "moments": moment_rows,
        "moment_facts": fact_rows,
        "better_options": better,
        "player_match": _player_rows(match_id, engine, ev_rows),
        "team_match": _team_rows(match_id, home, away, ev_rows, snap, moments),
        "decision_labels": decision_rows(events, metrics_list, snaps_before, home),
    }
    # Shots and passes (and the two better-option triggers) fill different columns: pad with nulls.
    padded = {
        name: [{c: r.get(c) for c in BY_NAME[name].names} for r in rows] for name, rows in tables.items()
    }
    return MatchRows(match_id, home, away, padded)


def team_rows(team_ids: list[str]) -> list[Row]:
    out = []
    for tid in sorted(team_ids):
        t: Team = get_team(tid)
        row = {
            "team_id": t.team_id,
            "name": t.name,
            "short_name": t.short_name or t.team_id,
            "formation": t.formation,
            "strength": t.strength,
            "primary_color": t.primary_color,
            "secondary_color": t.secondary_color,
            "style": t.style,
        }
        assert set(row) == set(TEAMS.names)
        out.append(row)
    return out


def player_rows(team_ids: list[str]) -> list[Row]:
    out = []
    for tid in sorted(team_ids):
        for p in sorted(get_team(tid).players, key=lambda p: p.player_id):
            out.append(
                {
                    "player_id": p.player_id,
                    "team_id": tid,
                    "name": p.name,
                    "shirt_number": p.number,
                    "position": p.position,
                    "line": p.line,
                    "base_x": p.base[0],
                    "base_y": p.base[1],
                }
            )
    return out


def build_tables(matches: list[list[Event]]) -> dict[str, list[Row]]:
    """Every table for many matches, in a stable order (matches by id, events by seq)."""
    processed = [process_match(m) for m in matches]
    clubs = sorted({t for pm in processed for t in (pm.home, pm.away)})
    tables: dict[str, list[Row]] = {
        "teams": team_rows(clubs),
        "players": player_rows(clubs),
    }
    for name in (
        "matches",
        "events",
        "moments",
        "moment_facts",
        "better_options",
        "player_match",
        "team_match",
        "decision_labels",
    ):
        tables[name] = [row for pm in processed for row in pm.tables[name]]
    return tables
