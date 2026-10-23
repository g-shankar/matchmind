# Architecture and system map

PitchPulse is one Python service (the Matchmind engine plus a FastAPI app) and
one React web app. Everything runs offline by default; each Azure service is a
switch the owner turns on with their own subscription.

Labels used on every component below:

| Label | Meaning |
|---|---|
| **Live** | Runs in this repository today with no cloud account |
| **Built-off** | Code, tests and infrastructure exist; off until the owner deploys and switches it on. Tested against fakes, not against a live Azure resource |
| **Planned** | Not built |

Nothing is deployed yet (preview URL: not deployed yet, see
[BUILD-STATUS.md](BUILD-STATUS.md)).

## System map

```
                          TRUST BOUNDARY: the public internet (anyone, no sign-in)
 ┌─────────────────────────────────────────────────────────────────────────────────────┐
 │ Browser (React app)  [Live]                MCP clients  [Live]     OBS / vMix [Live] │
 │ #studio #overlay #split #follow #fan #lab   any MCP host, read-only  ?capture=1#overlay│
 │ offline demo (?demo=1) [Live]                                                        │
 └──────┬──────────────────────┬───────────────────────────┬───────────────────────────┘
        │ WebSocket /ws/match  │ REST /api/*  (no-store)    │ POST /mcp (stateless, JSON)
        ▼                      ▼                            ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────┐
 │ FastAPI app (matchmind.api)  [Live]   origin allow-list, per-IP rate limits, size    │
 │                                       caps, CSP + HSTS on pages, no-store on /api    │
 │   reads.py: one accessor per read, shared by REST and MCP                            │
 │                                                                                     │
 │   MatchSession (one shared match clock: play, pause, speed, seek, bookmarks)         │
 │     │                                                                               │
 │     ▼                                                                               │
 │   Stats engine (deterministic)  [Live] ──► facts (the only numbers anyone may say)   │
 │     │                                                                               │
 │     ▼                                                                               │
 │   Studio crew  [Live, template mode]                                                │
 │     Spotter ─► Analyst ─► Fact-checker ─► Commentator ─► Fact-checker ─► Producer    │
 │     (det.)     (tmpl|model) (det.)        (tmpl|model)   (det.)          (det.)      │
 │                                                     └─► Recap (tmpl|model)           │
 │                                                     └─► Translator (Built-off)       │
 │     orchestrator: in-process [Live] | Microsoft Agent Framework [Built-off, free]    │
 │                                                                                     │
 │   Trust layer [Live]: claims, parity, /audit      Cue compiler [Live]: cue sheet v1.0│
 │   Ask the studio [Live]: guard ─► rules ─► (model intent: Built-off) ─► templates    │
 │   Metric registry, basic stats, physical stats from synthetic tracking [Live]        │
 │   Auto-eventing from synthetic tracking + pixel path [Live, benchmark]               │
 │   Dataset export /api/dataset [Live]                                                │
 └───────┬───────────────────────────┬───────────────────────────────┬─────────────────┘
         │ match source              │ model calls (paid)            │ telemetry
         ▼                           ▼                               ▼
 ┌──────────────────────┐   ┌──────────────────────────────────┐   ┌───────────────────┐
 │ File: bundled JSONL, │   │ Azure OpenAI gpt-4o-mini on a    │   │ OpenTelemetry      │
 │ own JSONL/CSV feed   │   │ Microsoft Foundry resource       │   │ spans [Live, no-op]│
 │ (matchmind-ingest)   │   │ [Built-off]                      │   │ App Insights +     │
 │ [Live]               │   │ Foundry Agent Service agents     │   │ Foundry Tracing    │
 │ Azure Event Hubs     │   │ [Built-off]                      │   │ [Built-off]        │
 │ consumer [Built-off] │   │ Azure AI Translator [Built-off]  │   └───────────────────┘
 └──────────▲───────────┘   └──────────────────────────────────┘
            │ publish (keyless)
 ┌──────────┴───────────┐   ┌──────────────────────────────────┐   ┌───────────────────┐
 │ Simulator            │   │ Lakehouse export (Parquet/CSV)   │   │ Azure AI Speech    │
 │ matchmind-sim [Live] │   │ [Live]; Fabric notebook + KQL    │   │ voices [Planned]   │
 │ Event Hubs publisher │   │ [Built-off, not run in Fabric]   │   │ Real video input   │
 │ + Container Apps job │   │ Live enriched stream [Planned]   │   │ [Planned]          │
 │ [Built-off]          │   └──────────────────────────────────┘   └───────────────────┘
 └──────────────────────┘
```

Hosting: Azure Container Apps (one replica, the match session is in memory),
Container Registry, Log Analytics, two user-assigned managed identities, all in
`deployment/azure_bicep/main.bicep`. **Built-off**: the template builds and
lints in CI; it has not been deployed.

## Components

