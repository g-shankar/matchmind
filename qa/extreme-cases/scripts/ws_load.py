"""Open N WebSocket viewers against a local PitchPulse server and measure it.

Local load test only (never point it at a deployed URL). Every viewer can come
from its own address (X-Forwarded-For from localhost, which uvicorn's proxy
headers accept only from 127.0.0.1) or all from one address.

Usage:
  python3 ws_load.py --base http://127.0.0.1:8820 --n 100 --seconds 30 --pid <server pid>
  python3 ws_load.py --base http://127.0.0.1:8820 --n 1000 --seconds 30 --same-ip

Prints one JSON object with: accepted/refused counts, connect and snapshot times,
snapshot size, message rates, match seconds delivered per wall second (expected
base_rate x speed = 100 at the default 10x), set_view round trip under load,
REST latency under load, and server RSS before/after.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx
import websockets


def rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = min(len(values) - 1, max(0, round(p / 100 * (len(values) - 1))))
    return round(values[k], 1)


class Viewer:
    def __init__(self, i: int, ip: str) -> None:
        self.i, self.ip = i, ip
        self.accepted = False
        self.refused: str | None = None
        self.connect_ms: float | None = None
        self.snapshot_ms: float | None = None
        self.snapshot_bytes = 0
        self.msgs = 0
        self.bytes = 0
        self.ticks: list[tuple[float, float]] = []  # (wall, timeline-ish seconds)
        self.closed_code: int | None = None
        self.view_rtt_ms: list[float] = []
        self._view_sent: float | None = None

    async def run(self, url: str, stop: asyncio.Event, probe: bool) -> None:
        t0 = time.perf_counter()
        headers = {"X-Forwarded-For": self.ip}
        try:
            ws = await websockets.connect(url, additional_headers=headers, max_size=None, open_timeout=30)
        except Exception as exc:  # noqa: BLE001
            self.refused = type(exc).__name__
            return
        self.connect_ms = (time.perf_counter() - t0) * 1000
        try:
            async def reader() -> None:
                async for raw in ws:
                    now = time.perf_counter()
                    self.msgs += 1
                    self.bytes += len(raw)
                    msg = json.loads(raw)
                    t = msg.get("type")
                    if t == "INITIAL_SNAPSHOT" and self.snapshot_ms is None:
                        self.accepted = True
                        self.snapshot_ms = (now - t0) * 1000
                        self.snapshot_bytes = len(raw)
                    elif t == "MATCH_TICK":
                        ev = msg["data"].get("event") or {}
                        if ev:
                            clock = ev.get("clock_s", 0.0) + (10_000 if ev.get("period") == 2 else 0)
                            self.ticks.append((now, clock))
                    elif t == "PROFILE_CHANGED" and self._view_sent is not None:
                        self.view_rtt_ms.append((now - self._view_sent) * 1000)
                        self._view_sent = None

            task = asyncio.create_task(reader())
            if probe:
                lang = ["en", "es"]
                k = 0
                while not stop.is_set():
                    await asyncio.sleep(1.2)
                    if self._view_sent is None:
                        self._view_sent = time.perf_counter()
                        k += 1
                        await ws.send(json.dumps({"action": "set_view", "language": lang[k % 2]}))
            else:
                await stop.wait()
            task.cancel()
        except websockets.ConnectionClosed as exc:
            self.closed_code = exc.code
        finally:
            self.closed_code = self.closed_code or ws.close_code
            await ws.close()


def delivered_rate(ticks: list[tuple[float, float]]) -> float | None:
    """Match seconds received per wall second, within each half (period jumps excluded)."""
    total_clock, total_wall = 0.0, 0.0
    for (w0, c0), (w1, c1) in zip(ticks, ticks[1:], strict=False):
        if 0 <= c1 - c0 < 1000:
            total_clock += c1 - c0
            total_wall += w1 - w0
    return round(total_clock / total_wall, 1) if total_wall > 0 else None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8820")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--same-ip", action="store_true")
    ap.add_argument("--pid", type=int, default=0)
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()
    if not args.base.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit("local servers only")
    url = args.base.replace("http", "ws", 1) + "/ws/match"
    out: dict = {"n": args.n, "seconds": args.seconds, "same_ip": args.same_ip}
    async with httpx.AsyncClient(base_url=args.base, timeout=30) as http:
        if not args.no_reset:
            await http.post("/api/match/reset", headers={"X-Forwarded-For": "10.255.0.1"})
            await asyncio.sleep(0.6)
        out["rss_before_mb"] = rss_mb(args.pid)
        viewers = [
            Viewer(i, "10.9.9.9" if args.same_ip else f"10.{(i >> 16) & 255}.{(i >> 8) & 255}.{i & 255}")
            for i in range(args.n)
        ]
        stop = asyncio.Event()
        t0 = time.perf_counter()
        tasks = [asyncio.create_task(v.run(url, stop, probe=(i == 0))) for i, v in enumerate(viewers)]
        await asyncio.sleep(min(5.0, args.seconds / 3))
        out["connect_phase_s"] = round(time.perf_counter() - t0, 2)
        out["rss_connected_mb"] = rss_mb(args.pid)
        rest_ms: list[float] = []
        snap_ms: list[float] = []
        rest_errors = 0
        end = time.perf_counter() + args.seconds
        while time.perf_counter() < end:
            for path, sink in (("/api/health", rest_ms), ("/api/match/snapshot", snap_ms)):
                s = time.perf_counter()
                try:
                    r = await http.get(path, headers={"X-Forwarded-For": "10.254.0.1"})
                    if r.status_code == 200:
                        sink.append((time.perf_counter() - s) * 1000)
                    else:
                        rest_errors += 1
                except httpx.HTTPError:
                    rest_errors += 1
            await asyncio.sleep(0.5)
        out["rss_peak_window_mb"] = rss_mb(args.pid)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(2)
        out["rss_after_close_mb"] = rss_mb(args.pid)
    acc = [v for v in viewers if v.accepted]
    out["accepted"] = len(acc)
    out["refused"] = len([v for v in viewers if not v.accepted])
    out["closed_by_server_codes"] = sorted({v.closed_code for v in viewers if v.closed_code not in (None, 1000)})
    out["connect_ms_p50_p95"] = [pct([v.connect_ms for v in acc if v.connect_ms], p) for p in (50, 95)]
    out["snapshot_ms_p50_p95_max"] = [pct([v.snapshot_ms for v in acc if v.snapshot_ms], p) for p in (50, 95, 100)]
    out["snapshot_kb"] = round(statistics.mean([v.snapshot_bytes for v in acc]) / 1024, 1) if acc else None
    out["msgs_per_viewer_per_s"] = round(statistics.mean([v.msgs for v in acc]) / args.seconds, 1) if acc else None
    out["kb_per_viewer_per_s"] = round(statistics.mean([v.bytes for v in acc]) / 1024 / args.seconds, 1) if acc else None
    rates = [r for r in (delivered_rate(v.ticks) for v in acc) if r is not None]
    out["match_s_per_wall_s_min_p50"] = [min(rates) if rates else None, pct(rates, 50)]
    out["set_view_rtt_ms_p50_max"] = [pct(viewers[0].view_rtt_ms, 50), pct(viewers[0].view_rtt_ms, 100)]
    out["rest_health_ms_p50_p95"] = [pct(rest_ms, 50), pct(rest_ms, 95)]
    out["rest_snapshot_ms_p50_p95"] = [pct(snap_ms, 50), pct(snap_ms, 95)]
    out["rest_errors"] = rest_errors
    print(json.dumps(out))


if __name__ == "__main__":
    asyncio.run(main())
