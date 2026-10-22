# PitchPulse

**Every broadcast has a crew. We built one.** PitchPulse, powered by the
Matchmind engine, turns a stream of synthetic football events into explained,
personalised, multilingual match intelligence for studios, streaming
platforms and fans. It spots the moments that matter, proves why they matter
with numbers, tells the story for each viewer in their language, and can show
you exactly why he should have passed.

Built for the Microsoft x Premier League "Inside the Game" hackathon. All
clubs, players and matches are invented; no real teams, people or broadcaster
branding appear anywhere.

![Should he have passed? The open teammate, the passing lane and the chance he gave up](docs/images/should-he-have-passed.png)

## The five-stage pipeline

| Stage | What happens | Where |
|---|---|---|
| 1. Ingest | A synthetic match engine plays 90 minutes on a 105 x 68 m pitch and streams typed events | `backend/src/matchmind/simulator`, Azure Event Hubs |
| 2. Interpret | A deterministic stats engine scores every event: xG, pass difficulty, pressure, expected threat, sprints, momentum, and the better option a shooter ignored | `backend/src/matchmind/stats`, [docs/METRICS.md](docs/METRICS.md) |
| 3. Explain | A five-agent studio crew: Spotter, Analyst, Commentator, Fact-checker, Producer | `backend/src/matchmind/crew`, Microsoft Foundry |
| 4. Render | Broadcast overlays, a studio board, a replay that draws the missed pass on the pitch | `frontend/` |
| 5. Personalise | Casual, tactical, fantasy and player-spotlight voices, a favourite club, a single-metric focus, 13 languages | `frontend/`, Azure AI Translator |

The rule that holds it together: **every number on screen comes from the stats
engine, never from a model.** The Fact-checker rejects any generated sentence
that uses a number (in digits or in words) the moment's facts do not contain,
and a rejected sentence is never shown.

## Microsoft services, feature by feature

Status labels are honest: **Running** means it works in this repo today with
no cloud account; **Built, off until deployed** means the code, tests and
infrastructure are done and it switches on with the owner's Azure
subscription; **Planned** means not built.

| Judging area | PitchPulse feature | Microsoft service | Status |
|---|---|---|---|
| Analyze match events in real time | Simulator streams each event, partitioned by match | Azure Event Hubs (keyless, local auth off) | Built, off until deployed |
| | Stats engine and crew react to each event as it arrives over a WebSocket | Azure Container Apps | Running locally; Container Apps built |
| | Live xG race, pressure by five-minute window, sprint leaders over the event stream | Microsoft Fabric Real-Time Intelligence (Eventhouse, KQL) | Queries and mappings built, not connected yet |
| Generate stories, highlights and recaps | Commentator voices each moment; a full-time recap per audience and language | Azure OpenAI `gpt-4o-mini` on a Microsoft Foundry resource | Built, off until deployed (templates run today) |
| Explain key moments and tactical patterns | Analyst explains why a moment matters with evidence rows; "Should he have passed?" is detected, measured and drawn | Microsoft Foundry agents, stats engine | Running (templates); model mode built |
| Expand datasets for AI and analytics | Generate any number of new seeded matches; export a star schema and a labelled shot and pass decision set | Microsoft Fabric Lakehouse (Parquet to Delta) | Export running; Fabric load built, not connected yet |
| | 7,260-record evaluation set in Azure AI Evaluation format, scored locally | Microsoft Foundry evaluations | Running locally; Foundry evaluators documented |
| Insights for fans around the world | Five hand-written studio languages (English, Spanish, French, Arabic right-to-left, Japanese) | | Running |
| | Eight world languages (Portuguese, German, Hindi, Chinese, Kiswahili, Indonesian, Turkish, Korean), numbers and names protected, fact-checked again after translation | Azure AI Translator (keyless) | Built, off until deployed (shown in English and labelled) |
| Personalised experiences for studios, platforms and fans | Broadcast overlay, studio board, fan vs analyst split, player focus, "My match" | Azure Container Apps | Running locally |
| Trustworthy AI | Agent traces with GenAI semantic conventions, no text or viewer data | Application Insights, Foundry tracing | Built, off until deployed |
| | Agent cards for all five agents, generated from the code | Microsoft Foundry | Running (`foundry/agents/`); not registered in Foundry Agent Service |
| Engineering | CI with tests, secret scanning, licence check, Bicep lint, container smoke test; CodeQL; Dependabot; code review on every PR | GitHub Actions, GitHub code scanning, GitHub Copilot code review | Running |
| | One-click deploy with what-if, OIDC sign-in, no stored secrets | GitHub Actions, Azure Bicep, Microsoft Entra ID | Built, needs the owner's subscription |

