"""Backend killed mid-session, API blocked, offline demo, Ask failing: what the viewer sees."""
import asyncio, json, os, signal, subprocess, time
from playwright.async_api import async_playwright
S = "/tmp/launch-checks"
SHOTS = "./qa/launch-checks/shots"
BASE = "http://localhost:8860"
import sys
PREFIX = sys.argv[1] if len(sys.argv) > 1 else ""
ONLY_KILL = len(sys.argv) > 2
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)

async def badge(pg):
    return await pg.evaluate("""() => { const t = document.body.innerText.toLowerCase(); const out = ['live engine','offline demo','connecting…'].filter(x => t.includes(x)); if (t.includes('could not be loaded')) out.push('LOAD FAILED notice'); return out; }""")

def server_pid():
    return int(open(f"{S}/server.pid").read().strip())

async def wait_health(timeout=90):
    import httpx
    t = time.time()
    while time.time() - t < timeout:
        try:
            if httpx.get(BASE + "/api/health", timeout=1).status_code == 200: return round(time.time() - t, 1)
        except Exception: pass
        await asyncio.sleep(0.5)
    return None

async def main():
    res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        # 1. Kill the backend mid-session.
        ctx = await b.new_context(**PHONE); pg = await ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(BASE + "/#studio"); await pg.wait_for_timeout(5000)
        timeline = [{"t": 0, "badge": await badge(pg)}]
        pid = server_pid(); os.kill(pid, signal.SIGTERM)
        t0 = time.time()
        for i in range(12):
            await pg.wait_for_timeout(1000)
            timeline.append({"t": round(time.time() - t0, 1), "badge": await badge(pg)})
            if i == 1: await pg.screenshot(path=f"{SHOTS}/{PREFIX}failure-1-server-killed-2s.png")
        await pg.screenshot(path=f"{SHOTS}/{PREFIX}failure-2-server-killed-12s.png")
        newpid = subprocess.check_output([f"{S}/scripts/start_server.sh"]).decode().strip()
        up = await wait_health()
        await pg.wait_for_timeout(10000)
        timeline.append({"t": round(time.time() - t0, 1), "badge": await badge(pg), "note": f"server back after {up}s (pid {newpid})"})
        await pg.screenshot(path=f"{SHOTS}/{PREFIX}failure-3-server-back.png")
        res["kill_backend"] = {"timeline": timeline, "page_errors": errs,
                               "stack_trace_shown": "Traceback" in await pg.evaluate("document.body.innerText")}
        await ctx.close()
        if ONLY_KILL:
            json.dump(res, open(f"{S}/{PREFIX}failure_kill.json", "w"), indent=1); print(json.dumps(res)); return
        # 2. Network off for /api and /ws on first load (auto mode) -> offline demo.
        ctx = await b.new_context(**PHONE); pg = await ctx.new_page()
        await pg.route("**/api/**", lambda r: r.abort()); await pg.route_web_socket("**/ws/**", lambda ws: ws.close())
        await pg.goto(BASE + "/#studio"); await pg.wait_for_timeout(8000)
        txt = await pg.evaluate("document.body.innerText")
        res["api_blocked_auto"] = {"badge": await badge(pg), "demo_hint": "not reachable" in txt}
        await pg.screenshot(path=f"{SHOTS}/failure-4-api-blocked-auto.png")
        await ctx.close()
        # 3. Same with ?live=1 (never falls back).
        ctx = await b.new_context(**PHONE); pg = await ctx.new_page()
        await pg.route("**/api/**", lambda r: r.abort()); await pg.route_web_socket("**/ws/**", lambda ws: ws.close())
        await pg.goto(BASE + "/?live=1#studio"); await pg.wait_for_timeout(8000)
        txt = await pg.evaluate("document.body.innerText")
        res["api_blocked_live_only"] = {"badge": await badge(pg), "text_head": txt[:300]}
        await pg.screenshot(path=f"{SHOTS}/failure-5-api-blocked-live-only.png")
        await ctx.close()
        # 4. Forced offline demo, typed question.
        ctx = await b.new_context(**PHONE); pg = await ctx.new_page()
        await pg.goto(BASE + "/?demo=1#studio"); await pg.wait_for_timeout(6000)
        res["demo"] = {"badge": await badge(pg)}
        await pg.screenshot(path=f"{SHOTS}/failure-6-offline-demo.png")
        await ctx.close()
        # 5. Live, but /api/ask fails (500, then network error): what does the Ask box say?
        for mode in ["500", "abort"]:
            ctx = await b.new_context(viewport={"width": 1440, "height": 900}); pg = await ctx.new_page()
            if mode == "500":
                await pg.route("**/api/ask", lambda r: r.fulfill(status=500, content_type="application/json", body='{"detail":"Something went wrong on our side. Please try again."}'))
            else:
                await pg.route("**/api/ask", lambda r: r.abort())
            await pg.goto(BASE + "/#studio"); await pg.wait_for_timeout(5000)
            box = pg.get_by_role("textbox").first
            await box.scroll_into_view_if_needed(); await box.fill("Who has had more shots?"); await box.press("Enter")
            await pg.wait_for_timeout(2500)
            alerts = await pg.evaluate("[...document.querySelectorAll('[role=alert]')].map(e => e.innerText.trim()).filter(Boolean)")
            res[f"ask_{mode}"] = {"alerts": alerts}
            await box.screenshot(path=f"{SHOTS}/failure-7-ask-{mode}.png") if False else None
            await pg.screenshot(path=f"{SHOTS}/failure-7-ask-{mode}.png", full_page=False)
            await ctx.close()
        await b.close()
    json.dump(res, open(f"{S}/failure_checks.json", "w"), indent=1)
    print(json.dumps(res, indent=1)[:4000])
asyncio.run(main())
