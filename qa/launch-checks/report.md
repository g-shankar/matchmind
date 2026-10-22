# Launch checks: pre-launch test round, part 3

Branch `feat/launch-checks` from `74ed870`, 22 Oct 2026. Every run was local, against a server started from this worktree on port 8860. It used the bundled synthetic demo match (MM-DEMO-001, invented clubs and players) with the AI switch off, unless a check says otherwise. Nothing touched Azure, no paid service was called and no capacity was changed. Evidence files are in [`evidence/`](evidence/), screenshots in [`shots/`](shots/) and probe scripts in [`scripts/`](scripts/). `scripts/start_server.sh` starts the server the way these runs did.

Browsers: only headless Chromium is installed here. Safari, Firefox and WebKit were **not tested**. Phones and tablets were emulated in Chromium (viewport, pixel ratio, touch, mobile user agent).

## Summary

Four problems were fixed, each in its own commit with a test or a measured before/after:

- **LC-2 (High):** after a server restart a viewer stayed on "Connecting…" until they refreshed.
- **LC-1 (Medium):** one address could slow every viewer by looping on read routes that had no limit.
- **LC-3 (Medium):** the header scoreboard ran under the play button on tablets and at 200% zoom.
- **LC-8 (Low):** the licence check let packages with no licence or a non-commercial licence through.

A follow-up round (branch `feat/lc-polish` from `e81c756`, same day, server on port 8890) closed the cheap open items, each in its own commit with a test and a measured before/after:

- **LC-4 contrast** (`4bb19b3`): axe `color-contrast` went from 2-6 elements per view to **0 on every view** at 1440 and 375 px.
- **LC-6 other axe rules** (`b60d376`, `fc05c4d`): axe 4.10.2 now reports **0 violations of any impact** on all six views at 1440 and 375 px, live and offline demo, and with the recap and About dialogs open.
- **LC-5 touch targets** (`4d2712b`): pitch markers are 44 x 44 px on a touch screen (17-23 px before), with no change to how they look.
- **LC-15** (`e15b12e`), **LC-11** (`0fce286`), **LC-14** (`fb17874`), **LC-16** (`610e562`): fixed, details in the findings table.
- **LC-7** (`e8d780e`): the dev server now listens on `localhost` only and CI audits the shipped npm packages. The 13 dev-tool advisories stay open because the upgrades are not drop-in (see LC-7 below).

Open items that need the owner: no alerts or budget in the Azure template (LC-9), the replica size against the 200-viewer cap (LC-10, carried over from EC-9), no privacy notice (LC-12) and the commit author identities (LC-13). LC-7's dev-tool upgrades are open engineering work.

Counts (rows in the table below): **PASS 46, FAIL 11, N/A 6**. Seven of the FAIL rows are fixed (four in the first round, three in the follow-up); four are open (rows 22, 46, 58 and 60).

