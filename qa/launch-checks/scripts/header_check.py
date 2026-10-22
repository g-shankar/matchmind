"""Header pieces must never overlap, at any width, with the longest clock label (full time)."""
import asyncio, json, sys
import httpx
from playwright.async_api import async_playwright
SHOTS = "./qa/launch-checks/shots"
TAG = sys.argv[1]
JS = """() => { const h = document.querySelector('header'); const items = [...h.querySelectorAll('h1, button, [dir=ltr]')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && getComputedStyle(e).position !== 'absolute'; });
  const boxes = items.map(e => [e, e.getBoundingClientRect()]); const hits = [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) { const [a, ra] = boxes[i], [b, rb] = boxes[j];
    if (a.contains(b) || b.contains(a)) continue;
    const ox = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), oy = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
    if (ox > 1 && oy > 1) hits.push((a.innerText || a.getAttribute('aria-label') || a.tagName).trim().slice(0, 20) + ' x ' + (b.innerText || b.getAttribute('aria-label') || b.tagName).trim().slice(0, 20)); }
  // Also: does any descendant text spill past its scoreboard box?
  const sb = h.querySelector('[dir=ltr]'); const spill = sb ? [...sb.children].some(c => c.scrollWidth > c.clientWidth + 1) : null;
  const maxRight = Math.max(...boxes.map(([e, r]) => r.right)); return { hits, max_right: Math.round(maxRight), vw: innerWidth, scoreboard_children_spill: spill, label: sb ? sb.innerText.replace(/\\n/g, ' ') : null }; }"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        pg = await (await b.new_context(bypass_csp=True, viewport={"width": 1280, "height": 800})).new_page()
        await pg.goto("http://localhost:8860/#studio"); await pg.wait_for_timeout(3000)
        c = httpx.Client(headers={"x-forwarded-for": "10.3.3.3"})
        c.post("http://localhost:8860/api/match/seek", json={"clock_s": 5400, "period": 2}); await pg.wait_for_timeout(700)
        c.post("http://localhost:8860/api/match/speed", json={"speed_multiplier": 60})
        await pg.wait_for_function("document.querySelector('header').innerText.toUpperCase().includes('FULL TIME')", timeout=120000)
        await pg.wait_for_timeout(1500); await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
        out = {}
        for w in [320, 360, 390, 640, 700, 768, 900, 1024, 1280, 1440]:
            await pg.set_viewport_size({"width": w, "height": 800}); await pg.wait_for_timeout(300)
            out[w] = await pg.evaluate(JS)
            if w in (640, 768, 1024): await pg.screenshot(path=f"{SHOTS}/{TAG}-header-{w}.png", clip={"x": 0, "y": 0, "width": w, "height": 130})
        print(json.dumps(out, indent=0))
        await b.close()
asyncio.run(main())
