"""One client address toggling pause as fast as the per-connection limit allows,
while a bystander viewer watches. Local only.

Usage: python3 pause_storm.py --port 8820 --conns 20 --seconds 15
Prints how many pause changes the bystander saw, how many the storm got through,
and how far the shared match clock moved for the bystander.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import websockets


async def bystander(url: str, stop: asyncio.Event, out: dict) -> None:
    async with websockets.connect(url, additional_headers={"X-Forwarded-For": "10.1.1.1"}, max_size=None) as ws:
        first = last = None
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), 0.5)
            except TimeoutError:
                continue
            m = json.loads(raw)
            if m["type"] == "PLAYBACK_CONTROL":
                out["playback_msgs"] = out.get("playback_msgs", 0) + 1
            if m["type"] == "MATCH_TICK":
                c = m["data"]["event"]["clock_s"]
                first = c if first is None else first
                last = c
        out["clock_moved_s"] = round((last or 0) - (first or 0), 1)


async def stormer(url: str, stop: asyncio.Event, out: dict) -> None:
    async with websockets.connect(url, additional_headers={"X-Forwarded-For": "10.6.6.6"}, max_size=None) as ws:
        async def drain() -> None:
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "ERROR":
                    out["refused"] = out.get("refused", 0) + 1

        task = asyncio.create_task(drain())
        while not stop.is_set():
            await ws.send(json.dumps({"action": "toggle_pause"}))
            out["sent"] = out.get("sent", 0) + 1
            await asyncio.sleep(0.1)
        task.cancel()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8820)
    ap.add_argument("--conns", type=int, default=20)
    ap.add_argument("--seconds", type=float, default=15)
    args = ap.parse_args()
    url = f"ws://127.0.0.1:{args.port}/ws/match"
    stop = asyncio.Event()
    seen: dict = {}
    storm: dict = {}
    tasks = [asyncio.create_task(bystander(url, stop, seen))]
    await asyncio.sleep(1)
    tasks += [asyncio.create_task(stormer(url, stop, storm)) for _ in range(args.conns)]
    t0 = time.time()
    await asyncio.sleep(args.seconds)
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    print(json.dumps({"seconds": round(time.time() - t0, 1), "storm": storm, "bystander": seen}))


if __name__ == "__main__":
    asyncio.run(main())
