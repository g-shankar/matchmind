"""`Intent` + the match as of the playback clock -> one fact-checked answer.

Answers are template sentences (ask/i18n.py) filled only with numbers and
names taken from the stats engine at the current position: the match state,
player stats, team totals and the moments spotted so far. Nothing after the
clock is ever read, so an answer cannot give away the future. With spoilers
off (catch-up mode) the score, goals, assists and VAR outcomes are never read
either (crew/spoilers.py).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from matchmind.crew.contracts import Evidence, FactValue, Moment, MomentKind, without_retracted
from matchmind.crew.i18n import fill
from matchmind.crew.spoilers import SPOILER_FACT_KEYS, is_spoiler_moment
from matchmind.crew.spotter import r1, r2, surname
from matchmind.simulator.teams import Team
from matchmind.stats.models import MatchStateSnapshot, PlayerStats

from .guard import safe_display_name
from .i18n import ask_pack
from .intents import SPOILER_INTENTS, Intent

MOMENTUM_ON_TOP = 15  # |momentum| at or above this names the side on top
MAX_LINE_ITEMS = 4


@dataclass(frozen=True)
class AskContext:
    """The match as of the playback clock. Built by the API (or the offline fixture
    builder) from the stats engine; nothing in it is later than `clock`."""

    match_id: str
    clock: str
    clock_s: float
    period: int
    ended: bool
    home_id: str
    away_id: str
    teams: Mapping[str, Team]
    snapshot: MatchStateSnapshot
    players: Sequence[PlayerStats]
    moments: Sequence[Moment] = ()
    team_totals: Mapping[str, Mapping[str, Any]] | None = None  # basic stats `teams`, when known
    physical_source: str = "event_estimate"


@dataclass
class Composed:
    status: str  # answered | hidden | clarify | not_yet
    sentences: list[tuple[str, str]] = field(default_factory=list)  # (text, template)
    facts: dict[str, FactValue] = field(default_factory=dict)
    evidence_keys: list[tuple[str, str | None]] = field(default_factory=list)  # (fact key, unit)
    labels: dict[str, str] = field(default_factory=dict)  # evidence labels for keys named on the fly
    source_event_ids: list[str] = field(default_factory=list)
    moment_ids: list[str] = field(default_factory=list)


def minute_of(clock_s: float, period: int) -> int:
    return int(clock_s // 60)


def _name(ctx: AskContext, player_id: str) -> str:
    """The player's squad name, or his shirt number when the name is not safe to print."""
    for t in ctx.teams.values():
        for p in t.players:
            if p.player_id == player_id:
                return p.name if safe_display_name(p.name) else f"#{p.number}"
    return player_id


def _team_name(ctx: AskContext, team_id: str | None) -> str:
    if team_id is None or team_id not in ctx.teams:
        return team_id or ""
    name = ctx.teams[team_id].name
    return name if safe_display_name(name) else team_id


def _number(ctx: AskContext, player_id: str) -> int | None:
    for t in ctx.teams.values():
        for p in t.players:
            if p.player_id == player_id:
                return p.number
    return None


class _Writer:
    def __init__(self, ctx: AskContext, language: str) -> None:
        self.ctx = ctx
        self.lang = language
        self.pack = ask_pack(language)
        self.out = Composed(status="answered")
        self.out.facts.update(
            clock=ctx.clock, home=_team_name(ctx, ctx.home_id), away=_team_name(ctx, ctx.away_id)
        )

    def fact(
        self,
        key: str,
        value: FactValue,
        unit: str | None = None,
        evidence: bool = False,
        label: str | None = None,
    ) -> None:
        self.out.facts[key] = value
        if evidence:
            self.out.evidence_keys.append((key, unit))
        if label is not None:
            self.out.labels[key] = label

    def say(self, key: str, **extra: FactValue) -> None:
        template = self.pack[key]
        values = {**self.out.facts, **extra}
        self.out.sentences.append((fill(template, values, self.lang), template))

    def word(self, group: str, key: str) -> str:
        return str(self.pack[group].get(key, key))

    def moments(self, *kinds: MomentKind, spoilers: bool = True) -> list[Moment]:
        kept = without_retracted(list(self.ctx.moments))
        out = [m for m in kept if not kinds or m.kind in kinds]
        return out if spoilers else [m for m in out if not is_spoiler_moment(m)]

    def cite(self, moments: Sequence[Moment]) -> None:
        for m in moments:
            self.out.moment_ids.append(m.moment_id)
            self.out.source_event_ids += m.source_event_ids


