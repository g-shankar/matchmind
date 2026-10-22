"""Load an external match feed from disk: our JSON-lines schema or the generic CSV.

    feed = load_feed("my_match.jsonl")                                   # bundled clubs
    feed = load_feed("my_match.jsonl", roster="roster.yaml")             # invented clubs
    feed = load_feed("my_match.csv", roster="roster.yaml", mapping="mapping.yaml")

Either way the events pass the same strict checks (`validate.py`) before the
session sees them. There is deliberately no upload endpoint on the public app:
a feed is a file the operator puts on disk (docs/DATASET.md explains why).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from matchmind.schema import Event
from matchmind.simulator.teams import Team

from .errors import IngestError
from .roster import load_roster
from .validate import DEFAULT_LIMITS, Limits, validate_events

JSON_SUFFIXES = {".jsonl", ".ndjson"}


@dataclass(frozen=True)
class Feed:
    events: list[Event]
    teams: dict[str, Team]
    source: str  # "jsonl" or "csv"

    @property
    def match_id(self) -> str:
        return self.events[0].match_id


def _check_size(path: Path, limits: Limits) -> None:
    if not path.is_file():
        raise IngestError(f"Match file not found: {path}")
    if path.stat().st_size > limits.max_bytes:
        raise IngestError(f"{path.name} is larger than {limits.max_bytes // (1024 * 1024)} MB")


def read_event_lines(path: str | Path, limits: Limits = DEFAULT_LIMITS) -> list[Event]:
    """Events from a JSON-lines file in our schema, with size caps and line numbers in errors."""
    path = Path(path)
    _check_size(path, limits)
    events: list[Event] = []
    with path.open("rb") as fh:
        for lineno, raw in enumerate(fh, start=1):
            if len(raw) > limits.max_line_bytes:
                raise IngestError(f"Line {lineno} is longer than {limits.max_line_bytes // 1024} KB")
            if not raw.strip():
                continue
            if len(events) >= limits.max_events:
                raise IngestError(f"The feed has more than {limits.max_events} events")
            try:
                events.append(Event.model_validate_json(raw))
            except ValidationError as exc:
                raise IngestError.from_validation("event", exc, where=f"line {lineno}: ") from None
    return events


def load_feed(
    path: str | Path,
    roster: str | Path | dict[str, Team] | None = None,
    mapping: str | Path | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> Feed:
    path = Path(path)
    teams = load_roster(roster) if isinstance(roster, str | Path) else roster
    suffix = path.suffix.lower()
    if suffix == ".csv":
        if mapping is None:
            raise IngestError("A CSV feed needs a mapping file (--mapping or MATCHMIND_FEED_MAPPING)")
        from .csv_feed import read_csv_feed

        _check_size(path, limits)
        raw, source = read_csv_feed(path, mapping, teams, limits), "csv"
    elif suffix in JSON_SUFFIXES:
        raw, source = read_event_lines(path, limits), "jsonl"
    else:
        raise IngestError("Feeds are .jsonl (our event schema) or .csv (with a mapping file)")
    events, resolved = validate_events(raw, teams, limits)
    return Feed(events=events, teams=resolved, source=source)
