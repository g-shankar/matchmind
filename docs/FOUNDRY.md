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

**Running** means it works in the default build today. **Built, off** means it is built and
tested offline against fakes (no Azure account), and stays off until the owner deploys it and
turns its switch on. Nothing below is deployed yet.

| Piece | Status |
|---|---|
| Crew in template mode (free, offline) | **Running** (default) |
| Microsoft Foundry resource (`AIServices`, project management on), Foundry project `proj-pitchpulse`, `gpt-4o-mini` deployment | **Built, off**: in the Bicep template (`deployOpenAi=false`). `bicep build` and `bicep lint` clean (Bicep CLI 0.48.1); not deployed |
| Crew calling the Foundry deployment (Azure OpenAI chat completions, Entra ID, JSON answers, budget, breaker, fact-check gate) | **Built, off** until the owner approves spend (`MATCHMIND_AI_ENABLED=false`) |
| Crew model steps as **Foundry Agent Service** agents (`MATCHMIND_LLM_PROVIDER=foundry_agents`) | **Built, off**: tested against a fake Agent Service; the SDK calls are checked against the installed `azure-ai-projects` 2.9 source. Not yet run against a live project |
| `matchmind-foundry register` (create or update the agents from the cards; `--dry-run`) | **Built**: dry run works offline; the live run is an owner step (`setup/owner-todo.md`) |
| `matchmind-foundry trace-demo` (a few demo moments through the agents, for portal traces) | **Built**: owner step, paid, needs `--yes` |
| Crew chained by **Microsoft Agent Framework** workflows (`MATCHMIND_ORCHESTRATOR=agent_framework`) | **Future enterprise extension, off by default**: free and local; parity tests replay the demo match through both orchestrators and get identical cards |
| OpenTelemetry spans per agent step (GenAI conventions) | **Built**, tested with an in-memory exporter; a no-op until Application Insights is configured |
| Application Insights (workspace-based, local auth off) + Foundry project connection for the Tracing view | **Built, off**: in the Bicep template (`deployObservability=false`); not deployed |
| Agent cards `foundry/agents/*.yaml` | **Running**: generated from the code by `matchmind-foundry export`; a test fails when they are stale |
| Evaluation dataset + local evaluators | **Running**: `matchmind-foundry eval-dataset` / `eval`; scores in `docs/EVALUATION.md` |
| Foundry cloud evaluators (Groundedness, Relevance) | **Documented, not run** (paid, owner-run; `docs/EVALUATION.md`) |

## What runs where

| Agent | Default build | With `MATCHMIND_AI_ENABLED=true` | `+ MATCHMIND_LLM_PROVIDER=foundry_agents` |
|---|---|---|---|
| Spotter | app (deterministic) | app | app |
| Analyst | app (templates) | app -> Azure OpenAI deployment | app -> Foundry agent `pitchpulse-analyst` |
| Fact-checker | app (deterministic) | app: gates every model text | app: gates every agent answer |
| Commentator | app (templates) | app -> Azure OpenAI deployment | app -> Foundry agent `pitchpulse-commentator` |
| Producer (cards) | app (deterministic) | app | app |
| Producer (recap) | app (templates) | app -> Azure OpenAI at full time | app -> Foundry agent `pitchpulse-producer-recap` at full time |

Orchestration is a separate, free switch: `MATCHMIND_ORCHESTRATOR=in_process` (default) or
`agent_framework`. Either way the same agent steps run; `/api/crew/status` reports both
`provider` (`templates`, `azure_openai`, `foundry_agents`) and `orchestrator`.

Spotter, Fact-checker and the Producer's card placement are not Foundry agents on purpose:
numbers come from the stats engine, never from a model, and the fact-checker must sit in the
same process as the call it gates.

## Infrastructure (deployment/azure_bicep/main.bicep)

With `deployOpenAi=true`:

- `Microsoft.CognitiveServices/accounts` **kind `AIServices`**, `allowProjectManagement: true`,
  custom subdomain, **`disableLocalAuth: true`** (no keys exist), system-assigned identity
  (projects need one; it gets no roles). API version `2025-06-01`.
