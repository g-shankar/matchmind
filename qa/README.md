# Pre-launch test round: summary

22 Oct 2026, PR #8 branch. Everything ran locally against a production build of the branch served by the backend (the Azure preview is not deployed yet, so a local production copy stood in for it), with the bundled synthetic match, fictional data only, paid AI off and no paid service, email or payment touched.

## Verdict: **Ready with conditions**

The app does what it promises for a first-time visitor on desktop and on a slow phone, held up under load and hostile input, and every Critical/High/Medium finding that code could fix is fixed with a test. It is not "ready" outright because a few things only the owner can decide are still open (sign-off list below), and Safari, Firefox and real devices were not tested (only Chromium is available here).

| Part | Report | Result |
|---|---|---|
| 1. First-user walkthrough | [first-users/report.md](first-users/report.md) | 2 rounds × 4 testers. All 8 reached first success. Phone tester went from "would not come back" to "would". Issues 27 → 14 → all fixed except 2 partly |
| 2. Extreme cases | [extreme-cases/report.md](extreme-cases/report.md) | 12 findings (2 High, 4 Medium, 6 Low); both Highs and 6 others fixed with failing-then-passing tests; 4 left with reasons |
| 3. Launch checks | [launch-checks/report.md](launch-checks/report.md) | 63 checks; 1 High (stuck after a restart) and 8 others fixed; axe accessibility now 0 violations on every view at 1440 and 375 px |
| Security reviews | this file | 3 independent reviews of the round's changes (rounds 3-5): 0 Critical, 0 High; every Medium and Low fixed with tests |

Final checks on the branch head: backend `pytest -q` **1192 passed**, `ruff check .` and `ruff format --check .` clean; frontend `npm run typecheck`, `npm test` (**317 passed**), `npm run build` OK; dataset regenerates byte for byte. The interface is now fully translated in all five studio languages (English, Spanish, French, Arabic, Japanese), with a test that fails on any untranslated key.

## Findings, ranked

Only open items and the most serious fixed ones are listed; each report has the full table.

| id | Severity | Area | What happens | Status | Requirement |
|---|---|---|---|---|---|
| EC-1 | High | Volume | 200 viewers that stop reading could pin ~800 MB in a 1 GiB container | Fixed: shared send-queue budget, slow viewers dropped | CLAUDE.md §8, §3.5 |
| EC-2 | High | Shared clock | Pause/speed had no shared throttle; one address could stall the match for everyone | Fixed: shared 0.3 s throttle | §4 |
| LC-2 | High | Failure handling | After any server restart every live viewer stayed stuck until they refreshed | Fixed: reconnect with back-off | §3.3, §3.4 |
| R1-01/02 | Major (UX) | First visit | Visitors landed at full time; moment chips paused on an empty pitch | Fixed (ADR 0008) | §3 |
| R1-08 | Major (UX) | Slow 3G | 12.8 s to first content on a phone | Fixed: 0.5-1.6 s | §3.5 |
| SEC3 F2/F3/F7, SEC4 1-2 | Medium | Catch-up mode | The score could be read from shot end points, VAR events, kick-offs, numbering and the Lab tables | Fixed; residual timing tell documented | ASK.md, THREAT-MODEL.md |
| SEC3 F1/F4 | Medium | Ask the studio | Wrapped questions answered; one address could drain the AI budget | Fixed: wrapped refusals in 5 languages, own budget and per-client quota | §4 |
| EC-9 / LC-10 | Medium | Capacity | One replica tops out at 200-400 viewers on 4 cores; the template runs 0.5 vCPU with a 200-viewer cap | **Open: owner decision** (production change) | §8 |
| EC-10 | Medium | Shared clock | Anyone can pause the shared match for everyone (by design) | **Open**: needs an operator role or sign-in | ADR 0006/0008 |
| LC-9 | Medium | Monitoring / cost | No alerts, budget, uptime test, log cap or incident contacts in the Azure template | **Open: owner decision** (paid/production) | §8, §2.3 |
| LC-12 | Medium | Privacy | No privacy notice or terms; client IPs in access logs for 30 days | **Open: owner and legal** (not edited, by instruction) | §4 |
| LC-13 | Medium | Brand | Most commit authors in the history use an automation identity, not a team member's name | **Open: owner decision** before the repo goes public | §2.4 |
| LC-7 | Medium | Dev dependencies | 13 dev-only npm advisories; the fix needs Node 22 in CI and the image, and Tailwind 4 | Partly: dev server on localhost, CI audits production deps; upgrades left | §4, §7 |
| SEC5 1-3 | Low | Catch-up / Ask | Raw moment ids, an over-broad "about" answer, held cards lost between pumps | Fixed: opaque catch-up ids, narrower about answer, held cards kept across pumps | §4, §5.7 |
| EC-11 | Low | VAR | REST/MCP card for a ruled-out goal has no ruled-out marker | Left: bookmarks and audit carry it | — |
| R1-14 / R2-09 | Minor (UX) | Arabic colon / 3G header | Partly fixed | Partly | §3 |

## Skipped, and why

- **Payments, email, accounts, roles, uploads, database backups:** the app has none (checked in code). Isolation and roles were tested as per-viewer settings and shared-clock controls instead.
- **Safari, Firefox, WebKit, real phones, on-screen keyboard:** not installed in this environment; Chromium with device emulation was used.
- **Azure (preview deploy, Bicep build, Docker build, Event Hubs and Foundry against real Azure):** off limits without the owner's sign-off and no Azure account here. These paths were tested only against fakes and unreachable `.invalid` hosts.
- **A third tester round:** the round-2 fixes were checked in headless Chromium at phone and desktop size and by an independent security review, not by new testers.

## Sign-off list (owner)

1. **Capacity (EC-9/LC-10):** recommend 1 vCPU with the 200-viewer cap (or keep 0.5 vCPU and lower the cap to about 100). Production change.
2. **Alerts and budget (LC-9):** add an action group, restart/memory alerts, an availability test, a budget alert and a Log Analytics daily cap. Small monthly cost.
3. **Privacy notice and terms (LC-12):** a short notice ("no accounts, no personal data, viewer choices stay in your browser, access logs keep IP addresses for 30 days") and terms for the demo and dataset downloads.
4. **Commit identities (LC-13):** decide before the repository is made public.
5. **Deploy the preview:** the Azure Container Apps preview is not deployed yet; deploying is a production change.
6. **Paid AI and translation:** still off. Ask now has its own budget and per-client quota, so switching AI on no longer drains the crew's budget, but it remains a paid change.
7. **Dev tool upgrades (LC-7):** Node 22 in CI and the image, then vite 8 / vitest 5 / Tailwind 4.
8. **Accept the documented residuals:** catch-up mode keeps the score and goals off screen, but a determined analyst of the raw feed can still infer goals from timing; anyone can pause the shared match.
