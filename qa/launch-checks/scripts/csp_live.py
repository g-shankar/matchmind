import asyncio, json, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        pg = await b.new_page()
        msgs = []
        pg.on("console", lambda m: msgs.append(m.text[:200]))
        ws = []
        pg.on("websocket", lambda w: ws.append(w.url))
        await pg.goto("http://localhost:8890/?live=1#studio")
        await pg.wait_for_timeout(6000)
        body = await pg.inner_text("body")
        print(json.dumps({"websockets": ws, "csp_violations": [m for m in msgs if "Content Security Policy" in m],
                          "connecting_badge": "Connecting" in body, "demo": "Offline demo" in body}))
        await b.close()
asyncio.run(main())
