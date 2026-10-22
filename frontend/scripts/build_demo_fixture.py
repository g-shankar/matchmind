"""Record the offline demo fixture for the PitchPulse web app.

Reads one synthetic match (JSONL from the Matchmind simulator) and writes
`frontend/public/demo/demo-match.json`: every match tick, every studio moment
and the full-match recaps, in the same shapes the live WebSocket server sends
(see `frontend/src/api/contract.ts`). The browser's offline demo mode replays
this file when no server is reachable.

Everything here is deterministic: same input, byte-identical output. All
numbers come from `matchmind.stats.metrics` and the rules below; every number
written into a text is also listed in that moment's evidence, and the script
checks this before it writes the file.

Run from the repository root:

    python frontend/scripts/build_demo_fixture.py
"""

# Template text in three languages is kept on one line per string for review.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

from matchmind.simulator import pitch
from matchmind.simulator.teams import get_team
from matchmind.stats import metrics as M

REPO = Path(__file__).resolve().parents[2]
DEFAULT_IN = REPO / "backend" / "data" / "matches" / "MM-DEMO-001.jsonl"
DEFAULT_OUT = REPO / "frontend" / "public" / "demo" / "demo-match.json"

FIXTURE_VERSION = 1
PERSONAS = ("casual", "tactical", "fantasy")
LANGS = ("en", "es", "ar")

# Rolling state
WINDOW_S = 300.0
MIN_WINDOW_S = 60.0
MOMENTUM_TAU_S = 60.0
CHAIN_MID = 3.5
TURNOVER_MID = 3.6
# Spotter rules
BIG_CHANCE_CQ = 0.3
PRESSURE_SPELL_LEVEL = 70
PRESSURE_SPELL_S = 180.0
SWING_MIN = 40.0
SWING_SD = 1.5
SWING_MIN_SAMPLES = 50
SWING_GAP_S = 300.0
SPEED_BURST_MS = 8.5
HARD_PASS_LEVEL = 70
PITCH_TAG_GAP_S = 20.0
# Better option / unfound run
BETTER_MARGIN = 0.10
BETTER_RATIO = 1.8
MIN_MARKER_M = 7.0  # same "unmarked" rule as the stats engine
RUN_ONSIDE_TOL_M = 0.3
RUN_BEYOND_M = 1.5
RUN_LOOKAHEAD_S = 1.0
RUN_LANE_MIN = 0.6
RUN_MIN_CHANCE = 0.2

ON_BALL = {"pass", "carry", "dribble", "shot", "interception", "tackle", "clearance", "recovery"}
DURATION = {"lower_third": 8, "side_panel": 12, "full_screen": 15, "pitch_tag": 5}

NOTES = (
    "Synthetic match, invented clubs and players. distance_km counts on-ball distance (carries and "
    "dribbles) plus tracked runs in behind only; the engine has no full-match player tracking. "
    "xt_delta is not computed yet (null). Rolling state uses a 5-minute window of match clock."
)


# --------------------------------------------------------------- helpers


def rnd(x: float, d: int = 2) -> float:
    v = round(float(x), d)
    return 0.0 if v == 0 else v


def fmt_clock(clock_s: float, period: int) -> str:
    base = 2700 if period == 1 else 5400
    s = int(clock_s)
    if s >= base:
        extra = s - base
        return f"{base // 60}+{extra // 60}:{extra % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


def xy(p: tuple[float, float]) -> dict[str, float]:
    return {"x": rnd(p[0]), "y": rnd(p[1])}


class Ctx:
    """Match-wide lookups: teams, names, frames."""

    def __init__(self, home_id: str, away_id: str) -> None:
        self.home_id = home_id
        self.away_id = away_id
        self.teams = {home_id: get_team(home_id), away_id: get_team(away_id)}
        self.players = {p.player_id: p for t in self.teams.values() for p in t.players}

    def att(self, p: dict[str, float] | tuple[float, float], team: str) -> tuple[float, float]:
        pos = (p["x"], p["y"]) if isinstance(p, dict) else p
        return M.to_attacking(pos, team, self.home_id)

    def absolute(self, p: tuple[float, float], team: str) -> tuple[float, float]:
        return p if team == self.home_id else pitch.flip(p)

    def other(self, team: str) -> str:
        return self.away_id if team == self.home_id else self.home_id

    def short(self, team: str) -> str:
        return self.teams[team].short_name

    def surname(self, pid: str) -> str:
        return self.players[pid].name.split()[-1]

    def team_info(self, team: str) -> dict[str, Any]:
        t = self.teams[team]
        return {
            "team_id": t.team_id,
            "name": t.name,
            "short_name": t.short_name,
            "primary_color": t.primary_color,
            "secondary_color": t.secondary_color,
            "formation": t.formation,
            "style": t.style,
            "players": [
                {
                    "player_id": p.player_id,
                    "name": p.name,
                    "number": p.number,
                    "position": p.position,
                    "line": p.line,
                }
                for p in t.players
            ],
        }


# --------------------------------------------------------- event metrics


def shot_model(ev: dict, ctx: Ctx) -> dict[str, Any]:
    team = ev["team"]
    shooter = ctx.att(ev["start"], team)
    ff = ev.get("freeze_frame") or []
    outfield = [ctx.att(p, team) for p in ff if not p["teammate"] and not p["keeper"]]
    keeper = next((ctx.att(p, team) for p in ff if not p["teammate"] and p["keeper"]), None)
    blockers = M.blockers_in_cone(shooter, outfield)
    on_line = M.keeper_on_line(shooter, keeper)
    header = ev.get("body_part") == "head"
    cq = M.chance_quality(shooter, header=header, blockers=blockers, keeper_on_line=on_line)
    return {
        "pos": shooter,
        "cq": cq,
        "blockers": blockers,
        "keeper_on_line": on_line,
        "header": header,
        "distance": round(pitch.distance_to_goal(shooter), 1),
    }


def event_metrics(ev: dict, ctx: Ctx, shot: dict | None) -> dict[str, Any]:
    t = ev["type"]
    team = ev.get("team")
    start, end = ev.get("start"), ev.get("end")
    m: dict[str, Any] = {
        "pass_distance_m": None,
        "pass_difficulty": None,
        "progressive": False,
        "ball_speed_kmh": M.kmh(ev.get("ball_speed_mps")),
        "player_speed_kmh": M.kmh(ev.get("player_speed_mps")),
        "sprint": (ev.get("player_speed_mps") or 0.0) >= M.SPRINT_MS,
        "fast_shot": t == "shot" and (ev.get("ball_speed_mps") or 0.0) >= M.FAST_SHOT_MS,
        "chance_quality": None,
        "distance_to_goal_m": None,
        "pitch_zone": None,
        "xt_delta": None,
    }
    if team and start:
        s = ctx.att(start, team)
        m["pitch_zone"] = M.zone(*s)
        if end and t in ("pass", "carry"):
            e = ctx.att(end, team)
            m["progressive"] = M.is_progressive(s, e)
        if end and t == "pass":
            e = ctx.att(end, team)
            dist = pitch.dist(s, e)
            m["pass_distance_m"] = round(dist, 1)
            m["pass_difficulty"] = M.pass_difficulty(
                dist,
                len(ev.get("pressure_players") or []),
                e[0] - s[0],
                e[0],
                str(ev.get("details", {}).get("pass_type", "")),
            )
    if shot is not None:
        m["chance_quality"] = shot["cq"]
        m["distance_to_goal_m"] = shot["distance"]
    return m


def public_event(ev: dict, metrics: dict) -> dict[str, Any]:
    """Only the contract fields: labels, freeze frames and tracking never leave the engine."""

    def pt(p: dict | None) -> dict | None:
        return None if p is None else {"x": rnd(p["x"], 1), "y": rnd(p["y"], 1)}

    return {
        "event_id": ev["event_id"],
        "seq": ev["seq"],
        "match_clock": ev["match_clock"],
        "clock_s": rnd(ev["clock_s"]),
        "period": ev["period"],
        "type": ev["type"],
        "team": ev.get("team"),
        "player_id": ev.get("player_id"),
        "receiver_id": ev.get("receiver_id"),
        "start": pt(ev.get("start")),
        "end": pt(ev.get("end")),
        "outcome": ev.get("outcome"),
        "under_pressure": bool(ev.get("under_pressure")),
        "details": dict(ev.get("details") or {}),
        "metrics": metrics,
    } | (
        {"reviewed_event_id": ev["reviewed_event_id"], "review_reason": ev.get("review_reason")}
        if ev.get("reviewed_event_id")
        else {}
    )


# ------------------------------------------------- better option / run


def analyse_shot(ev: dict, ctx: Ctx, shot: dict) -> dict[str, Any] | None:
    """The shot taken versus the best pass that was on (NEXT-STEPS 2.1)."""
    team = ev["team"]
    ff = ev.get("freeze_frame") or []
    s = shot["pos"]
    opponents = [ctx.att(p, team) for p in ff if not p["teammate"]]
    outfield = [ctx.att(p, team) for p in ff if not p["teammate"] and not p["keeper"]]
    keeper = next((ctx.att(p, team) for p in ff if not p["teammate"] and p["keeper"]), None)
    if len(opponents) < 2:
        return None
    second_last = sorted((o[0] for o in opponents), reverse=True)[1]
    best = None
    for p in ff:
        if not p["teammate"] or p["actor"] or p["keeper"]:
            continue
        mate = ctx.att(p, team)
        if mate[0] > max(s[0], second_last):
            continue
        marker = min(pitch.dist(mate, o) for o in opponents)
        if marker < MIN_MARKER_M:
            continue
        success, _lane = M.pass_success_probability(s, mate, opponents)
        mate_cq = M.chance_quality(
            mate, blockers=M.blockers_in_cone(mate, outfield), keeper_on_line=M.keeper_on_line(mate, keeper)
        )
        value = success * mate_cq
        if best is None or value > best["value"]:
            best = {
                "pid": p["player_id"],
                "pos": mate,
                "value": value,
                "success": success,
                "cq": mate_cq,
                "marker": marker,
            }
    if best is None:
        return None
    shot_value = shot["cq"]
    if not (best["value"] >= shot_value + BETTER_MARGIN and best["value"] >= BETTER_RATIO * shot_value):
        return None
    return {
        "shot_event_id": ev["event_id"],
        "shooter_id": ev["player_id"],
        "teammate_id": best["pid"],
        # chance values keep 3 dp so the ratio shown next to them reads true
        "shot_chance_quality": rnd(shot_value, 3),
        "alt_chance_quality": rnd(best["cq"], 3),
        "pass_success": rnd(best["success"]),
        "alt_value": rnd(best["value"], 3),
        "times_better": rnd(best["value"] / shot_value, 1),
        "pass_distance_m": rnd(pitch.dist(s, best["pos"]), 1),
        "nearest_marker_m": rnd(best["marker"], 1),
        "shooter_pos": xy(ctx.absolute(s, team)),
        "teammate_pos": xy(ctx.absolute(best["pos"], team)),
        "defenders": [xy(ctx.absolute(o, team)) for o in outfield],
        "keeper": xy(ctx.absolute(keeper, team)) if keeper else None,
    }


def analyse_run(ev: dict, ctx: Ctx) -> dict[str, Any] | None:
    """A run in behind where the through ball was on but never came (NEXT-STEPS 2.1)."""
    frames = ev.get("tracking") or []
    if ev.get("outcome") != "not_found" or len(frames) < 2:
        return None
    team, runner = ev["team"], ev["player_id"]
    carrier = ev.get("details", {}).get("carrier_id")
    info = []
    for f in frames:
        opp = [ctx.att(p, team) for p in f["players"] if not p["teammate"]]
        if len(opp) < 2:
            return None
        line = sorted((o[0] for o in opp), reverse=True)[1]
        rp = next((ctx.att(p, team) for p in f["players"] if p["player_id"] == runner), None)
        cp = next((ctx.att(p, team) for p in f["players"] if p["player_id"] == carrier), None)
        if rp is None:
            return None
        info.append(
            {
                "t": f["t_offset_s"],
                "line": line,
                "runner": rp,
                "ball": ctx.att(f["ball"], team),
                "carrier": cp,
            }
        )
        info[-1]["opp"] = opp
        info[-1]["outfield"] = [
            ctx.att(p, team) for p in f["players"] if not p["teammate"] and not p["keeper"]
        ]
        info[-1]["keeper"] = next(
            (ctx.att(p, team) for p in f["players"] if not p["teammate"] and p["keeper"]), None
        )
    on = None
    for i, fr in enumerate(info):
        later = next((g for g in info[i:] if g["t"] >= fr["t"] + RUN_LOOKAHEAD_S - 1e-6), None)
        if later is None:
            break
        if (
            fr["runner"][0] <= fr["line"] + RUN_ONSIDE_TOL_M
            and later["runner"][0] >= later["line"] + RUN_BEYOND_M
        ):
            success, _ = M.pass_success_probability(fr["ball"], later["runner"], fr["opp"])
            if success >= RUN_LANE_MIN:
                on = (fr, later, success)
                break
    if on is None:
        return None
    last = info[-1]
    blockers = M.blockers_in_cone(last["runner"], last["outfield"])
    projected = M.chance_quality(
        last["runner"], blockers=blockers, keeper_on_line=M.keeper_on_line(last["runner"], last["keeper"])
    )
    if projected < RUN_MIN_CHANCE:
        return None
    fr, later, success = on
    clear = max(g["runner"][0] - g["line"] for g in info)
    carrier_pos = fr["carrier"] if fr["carrier"] is not None else fr["ball"]
    pass_on_at = rnd(fr["t"], 1)
    return {
        "run_event_id": ev["event_id"],
        "runner_id": runner,
        "carrier_id": carrier,
        "found": False,
        "pass_on_at_s": pass_on_at,
        "pass_on_clock": fmt_clock(ev["clock_s"] + pass_on_at, ev["period"]),
        "clear_of_line_m": rnd(clear, 1),
        "projected_chance_quality": rnd(projected),
        "one_on_one": blockers == 0,
        "carrier_pos": xy(ctx.absolute(carrier_pos, team)),
        "runner_path": [xy(ctx.absolute(g["runner"], team)) for g in info],
        "target": xy(ctx.absolute(later["runner"], team)),
        "defenders_at_pass": [xy(ctx.absolute(o, team)) for o in fr["outfield"]],
        "_lane": success,
    }


