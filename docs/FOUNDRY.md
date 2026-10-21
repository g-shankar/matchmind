# Microsoft Foundry and the studio crew

PitchPulse's studio crew is five agents in a fixed pipeline:

```
event + stats -> Spotter -> Analyst -> Fact-checker                  (once per event)
bundle + viewer -> Commentator -> Fact-checker -> Producer (+ recap)   (per audience x language)
```

The Analyst, Commentator and the Producer's recap can write with a model on
Microsoft Foundry; every model text passes the Fact-checker or the viewer sees
the localised template. Spotter, Fact-checker and Producer cards are
deterministic code on purpose (same match, same moments, every time).

## Status

| Piece | Status |
|---|---|
| Crew in template mode (free, offline) | **Live** (default) |
| Microsoft Foundry resource (`AIServices`, project management on), Foundry project `proj-pitchpulse`, `gpt-4o-mini` deployment | **In the Bicep template, off** (`deployOpenAi=false`). Validated with `bicep build` and `bicep lint` (Bicep CLI 0.48.1, no warnings); not deployed |
| Crew calling the Foundry deployment (Azure OpenAI chat completions, Entra ID, JSON answers, budget, breaker, fact-check gate) | **Built and tested with fakes; off** until the owner approves spend (`MATCHMIND_AI_ENABLED=false`) |
| OpenTelemetry spans per agent step (GenAI conventions) | **Built and tested** with an in-memory exporter; a no-op until Application Insights is configured |
| Application Insights (workspace-based, local auth off) + Foundry project connection for the Tracing view | **In the Bicep template, off** (`deployObservability=false`); not deployed |
| Agent manifests `foundry/agents/*.yaml` | **Live**: generated from the code by `matchmind-foundry export`; a test fails when they are stale |
| Evaluation dataset + local evaluators | **Live**: `matchmind-foundry eval-dataset` / `eval`; scores in `docs/EVALUATION.md` |
| Foundry cloud evaluators (Groundedness, Relevance) | **Documented, not run** (paid, owner-run; `docs/EVALUATION.md`) |
| Agents registered in Foundry Agent Service | **Not connected.** The manifests carry every field a prompt agent needs, but nothing registers them; see below |

## Infrastructure (deployment/azure_bicep/main.bicep)

With `deployOpenAi=true`:

- `Microsoft.CognitiveServices/accounts` **kind `AIServices`**, `allowProjectManagement: true`,
  custom subdomain, **`disableLocalAuth: true`** (no keys exist), system-assigned identity
  (projects need one; it gets no roles). API version `2025-06-01`.
- `accounts/projects` **`proj-pitchpulse`**: the Foundry project for agents, evaluations and tracing.
- `accounts/deployments` **`gpt-4o-mini`** (GlobalStandard, `openAiCapacity` thousand tokens per
  minute). Deployments sit on the Foundry resource and are shared by its projects.
- The app identity gets **Cognitive Services OpenAI User** on the resource only: inference, no
  management. No Azure AI User role is granted: the app never calls the project API.
- App settings: `AZURE_OPENAI_ENDPOINT` (`https://<name>.openai.azure.com/`) and
  `AZURE_AI_PROJECT_ENDPOINT` (`https://<name>.services.ai.azure.com/api/projects/proj-pitchpulse`).

With `deployObservability=true`:

- `Microsoft.Insights/components` (workspace-based on the existing Log Analytics workspace,
  **`DisableLocalAuth: true`**, 30-day retention).
- The app identity gets **Monitoring Metrics Publisher** on that component: write telemetry,
  read nothing.
- App settings `APPLICATIONINSIGHTS_CONNECTION_STRING`,
  `APPLICATIONINSIGHTS_AUTHENTICATION_STRING=Authorization=AAD;ClientId=<app identity>` and
  `OTEL_SERVICE_NAME=pitchpulse-crew`. With local auth off, the ingestion string identifies the
  resource but cannot write to it without an Entra ID token, so it is not a key; the template
  still never outputs it (CI checks outputs).
- With both switches on, a project connection (category `AppInsights`) links the Foundry project
  to the component, so the project's **Tracing** page shows the crew's spans.

Outputs are names and endpoints only: `openAiEndpoint`, `foundryName`, `foundryProjectEndpoint`,
`appInsightsName`.

## Tracing (backend/src/matchmind/crew/telemetry.py)

Every crew step that lands in the in-app trace (`/api/crew/trace`) also becomes one OpenTelemetry
span, `invoke_agent <Agent>`:

