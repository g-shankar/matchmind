"""Export one synthetic match for download: events, metadata, rosters, data dictionary.

Formats:
- `jsonl`: the events exactly as the engine wrote them, one JSON object per line
  (the full schema, nested freeze frames, run tracking and line-ups included).
- `csv`: the same events as a flat table (`EVENT_COLUMNS`); nested arrays are
  left out (they are in the JSONL), details are one JSON cell.
- `zip`: README.txt, match.json (metadata), events.jsonl, events.csv,
  rosters.csv, DATA-DICTIONARY.md, event.schema.json and, when asked,
  tracking.csv: a bounded 25 Hz synthetic tracking sample for one time window.

Everything is produced lazily (generators), so the API can stream it. CSV cells
follow the Lakehouse export's conventions (`analytics.writers`): UTF-8, LF,
`true`/`false`, ISO-8601 UTC, empty for null. Text cells never start with a
spreadsheet formula character.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from matchmind.analytics.schema import Col
from matchmind.analytics.writers import _csv_cell
from matchmind.schema import PITCH_LENGTH_M, PITCH_WIDTH_M, SCHEMA_VERSION, Event, EventType
from matchmind.simulator.teams import TEAMS, Team

from .catalog import SCENARIOS, MatchEntry

FORMATS = ("jsonl", "csv", "zip")
TRACKING_HZ = 25.0
TRACKING_MAX_WINDOW_S = 60.0
TRACKING_LEAD_S = 20.0  # events rendered before the window so players are already in shape
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

EVENT_COLUMNS: tuple[Col, ...] = (
    Col("event_id", "string", "Unique id: <match_id>-<seq, 5 digits>."),
    Col("match_id", "string", "Match id (see match.json)."),
    Col("seq", "int64", "Order within the match, from 0, strictly increasing."),
    Col("ts", "timestamp", "Wall-clock time the event happened (UTC)."),
    Col("period", "int64", "1 or 2."),
    Col("clock_s", "float64", "Match clock in seconds; period 2 starts at 2700."),
    Col("match_clock", "string", "Broadcast clock, e.g. 67:20 or 90+2:15."),
    Col("type", "string", "Event type (enum EventType)."),
    Col("team", "string", "Team id of the actor, or empty."),
    Col("player_id", "string", "Actor, <team>-<shirt number>, or empty."),
    Col("receiver_id", "string", "Intended receiver of a pass (set even if incomplete)."),
    Col("possession_id", "int64", "Possession counter; changes when the team on the ball changes."),
    Col("start_x", "float64", "Start x in metres, 0-105; home attacks towards 105."),
    Col("start_y", "float64", "Start y in metres, 0-68."),
    Col("end_x", "float64", "End x in metres, 0-105."),
    Col("end_y", "float64", "End y in metres, 0-68."),
    Col("outcome", "string", "Outcome (enum Outcome), or empty."),
    Col("ball_speed_mps", "float64", "Ball speed in metres per second."),
    Col("player_speed_mps", "float64", "Actor's speed in metres per second."),
    Col("under_pressure", "bool", "An opponent was close enough to press the actor."),
    Col("pressure_players", "string", "Pressing opponents' player ids, separated by ';'."),
    Col("body_part", "string", "Shots: right_foot, left_foot or head."),
    Col("freeze_frame_players", "int64", "Shots: players in the freeze frame (frame itself in the JSONL)."),
    Col("tracking_frames", "int64", "Runs: tracking frames attached (frames themselves in the JSONL)."),
    Col("details", "string", "Type-specific extras as one JSON object (see the dictionary)."),
    Col("labels", "string", "Ground-truth labels separated by ';' (evaluation only)."),
)

ROSTER_COLUMNS: tuple[Col, ...] = (
    Col("team_id", "string", "Club id."),
    Col("team_name", "string", "Club name (invented)."),
    Col("side", "string", "home or away in this match."),
    Col("player_id", "string", "<team>-<shirt number>."),
    Col("number", "int64", "Shirt number."),
    Col("name", "string", "Player name (invented)."),
    Col("position", "string", "Position code, e.g. GK, RCB, CAM, ST."),
    Col("line", "string", "GK, DEF, MID or FWD."),
)

TRACKING_COLUMNS: tuple[Col, ...] = (
    Col("period", "int64", "1 or 2."),
    Col("clock_s", "float64", "Match clock in seconds at this frame (25 frames a second)."),
    Col("ball_alive", "bool", "Ball in play at this frame."),
    Col("object", "string", "'ball' or a player id."),
    Col("team", "string", "Player's team, empty for the ball."),
    Col("x", "float64", "x in metres, 0-105; empty while not tracked (ball hidden, player sent off)."),
    Col("y", "float64", "y in metres, 0-68; empty while not tracked."),
)


@dataclass(frozen=True)
class TrackingWindow:
    period: int
    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        if self.period not in (1, 2):
            raise ValueError("period must be 1 or 2")
        if not 0 <= self.start_s < self.end_s:
            raise ValueError("the tracking window must start before it ends")
        if self.end_s - self.start_s > TRACKING_MAX_WINDOW_S:
            raise ValueError(f"the tracking window is at most {TRACKING_MAX_WINDOW_S:g} seconds")


def _cell(value: Any) -> str:
    text = _csv_cell(value)
    if isinstance(value, str) and text.startswith(_FORMULA_START):
        return "'" + text
    return text


def csv_lines(cols: Iterable[Col], rows: Iterable[dict[str, Any]]) -> Iterator[str]:
    names = [c.name for c in cols]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(names)
    for row in rows:
        writer.writerow([_cell(row.get(n)) for n in names])
        if buf.tell() > 64 * 1024:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    yield buf.getvalue()


def event_row(e: Event) -> dict[str, Any]:
    return {
        "event_id": e.event_id,
        "match_id": e.match_id,
        "seq": e.seq,
        "ts": e.ts,
        "period": e.period,
        "clock_s": e.clock_s,
        "match_clock": e.match_clock,
        "type": e.type.value,
        "team": e.team,
        "player_id": e.player_id,
        "receiver_id": e.receiver_id,
        "possession_id": e.possession_id,
        "start_x": e.start.x if e.start else None,
        "start_y": e.start.y if e.start else None,
        "end_x": e.end.x if e.end else None,
        "end_y": e.end.y if e.end else None,
        "outcome": e.outcome.value if e.outcome else None,
        "ball_speed_mps": e.ball_speed_mps,
        "player_speed_mps": e.player_speed_mps,
        "under_pressure": e.under_pressure,
        "pressure_players": ";".join(e.pressure_players) or None,
        "body_part": e.body_part.value if e.body_part else None,
        "freeze_frame_players": len(e.freeze_frame) if e.freeze_frame is not None else None,
        "tracking_frames": len(e.tracking) if e.tracking is not None else None,
        "details": json.dumps(e.details, separators=(",", ":"), sort_keys=True) if e.details else None,
        "labels": ";".join(e.labels) or None,
    }


def jsonl_lines(events: Iterable[Event]) -> Iterator[str]:
    for e in events:
        yield e.to_json() + "\n"


def teams_of(events: list[Event], teams: dict[str, Team] | None = None) -> dict[str, Team]:
    start = events[0]
    ids = (str(start.details["home"]), str(start.details["away"]))
    pool = teams or TEAMS
    return {tid: pool[tid] for tid in ids}


def roster_rows(events: list[Event], teams: dict[str, Team] | None = None) -> Iterator[dict[str, Any]]:
    home = str(events[0].details["home"])
    for tid, team in teams_of(events, teams).items():
        for p in team.players:
            yield {
                "team_id": tid,
                "team_name": team.name,
                "side": "home" if tid == home else "away",
                "player_id": p.player_id,
                "number": p.number,
                "name": p.name,
                "position": p.position,
                "line": p.line,
            }


def metadata(entry: MatchEntry, events: list[Event], teams: dict[str, Team] | None = None) -> dict[str, Any]:
    start, end = events[0], events[-1]
    clubs = teams_of(events, teams)
    side = {t: {"team_id": t, "name": c.name, "formation": c.formation} for t, c in clubs.items()}
    counts: dict[str, int] = {}
    for e in events:
        counts[e.type.value] = counts.get(e.type.value, 0) + 1
    return {
        "match_id": entry.match_id,
        "synthetic": True,
        "note": "Synthetic data from the PitchPulse match engine. Invented clubs and players only.",
        "kind": entry.kind,
        "scenario": entry.scenario,
        "scenario_description": SCENARIOS.get(entry.scenario, ""),
        "seed": entry.seed,
        "schema_version": SCHEMA_VERSION,
        "pitch": {"length_m": PITCH_LENGTH_M, "width_m": PITCH_WIDTH_M, "home_attacks": "+x"},
        "kickoff": start.ts.isoformat().replace("+00:00", "Z"),
        "home": side[str(start.details["home"])],
        "away": side[str(start.details["away"])],
        "final_score": {"home": end.details.get("score_home"), "away": end.details.get("score_away")},
        "events": len(events),
        "event_types": dict(sorted(counts.items())),
    }


def tracking_rows(events: list[Event], window: TrackingWindow) -> Iterator[dict[str, Any]]:
    """A synthetic 25 Hz sample for one window, rendered from the events in and just before it.

    Uses the auto-eventing renderer (`autoevent.tracking`, read-only). Rendering only the
    window keeps it cheap; the noise is seeded per match, so a sample is reproducible but
    not frame-identical to a whole-match render."""
    from matchmind.autoevent.tracking import render_tracking

    lo = window.start_s - TRACKING_LEAD_S
    inside: list[Event] = []
    before: Event | None = None  # the last event before the lead-in, so a quiet spell still renders
    for e in events[1:]:
        if e.period != window.period:
            continue
        if e.clock_s < lo:
            if e.type != EventType.PERIOD_START:
                before = e
            continue
        if not inside and before is not None:
            inside.append(before)
        inside.append(e)
        if e.clock_s > window.end_s:
            break  # one event past the window, so the render runs to its end
    if not inside:
        return
    # Red cards shown before the window, so a sent-off player is not drawn.
    reds = [
        e
        for e in events
        if e.type == EventType.CARD
        and e.details.get("card") == "red"
        and (e.period, e.clock_s) < (window.period, lo)
    ]
    # The renderer takes the period's first event as its start; start it at the window.
    start = events[0].model_copy(update={"period": window.period, "clock_s": inside[0].clock_s})
    feed = render_tracking([start, *reds, *inside], hz=TRACKING_HZ)
    for frame in feed.frames:
        if frame.period != window.period or not window.start_s <= frame.clock_s <= window.end_s:
            continue
        ball = frame.ball
        yield {
            "period": frame.period,
            "clock_s": frame.clock_s,
            "ball_alive": frame.alive,
            "object": "ball",
            "team": None,
            "x": round(ball[0], 2) if ball else None,
            "y": round(ball[1], 2) if ball else None,
        }
        for i, pid in enumerate(feed.player_ids):
            pos = frame.player(i)
            yield {
                "period": frame.period,
                "clock_s": frame.clock_s,
                "ball_alive": frame.alive,
                "object": pid,
                "team": feed.player_teams[i],
                "x": round(pos[0], 2) if pos else None,
                "y": round(pos[1], 2) if pos else None,
            }


README = """PitchPulse synthetic match export
=================================