def compose(intent: Intent, ctx: AskContext, language: str, spoilers: bool = True) -> Composed:
    w = _Writer(ctx, language)
    if not spoilers and intent.kind in SPOILER_INTENTS:
        return Composed(status="hidden")
    handler = _HANDLERS[intent.kind]
    handler(w, intent, spoilers)
    if not spoilers:  # belt and braces: no result fact leaves a catch-up answer
        w.out.facts = {k: v for k, v in w.out.facts.items() if k not in SPOILER_FACT_KEYS}
    return w.out


# --- One handler per intent ----------------------------------------------------------------------


def _score(w: _Writer, intent: Intent, spoilers: bool) -> None:
    snap = w.ctx.snapshot
    w.fact("score_home", snap.score_home, evidence=True)
    w.fact("score_away", snap.score_away, evidence=True)
    w.say("score_full" if w.ctx.ended else "score_live")
    w.cite(w.moments(MomentKind.GOAL))


def _scorers(w: _Writer, intent: Intent, spoilers: bool) -> None:
    goals = w.moments(MomentKind.GOAL)
    if intent.team:
        goals = [m for m in goals if m.team == intent.team]
    if not goals:
        w.say("scorers_none")
    else:
        items = [f"{_short(w, m)} {m.match_clock} ({_team_name(w.ctx, m.team)})" for m in goals]
        w.fact("n_goals", len(goals), evidence=True)
        w.fact("goals_line", ", ".join(items))
        w.say("scorers")
        w.cite(goals)
    ruled = [m for m in w.ctx.moments if m.kind == MomentKind.CORRECTION]
    if ruled:
        lines = [f"{_short(w, m)} {m.facts.get('ruled_out_clock', m.match_clock)}" for m in ruled]
        w.fact("ruled_out_line", ", ".join(lines))
        w.say("scorers_ruled_out")
        w.cite(ruled)


def _short(w: _Writer, m: Moment) -> str:
    pid = m.player_ids[0] if m.player_ids else None
    return surname(_name(w.ctx, pid)) if pid else _team_name(w.ctx, m.team)


_TEAM_FIELDS: dict[str, tuple[str, str | None, int | None]] = {
    # metric -> (team totals field, unit, decimals)
    "shots_on_target": ("shots_on_target", None, None),
    "possession": ("possession_pct", "%", 1),
    "pass_accuracy": ("pass_accuracy_pct", "%", 1),
    "passes": ("passes_completed", None, None),
    "tackles": ("tackles_won", None, None),
    "distance": ("distance_km", " km", 1),
}


def _team_values(w: _Writer, metric: str) -> tuple[Any, Any, str | None] | None:
    snap = w.ctx.snapshot
    if metric == "xg":
        return r2(snap.xg_home), r2(snap.xg_away), None
    if metric == "shots":
        return snap.shots_home, snap.shots_away, None
    totals = w.ctx.team_totals
    spec = _TEAM_FIELDS.get(metric)
    if totals is None or spec is None:
        return None
    field_name, unit, _ = spec
    home = (totals.get(w.ctx.home_id) or {}).get(field_name)
    away = (totals.get(w.ctx.away_id) or {}).get(field_name)
    if home is None or away is None:
        return None
    return home, away, unit