| # | Area | Check | Result | Evidence |
|---|---|---|---|---|
| 1 | Full checks | Backend tests | PASS | `pytest -q`: **1068 passed** in 389 s (1055 before this branch's fixes). Follow-up round: **1173 passed** in 451 s (1167 at `e81c756`); `ruff check .` and `ruff format --check .` clean |
| 2 | Full checks | `ruff check .`, `ruff format --check .` | PASS | "All checks passed!"; "141 files already formatted" |
| 3 | Full checks | Frontend typecheck, tests, build | PASS | **225 passed** (25 files; 223 before), build OK. Follow-up round: **307 passed** (29 files; 247 in 28 files at `e81c756`), build OK |
| 4 | Full checks | Dataset regenerates byte for byte | PASS | `python3 -m matchmind.simulator.cli dataset --out <tmp>` then `diff -r <tmp> data/matches`: no output (6 files) |
| 5 | Security | REST rate limits (moment, recap, ask, POST, export) | PASS | [rest_probe.json](evidence/rest_probe.json): recap 30 of 100 got 200 and the rest 429; speed 10 of 50; export 2 of 30 |
| 6 | Security | Rate limits on the other read routes | FAIL, fixed (LC-1) | Before: 1000 of 1000 got 200 from one address. After: a burst of 60, then 429 ([bystander-after.jsonl](evidence/bystander-after.jsonl)) |
| 7 | Security | WebSocket: per-IP cap, size cap, unknown action, origin | PASS | [ws_probe.json](evidence/ws_probe.json): 20 of 25 accepted from one IP; a 5 KB message is refused in plain words; a foreign origin gets 403 |
| 8 | Security | MCP: rate limit, batches, Host and Origin | PASS | [inject_probe.json](evidence/inject_probe.json): batch 400, unknown Host 421, unknown Origin 403 |
| 9 | Security | Ask box injection (override, markup, SQL, bidi) | PASS | [inject_probe.json](evidence/inject_probe.json): every case refused in one plain sentence; `text/plain` 415; 10 KB body 413; unknown field 400 |
| 10 | Security | Query parameter injection and path traversal | PASS | Every case 400 or 404 in plain words; `/docs` and `/openapi.json` 404 |
| 11 | Security | Feed ingest with hostile files | PASS | NaN, off-pitch, formula, clock running backwards, 400,000 rows and markup in a name: all `REJECTED` with a reason |
| 12 | Security | Uploads | N/A | There is no upload route |
| 13 | Security | Secrets in the tree and in all 166 commits | PASS | Secret-pattern grep over `git log --all -p`: 0 hits. The only tree hits are a dummy `InstrumentationKey=00000000-0000` in a test and `sha512` lock-file integrity strings |
| 14 | Security | `.env.example` holds placeholders only | PASS | `backend/.env.example` |
| 15 | Security | Client bundle carries no secrets or server settings | PASS | grep of `dist/assets/*.js`: 0 hits; only `VITE_API_URL` and `BASE_URL` are read |
| 16 | Security | Page headers: CSP, `frame-ancestors`, nosniff, Referrer-Policy | PASS | [headers.txt](evidence/headers.txt) |
| 17 | Security | HSTS when the public origin is https | PASS | `test_api.py::test_hsts_only_when_the_public_origin_is_https` |
| 18 | Security | `Cache-Control: no-store` on `/api` | PASS | [headers.txt](evidence/headers.txt); hashed assets are `immutable` |
| 19 | Security | Logs hold no question text | PASS | The canary question and the injection strings: 0 matches in the server log |
| 20 | Security | Backend dependency vulnerabilities | PASS | `pip-audit` on the image's 85 packages: none found |
| 21 | Security | npm audit, production | PASS | 0 vulnerabilities |
| 22 | Security | npm audit, full | FAIL (LC-7) | 13 advisories in dev tools only. Still 13: the upgrades are not drop-in (LC-7). The dev server now listens on `localhost` only, and CI runs `npm audit --omit=dev` (0 found) |
| 23 | Security | Licences | FAIL, fixed (LC-8) | With the stricter list: exit 0 on both sides |
| 24 | Security | Licence inventory | PASS (added) | [licences-backend.csv](licences-backend.csv), [licences-frontend.csv](licences-frontend.csv) |
| 25 | Accessibility | Keyboard-only walk, visible focus | PASS | 45 Tab stops, every one with a visible outline |
| 26 | Accessibility | Modal focus trap, Escape, focus return | PASS | Focus stayed inside the recap modal for 25 of 25 Tabs; Escape closed it and focus went back to its button |
| 27 | Accessibility | Screen-reader names | PASS | [aria-studio.yaml](evidence/aria-studio.yaml): 0 unnamed buttons or links |
| 28 | Accessibility | Colour contrast (axe 4.10.2, WCAG 2.2 AA) | FAIL, fixed (LC-4) | Before: `color-contrast` on every view, 2-7 elements each. After: 0 on all six views at 1440 and 375 px ([axe-after.json](evidence/axe-after.json), [axe-after-demo.json](evidence/axe-after-demo.json)); `frontend/src/lib/contrast.test.ts` checks every theme token pair |
| 29 | Accessibility | Other axe rules | FAIL, fixed (LC-6) | Before: landmarks, `aria-hidden-focus`, heading order, scrollable regions ([axe-before-lc-polish.json](evidence/axe-before-lc-polish.json)). After: 0 violations of any impact on every view at 1440 and 375 px, and with the recap and About dialogs open ([lc-polish-extra-checks.json](evidence/lc-polish-extra-checks.json)) |
| 30 | Accessibility | 200% zoom at 1280 px wide | FAIL, fixed (LC-3) | Before: [zoom200-1280-studio.png](shots/zoom200-1280-studio.png). After: [header-after.json](evidence/header-after.json) |
| 31 | Accessibility | Narrow layouts, no sideways scroll | PASS | Six views at 360, 390, 640, 768 and 1440 px |
| 32 | Accessibility | Tap targets at 375 px | FAIL, fixed (LC-5) | Before: pitch player markers 14-23 px. After, on a touch screen: every marker 44 x 44 px on the studio and player-focus pitches; with a mouse they keep the small area ([lc-polish-extra-checks.json](evidence/lc-polish-extra-checks.json), [lc5-touch-375-follow.png](shots/lc5-touch-375-follow.png)). The overlay's pitch backdrop has no markers to tap |
| 33 | Backups | Database backup | N/A | There is no database |
| 34 | Backups | Restore path for the state that exists | PASS | Redeploy the image by commit sha |
| 35 | Email | Deliverability | N/A | No email in the code (grep) |
| 36 | Failure handling | Backend killed mid-session, then back | FAIL, fixed (LC-2) | Before: [before-fix-failure-3-server-back.png](shots/before-fix-failure-3-server-back.png). After: [after-fix-failure-3-server-back.png](shots/after-fix-failure-3-server-back.png) |
| 37 | Failure handling | Network off on first load | PASS | Offline demo with the hint "The match server is not reachable…" |
| 38 | Failure handling | `?live=1` with the server unreachable | PASS (LC-15 fixed) | "Connecting…" badge and placeholders; after 15 s one sentence with a "Try now" button ([lc15-outage-17s.png](shots/lc15-outage-17s.png)) |
| 39 | Failure handling | Offline demo | PASS | "Offline demo" badge |
| 40 | Failure handling | Ask failing (500, network error) | PASS | One plain alert |
| 41 | Failure handling | AI on, provider unreachable (`.invalid` host) | PASS | Cards fall back to templates with `fallback_reason: circuit_open` |
| 42 | Failure handling | Event Hubs source unreachable (`.invalid` host) | PASS (LC-11 fixed) | Replays the bundled match and says so; `/api/source` now shows `state: "unavailable"`, `reason: "connect_failed"` after about 28 s, with no provider text ([source-unavailable.json](evidence/source-unavailable.json)) |
| 43 | Failure handling | No stack traces shown to users | PASS | No "Traceback" in any page; every API error is `{"detail": "plain words"}` |
| 44 | Monitoring | Health endpoint and container probes | PASS | `/api/health`; three probes in `main.bicep` |
| 45 | Monitoring | Crew health, source status, tracing | PASS | Tracing is built but off by default |
| 46 | Monitoring | Alerts, action group, availability test, budget | FAIL (LC-9) | None exist |
| 47 | Performance | Slow 3G at 375 x 812 | PASS | See "Performance on slow 3G" below |
| 48 | Performance | Bundle sizes | PASS | Main script 409 KB (127 KB gzip); views load lazily; the demo recording loads only in demo mode |
| 49 | Browsers | Chromium desktop 1440 x 900 | PASS | 0 console errors, no overflow |
| 50 | Browsers | iPhone size 390 x 844 (emulated) | PASS | Same |
| 51 | Browsers | Small Android 360 x 740 (emulated) | PASS | Same |
| 52 | Browsers | Tablet 768 x 1024 (emulated) | PASS | Same, after the LC-3 fix |
| 53 | Browsers | Safari, Firefox, real devices | N/A | Not installed; not tested |
| 54 | Legal / data | "Synthetic data only" | PASS | Names come from `teams.py`; ingest refuses real names |
| 55 | Legal / data | "No tracking" | PASS | CSP allows only this server; no analytics, cookies or beacons |
| 56 | Legal / data | "Read-aloud stays on the device" | PASS | `frontend/src/lib/speech.ts:35` uses only on-device voices |
| 57 | Legal / data | "Viewer choices stay in the browser" | PASS | Two `localStorage` keys, both read and written inside `try/catch` |
| 58 | Legal / data | Privacy notice and terms | FAIL (LC-12) | None exist; not edited, by instruction |
| 59 | Cost | Paid switches off by default | PASS | Bicep parameters and `deploy.yml` default to off |
| 60 | Cost | Capacity matches the connection cap | FAIL (LC-10) | 0.5 vCPU with a cap of 200 |
| 61 | Launch | Rollback path | PASS | Image tag per commit; `deployment/README.md` "Roll back". Not drilled |
| 62 | Launch | Off features labelled | PASS | UI labels and the Crew health panel |
| 63 | Launch | Contacts and incident plan | N/A, see LC-9 | Missing from `setup/owner-todo.md` |

## Security

**Rate limits held where they existed.** The paid-path GET bucket (30, 3/s), the POST bucket (10, 2/s), the export bucket, MCP's bucket and the WebSocket cap of 20 per IP all held against the live server.

**Eleven read routes had no limit (LC-1).** These were snapshot, players, bookmarks, stats, crew status, crew trace, metrics, languages, teams, auto-eventing and source.
- **Before:** with the server pinned to one core, one address keeping 100 requests in flight on the snapshot route raised a second viewer's REST p50 from 6 to 444 ms. WebSocket gaps grew from 410 ms to 1,152 ms.
- **After `1c3cae9`:** the same flood got 266 answers and 3,049 refusals. The bystander's p50 was 88 ms, and the WebSocket p99 gap was 306 ms, the same as with no flood (307 ms).
- Removing the cost of refusing requests altogether would need an edge rate limit, which is a paid add-on.

**Injection, secrets and headers:** see rows 9-19. `connect-src` allowed any WebSocket host (LC-14). Since `fb17874` it lists `'self'`, `MATCHMIND_PUBLIC_ORIGIN` and the allow-list, each with its `ws:`/`wss:` twin, and nothing else; in Chromium the page still opened its socket with 0 CSP violations ([csp-live.json](evidence/csp-live.json)).

**Dependencies.** The 13 npm advisories are all in dev tools and none ship in the image. They matter on developer machines when the dev server is reachable. `vite.config.ts` used to set `server.host: true`. Since `e8d780e` the dev and preview servers listen on `localhost` unless `PITCHPULSE_DEV_HOST` asks for another address (checked: Vite prints only the Local URL by default, and the Network URL only with the variable set).

**Licences.** Backend packages are MIT, BSD, Apache-2.0, PSF, MPL-2.0 (`certifi`) and CNRI (`regex`). Frontend production packages are MIT, ISC and OFL-1.1 (fonts). `make licence-check` checks whatever environment it runs in, so on a developer machine it can fail on a system package that is not ours. CI installs a clean environment, so CI is the reliable signal.

## Accessibility

Contrast failures on every view (LC-4); each needs 4.5:1. Fixed in `4bb19b3` through theme tokens and one shared helper (`frontend/src/lib/contrast.ts`), keeping the look:

| Text on background | Where | Before | After |
|---|---|---|---|
| White on brand red `#ff3b2f` | Active tab, red buttons, tags | 3.54:1 | White on the new `pp-pulseFill` token `#d0261c`: 5.28:1 |
| White on away orange `#f08a24` | Scoreboard | 2.51:1 | Dark ink `#0c0c0b` (the `night` token): 7.80:1 |
| Dark on home blue `#2f6fde` (`#2a5db6` when dimmed) | Shirt numbers, My match | 3.58:1 and 2.73:1 | White: 4.72:1; the unpicked club card is no longer dimmed with opacity |
| Cream on gold `#8b760b` | Lab heat map | 3.89:1 | Each cell picks the ink with the higher contrast: at least 4.5:1 at every shade (unit test) |
| Red `#ff3b2f` text on the raised panel | Labels | 4.50:1 (4.4989) | The `pulse` token is `#ff3e32`: 4.55:1 |

Text on a club colour now always takes the better of white and dark ink. The unit test covers every text token on every surface and ten kit colours.

LC-3 fix (`26f7b87`): the wordmark and the header speed buttons now appear from 1024 px; below that the speed buttons sit in the row under the tabs. `scripts/header_check.py` found no overlap at any width from 320 to 1440 px. At 320 px the clock label is clipped rather than overlapping.

## Backups and restore

There is no database and no stored user data. This is the state that exists:

| State | Where | Lost on restart? | How it comes back |
|---|---|---|---|
| Bundled matches, demo recording, built app | The image | No | Redeploy by commit sha |
| Match clock, cue sheet, cards, rate-limit buckets | Server memory, one replica | Yes: the match restarts from kick-off | Rebuilt on start, about 20 s |
| Viewer choices | The viewer's `localStorage` | No | Sent again to the server on every reconnect |
| Logs | Log Analytics, 30 days | No | Not needed for restore |

## Error and failure handling

What a viewer saw when the server was stopped and started again:
- **Before the fix:** the page fell back to the offline demo, whose recording lives on the same server, so the load failed. It showed "The match could not be loaded. Refresh to try again." and stayed stuck after the server returned.
- **After `f9c2d06`:** the page keeps retrying the live server, waiting 2, 4, 8 and then 10 s between attempts. It was back live about 30 s after the stop. A page that never reached a server still falls back to the demo.

## Monitoring and alerts

| Exists | Missing |
|---|---|
| Health endpoint and probes (but health does not check that the playback loop is advancing) | Alert rules and an action group |
| Crew health panel and `/api/crew/status` | An uptime test from outside |
| `/api/source` | A budget alert and a Log Analytics daily cap |
| Logs in Log Analytics; Application Insights built, off by default | Incident contacts |

## Performance on slow 3G

Chromium at 375 x 812 with 400 ms latency, 400 kbps and CPU slowed 4x:

| Mode | First paint | App shell | Match data on screen | First crew card | Transferred |
|---|---|---|---|---|---|
| Live server | 1.5 s | 3.9 s | 7.6 s | 7.7 s | 241 KB |
| Offline demo | 1.6 s | 3.9 s | 14.3 s | 14.4 s | 597 KB |

The page shows placeholders while it loads, never a blank wait.

## Cost and limits

Prices are approximate list prices, not verified; check them in the Azure pricing calculator.

| Resource | On by default? | Approximate monthly cost |
|---|---|---|
| Container App, 0.5 vCPU / 1 GiB, always on | Yes | About $30-40 |
| Event Hubs Basic | Yes | About $11 |
| Container Registry Basic | Yes | About $5 |
| Log Analytics | Yes | Per GB, with no daily cap |
| Foundry / `gpt-4o-mini` | No | $0 until switched on |
| Translator | No | $0 until switched on |
| Application Insights | No | $0 until switched on |

Capacity: 20 WebSockets per IP and 200 in total, on half a core (EC-9 measured that one replica tops out between 200 and 400 viewers on four cores).

## Launch-day readiness

- **Rollback:** use `az containerapp update --image <earlier sha>`, then also revert the commit on `main`, because the next deploy redeploys `main`'s head.
- **Off at launch:** paid AI, Translator, tracing, the Event Hubs source and Foundry agents. All are labelled.
- **First-week watch list:**
  1. Container restarts and memory.
  2. Viewer count against the cap of 200.
  3. 429 rates per route; raise `READ_BURST` if many viewers share one network address.
  4. Log ingestion volume.
  5. If AI is switched on: fallback and rejection rates, and the north-star count.
  6. CodeQL and Dependabot alerts.

## Findings

Severity as in the extreme-cases round: High means one anonymous caller can degrade the service for everyone, or a product promise breaks for all users.

| ID | Severity | Area | What happens | Status | Requirement |
|---|---|---|---|---|---|
| LC-1 | Medium | Rate limits | One address looping on an unlimited read route slowed every viewer (REST p50 6 to 444 ms) | **Fixed** `1c3cae9`; `backend/tests/test_launch_checks.py` | §4, §3.5 |
| LC-2 | High | Failure handling | After any restart, every live viewer was stuck until they refreshed | **Fixed** `f9c2d06`; `frontend/src/state/reconnect.test.ts` | §3.3, §3.4 |
| LC-3 | Medium | Layout / accessibility | Header "Full time" ran under the play button at 640-1000 px | **Fixed** `26f7b87`; `scripts/header_check.py` | §3.7, WCAG 1.4.10 |
| LC-4 | Medium | Contrast | Four colour pairs between 2.51:1 and 3.89:1 | **Fixed** `4bb19b3`; `frontend/src/lib/contrast.test.ts`; axe 0 | §3.7 |
| LC-5 | Low | Touch targets | Pitch player markers are 14-23 px | **Fixed** `4d2712b`; `Pitch2D.test.tsx`; 44 px measured | §3.7, WCAG 2.5.8 |
| LC-6 | Low | Accessibility | Landmarks, `aria-hidden-focus`, heading order, scroll tables | **Fixed** `b60d376`, `fc05c4d`; `App.test.tsx`, `BroadcastOverlay.test.tsx`, `RecapModal.test.tsx`; axe 0 | §3.7 |
| LC-7 | Medium | Dependencies | 13 dev-only npm advisories; dev server listens on all interfaces | **Partly fixed** `e8d780e`: dev server on `localhost`, CI audits shipped packages. Advisories open: vite 8 + vitest 5 + plugin-react 6 passed typecheck, 306 tests and the build in a scratch copy, but vitest 5 needs Node 22.12+ (CI and the image use Node 20), and tailwind 4 needs a new config format, so neither is drop-in | §4, §7 |
| LC-8 | Low | Licences | Check did not refuse unknown or non-commercial licences | **Fixed** `f0259a2` | §7 |
| LC-9 | Medium | Monitoring / cost | No alerts, budget, uptime test, log cap or incident contacts | Open: owner decision | §8, §2.3 |
| LC-10 | Medium | Capacity | Half a core with a cap of 200 (EC-9) | Open: owner decision | §8, §3.5 |
| LC-11 | Low | Monitoring | `/api/source` hides Event Hubs connection errors | **Fixed** `0fce286`: `state: "unavailable"`, `reason: "connect_failed"` (or `"stream_stopped"`), never provider text; `test_live_source.py` | §3.4 |
| LC-12 | Medium | Privacy | No privacy notice or terms; client IPs in logs for 30 days | Open: owner and legal | §4 |
| LC-13 | Medium | Brand | Most commit authors use an automation identity, not a team member's name | Open: owner decision before the repo goes public | §2.4 |
| LC-14 | Low | CSP | `connect-src` allows any WebSocket host | **Fixed** `fb17874`: configured origins and their `ws:`/`wss:` twins only; `test_api.py` | §4 |
| LC-15 | Low | UX | A long outage shows only a "Connecting…" badge, no sentence | **Fixed** `e15b12e`: after 15 s one sentence in en/es/fr/ar/ja and a "Try now" button; `reconnect.test.ts`, `App.test.tsx`; measured: none at 8 s, shown at 17 s, gone 1 s after the server was back | §3.4 |
| LC-16 | Low | Docs | Threat model says Event Hubs has no connection-string path; the publisher still accepts one | **Fixed** `610e562`: the publisher is keyless only too; docs agree; `test_live_source.py` | §4 |

By severity: High 1 (fixed), Medium 9 (3 fixed, 1 partly fixed, 5 open), Low 6 (all fixed). Open: LC-9, LC-10, LC-12 and LC-13 (owner decisions) and LC-7's dev-tool upgrades.

## Commands run

The commands in the summary table above, plus:

```
pip-audit -r evidence/image-reqs.txt --no-deps
npm audit --omit=dev
npm audit
pip-licenses --partial-match --fail-on="GPL;AGPL;SSPL;UNKNOWN;NonCommercial;CC-BY-NC;BUSL;Commons Clause"
npx license-checker --production --excludePrivatePackages --failOn "GPL;AGPL;SSPL;UNKNOWN;UNLICENSED;CC-BY-NC-4.0;BUSL-1.1"
```

and every script in `scripts/`. The follow-up round also ran `scripts/axe_run.py` (six views at 1440 and 375 px, live and `?demo=1`), `scripts/lc_polish_checks.py` (dialogs, marker sizes, outage notice) and `scripts/csp_live.py`.

Not run: Bicep, the Docker image build, any Azure deploy, Safari, Firefox and real devices.