Everything in this archive is synthetic: produced by the PitchPulse match
engine with invented clubs and players. It is not real match data, and the
tracking sample (if present) is synthetic tracking rendered from the events,
not video.

Files
- match.json            metadata: scenario, seed, clubs, final score, event counts
- events.jsonl          every event in the full schema (one JSON object per line)
- events.csv            the same events as a flat table (nested arrays left out)
- rosters.csv           both squads
- event.schema.json     JSON Schema of one event line
- DATA-DICTIONARY.md    every field, type, unit, coordinate frame, clock and enum
- tracking.csv          (optional) 25 Hz synthetic tracking for one time window

Coordinates are metres on a 105 x 68 pitch; the home club attacks towards
x = 105 for the whole match. Regenerate the same match with its seed (see
docs/DATASET.md in the repository).
"""


class _Sink(io.RawIOBase):
    """A write-only, unseekable stream whose bytes are collected for streaming out."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, b: Any) -> int:
        self.chunks.append(bytes(b))
        return len(b)

    def take(self) -> bytes:
        out = b"".join(self.chunks)
        self.chunks.clear()
        return out


def zip_stream(members: Iterable[tuple[str, Iterable[str]]]) -> Iterator[bytes]:
    """A zip archive built member by member, yielded in chunks as it is written."""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name, parts in members:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 24, 15, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with zf.open(info, "w") as fh:
                for part in parts:
                    fh.write(part.encode("utf-8"))
                    if sum(len(c) for c in sink.chunks) > 256 * 1024:
                        yield sink.take()
            yield sink.take()
    yield sink.take()