- `accounts/projects` **`proj-pitchpulse`**: the Foundry project for agents, evaluations and tracing.
- `accounts/deployments` **`gpt-4o-mini`** (GlobalStandard, `openAiCapacity` thousand tokens per
  minute). Deployments sit on the Foundry resource and are shared by its projects.
- The app identity gets **Cognitive Services OpenAI User** on the resource only: inference, no
  management.
- With `llmProvider=foundry_agents` as well, the app identity also gets **Azure AI User**
  (`53ca6127-db72-4b80-b1b0-d745d6d5456d`) on the **project** only (not the resource): it can
  create agent versions from the cards and run them, and cannot manage the resource, its
  deployments or its connections. With the default `llmProvider=azure_openai` no project role is
  granted.
- App settings: `AZURE_OPENAI_ENDPOINT` (`https://<name>.openai.azure.com/`),
  `AZURE_AI_PROJECT_ENDPOINT` (`https://<name>.services.ai.azure.com/api/projects/proj-pitchpulse`,
  read by the Agent Service client), `MATCHMIND_LLM_PROVIDER` (parameter `llmProvider`, default
  `azure_openai`) and `MATCHMIND_ORCHESTRATOR` (parameter `orchestrator`, default `in_process`).
  The deploy workflow passes both from repo variables of the same names.

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
the prompt-agent definition (name, `kind: prompt`, model deployment, instructions, temperature,
`text.format` JSON schema, no tools). Deterministic agents have no model step and stay in our code.

## Foundry Agent Service runtime (backend/src/matchmind/foundry/agent_service.py)

`FoundryAgentsLLM` implements the crew's `LLM` interface, so it slots in where the Azure OpenAI
client does; `make_llm()` picks it when `MATCHMIND_AI_ENABLED=true` and
`MATCHMIND_LLM_PROVIDER=foundry_agents`. Per model step:

1. The step's output schema picks the agent (`AnalystOut` -> `pitchpulse-analyst`,
   `CommentatorOut` -> `pitchpulse-commentator`, `RecapOut` -> `pitchpulse-producer-recap`). The
   crew's system prompt must equal the agent's instructions, or the call is refused.
2. On first use per process the agent is looked up by name (`AIProjectClient.agents.get`). If it
   is missing, or its `pitchpulse_digest` metadata differs from the card's, a new version is
   created from the card (`agents.create_version`); otherwise the existing version is used. The
   lookup happens once per agent, not per viewer; after a failed call it happens again, so a
   deleted or replaced agent is picked up.