def _team_stat(w: _Writer, intent: Intent, spoilers: bool) -> None:
    metric = intent.metric or "xg"
    label = w.word("labels", metric)
    values = _team_values(w, metric)
    if values is None:
        w.say("team_na", label=label)
        return
    home, away, unit = values
    unit_text = (" " if w.lang == "fr" and unit == "%" else "") + (unit or "")
    suffix = _UNIT_SUFFIX.get(unit or "", "")
    keys = {side: f"{metric}_{side}{suffix}" for side in ("home", "away")}
    for side, value, team_id in (("home", home, w.ctx.home_id), ("away", away, w.ctx.away_id)):
        w.fact(
            keys[side],
            value,
            (unit or "").strip() or None,
            evidence=intent.team in (None, team_id),
            label=f"{label} · {w.out.facts[side]}",
        )
    if intent.team in (w.ctx.home_id, w.ctx.away_id):
        side = "home" if intent.team == w.ctx.home_id else "away"
        w.fact("team", _team_name(w.ctx, intent.team))
        w.say("team_one", label=label, value=w.out.facts[keys[side]], unit=unit_text)
    else:
        w.say("team_both", label=label, value_home=home, value_away=away, unit=unit_text)


_UNIT_SUFFIX = {"%": "_pct", " km": "_km", " km/h": "_kmh"}

_PLAYER_FIELDS: dict[str, tuple[str, str | None, int | None]] = {
    "distance": ("distance_km", " km", 2),
    "top_speed": ("top_speed_kmh", " km/h", 1),
    "passes": ("passes_completed", None, None),
    "tackles": ("tackles_won", None, None),
    "xg": ("xg", None, 2),
    "shots": ("shots", None, None),
    "sprints": ("sprints", None, None),
    "key_passes": ("key_passes", None, None),
    "interceptions": ("interceptions", None, None),
    "touches": ("touches", None, None),
}


def _player_value(p: PlayerStats, metric: str) -> float | int:
    field_name, _, decimals = _PLAYER_FIELDS[metric]
    value = getattr(p, field_name)
    if decimals == 2:
        return r2(value)
    if decimals == 1:
        return r1(value)
    return value


def _physical_note(w: _Writer, metric: str | None) -> None:
    if metric in ("distance", "top_speed", "sprints"):
        w.say("tracking_note" if w.ctx.physical_source == "synthetic_tracking" else "event_note")


def _top_player(w: _Writer, intent: Intent, spoilers: bool) -> None:
    metric = intent.metric or "distance"
    label = w.word("labels", metric)
    unit = _PLAYER_FIELDS[metric][1] or ""
    pool = [p for p in w.ctx.players if intent.team is None or p.team == intent.team]
    ranked = sorted(pool, key=lambda p: (-float(_player_value(p, metric)), p.player_id))
    ranked = [p for p in ranked if float(_player_value(p, metric)) > 0]
    if not ranked:
        w.say("top_none", label=label)
        return
    best = ranked[0]
    suffix = _UNIT_SUFFIX.get(unit, "_xg" if metric == "xg" else "")
    w.fact("player", _name(w.ctx, best.player_id))
    w.fact("team", _team_name(w.ctx, best.team))
    w.fact(
        f"value{suffix}",
        _player_value(best, metric),
        unit.strip() or None,
        evidence=True,
        label=str(w.out.facts["player"]),
    )
    w.say("top_lead", label=label, unit=unit, value=w.out.facts[f"value{suffix}"])
    if len(ranked) > 1:
        second = ranked[1]
        w.fact("second", _name(w.ctx, second.player_id))
        w.fact("second_team", _team_name(w.ctx, second.team))
        w.fact(
            f"second_value{suffix}",
            _player_value(second, metric),
            unit.strip() or None,
            evidence=True,
            label=str(w.out.facts["second"]),
        )
        w.say("top_second", unit=unit, second_value=w.out.facts[f"second_value{suffix}"])
    _physical_note(w, metric)


