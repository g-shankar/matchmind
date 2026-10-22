"""Live stream checks: the file rules applied one event at a time, plus delivery problems.

A live transport (Event Hubs) delivers *at least once* and, across partitions or
after a reconnect, not always in order. `StreamValidator` turns raw messages into
the same canonical, checked events a file gives, in seq order:

- Duplicates (the same seq, same content, e.g. a redelivery after a reconnect)
  are dropped and counted. The same seq with *different* content is a conflict:
  refused and counted, never applied (the first accepted version stands).
- Out of order: events ahead of the next expected seq wait in a bounded reorder
  buffer and are released in seq order. If a gap does not fill within
  `gap_timeout_s`, or the buffer is full, the missing seqs are skipped (counted)
  so one lost message cannot stall the match.
- Same second: many events share a clock second; order is by seq, and equal
  clocks are allowed.
- Before the match: events of a match whose match_start we never saw (we joined
  the stream late) are dropped until a match_start arrives. The last few are held
  briefly, so events that overtook their own match_start are not lost. With `match_id` set,
  only that match is followed; otherwise the first match_start seen.
- After match_end: everything is dropped.

Each accepted event still passes `MatchContext.normalise` and `ClockGuard`, so a
stream is held to exactly the rules of a file.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass

from pydantic import ValidationError

from matchmind.schema import Event, EventType
from matchmind.simulator.teams import Team

from .errors import IngestError
from .validate import DEFAULT_LIMITS, ClockGuard, Limits, MatchContext

REORDER_WINDOW = 256
GAP_TIMEOUT_S = 5.0


@dataclass
class StreamStats:
    received: int = 0
    accepted: int = 0
    duplicates: int = 0
    conflicts: int = 0
    rejected: int = 0
    too_big: int = 0
    before_start: int = 0
    other_match: int = 0
    after_end: int = 0
    reordered: int = 0
    skipped: int = 0
    last_problem: str | None = None

    def as_dict(self) -> dict[str, int | str | None]:
        return asdict(self)


def _digest(event: Event) -> str:
    return hashlib.sha256(event.model_dump_json().encode()).hexdigest()


class StreamValidator:
    """Not thread-safe; LiveFeed serialises calls."""

    def __init__(
        self,
        match_id: str | None = None,
        roster: dict[str, Team] | None = None,
        limits: Limits = DEFAULT_LIMITS,
        reorder_window: int = REORDER_WINDOW,
        gap_timeout_s: float = GAP_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.want = match_id.strip().upper() if match_id else None
        self.roster = roster
        self.limits = limits
        self.window = reorder_window
        self.gap_timeout_s = gap_timeout_s
        self.clock = clock
        self.stats = StreamStats()
        self.ctx: MatchContext | None = None
        self.guard = ClockGuard()
        self.expected = 0
        self.ended = False
        self._seen: dict[int, str] = {}  # seq -> content digest, for everything accepted or waiting
        self._pending: dict[int, Event] = {}
        self._early: deque[Event] = deque()  # before any match_start, bounded by the window
        self._gap_since: float | None = None

    @property
    def teams(self) -> dict[str, Team] | None:
        return self.ctx.teams if self.ctx else None

    @property
    def state(self) -> str:
        if self.ended:
            return "ended"
        return "live" if self.ctx else "waiting_for_match_start"

    def _problem(self, text: str) -> None:
        self.stats.rejected += 1
        self.stats.last_problem = text[:200]

    def offer(self, raw: str | bytes) -> list[Event]:
        """One raw message in; the events now ready to play (in seq order) out."""
        self.stats.received += 1
        if len(raw) > self.limits.max_line_bytes:
            self.stats.too_big += 1
            return []
        try:
            event = Event.model_validate_json(raw)
        except ValidationError as exc:
            self._problem(IngestError.from_validation("event", exc).args[0])
            return []
        if self.ended:
            self.stats.after_end += 1
            return []
        if self.ctx is None:
            return self._maybe_start(event)
        return self._take(event)

    def _take(self, event: Event) -> list[Event]:
        assert self.ctx is not None
        if event.match_id.strip().upper() != self.ctx.match_id:
            self.stats.other_match += 1
            return []
        digest = _digest(event)
        known = self._seen.get(event.seq)
        if known is not None:
            if known == digest:
                self.stats.duplicates += 1
            else:
                self.stats.conflicts += 1
                self.stats.last_problem = f"seq {event.seq} arrived again with different content; ignored"
            return []
        if event.seq < self.expected:
            # Older than what we already played (its slot was skipped): too late to use.
            self._problem(f"seq {event.seq} arrived after it was skipped")
            return []
        if len(self._seen) >= self.limits.max_events:
            self._problem(f"more than {self.limits.max_events} events in one match")
            return []
        self._seen[event.seq] = digest
        if event.seq != self.expected:
            self.stats.reordered += 1
        self._pending[event.seq] = event
        return self._release()

    def _maybe_start(self, event: Event) -> list[Event]:
        if event.type != EventType.MATCH_START or (self.want and event.match_id.strip().upper() != self.want):
            if len(self._early) >= self.window:
                self._early.popleft()
                self.stats.before_start += 1
            self._early.append(event)
            return []
        try:
            self.ctx = MatchContext.from_start(event, self.roster, self.limits)
            self.guard.check(event)
            start = self.ctx.normalise(event, seq=event.seq)
        except IngestError as exc:
            self.ctx = None
            self.guard = ClockGuard()
            self._problem(str(exc))
            return []
        self._seen[event.seq] = _digest(event)
        self.expected = event.seq + 1
        self.stats.accepted += 1
        early = [
            e for e in self._early if e.match_id.strip().upper() == self.ctx.match_id and e.seq > event.seq
        ]
        self.stats.before_start += len(self._early) - len(early)
        self._early.clear()
        out = [start]
        for e in sorted(early, key=lambda e: e.seq):
            out += self._take(e)
        return out

    def _release(self) -> list[Event]:
        ready: list[Event] = []
        while True:
            while self.expected in self._pending and not self.ended:
                event = self._pending.pop(self.expected)
                self.expected += 1
                accepted = self._accept(event)
                if accepted is not None:
                    ready.append(accepted)
            if not self._pending or self.ended:
                self._gap_since = None
                if self.ended:
                    self.stats.after_end += len(self._pending)
                    self._pending.clear()
                return ready
            now = self.clock()
            if self._gap_since is None:
                self._gap_since = now
            if len(self._pending) <= self.window and now - self._gap_since < self.gap_timeout_s:
                return ready
            nxt = min(self._pending)
            self.stats.skipped += nxt - self.expected
            self.stats.last_problem = f"seq {self.expected}-{nxt - 1} never arrived; skipped"
            self.expected = nxt
            self._gap_since = None

    def flush(self) -> list[Event]:
        """Release waiting events whose gap has timed out (call it now and then)."""
        if self.ctx is None or not self._pending:
            return []
        return self._release()

    def _accept(self, event: Event) -> Event | None:
        assert self.ctx is not None
        try:
            self.guard.check(event)
            out = self.ctx.normalise(event, seq=event.seq)
        except IngestError as exc:
            self._problem(f"seq {event.seq}: {exc}")
            return None
        self.stats.accepted += 1
        if out.type == EventType.MATCH_END:
            self.ended = True
        return out
