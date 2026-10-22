import asyncio, json, websockets
U = "ws://localhost:8860/ws/match"
async def one(h):
    try:
        ws = await websockets.connect(U, origin="http://localhost:8860", additional_headers=h, max_size=None)
        return ws
    except Exception as e:
        return e
async def main():
    out = {}
    socks = await asyncio.gather(*(one({"x-forwarded-for": "10.7.7.7"}) for _ in range(25)))
    ok = [s for s in socks if not isinstance(s, Exception)]
    out["one_ip_25"] = {"accepted_handshake": len(ok)}
    closed = 0
    for s in ok:
        try:
            m = json.loads(await asyncio.wait_for(s.recv(), 3)); 
        except Exception: closed += 1
    out["one_ip_25"]["closed_after_accept"] = closed
    for s in ok: await s.close()
    ws = await websockets.connect(U, origin="http://localhost:8860", max_size=None)
    await ws.recv()
    await ws.send("x" * 5000)
    for _ in range(5):
        m = json.loads(await asyncio.wait_for(ws.recv(), 3))
        if m["type"] == "ERROR": out["oversize"] = m["data"]; break
    await ws.send('{"action":"drop_tables"}')
    for _ in range(5):
        m = json.loads(await asyncio.wait_for(ws.recv(), 3))
        if m["type"] == "ERROR": out["unknown_action"] = m["data"]; break
    await ws.close()
    try:
        await websockets.connect(U, origin="https://evil.example")
        out["evil_origin"] = "accepted"
    except Exception as e:
        out["evil_origin"] = type(e).__name__ + " " + str(e)[:80]
    print(json.dumps(out, indent=1))
asyncio.run(main())