3. The step runs through the project's OpenAI Responses client
   (`get_openai_client(max_retries=0)`, then `responses.create` with
   `extra_body={"agent_reference": {"type": "agent_reference", "name", "version"}}`,
   `max_output_tokens=400` and the crew's 3 s timeout). The input is the same typed-facts JSON the
   Azure OpenAI path sends.
4. The answer is validated against the schema; one repair retry on a mismatch; then the crew's
   circuit breaker, model budget and **fact-checker** apply exactly as on the Azure OpenAI path.
   Any provider failure becomes a template card with `fallback_reason` (`timeout`, `error`,
   `schema`, `budget`, `circuit_open`, `fact_check: ...`); provider text never reaches a viewer.

Sign-in is Microsoft Entra ID only (`DefaultAzureCredential`: the app's managed identity in
Azure, `az login` on a laptop). Endpoint: `MATCHMIND_FOUNDRY_PROJECT_ENDPOINT`, or
`AZURE_AI_PROJECT_ENDPOINT` (set by the template). Model: `MATCHMIND_FOUNDRY_MODEL`, or
`AZURE_OPENAI_DEPLOYMENT`, or `gpt-4o-mini`. Packages: the `foundry` extra
(`azure-ai-projects>=2.9,<3`, MIT; it brings `openai`, Apache-2.0), imported only on first use.

Known limit: the Agent Service path has been checked against the SDK source and a fake service,
not yet against a live project (no paid Azure until the owner approves). Agents use the project's
Responses API; the response format is non-strict JSON schema because the answer schemas carry
length limits strict mode does not accept (the crew validates every answer anyway).

## Registering the agents (owner step)

```
matchmind-foundry register --dry-run          # exact request payloads; no sign-in, no calls
az login
export MATCHMIND_FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/proj-pitchpulse
matchmind-foundry register                    # created / updated / unchanged, per agent
```

Registration is idempotent: run it twice and the second run prints `unchanged` for all three
agents; change a prompt, schema or the model and it prints `updated` with a new version. It
refuses to run in CI (`CI` set). Registering costs nothing; runs are billed per token. The
running app creates missing agents itself on first use, so this step is for checking the
agents in the portal before switching the provider on.

`matchmind-foundry trace-demo --yes [--moments 3]` voices the first few demo moments through
the agents (Agent Framework orchestration when installed), with a budget of 4 model calls per
moment, and sends the crew's spans to the project's Application Insights when it has one
(signed in with Entra ID: your `az login` account needs Monitoring Metrics Publisher on it). The
spans should then show under the project's **Tracing** page and the runs under each agent in
the portal; this has not been checked on a live project yet, which is why capturing it is an
owner step.

## Microsoft Agent Framework orchestration (backend/src/matchmind/crew/workflow.py)

With `MATCHMIND_ORCHESTRATOR=agent_framework` (and the `agent-framework` extra:
`agent-framework-core>=1.22,<2`, MIT; the core package only, not the meta-package with every
connector), the crew's two chains run as Agent Framework workflows, one typed `Executor` per
agent:

```
process: SpotterExecutor -> AnalystExecutor -> FactCheckerExecutor --(next moment)--> AnalystExecutor
render:  CommentatorExecutor -> FactCheckerExecutor -> ProducerExecutor
```

Messages between executors are typed dataclasses (`SpotRequest`, `MomentQueue`,
`AnalystDraftMessage`, `VoiceRequest`, `CommentatorDraftMessage`, `CheckedNarrative`). Each
executor calls the crew's own step for its agent (`Crew.spot_step`, `analyst_step`,
`fact_check_explanation`, `commentator_step`, `fact_check_narrative`, `producer_step`), and the
model steps go through the same `LLM` interface, so either provider (templates, Azure OpenAI,
Foundry agents) works under either orchestrator. The process workflow loops from the
Fact-checker back to the Analyst once per moment, so moments are explained in the same order as
in process. Tests replay every event of the demo match through both orchestrators, voice every
moment for 16 viewer profiles, and require identical bundles, cards (byte for byte, as JSON),
traces and counters, in template mode and in a scripted model mode with rejections and failures.

The translator step, metric alerts and the recap stay in the crew's own code under both
orchestrators. If the environment asks for Agent Framework and the package is missing, the
crew logs it and runs in process (`/api/crew/status` says `in_process`).

## Switching it on (owner)

1. Approve the spend (project rule: paid Azure AI stays off until then).
2. Let the deploy identity grant the one new role, Monitoring Metrics Publisher
   (`3913510d-42f4-4e42-8a64-420c390055eb`), by adding it to the role condition
   (`setup/owner-todo.md`, step 2). Only needed for `DEPLOY_OBSERVABILITY`.
3. Set repo variables `DEPLOY_OPENAI=true`, `DEPLOY_OBSERVABILITY=true` and, for model text,
   `MATCHMIND_AI_ENABLED=true`; run the deploy workflow (`deployment/README.md`).
   For Foundry Agent Service add `MATCHMIND_LLM_PROVIDER=foundry_agents` (the deploy identity
   must be allowed to grant Azure AI User, `setup/owner-todo.md` step 2), and optionally
   `MATCHMIND_ORCHESTRATOR=agent_framework` (free).
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
- Foundry Agent Service: the agents themselves cost nothing; each run is billed as model tokens
  on the deployment, under the same budget and rate caps.
- Agent Framework orchestration: free (a local library).
- Agent manifests, the evaluation dataset and local evaluators: free.
- Foundry cloud evaluators: one judge-model call per row per evaluator; run on a sample.
