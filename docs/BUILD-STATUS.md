# Build status

Last updated: 22 Oct 2026, on the integration branch with every feature
merged. **Preview URL: not deployed yet** (the Azure Container Apps URL goes
here after the owner's first deploy).

Status words: **Done** (built, tested, running offline), **Done, off** (built
and tested against fakes; off until the owner deploys and switches it on),
**Planned** (not built). The single feature matrix with Running / Simulated /
Built-off / Planned labels is in the [README](../README.md#feature-status).

## Evidence commands (run on 22 Oct 2026)

| Command | Result |
|---|---|
| `cd backend && PYTHONPATH=$PWD/src python3 -m pytest -q` | **915 passed** in 380 s, 0 skipped, 0 failed |
| `cd backend && ruff check . && ruff format --check .` | All checks passed; 136 files formatted |
| `cd frontend && npm test` | **176 passed** (19 files) |
| `cd frontend && npm run typecheck && npm run build` | No type errors; build succeeds (chunk-size warning only) |
| `cd backend && matchmind-sim dataset --out /tmp/m && diff -r /tmp/m data/matches` | Identical (dataset reproducible byte for byte) |
| `cd backend && matchmind-foundry eval-dataset && matchmind-foundry eval` | 6,780 records; groundedness 6,780 / 6,780; strict 6,622 / 6,780; length 6,780 / 6,780; persona 6,720 / 6,780; language 6,780 / 6,780 |
| `cd backend && pytest tests/test_trust.py` | Passes: parity holds for 334 of 334 moments with no failed claim. Counted over the same sweep: 25,713 sentence claims, 17,889 of 17,889 sentences with a number verified |

Not run here: `make licence-check` and `make bicep` (need network installs and
the Azure CLI; both run in CI), the container smoke test (runs in CI).

## Areas

| Area | Status | Evidence |
|---|---|---|
| Simulator, event schema, bundled dataset | Done | `tests/test_simulator.py`; dataset diff above |
| Feed ingest (JSONL, CSV + mapping, roster) | Done | `tests/test_ingest.py` |
| Event Hubs publisher and consumer | Done, off | `tests/test_live_source.py` (fake consumer); not run against a live namespace |
| Stats engine, better option, unfound run, rolling state | Done | `tests/test_stats.py` |
| Physical stats from synthetic tracking | Done | `tests/test_physical.py` |
| Metric registry and basic stats | Done | `tests/test_registry.py` (docs generated from the registry) |
| Studio crew, template mode | Done | `tests/test_crew.py`, `tests/test_crew_budget.py` |
| Trust layer: claims, parity, audit | Done | `tests/test_trust.py` |
| VAR corrections and cue sheet v1.0 | Done | `tests/test_corrections.py`, `tests/test_cues.py`, `tests/test_cue_load.py` |
| Personas, club heart, focus player and metric | Done | `tests/test_club_heart.py`, `frontend/src/views/*.test.tsx` |
| Spoiler-safe catch-up | Done | `tests/test_spoilers.py`, `frontend/src/api/catchup.test.ts` |
| Ask the studio | Done (model intent: Done, off) | `tests/test_ask.py`, `frontend/src/components/askCatchUp.test.tsx` |
| Read-aloud (browser voices) | Done, off by default | `frontend/src/lib/speech.ts`; Azure AI Speech Planned |
| Languages: 5 studio packs | Done; not reviewed by native speakers | `tests/test_club_heart.py`, `tests/test_crew.py` |
| Languages: 8 world languages (Azure AI Translator) | Done, off | `tests/test_translator.py` |
| MCP server (15 tools) | Done | `tests/test_mcp.py` (byte parity, contract snapshot) |
| Auto-eventing benchmark and pixel path | Done (synthetic tracking, not video) | `tests/test_autoevent.py`, `tests/test_autoevent_benchmark.py` |
| Dataset export and data dictionary | Done | `tests/test_dataset.py` |
| Lakehouse export | Done | `tests/test_analytics.py` |
| Fabric notebook and Eventhouse KQL | Done, off (not run in Fabric) | `tests/test_analytics.py` (columns checked) |
| Azure OpenAI model steps | Done, off | `tests/test_crew.py` (fake model) |
| Foundry Agent Service runtime and registration | Done, off | `tests/test_foundry_agent_service.py` |
| Microsoft Agent Framework orchestration | Done, off by default | `tests/test_agent_framework.py` (identical cards) |
| Evaluation dataset and local evaluators | Done | `tests/test_foundry.py`; scorecard above |
| Tracing (OpenTelemetry; Application Insights export) | Done; export off | `tests/test_telemetry.py` |
| API, WebSocket, security controls | Done | `tests/test_api.py`, `tests/test_api_security.py`, `tests/test_session_security.py` |
| Web app: studio, overlay, split, player focus, my match, lab, offline demo | Done | `npm test`; offline demo fixture tests in `tests/test_ask.py` and `frontend/src/api/*.test.ts` |
| OBS / vMix capture | Done | `frontend/src/components/BroadcastOverlay.test.tsx`; docs/OBS.md |
| Deployment (Bicep, Dockerfile, CI, deploy workflow) | Done, off (not deployed) | CI: Bicep build and lint, no keys in outputs, container smoke test |
| Docs: architecture, ADRs, threat model, roadmap | Done | docs/ARCHITECTURE.md, docs/adr/, docs/THREAT-MODEL.md, docs/NEXT-STEPS.md |

## North-star metric

**Share of on-air sentences that print a number and have every number
machine-verified against the stats engine.** Today: **17,889 of 17,889**
(template mode, every moment of the five bundled matches x 4 personas x 5
studio languages, 0 cards withheld). It is the number that must not drop when
paid AI is switched on. Source: docs/TRUST.md.

## Known issues

- Paid AI has never run against a live model: all quality numbers are template
  mode.
- Nothing is deployed; Azure paths are tested against fakes only.
- Studio packs are not yet reviewed by native-speaking broadcasters.
- The tactical booking card prints no numbers (60 persona-vocabulary misses).
- The offline demo does not apply club heart framing (priority and club label
  only), holds only English, Spanish and Arabic text, and builds a simplified
  cue sheet.
- Ask: unknown names in Arabic or Japanese script are not detected; Japanese
  answers are in English; typed questions need the live server.
- Metric alerts for a focus metric are in the live `CUES` stream but not in the
  compiled REST cue sheet.
- Any demo video recorded before the VAR correction and the final tracking
  model shows out-of-date screens and must be re-recorded (docs/NEXT-STEPS.md).