def _player_stats(w: _Writer, intent: Intent, spoilers: bool) -> None:
    pid = intent.player_id or ""
    stats = next((p for p in w.ctx.players if p.player_id == pid), None)
    team_id = next(
        (t.team_id for t in w.ctx.teams.values() if any(p.player_id == pid for p in t.players)), None
    )
    w.fact("player", _name(w.ctx, pid))
    w.fact("team", _team_name(w.ctx, team_id))
    if stats is None or stats.touches == 0:
        w.say("player_none")
        return
    if intent.metric is not None:
        unit = _PLAYER_FIELDS[intent.metric][1] or ""
        key = "value" + _UNIT_SUFFIX.get(unit, "_xg" if intent.metric == "xg" else "")
        label = w.word("labels", intent.metric)
        w.fact(key, _player_value(stats, intent.metric), unit.strip() or None, evidence=True, label=label)
        w.say("player_metric", label=label, unit=unit, value=w.out.facts[key])
        _physical_note(w, intent.metric)
        return
    number = _number(w.ctx, pid)
    if number is not None:
        w.fact("number", number)
    w.fact("passes_completed", stats.passes_completed, evidence=True)
    w.fact("passes", stats.passes, evidence=True)
    w.fact("shots", stats.shots, evidence=True)
    w.fact("xg", r2(stats.xg), evidence=True)
    w.say("player_line")
    w.fact("distance_km", r2(stats.distance_km), "km", evidence=True)
    w.fact("top_speed_kmh", r1(stats.top_speed_kmh), "km/h", evidence=True)
    w.say("player_physical")
    if spoilers:
        w.fact("goals", stats.goals, evidence=True)
        w.fact("assists", stats.assists, evidence=True)
        w.say("player_goals")
    _physical_note(w, "distance")


def _control(w: _Writer, intent: Intent, spoilers: bool) -> None:
    snap = w.ctx.snapshot
    w.fact("possession_home_pct", r1(snap.home.possession_pct), "%", evidence=True)
    w.fact("possession_away_pct", r1(snap.away.possession_pct), "%", evidence=True)
    w.say("control")
    w.fact("cci_abs", r2(abs(snap.control_chaos)), evidence=True)
    w.fact("tempo", w.word("tempo", snap.tempo))
    w.say("control_tilt_control" if snap.control_chaos >= 0 else "control_tilt_chaos")


def _momentum(w: _Writer, intent: Intent, spoilers: bool) -> None:
    snap = w.ctx.snapshot
    momentum = int(round(snap.momentum))
    w.fact("momentum_abs", abs(momentum), evidence=True)
    if abs(momentum) >= MOMENTUM_ON_TOP:
        w.fact("on_top", w.out.facts["home"] if momentum > 0 else w.out.facts["away"])
        w.say("momentum_top")
    else:
        w.say("momentum_level")
    w.fact("pressure_home", int(round(snap.home.pressure_index)), evidence=True)
    w.fact("pressure_away", int(round(snap.away.pressure_index)), evidence=True)
    w.say("momentum_pressure")
    spells = w.moments(MomentKind.PRESSURE_SPELL)
    w.fact("n_pressure_spells", len(spells), evidence=True)
    w.say("momentum_spells")
    w.cite(spells[-MAX_LINE_ITEMS:])


def _better_option(w: _Writer, intent: Intent, spoilers: bool) -> None:
    found = w.moments(MomentKind.BETTER_OPTION, spoilers=spoilers)
    if not found:
        w.say("better_none")
        return
    w.fact("n_better_options", len(found), evidence=True)
    w.say("better_count")
    latest = found[-1]
    facts = latest.facts
    if all(k in facts for k in ("player", "teammate", "times_better")) and _safe_names(
        facts, "player", "teammate"
    ):
        w.fact("moment_clock", latest.match_clock)
        w.fact("player", str(facts["player"]))
        w.fact("teammate", str(facts["teammate"]))
        w.fact("times_better", facts["times_better"], "x", evidence=True)
        w.say("better_latest")
    w.cite(found[-MAX_LINE_ITEMS:])


def _safe_names(facts: Mapping[str, FactValue], *keys: str) -> bool:
    return all(safe_display_name(str(facts.get(k, ""))) for k in keys)


def _var(w: _Writer, intent: Intent, spoilers: bool) -> None:
    found = [m for m in w.ctx.moments if m.kind == MomentKind.CORRECTION]
    if not found:
        w.say("var_none")
        return
    w.fact("n_var", len(found), evidence=True)
    w.say("var_count")
    latest = found[-1]
    pid = latest.player_ids[0] if latest.player_ids else None
    if pid is not None:
        w.fact("player", _name(w.ctx, pid))
        w.fact("ruled_out_clock", str(latest.facts.get("ruled_out_clock", latest.match_clock)))
        w.fact("reason_word", w.word("reason", str(latest.facts.get("reason", "offside"))))
        w.say("var_latest")
    snap = w.ctx.snapshot
    w.fact("score_home", snap.score_home, evidence=True)
    w.fact("score_away", snap.score_away, evidence=True)
    w.say("var_now")
    w.cite(found)


