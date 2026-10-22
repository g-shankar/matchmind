"""Server restart with viewers connected. Local only.

Usage: python3 restart_check.py --port 8820 --n 50 --pid <server pid>
Opens N viewers, sends SIGTERM to the server, and reports how long the server
took to close them and with which close codes. Restart the server afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import time

import websockets


async def viewer(url: str, i: int, out: list) -> None:
    async with websockets.connect(url, additional_headers={"X-Forwarded-For": f"10.80.0.{i}"}, max_size=None) as ws:
        try:
            async for _ in ws:
                pass
        except websockets.ConnectionClosed:
            pass
        out.append((time.perf_counter(), ws.close_code))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8820)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--pid", type=int, required=True)
    args = ap.parse_args()
    url = f"ws://127.0.0.1:{args.port}/ws/match"
    closed: list = []
    tasks = [asyncio.create_task(viewer(url, i, closed)) for i in range(args.n)]
    await asyncio.sleep(3)
    t0 = time.perf_counter()
    os.kill(args.pid, signal.SIGTERM)
    await asyncio.wait(tasks, timeout=30)
    codes: dict = {}
    for _, c in closed:
        codes[str(c)] = codes.get(str(c), 0) + 1
    gone = 0.0
    for _ in range(300):
        try:
            os.kill(args.pid, 0)
        except ProcessLookupError:
            gone = time.perf_counter() - t0
            break
        await asyncio.sleep(0.1)
    print(json.dumps({
        "viewers": args.n,
        "closed": len(closed),
        "close_codes": codes,
        "last_close_s": round(max((t for t, _ in closed), default=t0) - t0, 2),
        "process_exit_s": round(gone, 2) if gone else "still running after 30 s",
    }))


if __name__ == "__main__":
    asyncio.run(main())
