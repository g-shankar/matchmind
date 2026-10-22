"""Device matrix, axe, keyboard walk, tap targets and zoom against the local server."""
import asyncio, json, sys
from playwright.async_api import async_playwright
BASE = "http://localhost:8860"
SHOTS = "./qa/launch-checks/shots"
AXE = "/tmp/launch-checks/tools/node_modules/axe-core/axe.min.js"
OUT = "/tmp/launch-checks/ui_checks.json"
VIEWS = ["studio", "overlay", "split", "follow", "fan", "lab"]
DEVICES = {
    "desktop-1440": dict(viewport={"width": 1440, "height": 900}),
    "iphone-390": dict(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True,
                       user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
    "android-360": dict(viewport={"width": 360, "height": 740}, device_scale_factor=3, is_mobile=True, has_touch=True,
                        user_agent="Mozilla/5.0 (Linux; Android 13; SM-A135F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"),
    "tablet-768": dict(viewport={"width": 768, "height": 1024}, device_scale_factor=2, is_mobile=True, has_touch=True),
}
OVERFLOW_JS = """() => { const w = document.documentElement.clientWidth; const offenders = [];
  for (const e of document.querySelectorAll('body *')) { const r = e.getBoundingClientRect();
    if (r.width && (r.right > w + 1) && getComputedStyle(e).position !== 'fixed') {
      let p = e.parentElement, clipped = false;
      while (p) { const s = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(s.overflowX)) { clipped = true; break; } p = p.parentElement; }
      if (!clipped) offenders.push((e.tagName + '.' + (e.className && e.className.baseVal === undefined ? e.className : '')).slice(0, 80) + ' right=' + Math.round(r.right)); } }
  return { scrollWidth: document.documentElement.scrollWidth, clientWidth: w, offenders: offenders.slice(0, 5), count: offenders.length }; }"""
TAP_JS = """() => { const out = []; const sel = 'a[href], button, input, select, textarea, [role=button], [role=tab], [role=switch], [tabindex]:not([tabindex="-1"])';
  for (const e of document.querySelectorAll(sel)) { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    if (!r.width || !r.height || s.visibility === 'hidden' || s.display === 'none') continue;
    out.push({ w: Math.round(r.width), h: Math.round(r.height), name: (e.getAttribute('aria-label') || e.textContent || e.getAttribute('title') || e.tagName).trim().slice(0, 40) }); }
  return out; }"""

async def ready(pg, view):
    await pg.goto(f"{BASE}/#{view}", wait_until="domcontentloaded")
    await pg.wait_for_function("document.querySelector('#root') && document.querySelector('#root').innerText.length > 200", timeout=30000)
    await pg.wait_for_timeout(3500)

async def main():
    res = {"devices": {}, "axe": {}, "keyboard": {}, "tap": {}, "zoom": {}, "aria": {}}
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        # A. device matrix
        for dname, opts in DEVICES.items():
            ctx = await b.new_context(**opts); pg = await ctx.new_page()
            errs = []; pg.on("console", lambda m, errs=errs: errs.append(m.text[:200]) if m.type == "error" else None)
            pg.on("pageerror", lambda e, errs=errs: errs.append("pageerror " + str(e)[:200]))
            d = {}
            for v in VIEWS:
                await ready(pg, v)
                ov = await pg.evaluate(OVERFLOW_JS)
                await pg.screenshot(path=f"{SHOTS}/{dname}-{v}.png")
                d[v] = ov
            d["console_errors"] = errs
            res["devices"][dname] = d
            await ctx.close()
        # B. axe (CSP blocks injected scripts, so bypass it in this context only)
        for dname in ["desktop-1440", "iphone-390"]:
            ctx = await b.new_context(bypass_csp=True, **DEVICES[dname]); pg = await ctx.new_page()
            res["axe"][dname] = {}
            for v in VIEWS:
                await ready(pg, v)
                await pg.add_script_tag(path=AXE)
                r = await pg.evaluate("async () => { const r = await axe.run(document, { runOnly: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice'] }); return r.violations.map(v => ({ id: v.id, impact: v.impact, n: v.nodes.length, help: v.help, sample: v.nodes.slice(0,3).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary||'').split('\\n').slice(1,2).join('')) })); }")
                res["axe"][dname][v] = r
            await ctx.close()
        # C. keyboard walk + modal focus trap (desktop)
        ctx = await b.new_context(**DEVICES["desktop-1440"]); pg = await ctx.new_page()
        await ready(pg, "studio")
        stops = []
        for i in range(45):
            await pg.keyboard.press("Tab")
            info = await pg.evaluate("""() => { const e = document.activeElement; if (!e || e === document.body) return null; const s = getComputedStyle(e); const r = e.getBoundingClientRect();
              return { tag: e.tagName, role: e.getAttribute('role'), name: (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 40),
                outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0, ring: s.boxShadow !== 'none', inView: r.bottom > 0 && r.top < innerHeight }; }""")
            stops.append(info)
            if i == 2: await pg.screenshot(path=f"{SHOTS}/keyboard-focus-desktop.png")
        res["keyboard"]["tab_stops"] = stops
        res["keyboard"]["no_visible_focus"] = [s for s in stops if s and not (s["outline"] or s["ring"])]
        # Modal: open the recap, walk Tab inside it, Escape, focus back on the opener.
        opener = pg.get_by_role("button", name="Recap").first
        await opener.focus(); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(1500)
        inside = []
        for _ in range(25):
            await pg.keyboard.press("Tab")
            inside.append(await pg.evaluate("() => !!document.activeElement.closest('[role=dialog]')"))
        await pg.screenshot(path=f"{SHOTS}/keyboard-recap-modal.png")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
        back = await pg.evaluate("() => ({ dialog: !!document.querySelector('[role=dialog]'), focus: (document.activeElement.textContent||'').trim().slice(0,20) })")
        res["keyboard"]["modal"] = {"tabs_inside": sum(inside), "of": len(inside), "after_escape": back}
        # Accessibility tree (ARIA snapshot) of the studio view
        snap = await pg.locator("body").aria_snapshot()
        open(OUT.replace("ui_checks.json", "aria-studio.yaml"), "w").write(snap)
        res["aria"]["lines"] = snap.count("\n")
        res["aria"]["unnamed_buttons"] = sum(1 for l in snap.splitlines() if l.strip() in ("- button", "- button:"))
        res["aria"]["unnamed_links"] = sum(1 for l in snap.splitlines() if l.strip() in ("- link", "- link:"))
        await ctx.close()
        # D. tap targets at 375 x 812
        ctx = await b.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=3, is_mobile=True, has_touch=True); pg = await ctx.new_page()
        for v in VIEWS:
            await ready(pg, v)
            t = await pg.evaluate(TAP_JS)
            res["tap"][v] = {"total": len(t), "under44": len([x for x in t if min(x["w"], x["h"]) < 44]),
                             "under24": len([x for x in t if min(x["w"], x["h"]) < 24]),
                             "examples_under24": [x for x in t if min(x["w"], x["h"]) < 24][:6]}
        await ctx.close()
        # E. 200% zoom at 1280 wide = a 640 CSS px viewport at device scale 2
        ctx = await b.new_context(viewport={"width": 640, "height": 400}, device_scale_factor=2); pg = await ctx.new_page()
        for v in ["studio", "overlay", "lab"]:
            await ready(pg, v)
            res["zoom"][v] = await pg.evaluate(OVERFLOW_JS)
            await pg.screenshot(path=f"{SHOTS}/zoom200-1280-{v}.png")
        await ctx.close()
        await b.close()
    json.dump(res, open(OUT, "w"), indent=1)
    print("done")
asyncio.run(main())
