# PitchPulse: build plan from here

PitchPulse (web app and studio screens) runs on the **Matchmind engine**
(simulator, stats, AI studio crew). Theme: **"Your AI studio crew"**: a
spotter, analyst, commentator, producer and fact-checker built as agents, which
turn one synthetic match into a personalised, multilingual studio show.
Signature feature: **"Should he have passed?"**.

Deadline: submissions close **27 Oct 2026**. Target: submit on 26 Oct.

Status labels: **Done** (built and tested), **Started** (partly built),
**To do**.

---

## 1. Engine: simulator and event schema (Done)

`backend/src/matchmind/schema`, `backend/src/matchmind/simulator`, 24 tests.

- Fictional clubs Northbridge FC (NBR) and Harbour City (HCY); invented players.
- Possession-chain match engine, seeded and reproducible.
- Shots carry a `freeze_frame` (everyone in the final 35 m).
- Runs in behind carry `tracking` (runner, carrier, back line, keeper every
  0.5 s for 3 s).
- Demo script `scripts/demo.yaml`: NBR 2-0 up, red card 52', HCY pressure
  spell 60-75', HCY win 3-2 in stoppage time; missed square balls at 34' and
  78'; unfound run at 61:12.
- CLI `matchmind-sim generate | live | dataset | schema`; Event Hubs sink with
  Entra ID auth.
- Open dataset in `backend/data/matches` (5 matches, reproducible byte for byte).

## 2. Stats engine (Started)

Done: `stats/models.py` (all output models), `stats/metrics.py` (pass
difficulty, progressive pass, chance quality, lane/pass-success model, zone).
Chance quality is calibrated: penalty spot 0.25, 20 m central 0.065, 6 m
central 0.56, tight angle 0.11.

To do:

1. `stats/better_option.py`
   - `analyse_shot(shot, home_id) -> BetterOption | None`. Convert the freeze
     frame to the shooter's attacking frame (`metrics.to_attacking`). Shot
     value = `chance_quality(shooter, blockers_in_cone, keeper_on_line,
     header)`. For each teammate (not keeper, onside: `u <= max(ball_u,
     second-last opponent u)`, nearest opponent >= 3 m): value =
     `pass_success_probability(shooter, mate, opponents)[0] *
     chance_quality(mate, blockers from mate)`. Flag when best value >= shot
     value + 0.10 **and** >= 1.8 x shot value.
   - `analyse_run(run, home_id) -> UnfoundRun | None`. Per frame: line =
     second-last defender u (keeper included). Pass is "on" at the first frame
     where the runner is onside (u <= line + 0.3) and 1.0 s later is >= 1.5 m
     beyond the line, with a clear lane (`pass_success_probability >= 0.6`).
     Projected chance = `chance_quality` at the runner's last frame with
     blockers between him and goal; `one_on_one` when there are none. Report
     only when not found and projected chance >= 0.2.
   - Tests: the demo's 34' and 78' shots flag their scripted teammate
     (`better_option:<id>` label) with times_better >= 2; the 61:12 run is
     flagged with pass_on_at_s <= 1.5 and one_on_one; across the 4 unscripted
     matches, fewer than 4 false flags per match.
2. `stats/state.py`: `StatsEngine.process(event) -> EventMetrics`, plus
   `snapshot() -> MatchStateSnapshot` and `players() -> dict[str,
   PlayerStats]`. Rolling 5-minute window of match clock per team: possession
   % (passes), field tilt % (final-third passes), pressure index 0-100 =
   `100 * (1 - exp(-(ft_passes + 2*box_entries + 4*shots + 20*xg) / 30))`,
   momentum = EMA of (pressure_home - pressure_away), control/chaos from
   average passes per possession and turnovers per minute, tempo label, events
   per minute. Player stats: touches, passes, accuracy, key passes (pass
   followed by a shot from the receiver in the same possession), xG, xA,
   goals, assists, tackles, interceptions, top speed, sprints (>8 m/s), carry
   distance.
   - Tests: the pressure index for HCY is higher in 60-75' than in 45-60' of
     the demo; score and xG totals match a recount; same input gives the same
     output.
3. `docs/METRICS.md`: every formula above in plain words.

## 3. AI studio crew (To do)

`backend/src/matchmind/crew/`. Contracts are pydantic models; every hand-off is
a typed object logged to an insight log with its source event ids (the
explainability trail).

| Agent | Input | Output | How |
|---|---|---|---|
| Spotter | event + EventMetrics + snapshot | `Moment` (kind, clock, team, players, `facts` dict, source_event_ids, priority) | Rule-based on purpose (reproducible): goal, card, milestone, shot cq >= 0.3, better_option, unfound run, momentum swing (5-min change >= 40 and >= 1.5 SD), pressure spell (index >= 70 for 3 min) |
| Analyst | Moment | `Explanation` (why, evidence list of {label, value, unit, source_event_id}, tactical tag) | LLM when enabled, else template |
| Commentator | Moment + Explanation + audience + lang | `Narrative` (headline <= 8 words, body <= 2 sentences) | LLM when enabled, else templates for en/es/fr/ar/ja |
| Producer | Narratives + viewer profile | `OverlayCard` list (slot, priority, show_at, duration, audience, lang) | Deterministic: de-duplicate, max one lower-third per 8 s, favourite player boost, persona filter |
| Fact-checker | any text + Moment.facts | pass / reject with reason | Every number in the text must appear in facts (rounding tolerance); length limits; banned names list (real clubs and players); optional Azure AI Content Safety |

