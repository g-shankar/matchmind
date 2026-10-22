# PitchPulse: architecture and roadmap

PitchPulse is the trust layer for match intelligence on a deterministic
football engine (Matchmind). It turns synthetic match events into explained,
personalised, multilingual broadcast graphics, and shows its working for every
number. Hackathon: Microsoft x Premier League "Inside the Game"; submissions
close 27 Oct 2026, target 26 Oct.

This page is the one-page summary. Details: [README.md](README.md) (feature
status matrix), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (system map),
[docs/adr/](docs/adr/README.md) (decisions), [docs/BUILD-STATUS.md](docs/BUILD-STATUS.md)
(evidence), [docs/NEXT-STEPS.md](docs/NEXT-STEPS.md) (remaining roadmap).

## Architecture in brief

```
source (simulator file | own feed | Event Hubs*) -> MatchSession (one shared clock)
  -> stats engine (deterministic facts)
  -> crew: Spotter -> Analyst -> Fact-checker -> Commentator -> Fact-checker -> Producer (+ recap, translator*)
  -> trust layer (claims, parity, audit) + cue sheet v1.0
  -> REST, WebSocket, MCP -> web app (studio, overlay, split, focus, my match, lab), OBS/vMix
* built, off until deployed with the owner's Azure subscription
```

Rules that shape it (ADRs 0001-0007): numbers come only from the stats engine
and a fact-checker gates every text; templates first and paid AI off by
default; MCP read-only and stateless; Agent Framework orchestration identical
to in-process; auto-eventing from synthetic tracking, not video; one shared
match clock; the cue sheet is a versioned contract.

## Roadmap

### Done (on the integration branch, tested)

- Synthetic match engine, event schema, 5 bundled matches, seeded generator,
  dataset export and data dictionary, feed ingest (JSONL, CSV).
- Stats engine: xG, pass difficulty, xT, better option, unfound run, momentum,
  control vs chaos, pressure, physical stats from synthetic tracking, metric
  registry, basic stats.
- Studio crew in template mode, 14 moment kinds, fact-checker with units,
  attribution and comparisons; per-sentence claims, parity and the moment audit.
- Cue sheet v1.0 with VAR retract and supersede; overlay and OBS/vMix capture.
- Personas (Fan, Analyst, Stats scout, Player cam), club heart, focus player and
  metric, spoiler-safe catch-up, Ask the studio, read-aloud.
- 5 studio languages; 8 world languages through Azure AI Translator (built, off).
- MCP server (15 read-only tools).
- Auto-eventing from synthetic tracking with a held-out benchmark and a pixel path.
- Azure OpenAI, Foundry Agent Service, Agent Framework, Event Hubs, Application
  Insights and Fabric paths: built and tested against fakes, off by default.
- Bicep, Dockerfile, CI (tests, secret scan, licence check, Bicep lint,
  container smoke test), CodeQL.

### Next (needs the owner; see setup/owner-todo.md)

- Deploy to Azure with the owner's subscription and publish the preview URL.
- Register the three Foundry agents and capture portal traces.
- Approve (or not) paid AI and run the model path evaluation on a sample.
- Re-render the demo video after the last data change.
- Native-speaker review of the five studio packs.

### Planned (not built)

- Neural voices with Azure AI Speech.
- Real video input.
- Live enriched stream from the stats engine to a second event hub.
- MCP `export_dataset` and `audit_claims` tools.
