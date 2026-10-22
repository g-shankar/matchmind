# First-user walkthrough: pre-launch test round, part 1

22 Oct 2026. Production build of the integration branch served locally by the backend (same layout as the container image) at `http://localhost:8800/`, bundled synthetic match MM-DEMO-001, paid AI off. The preview in Azure is not deployed yet, so this local production copy stood in for it. There is no database, sign-in, email or payment in this app, so no test inbox or test payment account was needed.

Testers were independent first-time users who saw only the screen (no source code, no docs). They ran one at a time, each finishing before the next started, in headless Chromium driven step by step with a screenshot after each action. Screenshots are in `round1/<tester>/` and `round2/<tester>/` (resized JPEGs; file names are `NN-step.jpg`).

## First success (from the code)

**A first-time visitor reaches a fact-checked explanation of a key match moment, in the audience and language they chose.** Concretely: a crew card or the "Should he have passed?" replay that explains *why* a moment mattered with numbers and evidence (every number from the stats engine, fact-check passed), after choosing who they are (Fan / Analyst / Stats scout) or a language.

## Before / after

| Tester | Round 1 (8819f9b) reached first success? | Clicks | Would come back | Round 2 (74ed870) reached? | Clicks | Would come back |
|---|---|---|---|---|---|---|
| Impatient skimmer (1440x900) | Yes | 2 (card visible at 0; the "Should he have passed?" chip dead-ended on an empty pitch) | Probably | Yes | 2 (first chip tried still dead-ended before 34:16 — fixed after round 2, R2-01) | Maybe |
| Skeptic (1440x900) | Yes | 4 (chip paused on empty pitch; had to find Play and scroll) | Yes | Yes | 2 | Yes |
| Phone user (375x812, slow 3G + 4x CPU) | Yes, after ~4 swipes | 1 tap + ~2700 px of scrolling; first content 12.8 s | **No** | Yes | 1 tap + one short swipe; first content 0.5-0.7 s | **Yes** |
| Breaker (1440x900) | Yes | 0-1 (server was stopped mid-run by another test process, not by the tester) | Yes | Yes | 0-1 | Yes |
| **Issues open after the round** | | **27** (9 major) | | | **14** (1 major) | |

After round 2 a second fix pass closed all 14 round-2 items (see below). A third tester round was not run; the round-2 fixes were checked by the builder in headless Chromium at 375x812 and 1440x900 (`fix-check-round2/`) and by an independent security review.

Measured on slow 3G (400 ms latency, 400 kbps, CPU 4x, 375x812):

| | Round 1 | Round 2 |
|---|---|---|
| First content on screen | 12.6-12.8 s | 0.5-1.6 s |
| Load event | 15.6 s | 7.8 s |
| First crew card readable | ~16-20 s, 2700 px down | 7.7-9 s, ~650 px down |
| Transferred | 585 KB | 143-241 KB |
| Sticky header on a phone | 373 px of 812 | 64 px |

## Round 1 issues, ranked (deduplicated by page spot, ordered by tester count)