# ------------------------------------------------------- rolling state


class StateEngine:
    def __init__(self, match_id: str, ctx: Ctx) -> None:
        self.match_id = match_id
        self.ctx = ctx
        self.window: deque[dict] = deque()
        self.period = 1
        self.period_start = 0.0
        self.momentum = 0.0
        self.last_clock = 0.0
        self.score = {ctx.home_id: 0, ctx.away_id: 0}
        self.xg = {ctx.home_id: 0.0, ctx.away_id: 0.0}
        self.shots = {ctx.home_id: 0, ctx.away_id: 0}
        self.prev_poss: tuple[int, str] | None = None
        self.goal_team: dict[str, str] = {}  # counted goals: shot event id -> team

    def start_period(self, period: int, clock: float) -> None:
        self.window.clear()
        self.period = period
        self.period_start = clock
        self.last_clock = clock
        self.prev_poss = None

    def process(self, ev: dict, metrics: dict, cq: float | None) -> None:
        clock = ev["clock_s"]
        team = ev.get("team")
        t = ev["type"]
        if t == "shot" and team:
            self.shots[team] += 1
            self.xg[team] += cq or 0.0
            if ev.get("outcome") == "goal":
                self.score[team] += 1
                self.goal_team[ev["event_id"]] = team
        elif t == "var_review" and ev.get("outcome") == "overturned":
            # The goal comes off the score; the shot and its xG still count (docs/METRICS.md).
            scored = self.goal_team.pop(ev.get("reviewed_event_id") or "", None)
            if scored is not None:
                self.score[scored] -= 1
        if team and t in ON_BALL:
            rec = {"clock": clock, "team": team, "pass": t == "pass", "ft": False, "box": False}
            rec.update(
                {"shot": t == "shot", "xg": cq or 0.0, "poss": ev.get("possession_id"), "turnover": False}
            )
            start, end = ev.get("start"), ev.get("end")
            ok = (
                ev.get("outcome") in ("complete", None) if t != "dribble" else ev.get("outcome") == "complete"
            )
            if end and start and t in ("pass", "carry", "dribble") and ok:
                s, e = self.ctx.att(start, team), self.ctx.att(end, team)
                rec["ft"] = t == "pass" and e[0] >= M.FINAL_THIRD_U
                rec["box"] = pitch.in_box(e) and not pitch.in_box(s)
            poss = ev.get("possession_id")
            if self.prev_poss is not None and poss != self.prev_poss[0] and team != self.prev_poss[1]:
                rec["turnover"] = True
            self.prev_poss = (poss, team)
            self.window.append(rec)
        while self.window and self.window[0]["clock"] < clock - WINDOW_S:
            self.window.popleft()
        # momentum: EMA of the pressure difference over match clock
        dt = max(0.0, clock - self.last_clock)
        self.last_clock = clock
        h, a = self.team_window(self.ctx.home_id), self.team_window(self.ctx.away_id)
        diff = h["pressure_index"] - a["pressure_index"]
        alpha = 1.0 - math.exp(-dt / MOMENTUM_TAU_S)
        self.momentum = pitch.clamp(self.momentum + alpha * (diff - self.momentum), -100.0, 100.0)

    def team_window(self, team: str) -> dict[str, Any]:
        w = self.window
        passes = sum(1 for r in w if r["pass"])
        own_passes = sum(1 for r in w if r["pass"] and r["team"] == team)
        ft_all = sum(1 for r in w if r["ft"])
        ft = sum(1 for r in w if r["ft"] and r["team"] == team)
        box = sum(1 for r in w if r["box"] and r["team"] == team)
        shots = sum(1 for r in w if r["shot"] and r["team"] == team)
        xg = sum(r["xg"] for r in w if r["shot"] and r["team"] == team)
        load = ft + 2 * box + 4 * shots + 20 * xg
        return {
            "possession_pct": rnd(100 * own_passes / passes, 1) if passes else 50.0,
            "field_tilt_pct": rnd(100 * ft / ft_all, 1) if ft_all else 50.0,
            "pressure_index": rnd(100 * (1 - math.exp(-load / 30)), 1),
            "shots": shots,
            "xg": rnd(xg),
            "final_third_passes": ft,
            "box_entries": box,
        }

    def snapshot(self, ev: dict) -> dict[str, Any]:
        clock = ev["clock_s"]
        span = max(MIN_WINDOW_S, min(WINDOW_S, clock - self.period_start))
        minutes = span / 60.0
        w = self.window
        passes = sum(1 for r in w if r["pass"])
        possessions = len({r["poss"] for r in w})
        turnovers = sum(1 for r in w if r["turnover"])
        avg_chain = passes / possessions if possessions else 0.0
        tpm = turnovers / minutes
        # Centred on a typical engine match (3.5 passes per possession, 3.6 turnovers a minute).
        control = pitch.clamp((avg_chain - CHAIN_MID) / 2.0, -1.0, 1.0)
        chaos = pitch.clamp((tpm - TURNOVER_MID) / 2.0, -1.0, 1.0)
        cc = pitch.clamp(control - chaos, -1.0, 1.0)
        tempo = (
            "Controlled"
            if cc >= 0.4
            else "Probing"
            if cc >= 0.0
            else "End to end"
            if cc >= -0.4
            else "Frantic"
        )
        hid, aid = self.ctx.home_id, self.ctx.away_id
        return {
            "match_id": self.match_id,
            "clock_s": rnd(clock),
            "match_clock": ev["match_clock"],
            "period": ev["period"],
            "home_id": hid,
            "away_id": aid,
            "score_home": self.score[hid],
            "score_away": self.score[aid],
            "home": self.team_window(hid),
            "away": self.team_window(aid),
            "momentum": rnd(self.momentum, 1),
            "control_chaos": rnd(cc),
            "tempo": tempo,
            "events_per_min": rnd(len(w) / minutes, 1),
            "turnovers_per_min": rnd(tpm),
            "avg_chain_passes": rnd(avg_chain),
            "xg_home": rnd(self.xg[hid]),
            "xg_away": rnd(self.xg[aid]),
            "shots_home": self.shots[hid],
            "shots_away": self.shots[aid],
        }


def control_chaos_view(state: dict) -> dict[str, Any]:
    return {
        "home_control_pct": state["home"]["possession_pct"],
        "away_control_pct": rnd(100 - state["home"]["possession_pct"], 1),
        "chaos_index": state["control_chaos"],
        "current_tempo": state["tempo"],
        "rolling_momentum_home": state["momentum"],
    }


# --------------------------------------------------------- player stats


class PlayerBook:
    def __init__(self, ctx: Ctx) -> None:
        self.s: dict[str, dict[str, Any]] = {}
        team_of = {p.player_id: t.team_id for t in ctx.teams.values() for p in t.players}
        for pid, team in team_of.items():
            self.s[pid] = {
                "player_id": pid,
                "team": team,
                "touches": 0,
                "passes": 0,
                "passes_completed": 0,
                "key_passes": 0,
                "shots": 0,
                "goals": 0,
                "assists": 0,
                "xg": 0.0,
                "xa": 0.0,
                "tackles_won": 0,
                "interceptions": 0,
                "top_speed_kmh": 0.0,
                "sprints": 0,
                "distance_m": 0.0,
                "carry_distance_m": 0.0,
            }

        self.last_pass: dict[Any, tuple[str, str]] = {}
        self.goal_by: dict[str, tuple[str, str | None]] = {}  # counted goal -> (scorer, assist)

    def process(self, ev: dict, cq: float | None) -> None:
        pid, t = ev.get("player_id"), ev["type"]
        if t == "var_review":
            if ev.get("outcome") == "overturned":
                scorer, assist = self.goal_by.pop(ev.get("reviewed_event_id") or "", (None, None))
                if scorer is not None:
                    self.s[scorer]["goals"] -= 1
                if assist is not None:
                    self.s[assist]["assists"] -= 1
            return
        if pid not in self.s:
            return
        st = self.s[pid]
        if t in ON_BALL:
            st["touches"] += 1
        speed = ev.get("player_speed_mps")
        if speed is not None:
            st["top_speed_kmh"] = max(st["top_speed_kmh"], M.kmh(speed) or 0.0)
            if speed >= M.SPRINT_MS:
                st["sprints"] += 1
        start, end = ev.get("start"), ev.get("end")
        if t in ("carry", "dribble") and start and end:
            d = pitch.dist((start["x"], start["y"]), (end["x"], end["y"]))
            st["carry_distance_m"] += d
            st["distance_m"] += d
        if t == "run":
            path = [
                (p["x"], p["y"])
                for f in ev.get("tracking") or []
                for p in f["players"]
                if p["player_id"] == pid
            ]
            if len(path) >= 2:
                st["distance_m"] += sum(pitch.dist(a, b) for a, b in zip(path, path[1:], strict=False))
            elif start and end:
                st["distance_m"] += pitch.dist((start["x"], start["y"]), (end["x"], end["y"]))
        if t == "pass":
            st["passes"] += 1
            if ev.get("outcome") == "complete":
                st["passes_completed"] += 1
                if ev.get("receiver_id"):
                    self.last_pass[ev.get("possession_id")] = (pid, ev["receiver_id"])
        elif t == "shot":
            st["shots"] += 1
            st["xg"] += cq or 0.0
            lp = self.last_pass.get(ev.get("possession_id"))
            if lp and lp[1] == pid and lp[0] in self.s:
                self.s[lp[0]]["key_passes"] += 1
                self.s[lp[0]]["xa"] += cq or 0.0
            if ev.get("outcome") == "goal":
                st["goals"] += 1
                assist = ev.get("details", {}).get("assist_id")
                if assist in self.s:
                    self.s[assist]["assists"] += 1
                self.goal_by[ev["event_id"]] = (pid, assist if assist in self.s else None)
        elif t == "tackle" and ev.get("outcome") == "won":
            st["tackles_won"] += 1
        elif t == "interception":
            st["interceptions"] += 1

    def view(self, pid: str) -> dict[str, Any]:
        st = self.s[pid]
        return {
            "player_id": pid,
            "team": st["team"],
            "touches": st["touches"],
            "passes": st["passes"],
            "passes_completed": st["passes_completed"],
            "pass_accuracy": rnd(100 * st["passes_completed"] / st["passes"], 1) if st["passes"] else 0.0,
            "key_passes": st["key_passes"],
            "shots": st["shots"],
            "goals": st["goals"],
            "assists": st["assists"],
            "xg": rnd(st["xg"]),
            "xa": rnd(st["xa"]),
            "tackles_won": st["tackles_won"],
            "interceptions": st["interceptions"],
            "top_speed_kmh": rnd(st["top_speed_kmh"], 1),
            "sprints": st["sprints"],
            "distance_km": rnd(st["distance_m"] / 1000, 3),
            "carry_distance_m": rnd(st["carry_distance_m"], 1),
        }

    def views(self) -> dict[str, dict[str, Any]]:
        return {pid: self.view(pid) for pid in sorted(self.s)}


# ------------------------------------------------------------ language


def num(v: Any, lang: str) -> str:
    s = str(v)
    return s.replace(".", ",") if lang == "es" and isinstance(v, float) else s


def count(n: int, lang: str, en: tuple[str, str], es: tuple[str, str], ar: tuple[str, str, str, str]) -> str:
    """'3 shots' / '3 tiros' / Arabic. The Arabic forms are (one, dual, plural for 3-10,
    singular for 11+); templates place them after a preposition or as an object."""
    if lang == "en":
        return f"{n} {en[0] if n == 1 else en[1]}"
    if lang == "es":
        return f"{n} {es[0] if n == 1 else es[1]}"
    one, two, few, many = ar
    if n == 1:
        return one
    if n == 2:
        return two
    if n == 0 or 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


SHOTS = (("shot", "shots"), ("tiro", "tiros"), ("تسديدة واحدة", "تسديدتين", "تسديدات", "تسديدة"))
KEY_PASSES = (
    ("key pass", "key passes"),
    ("pase clave", "pases clave"),
    ("تمريرة مفتاحية واحدة", "تمريرتين مفتاحيتين", "تمريرات مفتاحية", "تمريرة مفتاحية"),
)
FT_PASSES = (
    ("final-third pass", "final-third passes"),
    ("pase en el último tercio", "pases en el último tercio"),
    (
        "تمريرة واحدة في الثلث الأخير",
        "تمريرتين في الثلث الأخير",
        "تمريرات في الثلث الأخير",
        "تمريرة في الثلث الأخير",
    ),
)
DEFENDERS = (
    ("defender", "defenders"),
    ("defensor", "defensores"),
    ("مدافع واحد", "مدافعَين", "مدافعين", "مدافعًا"),
)
GOALS = (("goal", "goals"), ("gol", "goles"), ("هدف واحد", "هدفين", "أهداف", "هدفًا"))
TIMES = (
    ("occasion", "occasions"),
    ("ocasión", "ocasiones"),
    ("مناسبة واحدة", "مناسبتين", "مناسبات", "مناسبة"),
)
RUNS = (
    ("unfound run", "unfound runs"),
    ("desmarque sin premio", "desmarques sin premio"),
    ("انطلاقة واحدة لم تُستثمر", "انطلاقتين لم تُستثمرا", "انطلاقات لم تُستثمر", "انطلاقة لم تُستثمر"),
)

