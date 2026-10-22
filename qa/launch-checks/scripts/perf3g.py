"""Slow 3G (400 ms RTT, 400 kbps, CPU 4x) at 375 x 812: first paint, app ready, first crew card."""
import asyncio, json, sys, time
from playwright.async_api import async_playwright
SHOTS = "./qa/launch-checks/shots"
URLS = {"live": "http://localhost:8860/#studio", "offline-demo": "http://localhost:8860/?demo=1#studio"}
async def run(b, name, url, throttle=True):
    ctx = await b.new_context(bypass_csp=True, viewport={"width": 375, "height": 812}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg = await ctx.new_page(); cdp = await ctx.new_cdp_session(pg)
    await cdp.send("Network.enable")
    if throttle:
        await cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 400, "downloadThroughput": 400 * 1024 / 8, "uploadThroughput": 400 * 1024 / 8})
        await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    t0 = time.perf_counter(); out = {"run": name, "throttled": throttle}
    await pg.goto(url, wait_until="commit", timeout=300000)
    try:
        await pg.wait_for_function("document.querySelector('#root') && document.querySelector('#root').innerText.length > 200", timeout=300000)
        out["app_shell_s"] = round(time.perf_counter() - t0, 1)
        await pg.wait_for_function("/\\d+-\\d+/.test(document.body.innerText) && document.querySelector('svg circle')", timeout=300000)
        out["match_data_s"] = round(time.perf_counter() - t0, 1)
        await pg.wait_for_function("document.body.innerText.toUpperCase().includes('TEMPLATE')", timeout=300000)
        out["first_crew_card_s"] = round(time.perf_counter() - t0, 1)
    except Exception as e:
        out["timeout"] = str(e)[:120]
    out["fcp_ms"] = await pg.evaluate("(performance.getEntriesByName('first-contentful-paint')[0]||{}).startTime|0")
    res = await pg.evaluate("performance.getEntriesByType('resource').map(r => [r.name.replace(location.origin,''), r.transferSize, Math.round(r.duration)])")
    nav = await pg.evaluate("(()=>{const n=performance.getEntriesByType('navigation')[0]; return [n.transferSize, Math.round(n.duration)]})()")
    out["bytes_total_kb"] = round((sum(r[1] for r in res) + nav[0]) / 1024)
    out["largest"] = sorted(res, key=lambda r: -r[1])[:5]
    await pg.screenshot(path=f"{SHOTS}/slow3g-{name}{'' if throttle else '-unthrottled'}.png")
    await ctx.close(); return out
async def main():
    results = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        for name, url in URLS.items():
            results.append(await run(b, name, url, False))
            results.append(await run(b, name, url, True))
            print(json.dumps(results[-1]))
        await b.close()
    json.dump(results, open("/tmp/launch-checks/perf3g.json", "w"), indent=1)
asyncio.run(main())