| Component | Code | Label | Notes |
|---|---|---|---|
| Event schema | `backend/src/matchmind/schema` | Live | JSON Schema in `backend/schema/event.schema.json` |
| Synthetic match engine | `simulator/` | Live | Seeded, byte-reproducible; invented clubs and players |
| Event Hubs publisher | `simulator/publisher.py` | Built-off | Keyless; Container Apps job `caj-pitchpulse-sim` |
| Feed ingest (JSONL, CSV + mapping, roster) | `ingest/` | Live | Strict validation; no upload endpoint by design |
| Event Hubs consumer | `ingest/eventhubs.py`, `ingest/stream.py` | Built-off | Tested against a fake consumer; not run against a live namespace |
| Stats engine | `stats/` | Live | Deterministic; formulas in [METRICS.md](METRICS.md) |
| Metric registry | `stats/registry.py`, `GET /api/metrics` | Live | 24 metrics with formula, units, quality flag; 5 listed as not computed |
| Physical stats | `stats/physical.py` | Live | Estimated from synthetic tracking, labelled as such |
| Studio crew | `crew/` | Live (template mode) | Model steps Built-off |
| Trust layer | `crew/fact_checker.py`, `claims.py`, `audit.py` | Live | [TRUST.md](TRUST.md) |
| Club heart, personas, catch-up | `crew/club_heart.py`, `producer.py`, `spoilers.py` | Live | [PERSONALISATION.md](PERSONALISATION.md) |
| Cue sheet | `crew/cues.py`, `backend/schema/cue.schema.json` | Live | [CUE-SHEET.md](CUE-SHEET.md) |
| Ask the studio | `ask/` | Live (rules + templates) | Model intent Built-off; [ASK.md](ASK.md) |
| MCP server | `mcp/` | Live (future enterprise extension, not in the demo) | 15 read-only tools; [MCP.md](MCP.md) |
| Auto-eventing benchmark | `autoevent/` | Live | Tracking-feed detector on synthetic tracking, not video; [AUTO-EVENTING.md](AUTO-EVENTING.md) |
| Dataset export | `dataset/`, `GET /api/dataset*` | Live | [DATASET.md](DATASET.md) |
| Lakehouse export | `analytics/` | Live (future enterprise extension, not in the demo) | Fabric load Built-off, [ANALYTICS.md](ANALYTICS.md) |
| Foundry agent cards, evaluation | `foundry/`, `foundry/agents/*.yaml` | Live | Agent Service registration Built-off; [FOUNDRY.md](FOUNDRY.md) |
| Web app | `frontend/` | Live | Offline demo plays `frontend/public/demo/*.json` |
| Read-aloud | `frontend/src/lib/speech.ts` | Live, off by default | Browser voices only; Azure AI Speech Planned |

## Trust boundaries

| Boundary | What crosses it | Who is trusted | Controls (details in [THREAT-MODEL.md](THREAT-MODEL.md)) |
|---|---|---|---|
| Browser to API (REST) | Query strings, small JSON bodies | Nobody: no accounts, all data public and synthetic | Closed request models, size caps, per-IP token buckets keyed on the ingress's last `X-Forwarded-For` entry, `no-store`, CORS allow-list |
| Browser to WebSocket | `set_view`, playback actions | Nobody | Origin allow-list (Host never trusted), message size cap, per-IP connection cap, per-connection action limits, bounded send queue |
| MCP client to `/mcp` | JSON-RPC tool calls | Nobody | Read-only tools, closed inputs, Origin and Host checks, 16 KB bodies, no batches, own rate limit |
| Ask box | One free-text question | Nobody: treated as hostile | Guard, rule parser, fixed intents, templates, fact-check; text never logged |
| Feed to engine (file or Event Hubs) | Events from outside | The operator chooses the feed, but every value is still checked | `ingest/validate.py`: size, shape, clock, people, real names; scores always from the engine |
| App to Azure OpenAI / Foundry | Moment facts as JSON, never viewer text | Model output is untrusted | Fixed JSON schema, timeout, one repair retry, breaker, budget, fact-checker gate, template fallback |
| App to Azure AI Translator | English card text with protected spans | Output is untrusted | Protected numbers and names must round-trip; fact-checked again; English fallback |
| App to Azure (all) | Tokens | Managed identity only | No keys exist; local auth disabled on every resource |

## Data flows

1. **Match to screen.** Source (file or Event Hubs) -> `MatchSession` on one
   shared clock -> stats engine metrics per event -> Spotter moments with facts
   -> Analyst explanation -> Fact-checker -> Commentator per audience x language
   -> Fact-checker -> Producer card (slot, timing, priority) and cue compiler ->
   WebSocket `MATCH_TICK`, `CUES` -> browser and capture overlay.
2. **Evidence.** Card -> per-sentence `claims` (fact key, value, source event)
   -> `GET /api/match/moment/{id}/audit` -> "Show your working" drawer.
3. **Questions.** Ask box or MCP `ask_studio` -> guard -> intent -> engine
   snapshot as of the clock -> template -> fact-check -> answer with claims.
4. **Data out.** `GET /api/dataset/export`, `matchmind-sim export`,
   `matchmind-lakehouse export` -> JSONL, CSV, Parquet star schema -> (owner)
   Fabric Lakehouse.
5. **Traces.** Each crew step -> OpenTelemetry span (agent, timing, outcome;
   no text, no viewer data) -> no-op locally, Application Insights when
   deployed with observability on.

## Decisions

Architecture decisions are recorded in [adr/](adr/):

| ADR | Decision |
|---|---|
| [0001](adr/0001-deterministic-numbers-and-fact-checker.md) | Numbers come from a deterministic stats engine; a fact-checker gates every text |
| [0002](adr/0002-templates-first-ai-off-by-default.md) | Templates first; paid AI off by default |
| [0003](adr/0003-mcp-read-only-stateless.md) | MCP server is read-only and stateless |
| [0004](adr/0004-agent-framework-parity.md) | Microsoft Agent Framework orchestration must match the in-process crew exactly |
| [0005](adr/0005-auto-eventing-from-synthetic-tracking.md) | Auto-eventing from synthetic tracking, not video |
| [0006](adr/0006-one-shared-match-clock.md) | One shared match clock per server |
| [0007](adr/0007-cue-sheet-contract.md) | The cue sheet is a versioned output contract |