OUTCOME_PHRASE = {
    "saved": {"en": "the keeper saves it", "es": "el portero la detiene", "ar": "الحارس تصدّى لها"},
    "off_target": {"en": "it goes wide", "es": "se va fuera", "ar": "الكرة ذهبت خارج المرمى"},
    "blocked": {"en": "it is blocked", "es": "se la bloquean", "ar": "الدفاع صدّها"},
    "goal": {"en": "it flies in", "es": "entra como un rayo", "ar": "الكرة سكنت الشباك"},
}
ZONE_PHRASE = {
    "Penalty Box": {"en": "the box", "es": "el área", "ar": "منطقة الجزاء"},
    "Attacking Third": {"en": "the final third", "es": "el último tercio", "ar": "الثلث الأخير"},
    "Middle Third": {"en": "midfield", "es": "el centro del campo", "ar": "وسط الملعب"},
    "Defensive Third": {"en": "his own third", "es": "su propio tercio", "ar": "ثلثه الدفاعي"},
}
MILESTONE_LABELS = {
    "100th club appearance": {
        "en": "100th club appearance",
        "es": "partido número 100 con el club",
        "ar": "المباراة رقم 100 مع النادي",
    }
}

VAR_REASON: dict[str, dict[str, str]] = {
    "offside": {
        "en": "offside in the build-up",
        "es": "fuera de juego en la jugada",
        "ar": "تسلل في بناء الهجمة",
    },
    "handball": {"en": "a handball", "es": "una mano", "ar": "لمسة يد"},
    "foul": {"en": "a foul in the build-up", "es": "una falta en la jugada", "ar": "خطأ في بناء الهجمة"},
}

