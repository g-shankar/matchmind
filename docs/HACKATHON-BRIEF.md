# PitchPulse against the "Inside the Game" brief

One page for judges: each requirement in the brief, what PitchPulse does for
it, how to see it, and where we fall short. Status labels match the
[README's feature matrix](DETAILS.md#feature-status).

## The brief, line by line

| Brief asks for | PitchPulse | See it | Status |
|---|---|---|---|
| **Ingest** synthetic match events as they happen | Seeded match engine (passes, carries, tackles, recoveries, shots, VAR reviews, metadata) streams each event over a WebSocket; JSONL/CSV feed ingest; Event Hubs publisher and consumer | `?demo=1#studio`; `matchmind-ingest validate ...` | Running; Event Hubs deployed (simulator publishes; the app replays the bundled match) |
| **Interpret** into statistics, patterns and context | Deterministic stats engine, 24 registered metrics with formulas: xG, xT, pass difficulty 0-100, momentum, control vs chaos, pressure spells, physical stats | `GET /api/metrics`; [METRICS.md](METRICS.md) | Running |
| **Explain** why a moment matters | Analyst evidence rows; "Should he have passed?" compares the open teammate's chance with the shot taken and draws the lane | `?t=2060&p=1&pause=1#studio` | Running |
| **Render** insights next to the match | Studio board, broadcast overlay, OBS/vMix capture, pitch replays, versioned cue sheet | `#studio`, `#overlay`, `?capture=1#overlay` | Running |
| **Personalise**: analyst vs fan, favourite club, player focus, focus metric | Four personas, club heart, player focus, My match, Fan vs Analyst split | `#split`, `#follow`, `#fan` | Running |
| Player identification, speed and distance alerts | Name tags on pitch and overlay; `speed_burst` and `distance_milestone` moments on fixed thresholds | `#studio` | Running (synthetic tracking) |
| Pass quality: distance, accuracy, difficulty | Distance, forward progress, completion, `pass_difficulty` 0-100 | [METRICS.md](METRICS.md) | Running |
| Ball and shot speed | `ball_speed_kmh`, `rocket_shot` at 100 km/h or more | [METRICS.md](METRICS.md) | Running |
| **Auto-eventing**: a model over an incoming feed generates pass and speed metrics without hand tagging | A tracking-feed detector: passes, shots, tackles and kick speeds detected from a 25 Hz position feed; a pixel path that runs on rendered video frames first | [AUTO-EVENTING.md](AUTO-EVENTING.md) | Simulated (synthetic), see gap 1 |
| Narratives, milestones, recaps | Commentator voices each moment per persona and language; half-time and full-time recaps | `GET /api/match/recap` | Running |
| Explainability: control vs chaos, pressure, rhythm | Control vs chaos score, five-minute pressure windows, momentum swings | `#studio` | Running |
| Data innovation: new synthetic datasets | Five bundled matches, seeded generator, dataset export (JSONL, CSV, tracking window) | `matchmind-sim dataset`, `GET /api/dataset` | Running |
| Multiple languages | Five studio languages including right-to-left Arabic; eight more through Azure AI Translator | Language menu | Running; Translator live on Azure |
| Runs on Azure | Bicep for Container Apps, Event Hubs, Microsoft Foundry, Translator, Application Insights; keyless; CI and one-command deploy | [deployment/README.md](../deployment/README.md) | Live on Azure Container Apps, see gap 3 |

## Where we fall short, and what we did about it

### Gap 1: auto-eventing reads tracking, not broadcast video

The brief imagines a model running over a video feed. PitchPulse's detector
reads **player and ball positions at 25 frames a second**, the feed an optical
tracking system produces from stadium cameras. That is the step after
computer vision, and it is where pass, shot, tackle and speed metrics come
from in practice. We present it as what it is: a **tracking-feed detector**.

To show the vision step too, the **pixel path** draws top-down frames from the
feed and recovers positions from the pixels alone (background model, colour
classes, blob tracking; numpy only, no trained model), then runs the same
detector. It works on rendered synthetic video, not broadcast footage. There
is no real-video model anywhere in PitchPulse, and the benchmark is circular by
construction because the feed and the truth come from the same simulator
([AUTO-EVENTING.md](AUTO-EVENTING.md)).

### Gap 2: model calls are capped, so the crew falls back to templates

The deployed crew runs on Azure OpenAI (`gpt-5-mini`, keyless). Every card is
still checked by the fact-checker, and **template mode is the hallucination
guard**: if the model is off, slow, wrong or over its spending cap, the crew
uses the fact-checked template for that card and says so on the card and in the
Crew health panel ([ADR 0002](adr/0002-templates-first-ai-off-by-default.md),
[TRUST.md](TRUST.md)). The cap (`MATCHMIND_AI_BUDGET`, default 300 calls per
process) is deliberate cost control, so a long-running replica shows more
template cards than a fresh one. Local runs use templates by default
(`MATCHMIND_AI_ENABLED=false`).

### Gap 3: one replica, no consumer on Event Hubs

PitchPulse is live on Azure Container Apps (Sweden Central) with Azure OpenAI,
Azure AI Translator and Event Hubs, deployed from Bicep with managed identity
and no keys. It runs a single replica with in-memory state, and the app replays
the bundled demo match rather than consuming Event Hubs, which the simulator
job publishes to. Redeploy or roll back from Azure Cloud Shell:

```bash
git clone https://github.com/g-shankar/matchmind && cd matchmind
deployment/deploy.sh            # preview: what would be created, nothing is
deployment/deploy.sh --apply    # create it and print the preview URL
```

Details and roll-back: [deployment/README.md](../deployment/README.md).

## Beyond the brief

**In the product and the demo** (they serve the brief's personalisation and
trust goals, so they stay): Ask the studio, spoiler-safe catch-up, the trust
layer ("Show your working", claim audit), Crew health, VAR retractions.

**Future enterprise extensions** (built and tested, not needed for the brief,
and not in the demo):

| Extension | What it is for | Doc |
|---|---|---|
| MCP server | Read-only match tools for a broadcaster's own assistants and tooling | [MCP.md](MCP.md) |
| Microsoft Fabric Lakehouse and Eventhouse | Post-match analytics: star schema, decision dataset, KQL | [ANALYTICS.md](ANALYTICS.md) |
| Microsoft Agent Framework orchestrator | The same crew as typed workflows; identical cards to the in-process crew, off by default | [FOUNDRY.md](FOUNDRY.md), [ADR 0004](adr/0004-agent-framework-parity.md) |
| Evaluation set (6,780 records) | Regression scoring of the crew before a change ships, and Foundry cloud evaluators later | [EVALUATION.md](EVALUATION.md) |

The core pipeline does not depend on any of them: each sits behind its own
entry point and can be left out of a deployment.
