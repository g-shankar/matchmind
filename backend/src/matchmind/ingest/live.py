"""The hand-off between a live consumer thread and the match session.

The consumer (Event Hubs callback threads) calls `put()` with each raw message;
the session calls `drain()` on its playback step. In between sits a bounded
queue of checked events. When the session falls behind and the queue is full,
`put()` blocks the consumer: that is the backpressure, and the transport simply
stops pulling until there is room again. Nothing is dropped for being slow.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from matchmind.schema import Event, EventType
from matchmind.simulator.teams import Team

from .stream import StreamValidator

logger = logging.getLogger("pitchpulse.ingest")

MAX_READY = 2_000
DRAIN_LIMIT = 500


class LiveFeed:
    def __init__(
        self,
        validator: StreamValidator,
        max_ready: int = MAX_READY,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.validator = validator
        self.max_ready = max_ready
        self.clock = clock
        self._ready: deque[Event] = deque()
        self._cond = threading.Condition()
        self._closed = False
        self.error: str | None = None
        self.blocked_puts = 0  # how often backpressure held the consumer

    # --- consumer side ----------------------------------------------------------------------

    def put(self, raw: str | bytes, timeout: float | None = None) -> bool:
        """Check one raw message and queue what it releases. Blocks while the queue is
        full (backpressure). False when the feed is closed or the wait timed out."""
        deadline = None if timeout is None else self.clock() + timeout
        with self._cond:
            if len(self._ready) >= self.max_ready:
                self.blocked_puts += 1
            while len(self._ready) >= self.max_ready and not self._closed:
                remaining = None if deadline is None else deadline - self.clock()
                if remaining is not None and remaining <= 0:
                    return False
                self._cond.wait(timeout=0.5 if remaining is None else min(remaining, 0.5))
            if self._closed:
                return False
            try:
                self._ready.extend(self.validator.offer(raw))
            except Exception:  # noqa: BLE001 - one bad message must never stop the consumer
                logger.exception("live message could not be checked")
                self.validator.stats.rejected += 1
            self._cond.notify_all()
            return True

    def close(self, error: str | None = None) -> None:
        with self._cond:
            self._closed = True
            if error and not self.error:
                self.error = error[:200]
            self._cond.notify_all()

    # --- session side -----------------------------------------------------------------------

    def wait_for_start(self, timeout: float) -> Event | None:
        """Block until a match_start is ready (returned and removed), or None on timeout/close."""
        deadline = self.clock() + timeout
        with self._cond:
            while True:
                if self._ready and self._ready[0].type == EventType.MATCH_START:
                    return self._ready.popleft()
                remaining = deadline - self.clock()
                if self._closed or remaining <= 0:
                    return None
                self._cond.wait(timeout=min(remaining, 0.5))

    def drain(self, limit: int = DRAIN_LIMIT) -> list[Event]:
        """Up to `limit` checked events, in order. Never blocks."""
        with self._cond:
            self._ready.extend(self.validator.flush())
            out = [self._ready.popleft() for _ in range(min(limit, len(self._ready)))]
            if out:
                self._cond.notify_all()
            return out

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def teams(self) -> dict[str, Team] | None:
        return self.validator.teams

    @property
    def exhausted(self) -> bool:
        """Nothing more will come: match_end was handed over, or the consumer stopped."""
        with self._cond:
            return not self._ready and (self.validator.ended or self._closed)

    def status(self) -> dict[str, Any]:
        with self._cond:
            return {
                "state": "stopped" if self._closed and not self.validator.ended else self.validator.state,
                "match_id": self.validator.ctx.match_id if self.validator.ctx else None,
                "queued": len(self._ready),
                "backpressure_waits": self.blocked_puts,
                "error": self.error,
                **self.validator.stats.as_dict(),
            }