def _cards(w: _Writer, intent: Intent, spoilers: bool) -> None:
    found = w.moments(MomentKind.CARD)
    if intent.team:
        found = [m for m in found if m.team == intent.team]
    if not found:
        w.say("cards_none")
        return
    reds = sum(1 for m in found if m.facts.get("card") == "red")
    w.fact("n_yellow", len(found) - reds, evidence=True)
    w.fact("n_red", reds, evidence=True)
    w.say("cards_count")
    latest = found[-1]
    if latest.player_ids:
        w.fact("player", _name(w.ctx, latest.player_ids[0]))
        w.fact("team", _team_name(w.ctx, latest.team))
        w.fact("card_word", w.word("card_word", str(latest.facts.get("card", "yellow"))))
        w.fact("moment_clock", latest.match_clock)
        w.say("cards_latest")
    w.cite(found[-MAX_LINE_ITEMS:])


_CONST = re.compile(r"[+-]?\d+(?:[.,]\d+)?")


def _explain(w: _Writer, intent: Intent, spoilers: bool) -> None:
    """Fixed text written by the team. Its numbers are definition constants (ranges),
    listed as facts so the checker still ties every printed number to something."""
    template = w.pack["explain"][intent.metric or "chance_quality"]
    for i, token in enumerate(_CONST.findall(template)):
        value = float(token.replace(",", "."))
        w.fact(f"definition_{i}", int(value) if value.is_integer() else value)
    w.out.sentences.append((template, template))


_TRACKED_KINDS = (
    MomentKind.GOAL,
    MomentKind.CARD,
    MomentKind.BIG_CHANCE,
    MomentKind.BETTER_OPTION,
    MomentKind.UNFOUND_RUN,
    MomentKind.MOMENTUM_SWING,
    MomentKind.PRESSURE_SPELL,
    MomentKind.KEY_TACKLE,
    MomentKind.CORRECTION,
)


def _window(w: _Writer, intent: Intent, spoilers: bool) -> None:
    start, end = intent.from_minute or 0, intent.to_minute or 0
    now = minute_of(w.ctx.clock_s, w.ctx.period)
    w.fact("from_clock", f"{start}:00")
    w.fact("to_clock", f"{end}:00")
    if start >= now and not w.ctx.ended:
        w.out.status = "not_yet"
        w.say("not_yet")
        return
    kept = w.moments(*_TRACKED_KINDS, spoilers=spoilers)  # ruled-out goals are gone; corrections stay
    inside = [m for m in kept if start * 60 <= m.clock_s < end * 60]
    inside.sort(key=lambda m: (m.period, m.clock_s))
    if not inside:
        w.say("window_none")
    else:
        shown = inside[:MAX_LINE_ITEMS]
        items = [f"{w.word('kinds', str(m.kind))} ({_short(w, m)}, {m.match_clock})" for m in shown]
        w.fact("n_moments", len(inside), evidence=True)
        w.fact("moments_line", "; ".join(items))
        w.say("window_count")
        w.cite(shown)
    if end > now and not w.ctx.ended:
        w.say("window_partial")


_HANDLERS = {
    "score": _score,
    "scorers": _scorers,
    "team_stat": _team_stat,
    "top_player": _top_player,
    "player_stats": _player_stats,
    "control": _control,
    "momentum": _momentum,
    "better_option": _better_option,
    "var": _var,
    "cards": _cards,
    "explain_metric": _explain,
    "window": _window,
}


def evidence_for(composed: Composed, labels: Mapping[str, str]) -> list[Evidence]:
    labels = {**labels, **composed.labels}
    out = []
    for key, unit in composed.evidence_keys:
        if key not in composed.facts:
            continue
        out.append(
            Evidence(
                label=labels.get(key, key.replace("_", " ")),
                label_key=key,
                value=composed.facts[key],
                unit=unit,
                source_event_id=None,
            )
        )
    return out
