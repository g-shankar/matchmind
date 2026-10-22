"""Spoiler-safe catch-up: what a late joiner must not see until they tap "reveal".

One rule set, used by every surface (WebSocket payloads, the recap, Ask the
studio). A viewer with `ViewerProfile.spoilers == False` never receives:

- the score (scorebug fields, `home_score`/`away_score`, `state.score_*`,
  `MATCH_TICK.score`), nor the score copied into event details;
- goal and VAR-correction moments, half-time and full-time milestones (they
  carry the score), or any moment whose facts hold a score or a scored shot;
- shot and VAR-review outcomes on events (with them, a goal is one inference
  away), player goals and assists;
- outcome geometry: where a shot ended (every goal ends in the goal mouth) and who
  blocked it;
- VAR review events and kick-off passes themselves: in this engine a review always
  looks at a goal and every restart after the first whistle follows one, so these
  events are withheld from the stream, not just scrubbed (a scrubbed kick-off was
  still the only pass without a start point);
- the full feed's numbering: a withheld event would leave a gap in `seq` and in the
  event ids, so a catch-up event carries no `seq` and an opaque per-process id
  (card evidence points at the same opaque id, so cards still link to the pitch).
  Moment and card ids are built from event ids, so a catch-up payload carries them
  opaque too (`catchup_moment_id`, `catchup_card_id`): in cards, bookmarks, the recap
  and Ask answers. The moment, audit and MCP lookups take the opaque id back
  (`MatchSession.resolve_moment_id`) and answer with opaque ids again;
- the cue sheet (its scorebug layer is the score).

Pressure, momentum, xG, shots, chances and "should he have passed" moments
stay: they tell the story without the result.

What still remains (docs/THREAT-MODEL.md): where play restarts after a withheld
kick-off and the clock gap around it. Someone reading the raw catch-up stream can
infer a goal from those; the screen shows neither.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
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
SPOILER_DETAIL_KEYS: frozenset[str] = frozenset({"score_home", "score_away", "assist_id", "blocked_by"})
SPOILER_PLAYER_FIELDS: tuple[str, ...] = ("goals", "assists")
# Events whose outcome is hidden (a goal is a shot outcome; a VAR overturn says one was scored).
OUTCOME_HIDDEN_EVENTS: frozenset[str] = frozenset({"shot", "var_review"})
# Events whose end point is the outcome (a goal ends in the goal mouth).
END_HIDDEN_EVENTS: frozenset[str] = frozenset({"shot"})
# Events withheld from a spoiler-free stream altogether.
WITHHELD_EVENTS: frozenset[str] = frozenset({"var_review"})
# Passes withheld by type: every kick-off after the first whistle restarts play after a goal.
WITHHELD_PASS_TYPES: frozenset[str] = frozenset({"kickoff"})
# Catch-up event ids: keyed per process, so they cannot be reversed by hashing every
# full-feed id (those are public and sequential).
CATCHUP_ID_PREFIX = "ev-"
CATCHUP_MOMENT_PREFIX = "mo-"
CATCHUP_CARD_PREFIX = "cd-"
_CATCHUP_ID_KEY = secrets.token_bytes(32)


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


def is_withheld_event(payload: Mapping[str, Any]) -> bool:
    """An event a spoiler-free viewer never receives (its existence gives a goal away)."""
    if payload.get("type") in WITHHELD_EVENTS:
        return True
    details = payload.get("details") or {}
    return payload.get("type") == "pass" and details.get("pass_type") in WITHHELD_PASS_TYPES


def catchup_event_id(event_id: str) -> str:
    """The id a catch-up viewer sees for a full-feed event id: stable for this process,
    unordered, so withheld events leave no gap in it."""
    if event_id.startswith(CATCHUP_ID_PREFIX):
        return event_id  # already a catch-up id
    digest = hmac.new(_CATCHUP_ID_KEY, event_id.encode(), hashlib.sha256).hexdigest()[:16]
    return CATCHUP_ID_PREFIX + digest


def catchup_event_ids(ids: Iterable[str]) -> list[str]:
    return [catchup_event_id(i) for i in ids]


def _opaque(prefix: str, domain: bytes, value: str) -> str:
    digest = hmac.new(_CATCHUP_ID_KEY, domain + b"\0" + value.encode(), hashlib.sha256).hexdigest()[:16]
    return prefix + digest


def catchup_moment_id(moment_id: str) -> str:
    """The moment id a catch-up viewer sees. Moment ids carry the full feed's event id
    (`goal-MM-...-00817`), so in the clear they would show where events were withheld."""
    if moment_id.startswith(CATCHUP_MOMENT_PREFIX):
        return moment_id  # already a catch-up id
    return _opaque(CATCHUP_MOMENT_PREFIX, b"moment", moment_id)


def is_catchup_moment_id(moment_id: str) -> bool:
    return moment_id.startswith(CATCHUP_MOMENT_PREFIX)


def catchup_card_id(card_id: str) -> str:
    """The card id a catch-up viewer sees (unique per card, like the full one)."""
    if card_id.startswith(CATCHUP_CARD_PREFIX):
        return card_id
    return _opaque(CATCHUP_CARD_PREFIX, b"card", card_id)


def scrub_event(payload: dict[str, Any]) -> dict[str, Any]:
    """A kept event for a catch-up viewer (call `is_withheld_event` first)."""
    out = dict(payload)
    out["details"] = {k: v for k, v in payload.get("details", {}).items() if k not in SPOILER_DETAIL_KEYS}
    out["event_id"] = catchup_event_id(str(payload["event_id"]))
    out["seq"] = None  # the full feed's numbering would show where events were withheld
    if out.get("type") in OUTCOME_HIDDEN_EVENTS:
        out["outcome"] = None
    if out.get("type") in END_HIDDEN_EVENTS:
        out["end"] = None
    if "reviewed_event_id" in out:
        out["reviewed_event_id"] = None
    if "review_reason" in out:
        out["review_reason"] = None
    return out


def scrub_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "score_home": None, "score_away": None}


def scrub_player(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, **{f: None for f in SPOILER_PLAYER_FIELDS if f in payload}}


REPLAY_EVENT_KEYS: tuple[str, ...] = ("shot_event_id", "run_event_id")


def scrub_card(card: dict[str, Any]) -> dict[str, Any]:
    """A kept card for a catch-up viewer: every event id in it is the catch-up id, so it
    still links to the events on the pitch, and its card and moment ids are opaque, so it
    carries no full-feed numbering."""
    out = dict(card)
    if card.get("card_id"):
        out["card_id"] = catchup_card_id(str(card["card_id"]))
    if card.get("moment_id"):
        out["moment_id"] = catchup_moment_id(str(card["moment_id"]))
    if card.get("retracts"):
        out["retracts"] = [catchup_moment_id(str(m)) for m in card["retracts"]]
    out["evidence"] = [
        {**e, "source_event_id": catchup_event_id(e["source_event_id"])} if e.get("source_event_id") else e
        for e in card.get("evidence") or []
    ]
    if card.get("claims"):
        out["claims"] = [
            {**c, "source_event_ids": [catchup_event_id(i) for i in c.get("source_event_ids") or []]}
            for c in card["claims"]
        ]
    replay = card.get("replay")
    if isinstance(replay, dict):
        out["replay"] = {
            k: catchup_event_id(v) if k in REPLAY_EVENT_KEYS and isinstance(v, str) else v
            for k, v in replay.items()
        }
    return out


_EVENT_ID_FIELDS = frozenset({"event_id", "source_event_id", *REPLAY_EVENT_KEYS})
_MOMENT_ID_FIELDS = frozenset({"moment_id", "ruled_out_by"})


def with_catchup_ids(value: Any) -> Any:
    """A copy of a JSON payload with every event, moment and card id swapped for its
    catch-up id (a moment detail or audit asked for by a catch-up id)."""
    if isinstance(value, list):
        return [with_catchup_ids(v) for v in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for k, v in value.items():
        if k in _EVENT_ID_FIELDS and isinstance(v, str) and v:
            out[k] = catchup_event_id(v)
        elif k == "source_event_ids" and isinstance(v, list):
            out[k] = [catchup_event_id(x) if isinstance(x, str) else x for x in v]
        elif k in _MOMENT_ID_FIELDS and isinstance(v, str) and v:
            out[k] = catchup_moment_id(v)
        elif k == "retracts" and isinstance(v, list):
            out[k] = [catchup_moment_id(x) if isinstance(x, str) else x for x in v]
        elif k == "card_id" and isinstance(v, str) and v:
            out[k] = catchup_card_id(v)
        else:
            out[k] = with_catchup_ids(v)
    return out


def card_is_spoiler(card: Mapping[str, Any], moment: Moment | None) -> bool:
    """A card payload: by its moment when known, else by its kind and retracts."""
    if moment is not None and is_spoiler_moment(moment):
        return True
    if str(card.get("kind")) in SPOILER_KINDS or card.get("retracts"):
        return True
    return any(e.get("label_key") in SPOILER_FACT_KEYS for e in card.get("evidence") or [])
