# Deploying PitchPulse to Azure

One resource group, no keys. Every service call uses Microsoft Entra ID through
one user-assigned managed identity; GitHub signs in to Azure with OIDC.

## What gets created

| Resource | Purpose | Cost when idle |
|---|---|---|
| Container App `ca-pitchpulse` | API, WebSocket and the built frontend (one replica: the match session lives in memory) | Consumption plan, about 0.5 vCPU always on |
| Container Apps job `caj-pitchpulse-sim` | Ingest stage: streams the demo match into Event Hubs when started | None (runs only when started) |
| Event Hubs namespace (Basic) + `match-events` | Live event stream, local auth off | Small hourly charge |
| Azure OpenAI + `gpt-4o-mini` deployment | AI crew, local auth off | None; billed per token, and only used when `aiEnabled=true` |
| Azure AI Translator (optional, `deployTranslator=true`) | Extra languages, local auth off | Billed per character |
| Container Registry (Basic) | Images, admin user off, pulled by managed identity | Small daily charge |
| Log Analytics | Container logs via diagnostic settings | Per GB ingested |
| Managed identity `id-pitchpulse` | Roles: AcrPull, Cognitive Services OpenAI User, Event Hubs Data Sender/Receiver, Cognitive Services User (Translator) | None |

The template never outputs keys or connection strings; CI fails if
`listKeys` or a connection string appears in it.

## Deploy

1. Actions -> **deploy** -> Run workflow -> `what-if`. Review the plan.
2. Run again with `deploy`. The workflow:
   1. deploys the base infrastructure (`deployApps=false`),
   2. builds `deployment/Dockerfile` and pushes it to the registry as `pitchpulse:<commit sha>`,
   3. deploys the app and simulator job with that image (`deployApps=true`).
3. The preview URL is in the run summary.

Both modes need an approval on the `production` environment.

Start the live feed: `az containerapp job start -g <rg> -n caj-pitchpulse-sim`.

## Switching the AI crew on (owner approval needed)

Paid AI stays off by default. Once approved, run the deployment with
`aiEnabled=true` (and `deployTranslator=true` for Translator). No key is ever
needed: the app's managed identity already holds the roles.

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
