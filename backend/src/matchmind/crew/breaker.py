"""Circuit breaker shared by the paid model steps and the translator.

Three failures in a row open the breaker for 60 s; after that one call is let
through (half-open) and a single further failure opens it again.
"""

from __future__ import annotations

from collections.abc import Callable

BREAKER_FAILURES = 3
BREAKER_OPEN_S = 60.0


class CircuitBreaker:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.failures = 0
        self.open_until: float | None = None

    def is_open(self) -> bool:
        if self.open_until is None:
            return False
        if self.clock() >= self.open_until:
            self.open_until = None  # half-open: let the next call try
            self.failures = BREAKER_FAILURES - 1
            return False
        return True

    def peek_open(self) -> bool:
        """Open right now, without moving to half-open (for status reports)."""
        return self.open_until is not None and self.clock() < self.open_until

    def success(self) -> None:
        self.failures = 0
        self.open_until = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= BREAKER_FAILURES:
            self.open_until = self.clock() + BREAKER_OPEN_S
