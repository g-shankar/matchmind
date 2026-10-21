# Deploying PitchPulse to Azure

One resource group, no keys. Every service call uses Microsoft Entra ID through
user-assigned managed identities; GitHub signs in to Azure with OIDC.

## What gets created

| Resource | Purpose | Cost when idle |
|---|---|---|
| Container App `ca-pitchpulse` | API, WebSocket and the built frontend (one replica: the match session lives in memory) | Consumption plan, about 0.5 vCPU always on |
| Container Apps job `caj-pitchpulse-sim` | Ingest stage: streams the demo match into Event Hubs when started | None (runs only when started) |
| Event Hubs namespace (Basic) + `match-events` | Live event stream, local auth off | Small hourly charge |
| Microsoft Foundry resource (Azure AI Services, project management on) + project `proj-pitchpulse` + `gpt-4o-mini` deployment (only with `DEPLOY_OPENAI=true`) | AI crew model, Foundry agents, evaluations and tracing; local auth off | None; billed per token, used only when `MATCHMIND_AI_ENABLED=true` |
| Application Insights, workspace-based (only with `DEPLOY_OBSERVABILITY=true`) | Crew traces (OpenTelemetry, no text or viewer data), shown in Foundry's Tracing page; local auth off | Per GB ingested |
| Azure AI Translator (only with `DEPLOY_TRANSLATOR=true`) | Extra languages, local auth off | Billed per character |
| Container Registry (Basic) | Images, admin user off, pulled by managed identity | Small daily charge |
| Log Analytics | Container logs via diagnostic settings | Per GB ingested |
| Managed identity `id-pitchpulse-app` | AcrPull, Event Hubs Data Receiver, Cognitive Services OpenAI User (Foundry resource), Cognitive Services User (Translator), Monitoring Metrics Publisher (Application Insights, only with `DEPLOY_OBSERVABILITY=true`) | None |
| Managed identity `id-pitchpulse-sim` | AcrPull, Event Hubs Data Sender | None |

The template never outputs keys or connection strings; CI fails if
`listKeys` or a connection string appears in it, or if any output is named
like a key or connection string. The one exception inside the template is the
Application Insights ingestion string, passed to the app and to the Foundry
tracing connection: with local auth off it cannot write telemetry without an
Entra ID token, and it is never an output.

Older deploys: the Foundry resource is named `aif-...` (it replaces the
earlier `oai-...` Azure OpenAI account, which was never deployed). If an
`oai-...` account exists in your resource group, delete it after the switch.

## Deploy

Runs only from `main`.

1. Actions -> **deploy** -> Run workflow -> `what-if`. Review the plan.
2. Run again with `deploy`. The workflow:
   1. deploys the base infrastructure (`deployApps=false`),
   2. builds `deployment/Dockerfile`, starts it and checks `/api/health` and the frontend, and pushes it to the registry as `pitchpulse:<commit sha>`,
   3. deploys the app and simulator job with that image (`deployApps=true`).
3. The preview URL is in the run summary.

Both modes need an approval on the `production` environment.

Start the live feed: `az containerapp job start -g <rg> -n caj-pitchpulse-sim`.

## Switching the AI crew on (owner approval needed)

Paid AI stays off by default. Once approved, set the repo variables
`DEPLOY_OPENAI=true` and `MATCHMIND_AI_ENABLED=true` (plus `DEPLOY_TRANSLATOR=true`
for Translator) and run the deploy again. No key is ever needed: the app's
managed identity gets the roles.

## Switching crew tracing on

Set `DEPLOY_OBSERVABILITY=true` and redeploy. This needs one more role in the
deploy identity's allowed list, Monitoring Metrics Publisher
(`3913510d-42f4-4e42-8a64-420c390055eb`, `setup/owner-todo.md` step 2);
without it the deploy fails at the role assignment. Tracing works in
template mode (no model cost). With `DEPLOY_OPENAI=true` as well, the Foundry
project's **Tracing** page shows the spans. Details: `docs/FOUNDRY.md`.

## Roll back

Container Apps keeps earlier revisions:
`az containerapp revision list -g <rg> -n ca-pitchpulse`, then
`az containerapp update -g <rg> -n ca-pitchpulse --image <earlier image>`.
To remove everything: `az group delete -n <rg>`.

## Local checks

```
make bicep    # needs the Azure CLI
make image    # needs Docker
make check
```
