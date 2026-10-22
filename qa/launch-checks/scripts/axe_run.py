"""Run axe 4.10.2 on every view at 1440 and 375 against :8890. Usage: axe_run.py out.json"""
import asyncio, json, sys
from playwright.async_api import async_playwright
BASE = "http://localhost:8890"
AXE = "/tmp/claude-0/-home-user/4d294f7a-3913-5934-9756-ca99974ede83/scratchpad/launch/tools/node_modules/axe-core/axe.min.js"
VIEWS = ["studio", "overlay", "split", "follow", "fan", "lab"]
DEV = {"desktop-1440": dict(viewport={"width": 1440, "height": 900}),
       "phone-375": dict(viewport={"width": 375, "height": 812}, device_scale_factor=3, is_mobile=True, has_touch=True)}
async def main():
    res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        for d, o in DEV.items():
            ctx = await b.new_context(bypass_csp=True, **o); pg = await ctx.new_page(); res[d] = {}
            for v in VIEWS:
                await pg.goto(f"{BASE}/#{v}", wait_until="domcontentloaded")
                await pg.wait_for_function("document.querySelector('#root') && document.querySelector('#root').innerText.length > 200", timeout=30000)
                await pg.wait_for_timeout(4000)
                await pg.add_script_tag(path=AXE)
                r = await pg.evaluate("async () => { const r = await axe.run(document, { runOnly: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice'] }); return {version: axe.version, v: r.violations.map(v => ({ id: v.id, impact: v.impact, n: v.nodes.length, nodes: v.nodes.slice(0,8).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary||'').split('\\n').slice(1,2).join('') + ' :: ' + n.html.slice(0,140)) }))}; }")
                res[d][v] = r["v"]; res["version"] = r["version"]
            await ctx.close()
        await b.close()
    json.dump(res, open(sys.argv[1], "w"), indent=1)
    for d in DEV:
        for v in VIEWS: print(d, v, [(x["id"], x["impact"], x["n"]) for x in res[d][v]])
asyncio.run(main())
