"""Circuit breaker shared by the paid model steps and the translator.

Three failures in a row open the breaker for 60 s. After that exactly one call
is let through as a probe (half-open); everyone else still sees it open until
the probe reports back. Success closes it, a failure opens it again. A probe
that never reports (the caller gave up before calling) expires after
PROBE_TIMEOUT_S, so the breaker can never stay stuck.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

BREAKER_FAILURES = 3
BREAKER_OPEN_S = 60.0
PROBE_TIMEOUT_S = 10.0


class CircuitBreaker:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.failures = 0
        self.open_until: float | None = None
        self.probe_until: float | None = None  # a half-open probe is in flight until then
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        """False means "go ahead": the breaker is closed, or this caller is the one probe."""
        with self._lock:
            now = self.clock()
            if self.probe_until is not None:
                if now < self.probe_until:
                    return True  # someone else is probing
                self.probe_until = None  # that probe never reported: allow a new one
                self.open_until = now  # fall through to half-open below
            if self.open_until is None:
                return False
            if now >= self.open_until:
                self.open_until = None
                self.failures = BREAKER_FAILURES - 1
                self.probe_until = now + PROBE_TIMEOUT_S
                return False
            return True

    def peek_open(self) -> bool:
        """Open right now, without taking the probe (for status reports)."""
        with self._lock:
            return self.open_until is not None and self.clock() < self.open_until

    def cancel_probe(self) -> None:
        """The caller let through did not make the call after all (e.g. no budget)."""
        with self._lock:
            if self.probe_until is not None:
                self.probe_until = None
                self.open_until = self.clock()  # the next caller probes instead

    def success(self) -> None:
        with self._lock:
            self.failures = 0
            self.open_until = None
            self.probe_until = None

    def failure(self) -> None:
        with self._lock:
            self.probe_until = None
            self.failures += 1
            if self.failures >= BREAKER_FAILURES:
                self.open_until = self.clock() + BREAKER_OPEN_S