No service key exists anywhere: every Azure call signs in with Microsoft
Entra ID through managed identities, and every key-based login is switched off
on the resources themselves.

## The studio crew

| Agent | Job | Hands off |
|---|---|---|
| Spotter | Finds moments worth telling in the event stream and attaches the only numbers anyone may use | `Moment` |
| Analyst | Explains why the moment matters, with evidence rows | `Explanation` |
| Commentator | Voices it for one audience in one language | `Narrative` |
| Fact-checker | Rejects any number or name not backed by the moment's facts, including after translation | `FactCheck` |
| Producer | Picks the overlay slot, timing and priority for each viewer | `OverlayCard` |

Each model step has a timeout, one repair retry on a schema mismatch, a
circuit breaker and a process-wide budget. When any of them trips, the crew
falls back to its localised templates and says so on the card
(`fallback_reason`), so the broadcast never breaks. Hand-offs are pydantic
models; the agent cards in `foundry/agents/` are generated from them
(`matchmind-foundry export`). See [docs/FOUNDRY.md](docs/FOUNDRY.md).

Evaluation over every moment of the five bundled matches, all personas and
studio languages ([docs/EVALUATION.md](docs/EVALUATION.md)):

| Check | Pass rate |
|---|---|
| Numbers grounded in facts | 100% |
| Strict grounding (number words too) | 98.2% |
| Length limits | 100% |
| Persona vocabulary | 99.2% |
| Language | 100% |

## Run it

Needs Python 3.12 and Node 20. No cloud account and no keys.

```bash
# Backend: API, WebSocket and the crew in template mode
cd backend
pip install -e ".[dev]"
matchmind-api                      # http://127.0.0.1:8000

# Frontend, in another terminal
cd frontend
npm ci
VITE_API_URL=http://127.0.0.1:8000 npm run dev   # http://localhost:3000
```

Without a backend the frontend plays an offline demo recording of the same
match.

Other tools:

```bash
matchmind-sim dataset --out data/matches            # regenerate the bundled matches
matchmind-lakehouse export --seeds 20 --with-labels # Fabric-ready tables plus 20 new matches
matchmind-foundry eval-dataset && matchmind-foundry eval   # evaluation set and scorecard
matchmind-autoevent score data/matches/*.jsonl      # events detected from synthetic tracking
```

Checks: `make check` runs what CI runs.

## Deploy to Azure

`deployment/azure_bicep/main.bicep` creates one resource group: Container
Apps, Event Hubs, a Microsoft Foundry resource and project, Azure AI
Translator, Application Insights, Container Registry and Log Analytics, with
two managed identities holding only the roles they need. Paid AI is off by
default; each paid service has its own switch. See
[deployment/README.md](deployment/README.md) and
[setup/owner-todo.md](setup/owner-todo.md).

## Repository map

| Path | What |
|---|---|
| `backend/src/matchmind/simulator` | Synthetic match engine, invented clubs and players, Event Hubs publisher |
| `backend/src/matchmind/stats` | Deterministic metrics, chance model, better option, rolling match state |
| `backend/src/matchmind/crew` | The five agents, fact-checker, language packs, Azure OpenAI and Translator clients, tracing |
| `backend/src/matchmind/api` | FastAPI REST and WebSocket session |
| `backend/src/matchmind/analytics` | Lakehouse export and decision dataset |
| `backend/src/matchmind/foundry` | Agent cards and evaluation |
| `backend/src/matchmind/autoevent` | Events detected from synthetic tracking, scored against the truth |
| `frontend/` | React broadcast, studio and fan app |
| `analytics/fabric/` | Lakehouse notebook and Eventhouse KQL |
| `deployment/` | Bicep, Dockerfile, deploy notes |
| `docs/` | API contract, metrics, languages, analytics, Foundry, evaluation |

## How we work

One feature per pull request. Every pull request runs the full test suite,
secret scanning, CodeQL, the licence check and a container smoke test, gets
a GitHub Copilot code review, and gets an independent security review before
merge. Every dependency allows
commercial use.

## Licence

MIT.
