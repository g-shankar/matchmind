import asyncio, json, sys, websockets
async def main(sec):
    cards = []; errors = []
    async with websockets.connect("ws://localhost:8860/ws/match", origin="http://localhost:8860", max_size=None) as ws:
        end = asyncio.get_event_loop().time() + sec
        while asyncio.get_event_loop().time() < end:
            try: m = json.loads(await asyncio.wait_for(ws.recv(), 1))
            except asyncio.TimeoutError: continue
            if m["type"] in ("NEW_CARD", "CARD", "OVERLAY_CARD") or "card" in m["type"].lower():
                d = m.get("data") or {}
                cards.append({k: d.get(k) for k in ("kind", "produced_by", "fallback_reason", "headline")})
            if m["type"] == "ERROR": errors.append(m["data"])
    print(json.dumps({"cards": len(cards), "sample": cards[:4], "produced_by": sorted({str(c["produced_by"]) for c in cards}), "fallback_reasons": sorted({str(c["fallback_reason"]) for c in cards}), "errors": errors[:3]}, indent=1))
asyncio.run(main(float(sys.argv[1])))
