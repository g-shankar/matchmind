"""Extreme cases from the pre-launch test round (qa/extreme-cases/report.md).

Each test names the finding it guards (EC-n). The ones marked "held up" passed
before any change and stay as regression guards.
"""

from __future__ import annotations

import asyncio
import time

from matchmind.api.app import SEND_QUEUE_SHARE_BYTES, Connection, Hub, SendBudget


class StuckSocket:
    """A viewer that stopped reading: send_text never returns."""

    def __init__(self) -> None:
        self.closed_with: int | None = None

    async def send_text(self, text: str) -> None:
        await asyncio.Event().wait()

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


class QuickSocket:
    def __init__(self) -> None:
        self.sent = 0

    async def send_text(self, text: str) -> None:
        self.sent += 1


# --- EC-1: viewers that stop reading share one memory budget ---------------------------------


def test_ec1_stalled_viewers_cannot_pin_more_than_the_shared_budget():
    """Before: each stalled viewer could queue 4 MB, so 200 of them pinned about 800 MB
    in a 1 GiB container (measured: RSS 173 -> 795 MB). Now all queues share one budget."""

    async def main() -> None:
        hub = Hub(None)
        hub.send_budget = SendBudget(total=2 * 1024 * 1024)
        stuck = [
            Connection(StuckSocket(), time.monotonic, on_drop=hub.drop, budget=hub.send_budget)
            for _ in range(8)
        ]
        for c in stuck:
            hub.connections.add(c)
            c.start()
        quick_ws = QuickSocket()
        quick = Connection(quick_ws, time.monotonic, on_drop=hub.drop, budget=hub.send_budget)
        hub.connections.add(quick)
        quick.start()
        msg = {"type": "MATCH_TICK", "data": "x" * 20_000}
        for _ in range(60):  # 1.2 MB per viewer: under the 4 MB per-viewer cap
            hub.broadcast(msg)
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)
        used = sum(c.queued_bytes for c in stuck if not c.closed)
        assert used <= hub.send_budget.total + SEND_QUEUE_SHARE_BYTES
        assert hub.send_budget.used == used + quick.queued_bytes
        dropped = [c for c in stuck if c.closed]
        assert dropped and all(c.ws.closed_with == 1013 for c in dropped)  # type: ignore[attr-defined]
        assert all(c not in hub.connections for c in dropped)
        # The viewer that keeps up is never dropped for the others' backlog.
        assert not quick.closed and quick_ws.sent == 60

    asyncio.run(main())


def test_ec1_bytes_go_back_to_the_budget_when_a_viewer_leaves():
    async def main() -> None:
        budget = SendBudget(total=10 * 1024 * 1024)
        conn = Connection(StuckSocket(), time.monotonic, budget=budget)  # type: ignore[arg-type]
        writer = conn.start()
        for _ in range(10):
            conn.send({"type": "X", "data": "x" * 50_000})
        await asyncio.sleep(0.01)
        assert budget.used == conn.queued_bytes > 0
        conn.close()
        writer.cancel()  # what the endpoint does to a writer stuck past its grace period
        conn.drain_queue()
        assert budget.used == 0 and conn.queued_bytes == 0

    asyncio.run(main())
