"""Viewers that connect and never read: how much server memory can they pin?

Local only. Opens N raw WebSocket connections (each from its own X-Forwarded-For
address, accepted by uvicorn only from 127.0.0.1), with a small receive buffer,
and never reads. Samples the server's RSS every 2 s, then reads each socket to
see whether the server closed it (close code 1013 = dropped as too slow).

Usage: python3 slow_consumers.py --port 8820 --n 200 --seconds 60 --pid <server pid>
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import time


def rss_mb(pid: int) -> float | None:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


def open_raw(port: int, ip: str) -> socket.socket:
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    s.connect(("127.0.0.1", port))
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(
        (
            "GET /ws/match HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nX-Forwarded-For: {ip}\r\n\r\n"
        ).encode()
    )
    return s


def close_code(s: socket.socket) -> str:
    """Drain what is left and look for a close frame (opcode 8) at the end."""
    s.settimeout(3)
    data = b""
    try:
        while True:
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    except (TimeoutError, OSError):
        return "open"
    i = data.rfind(b"\x88")
    if i >= 0 and i + 3 < len(data):
        return str(int.from_bytes(data[i + 2 : i + 4], "big"))
    return "eof"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8820)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--pid", type=int, required=True)
    args = ap.parse_args()
    out: dict = {"n": args.n, "rss_before_mb": rss_mb(args.pid), "samples": []}
    socks = [open_raw(args.port, f"10.77.{i >> 8}.{i & 255}") for i in range(args.n)]
    t0 = time.time()
    peak = 0.0
    while time.time() - t0 < args.seconds:
        time.sleep(2)
        r = rss_mb(args.pid) or 0.0
        peak = max(peak, r)
        out["samples"].append([round(time.time() - t0), r])
    out["rss_peak_mb"] = peak
    codes: dict[str, int] = {}
    for s in socks:
        c = close_code(s)
        codes[c] = codes.get(c, 0) + 1
        s.close()
    out["server_close_codes"] = codes
    time.sleep(2)
    out["rss_after_mb"] = rss_mb(args.pid)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
