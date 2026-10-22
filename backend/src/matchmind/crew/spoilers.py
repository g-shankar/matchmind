"""Spoiler-safe catch-up: what a late joiner must not see until they tap "reveal".

One rule set, used by every surface (WebSocket payloads, the recap, Ask the
studio). A viewer with `ViewerProfile.spoilers == False` never receives:

- the score (scorebug fields, `home_score`/`away_score`, `state.score_*`,
  `MATCH_TICK.score`), nor the score copied into event details;
- goal and VAR-correction moments, half-time and full-time milestones (they
  carry the score), or any moment whose facts hold a score or a scored shot;
- shot and VAR-review outcomes on events (with them, a goal is one inference
  away), player goals and assists;
- the cue sheet (its scorebug layer is the score).

Pressure, momentum, xG, shots, chances and "should he have passed" moments
stay: they tell the story without the result.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from matchmind.crew.contracts import FactValue, Moment, MomentKind

SPOILER_KINDS: frozenset[str] = frozenset({MomentKind.GOAL.value, MomentKind.CORRECTION.value})
# Fact keys that state or imply the result. A moment holding any of them is a spoiler.
SPOILER_FACT_KEYS: frozenset[str] = frozenset(
    {
        "score_home",
        "score_away",
        "score_w",
        "score_l",
        "winner",
        "loser",
        "goals_line",
        "ruled_out_clock",
        "decision",
        "potm",
        "potm_short",
        "potm_team",
        "potm_goals",
        "potm_assists",
        "potm_xg",
        "potm_xa",
        "potm_key_passes",
        "potm_tackles",
        "goals",
        "assists",
        "player_goals",
        "player_assists",
    }
)
# Event detail keys and player fields hidden in spoiler-free payloads.
SPOILER_DETAIL_KEYS: frozenset[str] = frozenset({"score_home", "score_away", "assist_id"})
SPOILER_PLAYER_FIELDS: tuple[str, ...] = ("goals", "assists")
# Events whose outcome is hidden (a goal is a shot outcome; a VAR overturn says one was scored).
OUTCOME_HIDDEN_EVENTS: frozenset[str] = frozenset({"shot", "var_review"})


def is_spoiler_facts(facts: Mapping[str, FactValue]) -> bool:
    return any(k in facts for k in SPOILER_FACT_KEYS) or facts.get("outcome") == "goal"


def is_spoiler_moment(moment: Moment) -> bool:
    return str(moment.kind) in SPOILER_KINDS or bool(moment.retracts) or is_spoiler_facts(moment.facts)


def is_spoiler_kind(kind: str, facts: Mapping[str, FactValue] | None = None) -> bool:
    return kind in SPOILER_KINDS or (facts is not None and is_spoiler_facts(facts))


def spoiler_free_moments(moments: Iterable[Moment]) -> list[Moment]:
    return [m for m in moments if not is_spoiler_moment(m)]


def scrub_facts(facts: Mapping[str, FactValue]) -> dict[str, FactValue]:
    return {k: v for k, v in facts.items() if k not in SPOILER_FACT_KEYS}


# --- JSON payloads (api/view.py) ----------------------------------------------------------------


def scrub_event(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["details"] = {k: v for k, v in payload.get("details", {}).items() if k not in SPOILER_DETAIL_KEYS}
    if out.get("type") in OUTCOME_HIDDEN_EVENTS:
        out["outcome"] = None
    if "reviewed_event_id" in out:
        out["reviewed_event_id"] = None
    return out


def scrub_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "score_home": None, "score_away": None}


def scrub_player(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, **{f: None for f in SPOILER_PLAYER_FIELDS if f in payload}}


def card_is_spoiler(card: Mapping[str, Any], moment: Moment | None) -> bool:
    """A card payload: by its moment when known, else by its kind and retracts."""
    if moment is not None and is_spoiler_moment(moment):
        return True
    if str(card.get("kind")) in SPOILER_KINDS or card.get("retracts"):
        return True
    return any(e.get("label_key") in SPOILER_FACT_KEYS for e in card.get("evidence") or [])
