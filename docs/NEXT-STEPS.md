# Remaining roadmap

What is left after the integration branch, and who does it. Everything not
listed here is built and tested (see [BUILD-STATUS.md](BUILD-STATUS.md)). Owner
steps are written out in full in [setup/owner-todo.md](../setup/owner-todo.md).

Status labels: **Owner** (only the owner can do it: subscription, spend,
accounts), **Team** (the team can do it once unblocked), **Planned** (not
built).

## Before submission (target 26 Oct 2026)

| Item | Who | Notes |
|---|---|---|
| Deploy to Azure with the owner's subscription | Owner | OIDC set-up, `production` environment, what-if then deploy (`deployment/README.md`). Then the preview URL goes in BUILD-STATUS.md |
| Register the Foundry agents and capture portal screenshots | Owner | `matchmind-foundry register --dry-run`, then `register`; `trace-demo --yes` is paid (about 12 calls). Needs `DEPLOY_OPENAI=true` |
| Decide on paid AI | Owner | `MATCHMIND_AI_ENABLED=true` and `DEPLOY_OPENAI=true` only after approving spend. Until then every card is a fact-checked template |
| Re-render the demo video | Team, owner uploads | The demo match gained a VAR correction and the final tracking model changed its physical stats and benchmark, so any earlier recording shows out-of-date screens and numbers. Under 2 minutes, no third-party trademarks or music |
| Submission text | Team | Use the README's pitch, golden path and feature status labels as written; do not claim anything marked Built-off or Planned as running |

## After submission

| Item | Who | Notes |
|---|---|---|
| Native-speaker review of the studio packs | Team, with reviewers | en, es, fr, ar, ja were written by the team; review by native-speaking football broadcasters before any public launch (docs/LANGUAGES.md) |
| Model path evaluation | Owner approves, team runs | Build a dataset with a live model and run the local evaluators plus Foundry's Groundedness and Relevance on a sample (docs/EVALUATION.md) |
| Tactical booking card numbers | Team | The one persona-vocabulary gap in the scorecard: the tactical booking template prints no numbers |
| Club heart in the offline demo | Team | The browser demo changes only priority and the club label; the live backend does the full framing |
| Fabric | Owner | Trial capacity, load the Lakehouse export and run the Eventhouse queries (`analytics/fabric/README.md`) |

## Planned (not built)

| Item | Notes |
|---|---|
| Neural voices (Azure AI Speech) | Paid; owner approval first. Read-aloud uses browser voices today |
| Real video input | Today auto-eventing reads synthetic tracking, and the pixel path reads rendered synthetic frames |
| Live enriched stream | Stats engine output to a second event hub; today the enriched events are a file |
| MCP `export_dataset` and `audit_claims` tools | The same data is on REST today |
| Per-viewer clocks | Today one shared clock per server (ADR 0006) |