Orchestrator `crew/crew.py`:
- Spotter -> Analyst -> Fact-checker -> Commentator (per audience x language)
  -> Fact-checker -> Producer.
- Each LLM step: 3 s timeout, one repair retry on schema failure, then the
  template fallback with `fallback_reason` recorded on the card.
- Circuit breaker per agent: 3 failures in a row opens it for 60 s.
- Trace per moment (agent, ms, status, fallback) exposed at
  `/api/crew/trace`.

LLM client `crew/llm.py`: `TemplateLLM` (default, free, offline) and
`AzureOpenAILLM` (openai SDK `AzureOpenAI` with
`azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential(),
"https://cognitiveservices.azure.com/.default")`, JSON response format).
Switched on only by `MATCHMIND_AI_ENABLED=true` after owner approval.
Microsoft Agent Framework: wrap the five agents as Agent Framework agents and
the chain as a workflow once the package is installed and tested locally;
until then the README must not claim it.

Prompt-injection rule: agents receive only typed facts generated by our own
engine, never free text from users; outputs are fixed-schema JSON.

Tests: crew in template mode produces cards for both "Should he have passed?"
moments in en and es; the fact-checker rejects "72% better" when facts say
3.1x; a fake LLM that times out triggers the template fallback and the trace
shows it; circuit breaker opens after 3 failures.

## 4. Match session and API (To do)

Replace the old `backend/api/main.py` (removed in this branch) with
`backend/src/matchmind/api/`:
- `session.py` (framework-free, unit-tested): load the demo match, play it on
  the match clock at 1x / 10x / 60x, pause, reset, **seek** to a clock time
  (replays stats from the start, crew only for moments after the seek point),
  **bookmarks** (Spotter moments over the whole match), recap.
- `view.py`: convert engine output to the payloads the existing frontend
  expects (`MatchEvent`, `MatchInsight`, `ControlChaosState`, `MatchRecap` in
  `frontend/src/types.ts`), plus new fields: `card` (overlay contract),
  `replay` (geometry for the better-option and unfound-run drawings),
  `produced_by` ("ai" or "template").
- `app.py` (FastAPI): keep the existing WebSocket `/ws/match` messages
  (`INITIAL_SNAPSHOT`, `MATCH_TICK`, `MATCH_RESET`, `PLAYBACK_CONTROL`,
  `PERSONA_CHANGED`) and REST routes; add `/api/match/seek`,
  `/api/match/bookmarks`, `/api/crew/status`, `/api/crew/trace`. CORS from
  `MATCHMIND_ALLOWED_ORIGINS` only (no `*` with credentials). Serve the built
  frontend from `/` when `static/` exists. Limit WebSocket message size and
  validate every action.
- Dependencies to add to `backend/pyproject.toml`: `fastapi`, `uvicorn[standard]`,
  and an `ai` extra with `openai` and `azure-identity`.

## 5. Frontend (To do)

`frontend/` is React 18 + Vite + Tailwind (built earlier).
- Team names, short names and colours from the API (remove "Manchester Blue",
  "North London Red", "MCI", "ARS" and the real player defaults).
- Replace brand-like colours `#38003c` and `#00ff87` with PitchPulse's own
  palette; remove "Official Premier League" wording and "PL STUDIO".
- Remove the "AUTO-EVENTING: ACTIVE (16ms)" badge (no vision model exists);
  replace it with an honest "AI crew: live / template mode" badge from
  `/api/crew/status`.
- `Pitch2D`: draw `replay` geometry: shooter, open teammate, dashed passing
  lane, defenders, "3.1x better chance" label; for unfound runs the runner's
  path, the back line and the through-ball lane.
- Speed pills 1x / 10x / 60x; "Jump to moment" list from bookmarks.
- Rename "Line Break" badge to "Progressive pass" (that is what we measure).
- Fantasy persona: use only stats we compute (xG, xA, key passes, shots).
- API/WebSocket base URL from `VITE_API_URL`, falling back to same origin.
- Check at phone and desktop width (CLAUDE.md section 3).

## 6. Deployment and CI (To do)

- `deployment/azure_bicep/main.bicep`: remove the `listKeys()` outputs (they
  leak keys into deployment history); set `disableLocalAuth: true` on
  OpenAI, Translator and Event Hubs; add Log Analytics, Application Insights,
  a Container Apps environment and app with a system-assigned managed
  identity, and role assignments (Cognitive Services OpenAI User, Event Hubs
  Data Sender). Validate with `az bicep build` and a what-if before any
  deploy (owner approves the deploy).
- `deployment/Dockerfile`: Python 3.12, install `backend/`, copy the built
  frontend to `static/`, run as a non-root user.
- `.github/workflows/ci.yml`: gitleaks (full history), backend ruff + pytest
  + dataset reproducibility, frontend `npm ci && npm run build`, Docker build,
  licence check.
- `Makefile` with `check` and `licence-check` (`pip-licenses
  --fail-on="GPL;AGPL;SSPL"` and `npx license-checker --production
  --failOn "GPL;AGPL;SSPL"`).

## 7. Docs and submission (To do)

- Rewrite `README.md` (current one describes the old build: real players,
  YOLOv8, everything "Active"). Architecture map with Live / Planned labels.
- `PROJECT_PLAN.md`: replace with this plan's summary.
- Demo video (< 2 min, no third-party trademarks or music), pitch text naming
  Microsoft Foundry, Azure OpenAI, Container Apps, Event Hubs.
- Independent security review before merge (CLAUDE.md section 2, rule 1).
