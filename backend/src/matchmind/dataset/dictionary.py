"""The data dictionary (docs/DATA-DICTIONARY.md), generated, never hand-edited.

Built from the event model (`schema/events.py`, the same model that writes
`backend/schema/event.schema.json`) and measured on the bundled dataset, so a new
field, enum value or match shows up by re-running one command:

    cd backend && matchmind-sim dictionary            # writes ../docs/DATA-DICTIONARY.md
    cd backend && matchmind-sim dictionary --check    # exit 1 if the file is stale

Anything the model does not describe itself (units, frames) comes from the
notes below; a field or enum value without a note is still listed, marked
"not described yet", so the generator never fails on a schema change.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from matchmind.analytics.schema import Col
from matchmind.schema import PITCH_LENGTH_M, PITCH_WIDTH_M, SCHEMA_VERSION, Event

from .catalog import API_SEED_COUNT, CLI_MAX_SEED, SCENARIOS, SEED_START, bundled_entries, load_match
from .export import EVENT_COLUMNS, ROSTER_COLUMNS, TRACKING_COLUMNS, TRACKING_HZ, TRACKING_MAX_WINDOW_S

UNDESCRIBED = "not described yet"

# Unit, frame or id rule per field (keyed "Model.field"; "Event.field" for event fields).
NOTES: dict[str, str] = {
    "Event.schema_version": "contract version; bumped on a breaking change",
    "Event.event_id": "id: `<match_id>-<seq, 5 digits>`",
    "Event.match_id": "id, e.g. `MM-DEMO-001`, `MM-SYN-003`, `MM-GEN-01000`",
    "Event.seq": "order key; the only reliable order across the half-time clock reset",
    "Event.ts": "UTC; kick-off + real elapsed time (15 min half-time break included)",
    "Event.period": "1 or 2",
    "Event.clock_s": "seconds; period 1 runs from 0 (stoppage past 2700), period 2 restarts at 2700",
    "Event.match_clock": "text, `MM:SS` or `45+M:SS` / `90+M:SS`",
    "Event.team": "team id (`NBR`, `HCY`)",
    "Event.player_id": "player id `<team>-<shirt number>`",
    "Event.receiver_id": "player id",
    "Event.possession_id": "counter, new value when the team on the ball changes",
    "Event.start": "metres, absolute frame",
    "Event.end": "metres, absolute frame",
    "Event.ball_speed_mps": "metres per second",
    "Event.player_speed_mps": "metres per second",
    "Event.pressure_players": "player ids",
    "Event.freeze_frame": "metres, absolute frame",
    "Event.tracking": "every 0.5 s, metres, absolute frame",
    "Event.lineups": "both squads",
    "Event.details": "see 'Details by event type'",
    "Event.labels": "`prefix:value`; strip before anything reaches a model",
    "Point.x": "metres, 0 = home goal line, 105 = away goal line",
    "Point.y": "metres, 0-68 across the pitch",
    "FramePlayer.x": "metres, absolute frame",
    "FramePlayer.y": "metres, absolute frame",
    "FramePlayer.player_id": "player id",
    "FramePlayer.team": "team id",
    "TrackingFrame.t_offset_s": "seconds after the run event's clock_s",
    "LineupPlayer.player_id": "player id `<team>-<shirt number>`",
    "LineupPlayer.team": "team id",
    "LineupPlayer.number": "shirt number",
    "LineupPlayer.position": "position code (GK, RB, RCB, CDM, CAM, ST, ...)",
}

# What a field means, where the model itself has no description.
MEANINGS: dict[str, str] = {
    "Event.schema_version": "Event contract version.",
    "Event.event_id": "Unique id of the event.",
    "Event.match_id": "The match this event belongs to.",
    "Event.period": "Half: 1 or 2.",
    "Event.type": "What happened (enum EventType).",
    "Event.team": "Team of the actor; empty for match-level events.",
    "Event.player_id": "The actor.",
    "Event.possession_id": "Possession the event belongs to.",
    "Event.start": "Where the action started.",
    "Event.end": "Where the ball (or carrier) ended up.",
    "Event.outcome": "How the action ended (enum Outcome).",
    "Event.ball_speed_mps": "Ball speed of a pass, shot or clearance.",
    "Event.player_speed_mps": "Actor's speed (carries, dribbles, runs).",
    "Event.under_pressure": "An opponent was close enough to press the actor.",
    "Event.pressure_players": "The pressing opponents.",
    "Event.body_part": "Shots: the body part used.",
    "Event.details": "Type-specific extras.",
    "Point.x": "Along the pitch length.",
    "Point.y": "Across the pitch width.",
    "FramePlayer.player_id": "The player.",
    "FramePlayer.team": "The player's team.",
    "FramePlayer.x": "Position along the length.",
    "FramePlayer.y": "Position across the width.",
    "FramePlayer.keeper": "The player is a goalkeeper.",
    "FramePlayer.actor": "The player is the event's actor.",
    "TrackingFrame.t_offset_s": "Time of this frame after the event.",
    "TrackingFrame.ball": "Ball position.",
    "TrackingFrame.players": "Player positions.",
    "LineupPlayer.player_id": "The player.",
    "LineupPlayer.team": "The player's club.",
    "LineupPlayer.name": "Invented player name.",
    "LineupPlayer.number": "Shirt number.",
    "LineupPlayer.position": "Starting position.",
}

ENUM_MEANINGS: dict[str, dict[str, str]] = {
    "EventType": {
        "match_start": "First event: clubs in `details.home` / `details.away`, line-ups, seed.",
        "period_start": "Kick-off of a half.",
        "pass": "A pass; `details.pass_type` is ground, cross, through_ball or kickoff.",
        "carry": "The player runs with the ball.",
        "dribble": "A take-on; `details.opponent_id` is the defender beaten (or not).",
        "shot": "A shot, with a freeze frame; goals carry the new score in details.",
        "run": "An off-ball run in behind, with 3 s of tracking; found or not found.",
        "interception": "A pass cut out.",
        "tackle": "A tackle that wins the ball.",
        "clearance": "A defensive clearance.",
        "recovery": "A loose ball picked up.",
        "foul": "A foul; `details.fouled_id` is the player fouled.",
        "card": "A booking; `details.card` is yellow or red.",
        "milestone": "A scripted personal milestone (`details.label`).",
        "var_review": "A video review of a decision (synthetic).",
        "period_end": "End of a half, with the score.",
        "match_end": "Last event, with the final score.",
    },
    "Outcome": {
        "complete": "Pass reached a teammate.",
        "incomplete": "Pass did not reach a teammate.",
        "out": "Ball went out of play.",
        "won": "Duel or take-on won.",
        "goal": "Shot scored.",
        "saved": "Shot saved by the keeper.",
        "blocked": "Shot blocked by an outfield player (`details.blocked_by`).",
        "off_target": "Shot missed the target.",
        "found": "Run was picked out by a pass.",
        "not_found": "Run was not picked out.",
    },
    "BodyPart": {
        "right_foot": "Right foot.",
        "left_foot": "Left foot.",
        "head": "Header.",
    },
}


# --- JSON Schema -> readable types ----------------------------------------------------------


def _ref(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type(prop: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in prop:
        name = _ref(prop["$ref"])
        return f"enum `{name}`" if "enum" in defs.get(name, {}) else f"`{name}`"
    if "const" in prop:
        return f'"{prop["const"]}"'
    if "anyOf" in prop:
        parts = [_type(p, defs) for p in prop["anyOf"]]
        return " or ".join(dict.fromkeys(parts))
    t = prop.get("type")
    if t == "array":
        return f"array of {_type(prop.get('items', {}), defs)}"
    if t == "object":
        extra = prop.get("additionalProperties")
        return f"object of {_type(extra, defs)}" if isinstance(extra, dict) else "object"
    if t == "string" and prop.get("format") == "date-time":
        return "string (ISO 8601 date-time)"
    return str(t) if t else "any"


def _constraints(prop: dict[str, Any]) -> str:
    rules = []
    for key, sym in (
        ("minimum", ">="),
        ("exclusiveMinimum", ">"),
        ("maximum", "<="),
        ("exclusiveMaximum", "<"),
    ):
        if key in prop:
            rules.append(f"{sym} {prop[key]:g}" if isinstance(prop[key], float) else f"{sym} {prop[key]}")
    return ", ".join(rules)


def _default(prop: dict[str, Any], required: bool) -> str:
    if required:
        return "required"
    if "default" in prop:
        return f"default `{json.dumps(prop['default'])}`"
    return "optional"


def _esc(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _fields_table(model: str, schema: dict[str, Any], defs: dict[str, Any]) -> list[str]:
    required = set(schema.get("required", []))
    lines = [
        "| field | type | constraints | presence | unit / frame / id rule | description |",
        "|---|---|---|---|---|---|",
    ]
    for name, prop in schema.get("properties", {}).items():
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} |".format(
                name,
                _esc(_type(prop, defs)),
                _esc(_constraints(prop)) or "",
                _default(prop, name in required),
                _esc(NOTES.get(f"{model}.{name}", "")),
                _esc(prop.get("description") or MEANINGS.get(f"{model}.{name}", UNDESCRIBED)),
            )
        )
    return lines


def _enum_table(name: str, values: list[str]) -> list[str]:
    meanings = ENUM_MEANINGS.get(name, {})
    lines = ["| value | meaning |", "|---|---|"]
    lines += [f"| `{v}` | {_esc(meanings.get(v, UNDESCRIBED))} |" for v in values]
    return lines


def _cols_table(cols: tuple[Col, ...]) -> list[str]:
    lines = ["| column | type | meaning |", "|---|---|---|"]
    lines += [f"| `{c.name}` | {c.dtype} | {_esc(c.desc).replace('<', '&lt;')} |" for c in cols]
    return lines


# --- measured on the bundled dataset ---------------------------------------------------------


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "0.0%"


def _distribution(matches: list[tuple[str, list[Event]]], type_values: list[str]) -> list[str]:
    ids = [mid for mid, _ in matches]
    counts = {mid: Counter(e.type.value for e in evs) for mid, evs in matches}
    total = Counter()
    for c in counts.values():
        total.update(c)
    grand = sum(total.values())
    lines = [
        "| event type | " + " | ".join(f"`{m}`" for m in ids) + " | all | share |",
        "|---|" + "---:|" * (len(ids) + 2),
    ]
    for t in type_values:
        row = " | ".join(str(counts[m].get(t, 0)) for m in ids)
        lines.append(f"| `{t}` | {row} | {total.get(t, 0)} | {_pct(total.get(t, 0), grand)} |")
    sizes = " | ".join(str(sum(counts[m].values())) for m in ids)
    lines.append(f"| **all events** | {sizes} | {grand} | 100.0% |")
    return lines


def _outcomes(matches: list[tuple[str, list[Event]]], etype: str) -> list[str]:
    seen = Counter()
    for _, evs in matches:
        seen.update(e.outcome.value for e in evs if e.type.value == etype and e.outcome is not None)
    total = sum(seen.values())
    lines = ["| outcome | count | share |", "|---|---:|---:|"]
    lines += [
        f"| `{o}` | {n} | {_pct(n, total)} |" for o, n in sorted(seen.items(), key=lambda x: (-x[1], x[0]))
    ]
    return lines


def _details_keys(matches: list[tuple[str, list[Event]]], type_values: list[str]) -> list[str]:
    keys: dict[str, set[str]] = defaultdict(set)
    labels: Counter[str] = Counter()
    for _, evs in matches:
        for e in evs:
            keys[e.type.value].update(e.details)
            labels.update(lb.split(":", 1)[0] for lb in e.labels)
    lines = ["| event type | details keys seen |", "|---|---|"]
    for t in type_values:
        if keys.get(t):
            lines.append(f"| `{t}` | {', '.join(f'`{k}`' for k in sorted(keys[t]))} |")
    lines += ["", "Label prefixes seen (events carrying each):", ""]
    lines += [f"- `{p}`: {n}" for p, n in sorted(labels.items())]
    return lines


def _match_stats(matches: list[tuple[str, list[Event]]]) -> list[str]:
    lines = [
        "| match | goals | shots | passes | pass completion | cards | runs found / all | last clock |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for mid, evs in matches:
        shots = [e for e in evs if e.type.value == "shot"]
        passes = [e for e in evs if e.type.value == "pass"]
        done = sum(e.outcome is not None and e.outcome.value == "complete" for e in passes)
        runs = [e for e in evs if e.type.value == "run"]
        found = sum(e.outcome is not None and e.outcome.value == "found" for e in runs)
        goals = sum(e.outcome is not None and e.outcome.value == "goal" for e in shots)
        cards = sum(e.type.value == "card" for e in evs)
        lines.append(
            f"| `{mid}` | {goals} | {len(shots)} | {len(passes)} | {_pct(done, len(passes))} | {cards} "
            f"| {found} / {len(runs)} | {evs[-1].match_clock} |"
        )
    return lines


# --- the document ----------------------------------------------------------------------------


def render_dictionary(dataset_dir: Path | None = None) -> str:
    schema = Event.model_json_schema()
    defs = schema.get("$defs", {})
    entries = bundled_entries(dataset_dir)
    matches = [(e.match_id, load_match(e, dataset_dir)) for e in entries]
    type_values = defs["EventType"]["enum"]

    out: list[str] = [
        "# PitchPulse data dictionary",
        "",
        "<!-- Generated by `matchmind-sim dictionary`. Do not edit by hand. -->",
        "",
        "Generated from the event model (`backend/src/matchmind/schema/events.py`, exported as",
        "`backend/schema/event.schema.json`) and measured on the bundled dataset",
        "(`backend/data/matches`). To refresh it after a schema or data change, run",
        "`cd backend && matchmind-sim dictionary`; a test fails while it is out of date.",
        "",
        "Everything described here is **synthetic**: produced by the PitchPulse match engine",
        "with invented clubs and players. See `docs/DATASET.md` for how it is made and its",
        "realism limits.",
        "",
        f"Schema version: `{SCHEMA_VERSION}`.",
        "",
        "## Frames, clocks and ids",
        "",
        f"- **Pitch**: metres on a {PITCH_LENGTH_M:g} x {PITCH_WIDTH_M:g} pitch. `x` runs along the length",
        "  from the home goal line (0) to the away goal line (105); `y` runs across (0-68),",
        "  `y = 0` being the touchline on the home club's right as it attacks. The **home club",
        "  attacks towards x = 105 for the whole match** and the away club towards x = 0; ends",
        "  do not switch at half time. Every position in an event is in this absolute frame.",
        "- **Clock**: `clock_s` is the match clock in seconds. Period 1 starts at 0 and its",
        "  stoppage time runs past 2700; period 2 restarts at 2700 and its stoppage runs past",
        "  5400. So `clock_s` alone is not monotonic across half time: order by `seq`, or by",
        "  `(period, clock_s)`. Several events can share the same second.",
        "- **Broadcast clock**: `match_clock` is `MM:SS`, or `45+M:SS` / `90+M:SS` in stoppage.",
        "- **Wall clock**: `ts` is UTC: kick-off time plus real elapsed time, including a",
        "  15-minute half-time break.",
        "- **Ids**: `match_id` (`MM-DEMO-001` scripted demo, `MM-SYN-nnn` bundled unscripted,",
        "  `MM-GEN-nnnnn` seeded on request); `event_id` = `<match_id>-<seq, 5 digits>`;",
        "  team ids are 2-4 capital letters; `player_id` = `<team>-<shirt number>`.",
        "- **Speeds**: metres per second (`ball_speed_mps`, `player_speed_mps`).",
        "- **Labels** are ground truth for evaluation only; consumers strip them before",
        "  anything reaches a model.",
        "",
        "## Event fields (one JSON object per line)",
        "",
        *_fields_table("Event", schema, defs),
        "",
        "## Nested types",
        "",
    ]
    for name in sorted(n for n, d in defs.items() if "properties" in d):
        out += [f"### `{name}`", ""]
        if defs[name].get("description"):
            out += [_esc(defs[name]["description"]), ""]
        out += [*_fields_table(name, defs[name], defs), ""]
    out += ["## Enums", ""]
    for name in sorted(n for n, d in defs.items() if "enum" in d):
        out += [f"### `{name}`", "", *_enum_table(name, list(defs[name]["enum"])), ""]
    out += [
        "## Details by event type",
        "",
        "`details` is a flat object of strings, integers, numbers and booleans. Keys ending in",
        "`_id` are player ids. Measured on the bundled matches:",
        "",
        *_details_keys(matches, type_values),
        "",
        "## Export files",
        "",
        "`GET /api/dataset/export` and `matchmind-sim export` (docs/DATASET.md) write these.",
        "CSV conventions: UTF-8, LF line endings, `true`/`false`, ISO-8601 UTC, empty for null",
        "(the Lakehouse export's rules).",
        "",
        "### `events.csv` (flat view; nested arrays are in `events.jsonl`)",
        "",
        *_cols_table(EVENT_COLUMNS),
        "",
        "### `rosters.csv`",
        "",
        *_cols_table(ROSTER_COLUMNS),
        "",
        f"### `tracking.csv` (optional; {TRACKING_HZ:g} Hz, one window of at most "
        f"{TRACKING_MAX_WINDOW_S:g} s)",
        "",
        "Synthetic tracking rendered from the events by the auto-eventing renderer",
        "(`autoevent/tracking.py`): 2D positions, measurement noise and ball drop-outs",
        "added. One row per object per frame (the ball, then every player). It is not video.",
        "",
        *_cols_table(TRACKING_COLUMNS),
        "",
        "## Measured distributions (bundled dataset)",
        "",
        "### Event types per match",
        "",
        *_distribution(matches, type_values),
        "",
        "### Per match",
        "",
        *_match_stats(matches),
        "",
        "### Pass outcomes (all bundled matches)",
        "",
        *_outcomes(matches, "pass"),
        "",
        "### Shot outcomes (all bundled matches)",
        "",
        *_outcomes(matches, "shot"),
        "",
        "## Scenarios and seeds",
        "",
        "Same scenario + same seed = byte-identical events.",
        "",
        "| scenario | meaning |",
        "|---|---|",
        *[f"| `{k}` | {_esc(v)} |" for k, v in SCENARIOS.items()],
        "",
        "| match | scenario | seed | home | away | score | events |",
        "|---|---|---:|---|---|---|---:|",
        *[
            f"| `{e.match_id}` | `{e.scenario}` | {e.seed} | {e.home} | {e.away} | {e.score} | {e.events} |"
            for e in entries
        ],
        "",
        f"Seeded matches: `MM-GEN-<seed>` for seeds {SEED_START}-{SEED_START + API_SEED_COUNT - 1} through",
        f"the API, any seed 0-{CLI_MAX_SEED} through `matchmind-sim export --seed`; scenario",
        "`chance_model_with_beats`, home and away alternate with the seed.",
        "",
    ]
    return "\n".join(out)


@lru_cache(maxsize=2)
def _cached(dataset_dir: str) -> str:
    return render_dictionary(Path(dataset_dir))


def cached_dictionary(dataset_dir: Path | None = None) -> str:
    """The dictionary for a dataset folder, rendered once per process (for the API)."""
    from .catalog import default_dataset_dir

    return _cached(str(dataset_dir or default_dataset_dir()))