def export_parts(
    entry: MatchEntry,
    events: list[Event],
    fmt: str,
    dictionary: str,
    schema: dict[str, Any],
    tracking: TrackingWindow | None = None,
) -> tuple[str, str, Iterator[bytes]]:
    """(file name, media type, byte chunks) for one match in one format."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    if tracking is not None and fmt != "zip":
        raise ValueError("the tracking sample comes in the zip format only")
    name = entry.match_id
    if fmt == "jsonl":
        return f"{name}.jsonl", "application/x-ndjson", (s.encode() for s in jsonl_lines(events))
    if fmt == "csv":
        rows = (event_row(e) for e in events)
        return f"{name}.csv", "text/csv; charset=utf-8", (s.encode() for s in csv_lines(EVENT_COLUMNS, rows))
    members: list[tuple[str, Iterable[str]]] = [
        ("README.txt", [README]),
        ("match.json", [json.dumps(metadata(entry, events), indent=2) + "\n"]),
        ("events.jsonl", jsonl_lines(events)),
        ("events.csv", csv_lines(EVENT_COLUMNS, (event_row(e) for e in events))),
        ("rosters.csv", csv_lines(ROSTER_COLUMNS, roster_rows(events))),
        ("event.schema.json", [json.dumps(schema, indent=2) + "\n"]),
        ("DATA-DICTIONARY.md", [dictionary]),
    ]
    if tracking is not None:
        members.append(("tracking.csv", csv_lines(TRACKING_COLUMNS, tracking_rows(events, tracking))))
    prefix = f"{name}/"
    return f"{name}.zip", "application/zip", zip_stream((prefix + n, p) for n, p in members)
