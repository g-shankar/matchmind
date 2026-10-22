"""Bursts of REST, Ask and MCP requests against a local server. Local only.

Usage: python3 rest_burst.py --base http://127.0.0.1:8820 --n 300
Phase 1: --n requests from ONE address (expects the per-IP bucket to answer 429).
Phase 2: --n requests from --n different addresses (the bucket table, latency).
Phase 3: --n requests from one address with a spoofed leftmost X-Forwarded-For
         entry per request (must not buy fresh buckets).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import httpx

MCP_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "get_match_snapshot", "arguments": {}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def pct(v: list[float], p: float) -> float | None:
    if not v:
        return None
    v = sorted(v)
    return round(v[min(len(v) - 1, round(p / 100 * (len(v) - 1)))], 1)


async def one(http: httpx.AsyncClient, kind: str, xff: str) -> tuple[int, float]:
    t = time.perf_counter()
    h = {"X-Forwarded-For": xff}
    if kind == "ask":
        r = await http.post("/api/ask", json={"chip": "score"}, headers=h)
    elif kind == "mcp":
        r = await http.post("/mcp", json=MCP_BODY, headers={**h, **MCP_HEADERS})
    else:
        r = await http.get("/api/match/recap", headers=h)
    return r.status_code, (time.perf_counter() - t) * 1000


async def phase(http: httpx.AsyncClient, kind: str, n: int, mode: str) -> dict:
    def xff(i: int) -> str:
        if mode == "one":
            return "10.50.0.1"
        if mode == "many":
            return f"10.51.{i >> 8}.{i & 255}"
        return f"203.0.{i >> 8}.{i & 255}, 10.52.0.1"  # spoofed left entry, same real address

    t0 = time.perf_counter()
    res = await asyncio.gather(*(one(http, kind, xff(i)) for i in range(n)))
    codes: dict[int, int] = {}
    for c, _ in res:
        codes[c] = codes.get(c, 0) + 1
    ms = [m for c, m in res if c == 200]
    return {
        "kind": kind,
        "mode": mode,
        "codes": codes,
        "ok_ms_p50_p95": [pct(ms, 50), pct(ms, 95)],
        "wall_s": round(time.perf_counter() - t0, 2),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8820")
    ap.add_argument("--n", type=int, default=300)
    args = ap.parse_args()
    if not args.base.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit("local servers only")
    limits = httpx.Limits(max_connections=200)
    async with httpx.AsyncClient(base_url=args.base, timeout=60, limits=limits) as http:
        for kind in ("recap", "ask", "mcp"):
            for mode in ("one", "many", "spoof"):
                print(json.dumps(await phase(http, kind, args.n, mode)))
                await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
