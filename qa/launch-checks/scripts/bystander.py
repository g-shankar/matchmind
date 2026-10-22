"""One ordinary viewer (WebSocket + REST) while another address floods an unlimited GET route."""
import asyncio, json, sys, time
import httpx, websockets
BASE = "localhost:8860"
FLOOD_PATH = sys.argv[1] if len(sys.argv) > 1 else ""
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 20
CONC = int(sys.argv[3]) if len(sys.argv) > 3 else 100

async def viewer(stop, res):
    gaps = []; n = 0; last = None; clocks = []
    async with websockets.connect(f"ws://{BASE}/ws/match", origin="http://localhost:8860",
                                  additional_headers={"x-forwarded-for": "10.9.9.9"}, max_size=None) as ws:
        while not stop.is_set():
            try:
                m = await asyncio.wait_for(ws.recv(), 1.0)
            except asyncio.TimeoutError:
                continue
            now = time.perf_counter(); n += 1
            if last: gaps.append(now - last)
            last = now
            try:
                d = json.loads(m); c = (d.get("payload") or {}).get("clock_s") or (d.get("payload") or {}).get("match_clock_s")
                if isinstance(c, (int, float)): clocks.append((now, c))
            except Exception: pass
    gaps.sort()
    res["ws_msgs"] = n; res["ws_gap_p99_ms"] = round(gaps[int(len(gaps)*.99)]*1000) if gaps else None; res["ws_gap_max_ms"] = round(gaps[-1]*1000) if gaps else None

async def rest_user(stop, res):
    lat = []
    async with httpx.AsyncClient(timeout=30, headers={"x-forwarded-for": "10.9.9.9"}) as c:
        while not stop.is_set():
            t = time.perf_counter(); await c.get(f"http://{BASE}/api/match/snapshot"); lat.append(time.perf_counter()-t)
            await asyncio.sleep(0.25)
    lat.sort(); res["rest_over_1s"] = sum(x > 1 for x in lat); res["rest_samples"] = len(lat); res["rest_p50_ms"] = round(lat[len(lat)//2]*1000); res["rest_max_ms"] = round(lat[-1]*1000)

async def flood(stop, res):
    n = 0; codes = {}
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=CONC), headers={"x-forwarded-for": "10.6.6.6"}) as c:
        async def worker():
            nonlocal n
            while not stop.is_set():
                try:
                    r = await c.get(f"http://{BASE}{FLOOD_PATH}")
                except Exception:
                    codes["err"] = codes.get("err", 0) + 1; continue
                n += 1; codes[r.status_code] = codes.get(r.status_code, 0) + 1
        await asyncio.gather(*(worker() for _ in range(CONC)))
    res["flood_requests"] = n; res["flood_codes"] = codes

async def main():
    stop = asyncio.Event(); res = {"flood": FLOOD_PATH or None, "seconds": SECONDS}
    tasks = [viewer(stop, res), rest_user(stop, res)] + ([flood(stop, res)] if FLOOD_PATH else [])
    async def timer(): await asyncio.sleep(SECONDS); stop.set()
    await asyncio.gather(timer(), *tasks)
    print(json.dumps(res))
asyncio.run(main())
