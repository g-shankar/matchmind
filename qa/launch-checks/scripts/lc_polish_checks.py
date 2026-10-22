"""Modal axe, pitch marker tap sizes at 375 (touch) and the LC-15 outage notice, against :8890."""
import asyncio, json, subprocess, sys, time, urllib.request
from playwright.async_api import async_playwright
S = "/tmp/claude-0/-home-user/4d294f7a-3913-5934-9756-ca99974ede83/scratchpad/lc-polish"
AXE = "/tmp/claude-0/-home-user/4d294f7a-3913-5934-9756-ca99974ede83/scratchpad/launch/tools/node_modules/axe-core/axe.min.js"
SHOTS = "/home/user/wt/lc-polish/qa/launch-checks/shots"
BASE = "http://localhost:8890"
AXE_JS = "async () => (await axe.run(document, { runOnly: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice'] })).violations.map(v => ({ id: v.id, impact: v.impact, n: v.nodes.length }))"
DOTS_JS = """() => Array.from(document.querySelectorAll('[data-player-dot]')).map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })"""
async def ready(pg, url):
    await pg.goto(url, wait_until="domcontentloaded")
    await pg.wait_for_function("document.querySelector('#root') && document.querySelector('#root').innerText.length > 200", timeout=30000)
    await pg.wait_for_timeout(4000)
def healthy():
    try: return urllib.request.urlopen(BASE + "/api/health", timeout=2).status == 200
    except Exception: return False
async def main():
    res = {"modals": {}, "tap": {}, "outage": {}}
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        ctx = await b.new_context(bypass_csp=True, viewport={"width": 1440, "height": 900}); pg = await ctx.new_page()
        for name, label in [("recap", "Recap"), ("about", "About this demo")]:
            await ready(pg, f"{BASE}/#studio")
            await pg.get_by_role("button", name=label).first.click(); await pg.wait_for_timeout(2500)
            await pg.add_script_tag(path=AXE)
            res["modals"][name] = await pg.evaluate(AXE_JS)
        await ctx.close()
        for touch in (True, False):
            ctx = await b.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=3, is_mobile=touch, has_touch=touch); pg = await ctx.new_page()
            key = "touch-375" if touch else "mouse-375"; res["tap"][key] = {}
            for v in ["studio", "follow"]:
                await ready(pg, f"{BASE}/#{v}")
                coarse = await pg.evaluate("() => matchMedia('(pointer: coarse)').matches")
                dots = await pg.evaluate(DOTS_JS)
                res["tap"][key][v] = {"pointer_coarse": coarse, "markers": len(dots), "min_px": min((min(d) for d in dots), default=None), "max_px": max((min(d) for d in dots), default=None)}
            if touch: await pg.screenshot(path=f"{SHOTS}/lc5-touch-375-follow.png")
            await ctx.close()
        # LC-15: stop the server, wait past 15 s, then bring it back.
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True); pg = await ctx.new_page()
        await ready(pg, f"{BASE}/?lang=fr#studio")
        pid = int(open(f"{S}/server.pid").read().strip())
        subprocess.run(["kill", str(pid)], check=True)
        t0 = time.monotonic(); await pg.wait_for_timeout(8000)
        res["outage"]["at_8s"] = await pg.locator("[data-testid=connection-lost]").count()
        await pg.wait_for_timeout(9000)
        n = await pg.locator("[data-testid=connection-lost]").count()
        res["outage"]["at_17s"] = n
        res["outage"]["text_17s"] = (await pg.locator("[data-testid=connection-lost]").inner_text()) if n else None
        await pg.screenshot(path=f"{SHOTS}/lc15-outage-17s.png")
        subprocess.run([f"{S}/start.sh"], check=True, stdout=subprocess.DEVNULL)
        while not healthy(): await asyncio.sleep(1)
        res["outage"]["server_back_after_s"] = round(time.monotonic() - t0)
        await pg.locator("[data-testid=connection-lost] button").click()
        for _ in range(30):
            await pg.wait_for_timeout(1000)
            if await pg.locator("[data-testid=connection-lost]").count() == 0: break
        res["outage"]["notice_gone_s_after_back"] = round(time.monotonic() - t0) - res["outage"]["server_back_after_s"]
        await pg.screenshot(path=f"{SHOTS}/lc15-outage-back.png")
        await b.close()
    json.dump(res, open(sys.argv[1], "w"), indent=1); print(json.dumps(res, indent=1))
asyncio.run(main())