| Attribute | Value |
|---|---|
| `gen_ai.operation.name` | `invoke_agent` |
| `gen_ai.agent.name` / `gen_ai.agent.id` | `Analyst` / `pitchpulse-analyst` (and so on for each agent) |
| `gen_ai.system` / `gen_ai.provider.name` | `az.ai.openai` / `azure.ai.openai` (model steps in AI mode only) |
| `gen_ai.request.model` | the deployment, e.g. `gpt-4o-mini` (AI mode only) |
| `pitchpulse.step.status` | `ok`, `fallback`, `rejected`, `error` |
| `pitchpulse.fallback_reason`, `error.type` | one of `fact_check`, `circuit_open`, `budget`, `timeout`, `schema`, `error` |
| `pitchpulse.fact_check.verdict` | `pass` or `rejected` (Fact-checker steps) |
| `pitchpulse.produced_by` | `ai` or `template` (model-capable steps) |
| `pitchpulse.moment.id`, `pitchpulse.moment.kind`, `pitchpulse.crew.mode` | engine ids and the crew mode |

**Never in a span:** prompts, model answers, card or recap text, fact-check reason text, or
anything about a viewer (persona, language, favourite club, focus player). Tests assert this
attribute by attribute.

How it switches on: only when the optional `observability` extra
(`azure-monitor-opentelemetry`, MIT) is installed **and** `APPLICATIONINSIGHTS_CONNECTION_STRING`
is set. The exporter signs in with the managed identity when the authentication string says
`Authorization=AAD`. Only crew spans are sent: request, log, metric, live-metric and library
instrumentation are all switched off, and the exporter's own usage pings are disabled. Any setup
failure leaves tracing off; the crew never depends on it.

Where to look once deployed: Foundry portal -> project `proj-pitchpulse` -> **Tracing**, or
Application Insights -> **Transaction search**, filtered on
`gen_ai.agent.name`.

## Agent manifests (foundry/agents/)

`matchmind-foundry export` writes `spotter.yaml`, `analyst.yaml`, `commentator.yaml`,
`fact-checker.yaml` and `producer.yaml`. Nothing in them is typed by hand:

- `instructions`: the exact system prompts from `analyst.py`, `commentator.py`, `recap.py`;
- `input_schema`: the JSON each model step receives (a test checks real crew requests against
  it, with extra keys forbidden);
- `output_schema`: the pydantic answer contracts (`AnalystOut`, `CommentatorOut`, `RecapOut`);
- `contract`: each agent's typed hand-off in the pipeline (`Moment`, `Explanation`, `Narrative`,
  `FactCheck`, `OverlayCard`);
- model settings (deployment, API version, temperature, max tokens), guardrails (timeout, repair
  retry, breaker, budget, fact-check gate), `tools: []`.

How they map to Foundry Agent Service: each `model_steps[]` entry has an `agent_service` block with
the prompt-agent fields (name, model deployment, instructions, JSON-schema response format, no
tools). Deterministic agents have no model step and stay in our code.

Why the crew calls the deployment directly instead of through Agent Service: each step has a 3 s
budget on a live match, and the fact-checker and template fallback must sit in the same process
as the call. Agent Service would add a thread and run round-trip per moment for no extra
capability (the agents use no tools).

**Not built: a `register` command.** The Agent Service client API in `azure-ai-projects` changed
shape between releases and we cannot verify it without a deployed project, so we did not ship a
command we could not test. To try the agents in the Foundry playground, the owner can create a
prompt agent in the project by hand: pick the `gpt-4o-mini` deployment, paste `instructions`, set
the response format to the `output_schema`. Registering costs nothing; every playground run is
billed per token.

## Switching it on (owner)

1. Approve the spend (project rule: paid Azure AI stays off until then).
2. Let the deploy identity grant the one new role, Monitoring Metrics Publisher
   (`3913510d-42f4-4e42-8a64-420c390055eb`), by adding it to the role condition
   (`setup/owner-todo.md`, step 2). Only needed for `DEPLOY_OBSERVABILITY`.
3. Set repo variables `DEPLOY_OPENAI=true`, `DEPLOY_OBSERVABILITY=true` and, for model text,
   `MATCHMIND_AI_ENABLED=true`; run the deploy workflow (`deployment/README.md`).
4. Tracing works in template mode too: with `DEPLOY_OBSERVABILITY=true` alone the crew's
   deterministic and template steps are traced at no model cost.

## Cost

- Foundry resource and project: no charge on their own.
- `gpt-4o-mini`: billed per token, only when `MATCHMIND_AI_ENABLED=true`. The crew caps calls
  with `MATCHMIND_AI_BUDGET` (default 300 per process) and `MATCHMIND_AI_RATE_PER_MIN` (30), caches
  recaps per audience and caches cards per audience.
- Application Insights: billed per GB ingested into Log Analytics (monthly free allowance first;
  check current pricing). Spans are small (no text); a full match with a handful of audiences is
  a few thousand spans.
- Agent manifests, the evaluation dataset and local evaluators: free.
- Foundry cloud evaluators: one judge-model call per row per evaluator; run on a sample.
