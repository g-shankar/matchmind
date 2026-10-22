# ADR 0002: Templates first; paid AI off by default

Status: Accepted (Oct 2026)

## Decision

The crew's default mode is localised templates (`TemplateLLM`), free and
offline. Model steps (Analyst, Commentator, recap, Ask intent) run only when
`MATCHMIND_AI_ENABLED=true`, which the owner sets after approving spend. Azure
AI Translator needs its own switch on top. Places that must never spend
(evaluation, the bookmark pass, the cue-sheet compiler, the audit sweep, the
stdio MCP server, `matchmind-ingest play`) are pinned to
template mode whatever the switch says.

## Why

The project rules forbid paid services without owner approval, and the demo
must work for any judge with no Azure account. Templates also give a
deterministic fallback for every model failure (timeout, schema, breaker,
budget, fact-check rejection), so the broadcast never breaks.

## Alternatives considered

- **Model by default with a cache.** Rejected: spends money and needs keys to
  run the demo.
- **No model path at all.** Rejected: the hackathon asks for Azure AI; the
  model path is built and tested against fakes, ready to switch on.

## Consequences

- All measured results (docs/EVALUATION.md, docs/TRUST.md) are template-mode
  results. The model path has not been evaluated on live output.
- Every card says how it was made (`produced_by`, `fallback_reason`).
