"""Rate-limit probe against a local server: per-route burst from one address."""
import asyncio, sys, time, json, statistics
import httpx
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8860"

async def burst(c, method, path, n, conc=50, **kw):
    sem = asyncio.Semaphore(conc); codes = {}; lat = []
    async def one():
        async with sem:
            t = time.perf_counter()
            r = await c.request(method, BASE + path, **kw)
            lat.append(time.perf_counter() - t)
            codes[r.status_code] = codes.get(r.status_code, 0) + 1
    t0 = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(n)))
    lat.sort()
    return {"route": f"{method} {path}", "n": n, "codes": codes, "wall_s": round(time.perf_counter() - t0, 2),
            "p50_ms": round(lat[len(lat)//2]*1000), "p95_ms": round(lat[int(len(lat)*.95)]*1000)}

async def health_during(c, stop):
    lat = []
    while not stop.is_set():
        t = time.perf_counter(); await c.get(BASE + "/api/health"); lat.append(time.perf_counter() - t)
        await asyncio.sleep(0.05)
    lat.sort(); return {"health_p50_ms": round(lat[len(lat)//2]*1000), "health_max_ms": round(lat[-1]*1000), "samples": len(lat)}

async def main():
    out = []
    limits = httpx.Limits(max_connections=200)
    async with httpx.AsyncClient(timeout=60, limits=limits) as c:
        for m, p, n, kw in [
            ("GET", "/api/match/recap", 100, {}),
            ("POST", "/api/ask", 100, {"json": {"chip": "score"}}),
            ("POST", "/mcp", 100, {"json": {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "headers": {"accept": "application/json, text/event-stream"}}),
            ("POST", "/api/match/speed", 50, {"json": {"speed_multiplier": 10}}),
            ("GET", "/api/dataset/export?match_id=MM-DEMO-001&format=jsonl", 30, {}),
        ]:
            out.append(await burst(c, m, p, n, **kw))
        # Unlimited routes: flood and watch health from the same client.
        for p in ["/api/match/snapshot", "/api/auto-eventing", "/api/match/stats/basic", "/api/crew/trace?limit=100"]:
            stop = asyncio.Event()
            h = asyncio.create_task(health_during(c, stop))
            r = await burst(c, "GET", p, 1000, conc=50)
            stop.set(); r.update(await h); out.append(r)
    print(json.dumps(out, indent=1))
asyncio.run(main())