# kind -> persona -> lang -> (headline, body, why)
T: dict[str, dict[str, dict[str, tuple[str, str, str]]]] = {
    "goal": {
        "casual": {
            "en": (
                "GOAL! {p} scores for {t}!",
                "{p} finds the net and it is {H} {sh}-{sa} {A}. {extra}",
                "It was a {xg} xG chance from {dist} metres.",
            ),
            "es": (
                "¡GOL de {p} para {t}!",
                "{p} la mete y el marcador queda {H} {sh}-{sa} {A}. {extra}",
                "Era una ocasión de {xg} xG a {dist} metros.",
            ),
            "ar": (
                "هدف! {p} يسجل لصالح {t}",
                "{p} يهز الشباك والنتيجة الآن {H} {sh}-{sa} {A}. {extra}",
                "كانت فرصة بقيمة {xg} xG من مسافة {dist} مترًا.",
            ),
        },
        "tactical": {
            "en": (
                "{p} converts for {t}",
                "{p} finishes from {dist} m, a {xg} xG chance. {H} {sh}-{sa} {A}.",
                "{why}",
            ),
            "es": (
                "{p} define para {t}",
                "{p} remata desde {dist} m, una ocasión de {xg} xG. {H} {sh}-{sa} {A}.",
                "{why}",
            ),
            "ar": (
                "{p} يترجم الفرصة لصالح {t}",
                "{p} يسدد من مسافة {dist} م في فرصة قيمتها {xg} xG. النتيجة {H} {sh}-{sa} {A}.",
                "{why}",
            ),
        },
        "fantasy": {
            "en": (
                "Goal for {p}: the stat line grows",
                "{p} has {pxg} xG from {pshots} this match.{extra}",
                "Shots and xG show how often he reaches scoring spots.",
            ),
            "es": (
                "Gol de {p}: crecen sus números",
                "{p} suma {pxg} xG con {pshots} en el partido.{extra}",
                "Los tiros y el xG muestran cuántas veces pisa zonas de gol.",
            ),
            "ar": (
                "هدف من {p}: أرقامه ترتفع",
                "رصيد {p} في المباراة {pxg} xG من {pshots}.{extra}",
                "التسديدات وقيمة xG تبيّن كم مرة يصل إلى مناطق التسجيل.",
            ),
        },
    },
    "correction": {
        "casual": {
            "en": (
                "No goal! VAR rules out {p}",
                "The goal at {clk} is ruled out for {why_r}. It stays {H} {sh}-{sa} {A}.",
                "VAR checked the goal and ruled it out for {why_r}.",
            ),
            "es": (
                "¡No hay gol! El VAR anula a {p}",
                "El gol del {clk} queda anulado por {why_r}. Sigue {H} {sh}-{sa} {A}.",
                "El VAR revisó el gol y lo anuló por {why_r}.",
            ),
            "ar": (
                "لا هدف! الفار يلغي هدف {p}",
                "أُلغي هدف الدقيقة {clk} بسبب {why_r}. النتيجة تبقى {H} {sh}-{sa} {A}.",
                "راجع الفار الهدف وألغاه بسبب {why_r}.",
            ),
        },
        "tactical": {
            "en": (
                "VAR overturns the {t} goal",
                "{p}'s finish at {clk} is chalked off for {why_r}. Score: {H} {sh}-{sa} {A}.",
                "The shot still counts in the shot and xG totals; only the goal is removed.",
            ),
            "es": (
                "El VAR anula el gol de {t}",
                "El remate de {p} del {clk} se anula por {why_r}. Marcador: {H} {sh}-{sa} {A}.",
                "El tiro sigue contando en tiros y xG; solo se retira el gol.",
            ),
            "ar": (
                "الفار يلغي هدف {t}",
                "أُلغيت تسديدة {p} في الدقيقة {clk} بسبب {why_r}. النتيجة: {H} {sh}-{sa} {A}.",
                "التسديدة تبقى محسوبة في التسديدات وxG؛ الهدف وحده أُلغي.",
            ),
        },
        "fantasy": {
            "en": (
                "Goal ruled out: {p}",
                "VAR rules out the goal at {clk} for {why_r}. {p} keeps {pxg} xG from {pshots}.",
                "Goal and assist counts follow the official score, so this one comes off.",
            ),
            "es": (
                "Gol anulado: {p}",
                "El VAR anula el gol del {clk} por {why_r}. {p} mantiene {pxg} xG con {pshots}.",
                "Los goles y asistencias siguen el marcador oficial, así que este se retira.",
            ),
            "ar": (
                "هدف ملغى: {p}",
                "الفار يلغي هدف الدقيقة {clk} بسبب {why_r}. يحتفظ {p} بـ {pxg} xG من {pshots}.",
                "الأهداف والتمريرات الحاسمة تتبع النتيجة الرسمية، لذلك يُسحب هذا الهدف.",
            ),
        },
    },
    "card_red": {
        "casual": {
            "en": (
                "Red card! {p} is sent off",
                "{p} is off and {t} are down to {n} players. Huge moment!",
                "A red card leaves {t} a player short for the rest of the match.",
            ),
            "es": (
                "¡Roja! {p} se va a la calle",
                "{p} es expulsado y {t} se queda con {n} jugadores. ¡Momento clave!",
                "Una roja deja a {t} con uno menos el resto del partido.",
            ),
            "ar": (
                "بطاقة حمراء! طرد {p}",
                "طُرد {p} وأصبح {t} يلعب بـ{n} لاعبين. لحظة فارقة!",
                "البطاقة الحمراء تترك {t} بنقص عددي حتى نهاية المباراة.",
            ),
        },
        "tactical": {
            "en": (
                "{p} sent off: {t} down to {n}",
                "{t} must reshape with {n} players for the rest of the match.",
                "Playing a player short usually means a deeper block and less of the ball.",
            ),
            "es": (
                "Expulsado {p}: {t} con {n}",
                "{t} tendrá que reorganizarse con {n} jugadores el resto del partido.",
                "Jugar con uno menos suele obligar a defender más atrás y a tener menos el balón.",
            ),
            "ar": (
                "طرد {p}: {t} بـ{n} لاعبين",
                "على {t} إعادة تنظيم صفوفه بـ{n} لاعبين حتى نهاية المباراة.",
                "اللعب بنقص عددي يعني عادةً التراجع إلى الخلف واستحواذًا أقل على الكرة.",
            ),
        },
        "fantasy": {
            "en": (
                "Red card: {p} is off",
                "{p} leaves with {pxg} xG from {pshots}.",
                "A red card ends his output for the day, whatever the underlying numbers.",
            ),
            "es": (
                "Roja: {p} se va a la calle",
                "{p} se marcha con {pxg} xG en {pshots}.",
                "Una roja corta su producción del día, sean cuales sean sus números.",
            ),
            "ar": (
                "بطاقة حمراء: {p} خارج الملعب",
                "يغادر {p} برصيد {pxg} xG من {pshots}.",
                "البطاقة الحمراء تنهي إنتاجه في هذه المباراة مهما كانت أرقامه.",
            ),
        },
    },
    "card_yellow": {
        "casual": {
            "en": (
                "Yellow card for {p}",
                "{p} goes into the book for {t}. He has to be careful now.",
                "One more yellow and he would be sent off.",
            ),
            "es": (
                "Amarilla para {p}",
                "{p} ve la amarilla con {t}. Ahora tiene que ir con cuidado.",
                "Otra amarilla y se iría expulsado.",
            ),
            "ar": (
                "بطاقة صفراء في وجه {p}",
                "{p} يتلقى إنذارًا مع {t}. عليه الحذر من الآن.",
                "بطاقة صفراء أخرى تعني طرده.",
            ),
        },
        "tactical": {
            "en": (
                "{p} booked for {t}",
                "{p} is on a yellow and may have to hold back in duels.",
                "A booked player often defends more carefully, which opponents can target.",
            ),
            "es": (
                "Amonestado {p} en {t}",
                "{p} está amonestado y quizá deba medir sus duelos.",
                "Un jugador amonestado suele defender con más cautela, algo que el rival puede aprovechar.",
            ),
            "ar": (
                "إنذار {p} في صفوف {t}",
                "{p} مهدد بالطرد وقد يضطر إلى التحفظ في الالتحامات.",
                "اللاعب المُنذَر يدافع عادةً بحذر أكبر، وهو ما قد يستغله المنافس.",
            ),
        },
        "fantasy": {
            "en": (
                "Yellow card for {p}",
                "{p} has {pxg} xG from {pshots} so far.",
                "A booking means he must defend with care for the rest of the match.",
            ),
            "es": (
                "Amarilla para {p}",
                "{p} lleva {pxg} xG en {pshots}.",
                "Con la amarilla tendrá que defender con cuidado el resto del partido.",
            ),
            "ar": (
                "إنذار لـ{p}",
                "رصيد {p} حتى الآن {pxg} xG من {pshots}.",
                "بعد الإنذار عليه أن يدافع بحذر حتى نهاية المباراة.",
            ),
        },
    },
    "milestone": {
        "casual": {
            "en": (
                "Milestone day for {p}",
                "{p} marks his {lbl} today. A proud day for him and {t}.",
                "Milestones like this mark a long stay at the club.",
            ),
            "es": (
                "Día histórico para {p}",
                "{p} celebra hoy su {lbl}. Un día de orgullo para él y para {t}.",
                "Hitos así reflejan una larga trayectoria en el club.",
            ),
            "ar": (
                "يوم تاريخي لـ{p}",
                "يخوض {p} اليوم {lbl}. يوم فخر له ولـ{t}.",
                "إنجازات كهذه تعكس مسيرة طويلة مع النادي.",
            ),
        },
        "tactical": {
            "en": (
                "Milestone: {p}, {lbl}",
                "{p} ({t}) reaches his {lbl}.",
                "Experienced players like him bring continuity to the {t} side.",
            ),
            "es": (
                "Hito: {p}, {lbl}",
                "{p} ({t}) alcanza su {lbl}.",
                "Jugadores con experiencia como él dan continuidad a {t}.",
            ),
            "ar": (
                "إنجاز: {p}، {lbl}",
                "يصل {p} ({t}) إلى {lbl}.",
                "اللاعبون أصحاب الخبرة مثله يمنحون {t} الاستمرارية.",
            ),
        },
        "fantasy": {
            "en": (
                "{p} milestone: check his numbers",
                "{p} has {pxg} xG, {pxa} xA and {pkp} so far.",
                "A milestone is a landmark; his xG and xA show today's output.",
            ),
            "es": (
                "Hito de {p}: mira sus números",
                "{p} lleva {pxg} xG, {pxa} xA y {pkp}.",
                "El hito es una marca; su xG y su xA muestran su aporte de hoy.",
            ),
            "ar": (
                "إنجاز {p}: ماذا تقول أرقامه؟",
                "سجّل {p} حتى الآن {pxg} xG و{pxa} xA وصنع {pkp}.",
                "الإنجاز علامة فارقة، أما xG وxA فيُظهران إنتاجه اليوم.",
            ),
        },
    },
    "big_chance": {
        "casual": {
            "en": (
                "So close for {p}!",
                "{p} gets a big chance for {t}, but {oc}. What a chance that was!",
                "It was a {xg} xG chance from {dist} metres.",
            ),
            "es": (
                "¡Qué ocasión para {p}!",
                "{p} tiene una gran ocasión para {t}, pero {oc}. ¡Qué cerca!",
                "Era una ocasión de {xg} xG a {dist} metros.",
            ),
            "ar": (
                "فرصة ضائعة من {p}!",
                "{p} يحصل على فرصة كبيرة لصالح {t}، لكن {oc}. كانت قريبة جدًا!",
                "كانت فرصة بقيمة {xg} xG من مسافة {dist} مترًا.",
            ),
        },
        "tactical": {
            "en": (
                "Big chance: {xg} xG for {p}",
                "{p} shoots from {dist} m with {xg} xG, but {oc}.",
                "{cone}, so the chance was worth {xg} xG.",
            ),
            "es": (
                "Ocasión clara: {xg} xG para {p}",
                "{p} remata desde {dist} m con {xg} xG, pero {oc}.",
                "{cone}, así que la ocasión valía {xg} xG.",
            ),
            "ar": (
                "فرصة محققة: {xg} xG من {p}",
                "{p} يسدد من مسافة {dist} م بقيمة {xg} xG، لكن {oc}.",
                "{cone}، بلغت قيمة الفرصة {xg} xG.",
            ),
        },
        "fantasy": {
            "en": (
                "{p} big chance, no return yet",
                "{p} is on {pxg} xG from {pshots}.",
                "High xG without a goal suggests returns could follow.",
            ),
            "es": (
                "{p}: gran ocasión, sin premio",
                "{p} acumula {pxg} xG en {pshots}.",
                "Mucho xG sin gol sugiere que el gol puede llegar.",
            ),
            "ar": (
                "{p}: فرصة كبيرة بلا هدف",
                "رصيد {p} {pxg} xG من {pshots}.",
                "ارتفاع xG دون أهداف يوحي بأن الهدف قد يأتي لاحقًا.",
            ),
        },
    },
    "better_option": {
        "casual": {
            "en": (
                "Should he have passed?",
                "{s} went for goal, but {m} was in a better spot. The pass was worth {tb}x the shot!",
                "{s}'s shot was a {shot} chance; passing to {m} was worth {alt}.",
            ),
            "es": (
                "¿Debió pasarla?",
                "{s} buscó la portería, pero {m} estaba en mejor posición. ¡El pase valía {tb} veces más que el tiro!",
                "El tiro de {s} era una ocasión de {shot}; el pase a {m} valía {alt}.",
            ),
            "ar": (
                "هل كان عليه أن يمرر؟",
                "سدد {s} على المرمى، لكن {m} كان في موقع أفضل. التمريرة كانت تساوي {tb} أضعاف التسديدة!",
                "تسديدة {s} كانت فرصة بقيمة {shot}، بينما التمرير إلى {m} كان يساوي {alt}.",
            ),
        },
        "tactical": {
            "en": (
                "Should he have passed?",
                "{s} shot from a {shot} chance; {m} was free for a {alt} chance, {tb}x better.",
                "The lane to {m} was on: {ps} pass success over {pdist} m, nearest marker {marker} m away.",
            ),
            "es": (
                "¿Debió pasarla?",
                "{s} tiró con una ocasión de {shot}; {m} estaba libre para una de {alt}, {tb} veces mejor.",
                "La línea de pase a {m} estaba abierta: {ps} de probabilidad de éxito en {pdist} m, con el marcador más cercano a {marker} m.",
            ),
            "ar": (
                "هل كان عليه أن يمرر؟",
                "سدد {s} من فرصة بقيمة {shot}، بينما كان {m} حرًا لفرصة بقيمة {alt}، أي أفضل بـ{tb} مرة.",
                "ممر التمرير إلى {m} كان مفتوحًا: احتمال نجاح {ps} لمسافة {pdist} م، وأقرب مراقب على بعد {marker} م.",
            ),
        },
        "fantasy": {
            "en": (
                "Shot or assist? {s} chose the shot",
                "{s} took a {shot} xG shot instead of a pass worth {alt} to {m}.",
                "That pass would have put {m} through on {altcq} xG, with the xA going to {s}.",
            ),
            "es": (
                "¿Tiro o asistencia? {s} eligió tirar",
                "{s} tiró con {shot} xG en vez de un pase a {m} que valía {alt}.",
                "Ese pase habría dejado a {m} ante una ocasión de {altcq} xG, con el xA para {s}.",
            ),
            "ar": (
                "تسديدة أم صناعة؟ {s} اختار التسديد",
                "سدد {s} بفرصة {shot} xG بدلًا من تمريرة إلى {m} تساوي {alt}.",
                "تلك التمريرة كانت ستمنح {m} فرصة بقيمة {altcq} xG، وتمنح {s} قيمة xA.",
            ),
        },
    },
    "unfound_run": {
        "casual": {
            "en": (
                "{r} was through, nobody saw him!",
                "{r} ran clear of the defence, but {c} never played the pass. {oo}",
                "He got {clear} metres beyond the last defender.",
            ),
            "es": (
                "¡{r} estaba solo y nadie lo vio!",
                "{r} se escapó de la defensa, pero {c} nunca dio el pase. {oo}",
                "Llegó a {clear} metros por detrás del último defensor.",
            ),
            "ar": (
                "{r} انطلق وحيدًا ولم يره أحد!",
                "انطلق {r} خلف الدفاع، لكن {c} لم يمرر الكرة أبدًا. {oo}",
                "تجاوز آخر مدافع بمسافة {clear} مترًا.",
            ),
        },
        "tactical": {
            "en": (
                "Unfound run: {r} in behind",
                "{r} was onside and clear {when}, ending {clear} m beyond the line. {c} kept the ball.",
                "A through ball would have created a {proj} xG chance{oo2}.",
            ),
            "es": (
                "Desmarque sin premio: {r} a la espalda",
                "{r} estaba en posición legal y libre {when}, y acabó {clear} m por detrás de la línea. {c} se guardó el balón.",
                "Un pase al hueco habría generado una ocasión de {proj} xG{oo2}.",
            ),
            "ar": (
                "انطلاقة بلا تمريرة: {r} خلف الدفاع",
                "كان {r} في وضعية سليمة وحرًا {when}، وأنهى انطلاقته متقدمًا {clear} م خلف خط الدفاع. احتفظ {c} بالكرة.",
                "كانت التمريرة البينية ستصنع فرصة بقيمة {proj} xG{oo2}.",
            ),
        },
        "fantasy": {
            "en": (
                "Missed assist chance for {c}",
                "{c} could have found {r} for a {proj} xG chance.",
                "That pass would have earned {c} {proj} xA.",
            ),
            "es": (
                "Asistencia perdida para {c}",
                "{c} pudo encontrar a {r} para una ocasión de {proj} xG.",
                "Ese pase le habría dado a {c} {proj} de xA.",
            ),
            "ar": (
                "فرصة صناعة ضائعة على {c}",
                "كان بإمكان {c} إيجاد {r} لفرصة بقيمة {proj} xG.",
                "تلك التمريرة كانت ستمنح {c} قيمة {proj} xA.",
            ),
        },
    },
    "pressure_spell": {
        "casual": {
            "en": (
                "{t} are piling on the pressure",
                "{t} have pinned {o} back in their own half. Something has to give!",
                "Their pressure index has stayed at {thr} or more for {mins} minutes.",
            ),
            "es": (
                "{t} aprieta sin descanso",
                "{t} tiene encerrado a {o} en su campo. ¡Algo tiene que pasar!",
                "Su índice de presión lleva {mins} minutos en {thr} o más.",
            ),
            "ar": (
                "{t} يضغط بقوة",
                "{t} يحاصر {o} في نصف ملعبه. لا بد أن يحدث شيء!",
                "بقي مؤشر الضغط لديه عند {thr} أو أكثر لمدة {mins} دقائق.",
            ),
        },
        "tactical": {
            "en": (
                "Sustained pressure from {t}",
                "{t} pressure index is {idx}, from {ftp} and {wshots} in five minutes.",
                "The index has stayed at {thr} or above for {mins} minutes.",
            ),
            "es": (
                "Presión sostenida de {t}",
                "El índice de presión de {t} es {idx}, con {ftp} y {wshots} en cinco minutos.",
                "El índice lleva {mins} minutos en {thr} o más.",
            ),
            "ar": (
                "ضغط متواصل من {t}",
                "مؤشر ضغط {t} عند {idx}، مع {ftp} و{wshots} خلال خمس دقائق.",
                "بقي المؤشر عند {thr} أو أكثر لمدة {mins} دقائق.",
            ),
        },
        "fantasy": {
            "en": (
                "{t} attackers are getting looks",
                "{t} have {wshots} and {wxg} xG in the last five minutes.",
                "Sustained pressure creates shots, and shots build xG.",
            ),
            "es": (
                "Los atacantes de {t} tienen ocasiones",
                "{t} suma {wshots} y {wxg} xG en los últimos cinco minutos.",
                "La presión sostenida genera tiros, y los tiros suman xG.",
            ),
            "ar": (
                "مهاجمو {t} يحصلون على الفرص",
                "سجّل {t} في آخر خمس دقائق {wxg} xG من {wshots}.",
                "الضغط المتواصل يصنع التسديدات، والتسديدات ترفع xG.",
            ),
        },
    },
    "momentum_swing": {
        "casual": {
            "en": (
                "The momentum is with {t} now",
                "{t} have taken over this game. You can feel it turning!",
                "Momentum has moved {chg} points their way in five minutes.",
            ),
            "es": (
                "El impulso es ahora de {t}",
                "{t} ha tomado el mando del partido. ¡Se nota el cambio!",
                "El impulso se ha movido {chg} puntos a su favor en cinco minutos.",
            ),
            "ar": (
                "الزخم الآن لصالح {t}",
                "{t} يفرض سيطرته على المباراة. الأمور تتغير!",
                "تحرك مؤشر الزخم {chg} نقطة لصالحه خلال خمس دقائق.",
            ),
        },
        "tactical": {
            "en": (
                "Momentum swing towards {t}",
                "Momentum moved {chg} points in five minutes and now reads {mom} for {t}.",
                "{t} pressure index is {pi} against {opi} for {o}.",
            ),
            "es": (
                "Cambio de inercia hacia {t}",
                "El impulso se movió {chg} puntos en cinco minutos y ahora marca {mom} a favor de {t}.",
                "El índice de presión de {t} es {pi}, frente a {opi} de {o}.",
            ),
            "ar": (
                "تحوّل الزخم نحو {t}",
                "تحرك الزخم {chg} نقطة خلال خمس دقائق ويبلغ الآن {mom} لصالح {t}.",
                "مؤشر ضغط {t} عند {pi} مقابل {opi} لـ{o}.",
            ),
        },
        "fantasy": {
            "en": (
                "{t} attackers worth watching now",
                "{t} have {wshots} and {wxg} xG in the last five minutes.",
                "The side on top usually takes more shots, and shots build xG.",
            ),
            "es": (
                "Atentos a los atacantes de {t}",
                "{t} suma {wshots} y {wxg} xG en los últimos cinco minutos.",
                "El equipo dominante suele tirar más, y los tiros suman xG.",
            ),
            "ar": (
                "راقبوا مهاجمي {t} الآن",
                "سجّل {t} في آخر خمس دقائق {wxg} xG من {wshots}.",
                "الفريق المسيطر يسدد أكثر عادةً، والتسديدات ترفع xG.",
            ),
        },
    },
    "speed_burst": {
        "casual": {
            "en": (
                "{p} is flying!",
                "{p} hits {kmh} km/h. Good luck catching him!",
                "That is top sprint speed: {kmh} km/h.",
            ),
            "es": (
                "¡{p} va volando!",
                "{p} alcanza {kmh} km/h. ¡A ver quién lo pilla!",
                "Eso es velocidad punta: {kmh} km/h.",
            ),
            "ar": (
                "{p} ينطلق كالسهم!",
                "{p} يبلغ سرعة {kmh} كم/س. من يستطيع اللحاق به؟",
                "هذه سرعة قصوى: {kmh} كم/س.",
            ),
        },
        "tactical": {
            "en": (
                "Speed burst: {p} at {kmh} km/h",
                "{p} reaches {kmh} km/h on this action.",
                "Bursts above {thr} km/h stretch the defensive line.",
            ),
            "es": (
                "Arrancada: {p} a {kmh} km/h",
                "{p} alcanza {kmh} km/h en esta acción.",
                "Las arrancadas por encima de {thr} km/h estiran la línea defensiva.",
            ),
            "ar": (
                "انطلاقة سريعة: {p} بسرعة {kmh} كم/س",
                "{p} يبلغ {kmh} كم/س في هذه اللعبة.",
                "الانطلاقات التي تتجاوز {thr} كم/س تمدد خط الدفاع.",
            ),
        },
        "fantasy": {
            "en": (
                "{p}: pace on show",
                "{p} has {pxg} xG from {pshots} so far.",
                "Pace takes him into shooting spots, which is where xG comes from.",
            ),
            "es": (
                "{p}: velocidad a la vista",
                "{p} lleva {pxg} xG en {pshots}.",
                "La velocidad lo lleva a zonas de tiro, de donde sale el xG.",
            ),
            "ar": (
                "{p}: سرعة لافتة",
                "رصيد {p} حتى الآن {pxg} xG من {pshots}.",
                "السرعة تقوده إلى مناطق التسديد، ومنها تأتي قيمة xG.",
            ),
        },
    },
    "rocket_shot": {
        "casual": {
            "en": (
                "What a strike from {p}!",
                "{p} hits it at {kmh} km/h and {oc}!",
                "That shot left his foot at {kmh} km/h.",
            ),
            "es": (
                "¡Vaya disparo de {p}!",
                "¡{p} le pega a {kmh} km/h y {oc}!",
                "Ese disparo salió a {kmh} km/h.",
            ),
            "ar": (
                "يا لها من قذيفة من {p}!",
                "{p} يسدد بسرعة {kmh} كم/س و{oc}!",
                "انطلقت التسديدة بسرعة {kmh} كم/س.",
            ),
        },
        "tactical": {
            "en": (
                "Shot speed: {kmh} km/h",
                "{p} strikes at {kmh} km/h from {dist} m.",
                "Power is not placement: the chance was worth {xg} xG.",
            ),
            "es": (
                "Velocidad del disparo: {kmh} km/h",
                "{p} dispara a {kmh} km/h desde {dist} m.",
                "La potencia no lo es todo: la ocasión valía {xg} xG.",
            ),
            "ar": (
                "سرعة التسديدة: {kmh} كم/س",
                "{p} يسدد بسرعة {kmh} كم/س من مسافة {dist} م.",
                "القوة ليست كل شيء: قيمة الفرصة كانت {xg} xG.",
            ),
        },
        "fantasy": {
            "en": (
                "{p} lets fly",
                "{p} is on {pxg} xG from {pshots}.",
                "Every shot adds to his xG, the core attacking signal.",
            ),
            "es": (
                "{p} se atreve a disparar",
                "{p} suma {pxg} xG en {pshots}.",
                "Cada tiro suma a su xG, la señal ofensiva clave.",
            ),
            "ar": (
                "{p} يجرّب حظه",
                "رصيد {p} {pxg} xG من {pshots}.",
                "كل تسديدة تضيف إلى رصيده من xG، المؤشر الهجومي الأهم.",
            ),
        },
    },
    "hard_pass": {
        "casual": {
            "en": (
                "Brilliant pass from {p}",
                "{p} picks out {rcv} with a really tough ball. Class!",
                "The pass had a difficulty score of {pd} over {pdist} metres.",
            ),
            "es": (
                "Pasazo de {p}",
                "{p} encuentra a {rcv} con un pase dificilísimo. ¡Qué calidad!",
                "El pase tuvo una dificultad de {pd} en {pdist} metros.",
            ),
            "ar": (
                "تمريرة رائعة من {p}",
                "{p} يجد {rcv} بتمريرة صعبة للغاية. يا لها من مهارة!",
                "بلغت صعوبة التمريرة {pd} لمسافة {pdist} مترًا.",
            ),
        },
        "tactical": {
            "en": (
                "Hard pass completed: difficulty {pd}",
                "{p} finds {rcv} with a {pdist} m pass into {zone}.",
                "Difficulty combines length, pressure, forward progress, target zone and pass type.",
            ),
            "es": (
                "Pase difícil completado: dificultad {pd}",
                "{p} encuentra a {rcv} con un pase de {pdist} m hacia {zone}.",
                "La dificultad combina distancia, presión, avance, zona de destino y tipo de pase.",
            ),
            "ar": (
                "تمريرة صعبة مكتملة: صعوبة {pd}",
                "{p} يجد {rcv} بتمريرة لمسافة {pdist} م نحو {zone}.",
                "تجمع الصعوبة بين المسافة والضغط والتقدم ومنطقة الوصول ونوع التمريرة.",
            ),
        },
        "fantasy": {
            "en": (
                "{p} is creating",
                "{p} has {pkp} and {pxa} xA so far.",
                "Key passes and xA show who is setting up chances.",
            ),
            "es": (
                "{p} está generando juego",
                "{p} lleva {pkp} y {pxa} xA.",
                "Los pases clave y el xA muestran quién genera ocasiones.",
            ),
            "ar": (
                "{p} يصنع اللعب",
                "صنع {p} حتى الآن {pkp} و{pxa} xA.",
                "التمريرات المفتاحية وقيمة xA تكشف من يصنع الفرص.",
            ),
        },
    },
}

