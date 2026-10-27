<h1 align="center">PitchPulse</h1>

<p align="center"><strong>Every broadcast has a crew. We built one with AI.</strong><br>
Five agents turn synthetic football events into explained, personalised, multilingual match graphics, and every number on screen is checked against the stats engine.</p>

<p align="center">
<a href="https://github.com/g-shankar/matchmind/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/g-shankar/matchmind/actions/workflows/ci.yml/badge.svg"></a>
<a href="https://github.com/g-shankar/matchmind/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/g-shankar/matchmind/actions/workflows/codeql.yml/badge.svg"></a>
<a href="LICENSE"><img alt="Licence: MIT" src="https://img.shields.io/badge/licence-MIT-blue.svg"></a>
<img alt="Data: synthetic only" src="https://img.shields.io/badge/data-synthetic%20only-informational.svg">
</p>

**Live on Azure:** <https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/>
Jump to "Should he have passed?" at 34:16: [studio](https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/?t=2060&p=1&pause=1#studio) · Fan vs Analyst in [English](https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/?t=2060&p=1&pause=1&lang=en#split), [Spanish](https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/?t=2060&p=1&pause=1&lang=es#split), [Arabic](https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/?t=2060&p=1&pause=1&lang=ar#split)

**Demo video (112 s):** [docs/media/pitchpulse-demo.mp4](docs/media/pitchpulse-demo.mp4)

![Should he have passed? The open teammate, the passing lane and the chance he gave up](docs/images/should-he-have-passed.png)

## What it does

A synthetic match streams through five stages: **ingest -> stats engine -> AI crew -> broadcast overlays -> personalised views.**

- **Deep football brain.** A deterministic stats engine (24 metrics, 14 moment kinds) spots moments such as "Should he have passed?": the open teammate, the passing lane and the chance the shooter gave up.
- **Trust layer.** Numbers come from the engine, never from a model. The Fact-checker gates every sentence (17,889 of 17,889 on-air numeric sentences verified), and "Show your working" opens the evidence.
- **Made for each viewer.** Fan vs Analyst, club-heart framing, player focus, spoiler-safe catch-up and Ask the studio, in 5 studio languages plus 8 via Azure AI Translator.
- **Broadcast ready.** A versioned cue sheet drives the overlay, OBS and vMix, including VAR retractions.

## Prize tracks

**Best Multi-Agent Orchestration.** Five agents, one job each, handing off typed contracts:

| Agent | Job | Hands off |
|---|---|---|
| Spotter | Finds moments and attaches the only numbers anyone may use | `Moment` |
| Analyst | Explains why it matters, with evidence (Foundry model) | `Explanation` |
| Fact-checker | Vetoes any number or name not in the facts, also after translation | `FactCheck` |
| Commentator | Voices it for one audience in one language (Foundry model) | `Narrative` |
| Producer | Picks overlay slot, timing and priority; feeds the cue sheet | `OverlayCard`, cues |

Each model step has a timeout, a repair retry, a circuit breaker and a spend budget, and falls back visibly with the reason on the card. The chain runs in-process or on Microsoft Agent Framework with identical output (tested). Watch it live: [crew health](https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/api/crew/status) and [every hand-off](https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/api/crew/trace), or use "Stress test the crew" in the app to inject a wrong number and knock out an agent.

**Best Azure Cloud Native Integration.** Azure Container Apps (app and simulator job), Microsoft Foundry (`gpt-5-mini`), Azure AI Translator and Azure Event Hubs, all signed in with managed identities and key auth switched off. One Bicep file with what-if previews, deployed by `deployment/deploy.sh` or a GitHub Actions OIDC workflow with no stored secrets.

## Microsoft and Azure stack

| Service | Status on the live app |
|---|---|
| Azure Container Apps, Container Registry, Log Analytics | Live |
| Microsoft Foundry, `gpt-5-mini` deployment (Analyst, Commentator, recap) | Live |
| Azure AI Translator (8 languages, numbers protected) | Live |
| Microsoft Entra ID managed identities (no keys anywhere) | Live |
| Azure Event Hubs + simulator job | Deployed; the app replays the bundled match unless switched to the stream |
| Foundry Agent Service, Microsoft Agent Framework, Application Insights export, Fabric | Built and tested, off on the live app |
| GitHub Actions, CodeQL, Dependabot | CI on every PR: 1,500+ tests, secret scan, licence check, Bicep lint, container smoke test |

## Run it

```bash
# Offline demo, no backend (Node 20)
cd frontend && npm ci && npm run dev            # http://localhost:3000/?demo=1

# Full app in one container
docker build -f deployment/Dockerfile -t pitchpulse:local .
docker run --rm -p 8000:8000 -e MATCHMIND_PUBLIC_ORIGIN=http://localhost:8000 pitchpulse:local

# Deploy to Azure (Cloud Shell): preview first, then apply
deployment/deploy.sh && deployment/deploy.sh --apply
```

No keys needed locally: the crew runs on templates unless `MATCHMIND_AI_ENABLED=true`. `make check` runs what CI runs.

## Honest limits

All clubs, players and matches are invented; no real league data is used. Live AI quality has not been formally evaluated (quality numbers are template mode). Auto-eventing is benchmarked on synthetic tracking only.

## More

[Full details](docs/DETAILS.md) · [The brief, line by line](docs/HACKATHON-BRIEF.md) · [Architecture](docs/ARCHITECTURE.md) · [Foundry and agents](docs/FOUNDRY.md) · [Trust layer](docs/TRUST.md) · [Threat model](docs/THREAT-MODEL.md) · [Deployment](deployment/README.md)

Built by the PitchPulse team for the Microsoft x Premier League "Inside the Game" hackathon. MIT licence.