| id | Spot | What happened | Testers | Severity | Status |
|---|---|---|---|---|---|
| R1-01 | Playback clock | New visitors landed mid-match or at full time; autoplay at 10x/60x moved cards while reading; Restart kept the old speed | 4 | Major | Fixed: 1x default, restart resets speed, idle rewind to kick-off after 5 min with no viewers, full-time banner (ADR 0008) |
| R1-02 / R1-21 | Jump-to-moment and "Should he have passed?" chips | Click paused on an empty pitch, scrolled the pitch out of view, card not shown, replay never opened; "Show your working" opened another card | 3 | Major | Fixed: pitch shows recent events, view stays on the pitch, the moment's card is highlighted, special moments open the replay |
| R1-03 | Header | Audience picker confused with the "Fan vs Analyst" tab | 2 | Minor | Fixed: "I'm a" pills, distinct from tabs |
| R1-04 | Fan vs Analyst | Opened on kick-off, nearly empty; dropdown overflowed on phone | 2 | Minor | Fixed |
| R1-05 | Phone header | Sticky header 46% of the screen | 1 | Major | Fixed (64 px) |
| R1-06 | Phone order | Crew cards 2700 px down | 1 | Major | Fixed |
| R1-07 | Tap targets | Many controls 32-36 px | 1 | Major | Fixed (44 px; last one in R2-07) |
| R1-08 | Slow 3G | 12.8 s to first content | 1 | Major | Fixed (code splitting, compression, loading shell) |
| R1-09 | Rate-limit messages | English toast on the Arabic page | 1 | Major | Fixed: coded errors, translated in all 5 languages |
| R1-10 | Recap numbers | Raw internal keys shown | 1 | Minor | Fixed |
| R1-11 | Tags | `#decision_making` | 1 | Minor | Fixed |
| R1-12 / R1-26 | Recap and replay modals | Esc did not close the replay; focus escaped; title off screen at 390 px | 2 | Major | Fixed: shared accessible modal |
| R1-13 | Ask box | Silent empty submit; long input got a generic refusal | 1 | Minor | Fixed |
| R1-14 | Arabic | Score and speed buttons mirrored | 2 | Minor | Partly: score and speeds fixed; the colon was already correct |
| R1-15 | Replay text | 0.2 vs 0.24 vs 0.238 | 1 | Minor | Fixed (R2-14 made decimals consistent) |
| R1-16 | Header claims | "LIVE ENGINE" on a synthetic replay; AI tagline with AI off | 1 | Minor | Fixed: "Synthetic replay" / "Live feed", honest tagline |
| R1-17 | Pass % | Two pass percentages side by side | 1 | Minor | Fixed |
| R1-18 | Studio | Crew-health jargon in the fan view | 1 | Minor | Fixed (technical section) |
| R1-19 | Phone tab bar | Tabs clipped, no cue | 1 | Minor | Fixed (scroll cue) |
| R1-20 | Jump list | Unlabelled upcoming chips, duplicates | 1 | Minor | Fixed |
| R1-22 | Back button | Left the app | 1 | Minor | Fixed for modals (Back closes them); Back from a fresh tab still leaves, as in any site |
| R1-23 | About | No about/who made it | 1 | Minor | Fixed (footer, then a header About button in round 2) |
| R1-24 | Pitch labels | Tooltip overlapped markers | 1 | Trivial | Fixed |
| R1-25 | Language list | 8 greyed "needs Azure AI Translator" options | 1 | Trivial | Left as is: honest labels |
| R1-27 | API docs | `/docs` public | 1 | Low | Fixed: off when the server serves the app |

## Round 2 issues

| id | Spot | What happened | Testers | Severity | Status |
|---|---|---|---|---|---|
| R2-01 | "Should he have passed?" chip | Dead end before 34:16 | 1 | Major | Fixed: says when it comes and offers "Jump to 34:16" |
| R2-02 | Jump list | Special replays buried | 2 | Minor-major | Fixed: "Key replays" row first |
| R2-03 | About | Only at the bottom of the feed | 1 | Minor-major | Fixed: About in the top bar |
| R2-04 | Ask | Provenance questions refused | 1 | Minor | Fixed: fixed-text "about" answer in 5 languages |
| R2-05 | Autoplay | Nothing said it was a replay playing on its own | 2 | Minor | Fixed: "Replay 1x" label and pause tooltip |
| R2-06 | Audience | No visible change | 1 | Minor | Fixed: "Now explaining for…" note, "Written for" label |
| R2-07 | Speed button | 36 px wide | 1 | Minor | Fixed |
| R2-08 | Jump list | Titles not in the chosen language | 1 | Minor | Fixed |
| R2-09 | 3G first screen | Header empty for ~8 s | 1 | Minor | Partly: "Loading match…" label and placeholder; the score needs the first snapshot |
| R2-10 | Spanish header | Pill wrapped | 1 | Trivial | Fixed |
| R2-11 | Ask counter | "1000 of 200" | 1 | Minor | Fixed |
| R2-12 | Ask in Arabic | xG question refused | 1 | Minor | Fixed (25 more phrasings tested) |
| R2-13 | Language box | Odd in Arabic | 1 | Minor | Fixed |
| R2-14 | Replay text | Rounding looked inconsistent | 1 | Trivial | Fixed |

## Written down only: pricing, terms, privacy (not changed, by instruction)

What exists: an "About this demo" section (synthetic data, invented clubs, template crew with paid AI off, made by the PitchPulse team as a hackathon entry), the metric registry and benchmark under "Under the hood", honest "off / coming soon" labels.

What is missing: a privacy notice (even "no accounts, no personal data; viewer choices stay in your browser"), terms of use, a licence statement for the dataset downloads and MCP access, a pricing or "free demo" statement, a named contact, and a note on whether Ask questions are logged (they are not; only their length is) and how data would be handled once paid AI or translation is switched on.

## What held up across both rounds

No XSS from any injected text, no console errors, no stack traces; the ask box stayed on task (off-topic, "ignore your rules", wrapped requests and invented names refused in plain words); two tabs stay independent; downloads come down intact; catch-up mode hides the score in Ask; triple clicks never duplicated modals or broke playback.