TACTICAL_TAG = {
    "goal": "Finishing",
    "correction": "Officiating",
    "card_red": "Numerical disadvantage",
    "card_yellow": "Discipline",
    "milestone": "Squad continuity",
    "big_chance": "Chance creation",
    "better_option": "Shot selection",
    "unfound_run": "Run in behind",
    "pressure_spell": "Sustained pressure",
    "momentum_swing": "Momentum shift",
    "speed_burst": "Pace",
    "rocket_shot": "Ball striking",
    "hard_pass": "Line-breaking pass",
}


def render(key: str, base: dict[str, Any], per_lang: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Fill every persona x language template. `base` holds raw values (numbers are
    formatted per language); `per_lang` holds already-localised phrases."""
    out: dict[str, Any] = {}
    for persona in PERSONAS:
        out[persona] = {}
        for lang in LANGS:
            vals = {
                k: num(v, lang) if isinstance(v, int | float) and not isinstance(v, bool) else v
                for k, v in base.items()
            }
            vals.update(per_lang.get(lang, {}).get(persona, {}))
            vals.update({k: v for k, v in per_lang.get(lang, {}).items() if not isinstance(v, dict)})
            h, b, w = T[key][persona][lang]
            out[persona][lang] = {
                "headline": h.format(**vals).strip(),
                "body": re.sub(r"\s+", " ", b.format(**vals)).strip(),
                "why": w.format(**vals).strip(),
            }
    return out


# Evidence label translations (es, ar). Names stay as they are; labels carry no numbers.
LABELS_FIXED: dict[str, tuple[str, str]] = {
    "Chance quality": ("Calidad de la ocasión", "جودة الفرصة"),
    "Distance to goal": ("Distancia a la portería", "المسافة إلى المرمى"),
    "Scorer": ("Goleador", "المسجّل"),
    "Goal ruled out (scored at)": ("Gol anulado (marcado en)", "هدف ملغى (سُجّل في)"),
    "Assist": ("Asistente", "صاحب التمريرة الحاسمة"),
    "Card": ("Tarjeta", "البطاقة"),
    "Player": ("Jugador", "اللاعب"),
    "Milestone": ("Hito", "الإنجاز"),
    "Defenders in shooting cone": ("Defensores en el ángulo de tiro", "المدافعون في مخروط التسديد"),
    "Outcome": ("Resultado", "النتيجة"),
    "Shot chance quality": ("Calidad de la ocasión del tiro", "جودة فرصة التسديدة"),
    "Pass option value (pass success x chance quality)": (
        "Valor del pase (probabilidad de éxito por calidad de la ocasión)",
        "قيمة خيار التمرير (احتمال النجاح مضروبًا في جودة الفرصة)",
    ),
    "Teammate chance quality": ("Calidad de la ocasión del compañero", "جودة فرصة الزميل"),
    "Pass success probability": ("Probabilidad de éxito del pase", "احتمال نجاح التمريرة"),
    "Times better": ("Veces mejor", "عدد مرات الأفضلية"),
    "Pass distance": ("Distancia del pase", "مسافة التمريرة"),
    "Nearest marker to teammate": ("Marcador más cercano al compañero", "أقرب مراقب إلى الزميل"),
    "Shooter": ("Rematador", "المسدِّد"),
    "Free teammate": ("Compañero libre", "الزميل الحر"),
    "Pass on at": ("Pase posible a los", "التمريرة متاحة بعد"),
    "Pass on clock": ("Minuto del pase posible", "توقيت التمريرة المتاحة"),
    "Clear of the back line": ("Ventaja sobre la última línea", "التقدم خلف خط الدفاع"),
    "Projected chance quality": ("Calidad de ocasión prevista", "جودة الفرصة المتوقعة"),
    "One on one": ("Mano a mano", "مواجهة مباشرة مع الحارس"),
    "Runner": ("Jugador del desmarque", "صاحب الانطلاقة"),
    "Ball carrier": ("Poseedor del balón", "حامل الكرة"),
    "Pressure spell threshold": ("Umbral de racha de presión", "عتبة فترة الضغط"),
    "Spell length": ("Duración de la racha", "مدة فترة الضغط"),
    "Momentum change (5 min)": ("Cambio de impulso (últimos cinco minutos)", "تغير الزخم (آخر خمس دقائق)"),
    "Ball speed": ("Velocidad del balón", "سرعة الكرة"),
    "Player speed": ("Velocidad del jugador", "سرعة اللاعب"),
    "Speed burst threshold": ("Umbral de arrancada", "عتبة الانطلاقة السريعة"),
    "Pass difficulty": ("Dificultad del pase", "صعوبة التمريرة"),
    "End zone": ("Zona de destino", "منطقة الوصول"),
    "Receiver": ("Receptor", "المستلم"),
}
LABELS_NAMED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^(?P<n>.+) xG \(match\)$"), "{n}: xG en el partido", "{n}: xG في المباراة"),
    (re.compile(r"^(?P<n>.+) xA \(match\)$"), "{n}: xA en el partido", "{n}: xA في المباراة"),
    (re.compile(r"^(?P<n>.+) shots \(match\)$"), "{n}: tiros en el partido", "{n}: التسديدات في المباراة"),
    (
        re.compile(r"^(?P<n>.+) key passes \(match\)$"),
        "{n}: pases clave en el partido",
        "{n}: التمريرات المفتاحية في المباراة",
    ),
    (re.compile(r"^(?P<n>.+) goals$"), "Goles de {n}", "أهداف {n}"),
    (
        re.compile(r"^(?P<n>.+) players on the pitch$"),
        "Jugadores de {n} en el campo",
        "لاعبو {n} على أرض الملعب",
    ),
    (
        re.compile(r"^(?P<n>.+) shots \(last 5 min\)$"),
        "Tiros de {n} (últimos cinco minutos)",
        "تسديدات {n} (آخر خمس دقائق)",
    ),
    (
        re.compile(r"^(?P<n>.+) xG \(last 5 min\)$"),
        "xG de {n} (últimos cinco minutos)",
        "xG لـ{n} (آخر خمس دقائق)",
    ),
    (
        re.compile(r"^(?P<n>.+) final-third passes \(last 5 min\)$"),
        "Pases de {n} en el último tercio (últimos cinco minutos)",
        "تمريرات {n} في الثلث الأخير (آخر خمس دقائق)",
    ),
    (re.compile(r"^Momentum in favour of (?P<n>.+)$"), "Impulso a favor de {n}", "الزخم لصالح {n}"),
    (re.compile(r"^(?P<n>.+) pressure index$"), "Índice de presión de {n}", "مؤشر ضغط {n}"),
]


def translate_label(label: str) -> dict[str, str]:
    if label in LABELS_FIXED:
        es, ar = LABELS_FIXED[label]
        return {"es": es, "ar": ar}
    for pattern, es, ar in LABELS_NAMED:
        m = pattern.match(label)
        if m:
            return {"es": es.format(n=m["n"]), "ar": ar.format(n=m["n"])}
    raise KeyError(f"no translation for evidence label {label!r}")


def ev_item(label: str, value: Any, unit: str | None, src: str | None) -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit, "source_event_id": src}


def player_evidence(book: PlayerBook, pid: str, src: str, ctx: Ctx) -> list[dict[str, Any]]:
    v = book.view(pid)
    who = ctx.players[pid].name
    return [
        ev_item(f"{who} xG (match)", v["xg"], "xG", src),
        ev_item(f"{who} xA (match)", v["xa"], "xA", src),
        ev_item(f"{who} shots (match)", v["shots"], None, src),
        ev_item(f"{who} key passes (match)", v["key_passes"], None, src),
    ]


def player_vars(book: PlayerBook, pid: str, prefix: str = "p") -> tuple[dict[str, Any], dict[str, dict]]:
    v = book.view(pid)
    base = {f"{prefix}xg": v["xg"], f"{prefix}xa": v["xa"]}
    per = {
        lang: {
            f"{prefix}shots": count(v["shots"], lang, *SHOTS),
            f"{prefix}kp": count(v["key_passes"], lang, *KEY_PASSES),
        }
        for lang in LANGS
    }
    return base, per


def merge(*pers: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {lang: {} for lang in LANGS}
    for p in pers:
        for lang, d in p.items():
            out[lang].update(d)
    return out


# --------------------------------------------------------------- spotter


class Spotter:
    def __init__(self, ctx: Ctx, book: PlayerBook) -> None:
        self.ctx = ctx
        self.book = book
        self.moments: list[dict[str, Any]] = []
        self.last_tag_clock: float | None = None
        self.spell_start: dict[str, float | None] = {ctx.home_id: None, ctx.away_id: None}
        self.spell_flagged: dict[str, bool] = {ctx.home_id: False, ctx.away_id: False}
        self.mom_hist: deque[tuple[float, float]] = deque()
        self.swings: list[float] = []
        self.last_swing: float | None = None
        self.reds: dict[str, int] = {ctx.home_id: 0, ctx.away_id: 0}

    def start_period(self) -> None:
        self.last_tag_clock = None
        self.spell_start = dict.fromkeys(self.spell_start)
        self.spell_flagged = dict.fromkeys(self.spell_flagged, False)
        self.mom_hist.clear()
        self.last_swing = None

    def add(
        self,
        ev: dict,
        kind: str,
        slot: str,
        priority: int,
        key: str,
        base: dict,
        per: dict,
        evidence: list,
        team: str | None,
        player_ids: list[str],
        replay: dict | None = None,
        extra: dict | None = None,
    ) -> None:
        self.moments.append(
            {
                "moment_id": f"{ev['event_id']}-{kind}",
                "kind": kind,
                "slot": slot,
                "priority": priority,
                "show_at_s": rnd(ev["clock_s"]),
                "duration_s": DURATION[slot],
                "event_id": ev["event_id"],
                "match_clock": ev["match_clock"],
                "period": ev["period"],
                "team": team,
                "player_ids": player_ids,
                "evidence": evidence,
                "evidence_labels": {
                    lang: [translate_label(e["label"])[lang] for e in evidence] for lang in ("es", "ar")
                },
                "tactical_tag": TACTICAL_TAG[key],
                "replay": replay,
                "texts": render(key, base, per),
            }
            | (extra or {})
        )

    # -- per event --------------------------------------------------------
    def process(
        self, ev: dict, metrics: dict, shot: dict | None, better: dict | None, run: dict | None, state: dict
    ) -> None:
        ctx = self.ctx
        t, team, pid = ev["type"], ev.get("team"), ev.get("player_id")
        before = len(self.moments)
        if t == "shot" and shot is not None:
            if ev.get("outcome") == "goal":
                self.goal(ev, shot, state)
            elif shot["cq"] >= BIG_CHANCE_CQ:
                self.big_chance(ev, shot)
            if better is not None:
                self.better_option(ev, better)
        elif t == "var_review" and ev.get("outcome") == "overturned":
            self.correction(ev, state)
        elif t == "card":
            self.card(ev)
        elif t == "milestone" and pid:
            self.milestone(ev)
        elif t == "run" and run is not None:
            self.unfound_run(ev, run)
        self.pressure_spell(ev, state)
        self.momentum_swing(ev, state)
        if len(self.moments) == before and team and pid in ctx.players:
            self.pitch_tag(ev, metrics, shot)

    def goal(self, ev: dict, shot: dict, state: dict) -> None:
        ctx, src, pid, team = self.ctx, ev["event_id"], ev["player_id"], ev["team"]
        assist = ev.get("details", {}).get("assist_id")
        H, A = ctx.short(ctx.home_id), ctx.short(ctx.away_id)
        base = {
            "p": ctx.surname(pid),
            "t": ctx.short(team),
            "H": H,
            "A": A,
            "sh": state["score_home"],
            "sa": state["score_away"],
            "xg": rnd(shot["cq"]),
            "dist": shot["distance"],
        }
        pb, pp = player_vars(self.book, pid)
        base.update(pb)
        evidence = [
            ev_item(f"{H} goals", state["score_home"], None, src),
            ev_item(f"{A} goals", state["score_away"], None, src),
            ev_item("Chance quality", rnd(shot["cq"]), "xG", src),
            ev_item("Distance to goal", shot["distance"], "m", src),
            ev_item("Scorer", ctx.players[pid].name, None, src),
        ] + player_evidence(self.book, pid, src, ctx)
        per: dict[str, dict] = {lang: {} for lang in LANGS}
        players = [pid]
        if assist in ctx.players:
            a = ctx.surname(assist)
            ab, ap = player_vars(self.book, assist, "a")
            base.update(ab)
            evidence += [ev_item("Assist", ctx.players[assist].name, None, src)]
            evidence += player_evidence(self.book, assist, src, ctx)
            players.append(assist)
            x = {k: v for k, v in base.items() if k in ("xg", "axa")}
            for lang in LANGS:
                xa_l, xg_l = num(x["axa"], lang), num(x["xg"], lang)
                per[lang] = {
                    "casual": {
                        "extra": {
                            "en": f"{a} set it up!",
                            "es": f"¡Asistencia de {a}!",
                            "ar": f"التمريرة الحاسمة من {a}!",
                        }[lang]
                    },
                    "tactical": {
                        "why": {
                            "en": f"{a} played the final pass into a {xg_l} xG position.",
                            "es": f"{a} dio el último pase hacia una posición de {xg_l} xG.",
                            "ar": f"{a} مرر الكرة الأخيرة إلى موقع قيمته {xg_l} xG.",
                        }[lang]
                    },
                    "fantasy": {
                        "extra": {
                            "en": f" {a} adds {xa_l} xA from {ap[lang]['akp']}.",
                            "es": f" {a} añade {xa_l} xA con {ap[lang]['akp']}.",
                            "ar": f" وأضاف {a} {xa_l} xA من {ap[lang]['akp']}.",
                        }[lang]
                    },
                }
        else:
            for lang in LANGS:
                d, xg_l = num(base["dist"], lang), num(base["xg"], lang)
                per[lang] = {
                    "casual": {
                        "extra": {
                            "en": f"What a moment for {base['t']}!",
                            "es": f"¡Qué momento para {base['t']}!",
                            "ar": f"يا لها من لحظة لجماهير {base['t']}!",
                        }[lang]
                    },
                    "tactical": {
                        "why": {
                            "en": f"The finish came from {d} m at a {xg_l} xG rating.",
                            "es": f"El remate llegó desde {d} m con una valoración de {xg_l} xG.",
                            "ar": f"جاءت التسديدة من مسافة {d} م بتقييم {xg_l} xG.",
                        }[lang]
                    },
                    "fantasy": {"extra": ""},
                }
        self.add(ev, "goal", "lower_third", 95, "goal", base, merge(pp, per), evidence, team, players)

    def correction(self, ev: dict, state: dict) -> None:
        """VAR overturned a goal: a supersede card that rules the goal moment out."""
        ctx, src, team = self.ctx, ev["event_id"], ev.get("team")
        shot_id = ev.get("reviewed_event_id")
        goal = next((m for m in self.moments if m["event_id"] == shot_id and m["kind"] == "goal"), None)
        pid = ev.get("player_id")
        if goal is None or team is None or pid not in ctx.players:
            return
        reason = str(ev.get("review_reason") or "offside")
        H, A = ctx.short(ctx.home_id), ctx.short(ctx.away_id)
        base: dict[str, Any] = {
            "p": ctx.surname(pid),
            "t": ctx.short(team),
            "H": H,
            "A": A,
            "sh": state["score_home"],
            "sa": state["score_away"],
            "clk": goal["match_clock"],
        }
        pb, pp = player_vars(self.book, pid)
        base.update(pb)
        per = {lang: {"why_r": VAR_REASON[reason][lang]} for lang in LANGS}
        evidence = [
            ev_item(f"{H} goals", state["score_home"], None, src),
            ev_item(f"{A} goals", state["score_away"], None, src),
            ev_item("Goal ruled out (scored at)", goal["match_clock"], None, shot_id),
            ev_item("Scorer", ctx.players[pid].name, None, shot_id),
        ] + player_evidence(self.book, pid, src, ctx)
        extra = {"retracts": [goal["moment_id"]], "reason": f"var_{reason}"}
        self.add(
            ev,
            "correction",
            "full_screen",
            95,
            "correction",
            base,
            merge(pp, per),
            evidence,
            team,
            [pid],
            None,
            extra,
        )

    def card(self, ev: dict) -> None:
        ctx, src, pid, team = self.ctx, ev["event_id"], ev.get("player_id"), ev.get("team")
        if pid not in ctx.players:
            return
        colour = str(ev.get("details", {}).get("card", "yellow"))
        evidence = [ev_item("Card", colour, None, src), ev_item("Player", ctx.players[pid].name, None, src)]
        base: dict[str, Any] = {"p": ctx.surname(pid), "t": ctx.short(team)}
        pb, pp = player_vars(self.book, pid)
        base.update(pb)
        if colour == "red":
            self.reds[team] += 1
            base["n"] = 11 - self.reds[team]
            evidence.append(ev_item(f"{ctx.short(team)} players on the pitch", base["n"], None, src))
        evidence += player_evidence(self.book, pid, src, ctx)
        key = "card_red" if colour == "red" else "card_yellow"
        self.add(ev, "card", "lower_third", 80, key, base, pp, evidence, team, [pid])

    def milestone(self, ev: dict) -> None:
        ctx, src, pid, team = self.ctx, ev["event_id"], ev["player_id"], ev.get("team")
        label = str(ev.get("details", {}).get("label", "milestone"))
        names = MILESTONE_LABELS.get(label, dict.fromkeys(LANGS, label))
        base: dict[str, Any] = {"p": ctx.surname(pid), "t": ctx.short(team)}
        pb, pp = player_vars(self.book, pid)
        base.update(pb)
        per = {lang: {"lbl": names[lang]} for lang in LANGS}
        evidence = [ev_item("Milestone", label, None, src)] + player_evidence(self.book, pid, src, ctx)
        self.add(ev, "milestone", "lower_third", 60, "milestone", base, merge(pp, per), evidence, team, [pid])

    def big_chance(self, ev: dict, shot: dict) -> None:
        ctx, src, pid, team = self.ctx, ev["event_id"], ev["player_id"], ev["team"]
        oc = OUTCOME_PHRASE.get(ev.get("outcome") or "", OUTCOME_PHRASE["saved"])
        base: dict[str, Any] = {
            "p": ctx.surname(pid),
            "t": ctx.short(team),
            "xg": rnd(shot["cq"]),
            "dist": shot["distance"],
        }
        pb, pp = player_vars(self.book, pid)
        base.update(pb)
        bl = shot["blockers"]
        per = {}
        for lang in LANGS:
            if bl == 0:
                cone = {
                    "en": "No defender stood in the shooting cone",
                    "es": "Ningún defensor tapaba el ángulo de tiro",
                    "ar": "دون أي مدافع في مخروط التسديد",
                }[lang]
            else:
                c = count(bl, lang, *DEFENDERS)
                cone = {
                    "en": f"{c} stood in the shooting cone",
                    "es": f"{c} tapaban el ángulo de tiro",
                    "ar": f"مع وجود {c} في مخروط التسديد",
                }[lang]
            per[lang] = {"oc": oc[lang], "cone": cone}
        evidence = [
            ev_item("Chance quality", rnd(shot["cq"]), "xG", src),
            ev_item("Distance to goal", shot["distance"], "m", src),
            ev_item("Defenders in shooting cone", bl, None, src),
            ev_item("Outcome", ev.get("outcome") or "", None, src),
        ] + player_evidence(self.book, pid, src, ctx)
        self.add(
            ev, "big_chance", "side_panel", 70, "big_chance", base, merge(pp, per), evidence, team, [pid]
        )

    def better_option(self, ev: dict, bo: dict) -> None:
        ctx, src, team = self.ctx, ev["event_id"], ev["team"]
        s, m = bo["shooter_id"], bo["teammate_id"]
        base = {
            "s": ctx.surname(s),
            "m": ctx.surname(m),
            "shot": bo["shot_chance_quality"],
            "alt": bo["alt_value"],
            "altcq": bo["alt_chance_quality"],
            "tb": bo["times_better"],
            "ps": bo["pass_success"],
            "pdist": bo["pass_distance_m"],
            "marker": bo["nearest_marker_m"],
        }
        evidence = [
            ev_item("Shot chance quality", bo["shot_chance_quality"], "xG", src),
            ev_item("Pass option value (pass success x chance quality)", bo["alt_value"], "xG", src),
            ev_item("Teammate chance quality", bo["alt_chance_quality"], "xG", src),
            ev_item("Pass success probability", bo["pass_success"], None, src),
            ev_item("Times better", bo["times_better"], "x", src),
            ev_item("Pass distance", bo["pass_distance_m"], "m", src),
            ev_item("Nearest marker to teammate", bo["nearest_marker_m"], "m", src),
            ev_item("Shooter", ctx.players[s].name, None, src),
            ev_item("Free teammate", ctx.players[m].name, None, src),
        ]
        self.add(
            ev, "better_option", "full_screen", 90, "better_option", base, {}, evidence, team, [s, m], bo
        )

    def unfound_run(self, ev: dict, run: dict) -> None:
        ctx, src, team = self.ctx, ev["event_id"], ev["team"]
        r, c = run["runner_id"], run["carrier_id"]
        replay = {k: v for k, v in run.items() if not k.startswith("_")}
        base = {
            "r": ctx.surname(r),
            "c": ctx.surname(c),
            "pon": run["pass_on_at_s"],
            "clear": run["clear_of_line_m"],
            "proj": run["projected_chance_quality"],
        }
        oo1 = run["one_on_one"]
        per = {}
        for lang in LANGS:
            pon = num(run["pass_on_at_s"], lang)
            first = run["pass_on_at_s"] == 0
            per[lang] = {
                "oo": {
                    "en": "He would have been one on one with the keeper!"
                    if oo1
                    else "That was a real chance gone.",
                    "es": "¡Se habría quedado solo ante el portero!"
                    if oo1
                    else "Una ocasión de verdad que se esfumó.",
                    "ar": "كان سيصبح وجهًا لوجه مع الحارس!" if oo1 else "فرصة حقيقية ضاعت.",
                }[lang],
                "oo2": {
                    "en": ", one on one with the keeper",
                    "es": ", mano a mano con el portero",
                    "ar": "، في مواجهة مباشرة مع الحارس",
                }[lang]
                if oo1
                else "",
                "when": {
                    "en": "from the first stride" if first else f"{pon} s into the run",
                    "es": "desde la primera zancada" if first else f"a los {pon} s de iniciar el desmarque",
                    "ar": "منذ الخطوة الأولى" if first else f"بعد {pon} ث من بداية الانطلاقة",
                }[lang],
            }
        evidence = [
            ev_item("Pass on at", run["pass_on_at_s"], "s", src),
            ev_item("Pass on clock", run["pass_on_clock"], None, src),
            ev_item("Clear of the back line", run["clear_of_line_m"], "m", src),
            ev_item("Projected chance quality", run["projected_chance_quality"], "xG", src),
            ev_item("One on one", run["one_on_one"], None, src),
            ev_item("Runner", ctx.players[r].name, None, src),
            ev_item("Ball carrier", ctx.players[c].name, None, src),
        ]
        self.add(
            ev, "unfound_run", "full_screen", 90, "unfound_run", base, per, evidence, team, [r, c], replay
        )

    def team_window_vars(self, team: str, state: dict, src: str) -> tuple[dict, dict, list]:
        side = "home" if team == self.ctx.home_id else "away"
        w = state[side]
        short = self.ctx.short(team)
        base = {"wxg": w["xg"]}
        per = {
            lang: {
                "wshots": count(w["shots"], lang, *SHOTS),
                "ftp": count(w["final_third_passes"], lang, *FT_PASSES),
            }
            for lang in LANGS
        }
        evidence = [
            ev_item(f"{short} shots (last 5 min)", w["shots"], None, src),
            ev_item(f"{short} xG (last 5 min)", w["xg"], "xG", src),
            ev_item(f"{short} final-third passes (last 5 min)", w["final_third_passes"], None, src),
        ]
        return base, per, evidence

    def pressure_spell(self, ev: dict, state: dict) -> None:
        ctx = self.ctx
        for team, side in ((ctx.home_id, "home"), (ctx.away_id, "away")):
            idx = state[side]["pressure_index"]
            if idx < PRESSURE_SPELL_LEVEL:
                self.spell_start[team] = None
                self.spell_flagged[team] = False
                continue
            if self.spell_start[team] is None:
                self.spell_start[team] = ev["clock_s"]
            started = self.spell_start[team]
            if self.spell_flagged[team] or ev["clock_s"] - started < PRESSURE_SPELL_S:
                continue
            self.spell_flagged[team] = True
            src = ev["event_id"]
            mins = int((ev["clock_s"] - started) // 60)
            base = {
                "t": ctx.short(team),
                "o": ctx.short(ctx.other(team)),
                "idx": round(idx),
                "thr": PRESSURE_SPELL_LEVEL,
                "mins": mins,
            }
            wb, wp, wev = self.team_window_vars(team, state, src)
            base.update(wb)
            evidence = [
                ev_item(f"{ctx.short(team)} pressure index", round(idx), "0-100", src),
                ev_item("Pressure spell threshold", PRESSURE_SPELL_LEVEL, "0-100", src),
                ev_item("Spell length", mins, "min", src),
            ] + wev
            self.add(ev, "pressure_spell", "side_panel", 65, "pressure_spell", base, wp, evidence, team, [])

    def momentum_swing(self, ev: dict, state: dict) -> None:
        ctx, clock = self.ctx, ev["clock_s"]
        mom = state["momentum"]
        self.mom_hist.append((clock, mom))
        then = None
        while len(self.mom_hist) > 1 and self.mom_hist[1][0] <= clock - WINDOW_S:
            self.mom_hist.popleft()
        if self.mom_hist[0][0] <= clock - WINDOW_S:
            then = self.mom_hist[0][1]
        if then is None:
            return
        change = mom - then
        prior = list(self.swings)
        self.swings.append(change)
        if len(prior) < SWING_MIN_SAMPLES:
            return
        mean = sum(prior) / len(prior)
        sd = math.sqrt(sum((c - mean) ** 2 for c in prior) / len(prior))
        if abs(change) < SWING_MIN or abs(change) < SWING_SD * sd:
            return
        if self.last_swing is not None and clock - self.last_swing < SWING_GAP_S:
            return
        team = ctx.home_id if change > 0 else ctx.away_id
        if (mom > 0) != (change > 0):
            return  # a swing is reported only when the gaining side is now on top
        self.last_swing = clock
        src = ev["event_id"]
        side, oside = ("home", "away") if team == ctx.home_id else ("away", "home")
        base = {
            "t": ctx.short(team),
            "o": ctx.short(ctx.other(team)),
            "chg": round(abs(change)),
            "mom": round(abs(mom)),
            "pi": round(state[side]["pressure_index"]),
            "opi": round(state[oside]["pressure_index"]),
        }
        wb, wp, wev = self.team_window_vars(team, state, src)
        base.update(wb)
        evidence = [
            ev_item("Momentum change (5 min)", base["chg"], "points", src),
            ev_item(f"Momentum in favour of {base['t']}", base["mom"], "points", src),
            ev_item(f"{base['t']} pressure index", base["pi"], "0-100", src),
            ev_item(f"{base['o']} pressure index", base["opi"], "0-100", src),
        ] + wev
        self.add(ev, "momentum_swing", "side_panel", 60, "momentum_swing", base, wp, evidence, team, [])

    def pitch_tag(self, ev: dict, metrics: dict, shot: dict | None) -> None:
        clock = ev["clock_s"]
        if self.last_tag_clock is not None and clock - self.last_tag_clock < PITCH_TAG_GAP_S:
            return
        ctx, src, pid, team = self.ctx, ev["event_id"], ev["player_id"], ev["team"]
        pb, pp = player_vars(self.book, pid)
        base: dict[str, Any] = {"p": ctx.surname(pid), "t": ctx.short(team)}
        base.update(pb)
        pev = player_evidence(self.book, pid, src, ctx)
        if ev["type"] == "shot" and shot is not None and metrics["fast_shot"]:
            oc = OUTCOME_PHRASE.get(ev.get("outcome") or "", OUTCOME_PHRASE["saved"])
            base.update({"kmh": metrics["ball_speed_kmh"], "dist": shot["distance"], "xg": rnd(shot["cq"])})
            per = merge(pp, {lang: {"oc": oc[lang]} for lang in LANGS})
            evidence = [
                ev_item("Ball speed", metrics["ball_speed_kmh"], "km/h", src),
                ev_item("Distance to goal", shot["distance"], "m", src),
                ev_item("Chance quality", rnd(shot["cq"]), "xG", src),
            ] + pev
            kind, prio, players = "rocket_shot", 40, [pid]
        elif (ev.get("player_speed_mps") or 0.0) >= SPEED_BURST_MS:
            thr = M.kmh(SPEED_BURST_MS)
            base.update({"kmh": metrics["player_speed_kmh"], "thr": thr})
            per = pp
            evidence = [
                ev_item("Player speed", metrics["player_speed_kmh"], "km/h", src),
                ev_item("Speed burst threshold", thr, "km/h", src),
            ] + pev
            kind, prio, players = "speed_burst", 30, [pid]
        elif (
            ev["type"] == "pass"
            and ev.get("outcome") == "complete"
            and (metrics["pass_difficulty"] or 0) >= HARD_PASS_LEVEL
            and ev.get("receiver_id") in ctx.players
        ):
            rcv = ev["receiver_id"]
            end_zone = M.zone(*ctx.att(ev["end"], team))
            base.update(
                {
                    "rcv": ctx.surname(rcv),
                    "pd": metrics["pass_difficulty"],
                    "pdist": metrics["pass_distance_m"],
                }
            )
            per = merge(pp, {lang: {"zone": ZONE_PHRASE[end_zone][lang]} for lang in LANGS})
            evidence = [
                ev_item("Pass difficulty", metrics["pass_difficulty"], "0-100", src),
                ev_item("Pass distance", metrics["pass_distance_m"], "m", src),
                ev_item("End zone", end_zone, None, src),
                ev_item("Receiver", ctx.players[rcv].name, None, src),
            ] + pev
            kind, prio, players = "hard_pass", 30, [pid, rcv]
        else:
            return
        self.last_tag_clock = clock
        self.add(ev, kind, "pitch_tag", prio, kind, base, per, evidence, team, players)


# ----------------------------------------------------------------- recap

R: dict[str, dict[str, dict[str, Any]]] = {
    "casual": {
        "en": {
            "title_comeback": "{W} come back to beat {L}",
            "title_win": "{W} beat {L}",
            "title_draw": "{H} and {A} share the points",
            "headline": "{H} {sh}-{sa} {A}: what a game!",
            "p1_comeback": "What a game! {L} were {deficit} up, but {W} fought back to win {ws}-{ls}.",
            "p1_win": "{W} beat {L} {ws}-{ls} in a game full of chances.",
            "p1_draw": "{H} and {A} drew {sh}-{sa}.",
            "late": " The winner arrived at {wclock}, right at the death.",
            "p2_red": "{redp} was sent off for {redt} at {rclock}. ",
            "p2": "On {nbo_times} a player shot when a pass was the better choice, and there was {nur}.",
            "p3": "{H} had {xgh} xG from {shh}; {A} had {xga} xG from {sha}. Player of the match: {potm}.",
        },
        "es": {
            "title_comeback": "{W} remonta ante {L}",
            "title_win": "{W} gana a {L}",
            "title_draw": "{H} y {A} se reparten los puntos",
            "headline": "{H} {sh}-{sa} {A}: ¡qué partido!",
            "p1_comeback": "¡Qué partido! {L} ganaba por {deficit}, pero {W} remontó para ganar {ws}-{ls}.",
            "p1_win": "{W} ganó {ws}-{ls} a {L} en un partido lleno de ocasiones.",
            "p1_draw": "{H} y {A} empataron {sh}-{sa}.",
            "late": " El gol de la victoria llegó en el {wclock}, en el último suspiro.",
            "p2_red": "{redp} fue expulsado con {redt} en el {rclock}. ",
            "p2": "En {nbo_times} alguien tiró cuando el pase era mejor opción, y hubo {nur}.",
            "p3": "{H} sumó {xgh} xG con {shh}; {A}, {xga} xG con {sha}. Jugador del partido: {potm}.",
        },
        "ar": {
            "title_comeback": "{W} يقلب الطاولة على {L}",
            "title_win": "{W} يتغلب على {L}",
            "title_draw": "{H} و{A} يتقاسمان النقاط",
            "headline": "{H} {sh}-{sa} {A}: يا لها من مباراة!",
            "p1_comeback": "يا لها من مباراة! كان {L} متقدمًا بفارق {deficit}، لكن {W} عاد ليفوز {ws}-{ls}.",
            "p1_win": "فاز {W} على {L} {ws}-{ls} في مباراة مليئة بالفرص.",
            "p1_draw": "تعادل {H} و{A} {sh}-{sa}.",
            "late": " جاء هدف الفوز في الدقيقة {wclock}، في اللحظات الأخيرة.",
            "p2_red": "طُرد {redp} من {redt} في الدقيقة {rclock}. ",
            "p2": "في {nbo_times} سدد لاعب بينما كانت التمريرة الخيار الأفضل، وسُجلت {nur}.",
            "p3": "سجّل {H} {xgh} xG من {shh}، وسجّل {A} {xga} xG من {sha}. أفضل لاعب في المباراة: {potm}.",
        },
    },
    "tactical": {
        "en": {
            "title_comeback": "{W} {ws}-{ls} {L}: how the game turned",
            "title_win": "{W} {ws}-{ls} {L}: the analysis",
            "title_draw": "{H} {sh}-{sa} {A}: the analysis",
            "headline": "{W} edge the xG count {xgw} to {xgl}",
            "headline_under": "{W} win despite trailing {xgw} to {xgl} on xG",
            "headline_draw": "xG count: {H} {xgh}, {A} {xga}",
            "p1": "{H} {sh}-{sa} {A}. {H} created {xgh} xG from {shh}; {A} created {xga} xG from {sha}.",
            "p2_red": "The red card to {redp} at {rclock} left {redt} with {redn} players. ",
            "p2": "Peak five-minute pressure index: {H} {peakh}, {A} {peaka}.",
            "p3": "The engine flagged {nbo} shots where a pass was worth more, plus {nur}. Player of the match: {potm} ({pxg} xG, {pxa} xA).",
        },
        "es": {
            "title_comeback": "{W} {ws}-{ls} {L}: así cambió el partido",
            "title_win": "{W} {ws}-{ls} {L}: el análisis",
            "title_draw": "{H} {sh}-{sa} {A}: el análisis",
            "headline": "{W} gana el duelo de xG, {xgw} a {xgl}",
            "headline_under": "{W} gana pese a perder en xG, {xgw} a {xgl}",
            "headline_draw": "Duelo de xG: {H} {xgh}, {A} {xga}",
            "p1": "{H} {sh}-{sa} {A}. {H} generó {xgh} xG con {shh}; {A} generó {xga} xG con {sha}.",
            "p2_red": "La roja a {redp} en el {rclock} dejó a {redt} con {redn} jugadores. ",
            "p2": "Pico del índice de presión en cinco minutos: {H} {peakh}, {A} {peaka}.",
            "p3": "El motor detectó {nbo} tiros en los que un pase valía más, y {nur}. Jugador del partido: {potm} ({pxg} xG, {pxa} xA).",
        },
        "ar": {
            "title_comeback": "{W} {ws}-{ls} {L}: كيف انقلبت المباراة",
            "title_win": "{W} {ws}-{ls} {L}: التحليل",
            "title_draw": "{H} {sh}-{sa} {A}: التحليل",
            "headline": "{W} يتفوق في xG بنتيجة {xgw} مقابل {xgl}",
            "headline_under": "{W} يفوز رغم تأخره في xG بنتيجة {xgw} مقابل {xgl}",
            "headline_draw": "حصيلة xG: {H} {xgh}، {A} {xga}",
            "p1": "{H} {sh}-{sa} {A}. صنع {H} {xgh} xG من {shh}، وصنع {A} {xga} xG من {sha}.",
            "p2_red": "البطاقة الحمراء لـ{redp} في الدقيقة {rclock} تركت {redt} بـ{redn} لاعبين. ",
            "p2": "ذروة مؤشر الضغط خلال خمس دقائق: {H} {peakh}، {A} {peaka}.",
            "p3": "رصد المحرك {nbo} تسديدات كانت التمريرة فيها أجدى، إضافة إلى {nur}. أفضل لاعب: {potm} ({pxg} xG، {pxa} xA).",
        },
    },
    "fantasy": {
        "en": {
            "title": "Stats scout review: {H} {sh}-{sa} {A}",
            "headline": "{potm} leads the numbers",
            "p1": "{potm} tops the match with {pxg} xG, {pxa} xA, {pkp} and {pshots}.",
            "p2": "Top xG for {H}: {txh} with {txhv}. Top xG for {A}: {txa} with {txav}. Top xA: {tax} with {taxv}.",
            "p3": "Team totals: {H} {xgh} xG from {shh}, {A} {xga} xG from {sha}.",
        },
        "es": {
            "title": "Repaso del ojeador de datos: {H} {sh}-{sa} {A}",
            "headline": "{potm} lidera los números",
            "p1": "{potm} encabeza el partido con {pxg} xG, {pxa} xA, {pkp} y {pshots}.",
            "p2": "Máximo xG de {H}: {txh} con {txhv}. Máximo xG de {A}: {txa} con {txav}. Máximo xA: {tax} con {taxv}.",
            "p3": "Totales: {H} {xgh} xG con {shh}, {A} {xga} xG con {sha}.",
        },
        "ar": {
            "title": "مراجعة كشّاف الأرقام: {H} {sh}-{sa} {A}",
            "headline": "{potm} يتصدر الأرقام",
            "p1": "يتصدر {potm} المباراة برصيد {pxg} xG و{pxa} xA و{pkp} و{pshots}.",
            "p2": "الأعلى في xG لـ{H}: {txh} برصيد {txhv}. الأعلى في xG لـ{A}: {txa} برصيد {txav}. الأعلى في xA: {tax} برصيد {taxv}.",
            "p3": "حصيلة الفريقين: {H} {xgh} xG من {shh}، و{A} {xga} xG من {sha}.",
        },
    },
}


def potm_score(v: dict) -> float:
    return (
        4 * v["goals"]
        + 3 * v["assists"]
        + 3 * v["xg"]
        + 3 * v["xa"]
        + 0.5 * v["key_passes"]
        + 0.4 * (v["tackles_won"] + v["interceptions"])
        + 0.01 * v["passes_completed"]
    )


def build_recaps(
    ctx: Ctx,
    match_id: str,
    players: dict,
    moments: list,
    final: dict,
    goals: list,
    peaks: dict,
    final_clock: str,
) -> dict:
    hid, aid = ctx.home_id, ctx.away_id
    H, A = ctx.teams[hid].name, ctx.teams[aid].name
    sh, sa = final["score_home"], final["score_away"]
    winner = hid if sh > sa else aid if sa > sh else None
    loser = ctx.other(winner) if winner else None
    # largest deficit the winner overturned, and the goal that won it
    deficit, lead_goal = 0, None
    if winner:
        for g in goals:
            margin = g["score"][winner] - g["score"][loser]
            deficit = max(deficit, -margin)
        for g in goals:
            margin = g["score"][winner] - g["score"][loser]
            if margin > 0 and lead_goal is None:
                lead_goal = g
            elif margin <= 0:
                lead_goal = None
    potm_id = sorted(players, key=lambda p: (-potm_score(players[p]), p))[0]
    potm = players[potm_id]
    reds = [m for m in moments if m["kind"] == "card" and m["evidence"][0]["value"] == "red"]
    nbo = sum(1 for m in moments if m["kind"] == "better_option")
    nur = sum(1 for m in moments if m["kind"] == "unfound_run")
    team_of = {pid: players[pid]["team"] for pid in players}

    def top(team: str | None, key: str) -> str:
        pool = [p for p in players if team is None or team_of[p] == team]
        return sorted(pool, key=lambda p: (-players[p][key], p))[0]

    txh, txa, tax = top(hid, "xg"), top(aid, "xg"), top(None, "xa")
    stats: dict[str, Any] = {
        "home_team": H,
        "away_team": A,
        "score_home": sh,
        "score_away": sa,
        "xg_home": final["xg_home"],
        "xg_away": final["xg_away"],
        "shots_home": final["shots_home"],
        "shots_away": final["shots_away"],
        "pressure_peak_home": peaks[hid],
        "pressure_peak_away": peaks[aid],
        "better_options_flagged": nbo,
        "unfound_runs_flagged": nur,
        "player_of_the_match": ctx.players[potm_id].name,
        "potm_xg": potm["xg"],
        "potm_xa": potm["xa"],
        "potm_key_passes": potm["key_passes"],
        "potm_shots": potm["shots"],
        "top_xg_home": ctx.players[txh].name,
        "top_xg_home_value": players[txh]["xg"],
        "top_xg_away": ctx.players[txa].name,
        "top_xg_away_value": players[txa]["xg"],
        "top_xa": ctx.players[tax].name,
        "top_xa_value": players[tax]["xa"],
    }
    if deficit:
        stats["deficit_overturned"] = deficit
    late = lead_goal is not None and lead_goal["period"] == 2 and lead_goal["clock_s"] >= 85 * 60
    if late:
        stats["winning_goal_clock"] = lead_goal["match_clock"]
    if reds:
        red = reds[0]
        stats.update(
            {
                "red_card_player": ctx.players[red["player_ids"][0]].name,
                "red_card_clock": red["match_clock"],
                "red_card_team_players_left": red["evidence"][2]["value"],
            }
        )
    key_kinds = ("goal", "better_option", "unfound_run")
    ruled_out = {mid for m in moments for mid in m.get("retracts", [])}
    key_moments = [
        m for m in moments if (m["kind"] in key_kinds or m in reds) and m["moment_id"] not in ruled_out
    ]
    recaps: dict[str, dict] = {}
    for persona in PERSONAS:
        recaps[persona] = {}
        for lang in LANGS:
            tpl = R[persona][lang]

            def n(v: Any, lang: str = lang) -> str:
                return num(v, lang)

            v: dict[str, Any] = {
                "H": H,
                "A": A,
                "sh": sh,
                "sa": sa,
                "xgh": n(final["xg_home"]),
                "xga": n(final["xg_away"]),
                "shh": count(final["shots_home"], lang, *SHOTS),
                "sha": count(final["shots_away"], lang, *SHOTS),
                "potm": ctx.players[potm_id].name,
                "pxg": n(potm["xg"]),
                "pxa": n(potm["xa"]),
                "pkp": count(potm["key_passes"], lang, *KEY_PASSES),
                "pshots": count(potm["shots"], lang, *SHOTS),
                "nbo": nbo,
                "nbo_times": count(nbo, lang, *TIMES),
                "nur": count(nur, lang, *RUNS),
                "peakh": n(peaks[hid]),
                "peaka": n(peaks[aid]),
                "txh": ctx.players[txh].name,
                "txhv": n(players[txh]["xg"]),
                "txa": ctx.players[txa].name,
                "txav": n(players[txa]["xg"]),
                "tax": ctx.players[tax].name,
                "taxv": n(players[tax]["xa"]),
            }
            if winner:
                v.update(
                    {
                        "W": ctx.teams[winner].name,
                        "L": ctx.teams[loser].name,
                        "ws": max(sh, sa),
                        "ls": min(sh, sa),
                        "deficit": count(deficit, lang, *GOALS),
                        "xgw": n(final["xg_home"] if winner == hid else final["xg_away"]),
                        "xgl": n(final["xg_away"] if winner == hid else final["xg_home"]),
                    }
                )
            if late:
                v["wclock"] = lead_goal["match_clock"]
            if reds:
                v.update(
                    {
                        "redp": ctx.players[reds[0]["player_ids"][0]].name,
                        "redt": ctx.teams[reds[0]["team"]].name,
                        "rclock": reds[0]["match_clock"],
                        "redn": stats["red_card_team_players_left"],
                    }
                )
            if persona == "fantasy":
                title = tpl["title"].format(**v)
                headline = tpl["headline"].format(**v)
                paras = [tpl["p1"].format(**v), tpl["p2"].format(**v), tpl["p3"].format(**v)]
            elif persona == "casual":
                kind = "comeback" if winner and deficit else "win" if winner else "draw"
                title = tpl[f"title_{kind}"].format(**v)
                headline = tpl["headline"].format(**v)
                p1 = tpl[f"p1_{kind}"].format(**v) + (tpl["late"].format(**v) if late else "")
                p2 = (tpl["p2_red"].format(**v) if reds else "") + tpl["p2"].format(**v)
                paras = [p1, p2, tpl["p3"].format(**v)]
            else:
                kind = "comeback" if winner and deficit else "win" if winner else "draw"
                title = tpl[f"title_{kind}"].format(**v)
                ahead = winner and float(v["xgw"].replace(",", ".")) >= float(v["xgl"].replace(",", "."))
                headline = tpl[
                    "headline_draw" if not winner else "headline" if ahead else "headline_under"
                ].format(**v)
                p2 = (tpl["p2_red"].format(**v) if reds else "") + tpl["p2"].format(**v)
                paras = [tpl["p1"].format(**v), p2, tpl["p3"].format(**v)]
            recap = {
                "match_id": match_id,
                "persona": persona,
                "language": lang,
                "rtl": lang == "ar",
                "title": title,
                "headline": headline,
                "summary_paragraphs": paras,
                "key_moments": [
                    {
                        "match_clock": m["match_clock"],
                        "kind": m["kind"],
                        "headline": m["texts"][persona][lang]["headline"],
                        "moment_id": m["moment_id"],
                    }
                    for m in key_moments
                ],
                "player_of_the_match_id": potm_id,
                "player_of_the_match": ctx.players[potm_id].name,
                "stats": stats,
                "generated_at_clock": final_clock,
                "produced_by": "template",
                "fact_check": {"ok": True, "reasons": []},
            }
            bad = [x for s in [title, headline, *paras] for x in unsupported_numbers(s, list(stats.values()))]
            recap["fact_check"] = {"ok": not bad, "reasons": [f"number {x} not in stats" for x in bad]}
            recaps[persona][lang] = recap
    return recaps


# ------------------------------------------------------------- checking

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
BANNED = ("Manchester", "Arsenal", "Liverpool", "Chelsea", "Premier League", "Haaland", "Saka")


def numbers_in(text: str) -> list[float]:
    t = text.translate(ARABIC_DIGITS)
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    return [float(x) for x in NUM_RE.findall(t)]


def unsupported_numbers(text: str, values: list[Any]) -> list[float]:
    allowed: set[float] = set()
    for v in values:
        if isinstance(v, bool):
            continue
        if isinstance(v, int | float):
            allowed.add(float(v))
        elif isinstance(v, str):
            allowed.update(numbers_in(v))
    return [x for x in numbers_in(text) if x not in allowed]


def sentences(text: str) -> int:
    return len(re.findall(r"[.!?؟](?=\s|$)", text))


def self_check(fixture: dict, raw_events: list[dict]) -> list[str]:
    problems: list[str] = []
    for m in fixture["moments"]:
        values = [e["value"] for e in m["evidence"]]
        for lang in ("es", "ar"):
            labels = m["evidence_labels"][lang]
            if len(labels) != len(m["evidence"]):
                problems.append(f"{m['moment_id']}: evidence_labels[{lang}] length does not match evidence")
            names = " ".join(str(e["label"]) for e in m["evidence"])
            if any(re.search(r"\d", lab) and not re.search(r"\d", names) for lab in labels):
                problems.append(f"{m['moment_id']}: number in a translated evidence label")
        for persona, langs in m["texts"].items():
            for lang, tx in langs.items():
                where = f"{m['moment_id']} {persona}/{lang}"
                for part in ("headline", "body", "why"):
                    bad = unsupported_numbers(tx[part], values)
                    if bad:
                        problems.append(f"{where} {part}: numbers {bad} not in evidence")
                if len(tx["headline"].split()) > 8:
                    problems.append(f"{where}: headline over 8 words: {tx['headline']}")
                if sentences(tx["body"]) > 2:
                    problems.append(f"{where}: body over 2 sentences")
                if sentences(tx["why"]) > 1:
                    problems.append(f"{where}: why over 1 sentence")
                if "{" in tx["headline"] + tx["body"] + tx["why"]:
                    problems.append(f"{where}: unfilled placeholder")
    for persona, langs in fixture["recaps"].items():
        for lang, rc in langs.items():
            if not rc["fact_check"]["ok"]:
                problems.append(f"recap {persona}/{lang}: {rc['fact_check']['reasons']}")
    text = json.dumps(fixture, ensure_ascii=False)
    if '"labels"' in text or "freeze_frame" in text or '"tracking"' in text:
        problems.append("ground-truth labels or raw frames leaked into the fixture")
    for label in {lab for e in raw_events for lab in e.get("labels", [])}:
        if f'"{label}"' in text:
            problems.append(f"label {label} leaked")
    for word in BANNED:
        if word.lower() in text.lower():
            problems.append(f"banned real-world name in fixture: {word}")
    return problems


def check_scripted(fixture: dict, raw_events: list[dict]) -> list[str]:
    """Evaluation only: compare the detector against the simulator's ground truth.
    Labels never drive the output; this runs after the fixture is built."""
    problems: list[str] = []
    by_event = {m["event_id"]: m for m in fixture["moments"] if m["kind"] == "better_option"}
    runs = {m["event_id"]: m for m in fixture["moments"] if m["kind"] == "unfound_run"}
    for e in raw_events:
        for lab in e.get("labels", []):
            if lab.startswith("better_option:"):
                m = by_event.get(e["event_id"])
                want = lab.split(":", 1)[1]
                if m is None or m["replay"]["teammate_id"] != want or m["replay"]["times_better"] < 2:
                    problems.append(f"better option at {e['match_clock']} ({want}) not flagged")
            if lab == "scripted:run_not_found" and e["type"] == "run":
                m = runs.get(e["event_id"])
                if m is None or m["replay"]["pass_on_at_s"] > 1.5 or not m["replay"]["one_on_one"]:
                    problems.append(f"unfound run at {e['match_clock']} not flagged")
    return problems


# ------------------------------------------------------------------ build


def build(path: Path) -> tuple[dict, list[dict]]:
    raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    start = next(e for e in raw if e["type"] == "match_start")
    match_id = start["match_id"]
    ctx = Ctx(start["details"]["home"], start["details"]["away"])
    state_engine = StateEngine(match_id, ctx)
    book = PlayerBook(ctx)
    spotter = Spotter(ctx, book)
    prev_players = book.views()
    ticks: list[dict] = []
    goals: list[dict] = []
    peaks = {ctx.home_id: 0.0, ctx.away_id: 0.0}
    state: dict[str, Any] = {}
    for ev in raw:
        if ev["type"] == "period_start":
            state_engine.start_period(ev["period"], ev["clock_s"])
            spotter.start_period()
        shot = shot_model(ev, ctx) if ev["type"] == "shot" and ev.get("start") else None
        metrics = event_metrics(ev, ctx, shot)
        cq = shot["cq"] if shot else None
        state_engine.process(ev, metrics, cq)
        book.process(ev, cq)
        state = state_engine.snapshot(ev)
        for team, side in ((ctx.home_id, "home"), (ctx.away_id, "away")):
            peaks[team] = max(peaks[team], state[side]["pressure_index"])
        better = analyse_shot(ev, ctx, shot) if shot and ev.get("outcome") != "goal" else None
        run = analyse_run(ev, ctx) if ev["type"] == "run" else None
        if ev["type"] == "shot" and ev.get("outcome") == "goal":
            goals.append(
                {
                    "event_id": ev["event_id"],
                    "clock_s": ev["clock_s"],
                    "period": ev["period"],
                    "match_clock": ev["match_clock"],
                    "score": {ctx.home_id: state["score_home"], ctx.away_id: state["score_away"]},
                }
            )
        if ev["type"] == "var_review" and ev.get("outcome") == "overturned":
            goals = [g for g in goals if g["event_id"] != ev.get("reviewed_event_id")]
        spotter.process(ev, metrics, shot, better, run, state)
        now_players = book.views()
        changed = [now_players[p] for p in now_players if now_players[p] != prev_players[p]]
        prev_players = now_players
        ticks.append(
            {
                "event": public_event(ev, metrics),
                "clock": ev["match_clock"],
                "period": ev["period"],
                "score": {"home": state["score_home"], "away": state["score_away"]},
                "state": state,
                "control_chaos": control_chaos_view(state),
                "players_changed": changed,
            }
        )
    moments = spotter.moments
    recaps = build_recaps(
        ctx,
        match_id,
        prev_players,
        moments,
        state,
        goals,
        {k: round(v) for k, v in peaks.items()},
        raw[-1]["match_clock"],
    )
    fixture = {
        "fixture_version": FIXTURE_VERSION,
        "match_id": match_id,
        "source": f"Offline demo recorded from the Matchmind engine ({match_id}). Template crew, no AI.",
        "notes": NOTES,
        "teams": {"home": ctx.team_info(ctx.home_id), "away": ctx.team_info(ctx.away_id)},
        "crew": {
            "mode": "template",
            "model": None,
            "breakers_open": [],
            "moments": len(moments),
            "fallbacks": 0,
            "rejections": 0,
        },
        "ticks": ticks,
        "moments": moments,
        "recaps": recaps,
    }
    return fixture, raw


def serialise(fixture: dict) -> bytes:
    return json.dumps(fixture, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", type=Path, default=DEFAULT_IN)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    fixture, raw = build(args.input)
    data = serialise(fixture)
    again, _ = build(args.input)
    problems = []
    if serialise(again) != data:
        problems.append("fixture is not deterministic")
    problems += self_check(fixture, raw)
    problems += check_scripted(fixture, raw)
    if problems:
        print("Self-check failed:", file=sys.stderr)
        for p in problems[:50]:
            print(f"  - {p}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    kinds: dict[str, int] = {}
    for m in fixture["moments"]:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    print(f"Wrote {args.output} ({len(data) / 1e6:.2f} MB): {len(fixture['ticks'])} ticks, moments {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
